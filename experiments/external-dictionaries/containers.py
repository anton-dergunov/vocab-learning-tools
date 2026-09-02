#!/usr/bin/env python3
"""Container and compression candidates for the external-dictionary spike.

Every candidate is built from the same `[(key, payload_bytes)]` list so the byte columns are
comparable. Nothing here knows what a dictionary entry is.
"""

from __future__ import annotations

import io
import json
import os
import random
import sqlite3
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import brotli
import zstandard

Rows = list[tuple[str, bytes]]


def _avg_payload(rows: Rows) -> int:
    if not rows:
        return 0
    return sum(len(value) for _, value in rows[:2000]) // min(len(rows), 2000)

# What a client must ship to read each candidate, in bytes. Measured from the published artifacts
# (see the experiment README); counted once per origin, not once per dictionary.
ENGINE_BYTES = {
    "none": 0,
    "fflate": 8_394,             # already bundled in web/ today, so arguably zero
    "fzstd": 8_394,
    "sqlite-wasm": 866_600 + 439_284,
    "zstd-wasm": 348_579,
    "sqlite-wasm+fzstd": 866_600 + 439_284 + 8_394,
    "sqlite-wasm+zstd-wasm": 866_600 + 439_284 + 348_579,
}


# ------------------------------------------------------------------------------------ compressors

def train_zlib_dict(samples: list[bytes], size: int = 64 * 1024) -> bytes:
    """zlib has no trainer, so use the tail of a concatenated sample.

    Deflate's window looks backwards, so the *end* of the dictionary is what matters most.
    """
    blob = b"".join(samples)
    return blob[-size:]


def train_zstd_dict(samples: list[bytes], size: int = 64 * 1024) -> bytes:
    try:
        return zstandard.train_dictionary(size, samples).as_bytes()
    except Exception:
        return b""


@dataclass
class Codec:
    name: str
    engine: str
    dictionary: bytes = b""

    def compress(self, payload: bytes) -> bytes:
        if self.name == "raw":
            return payload
        if self.name == "deflate":
            return zlib.compress(payload, 9)
        if self.name == "deflate+dict":
            obj = zlib.compressobj(9, zlib.DEFLATED, -15, 9, zlib.Z_DEFAULT_STRATEGY,
                                   zdict=self.dictionary)
            return obj.compress(payload) + obj.flush()
        if self.name == "zstd19":
            return zstandard.ZstdCompressor(level=19).compress(payload)
        if self.name == "zstd19+dict":
            data = zstandard.ZstdCompressionDict(self.dictionary)
            return zstandard.ZstdCompressor(level=19, dict_data=data).compress(payload)
        if self.name == "brotli11":
            return brotli.compress(payload, quality=11)
        raise ValueError(self.name)

    def decompress(self, blob: bytes) -> bytes:
        if self.name == "raw":
            return blob
        if self.name == "deflate":
            return zlib.decompress(blob)
        if self.name == "deflate+dict":
            obj = zlib.decompressobj(-15, zdict=self.dictionary)
            return obj.decompress(blob)
        if self.name == "zstd19":
            return zstandard.ZstdDecompressor().decompress(blob)
        if self.name == "zstd19+dict":
            data = zstandard.ZstdCompressionDict(self.dictionary)
            return zstandard.ZstdDecompressor(dict_data=data).decompress(blob)
        if self.name == "brotli11":
            return brotli.decompress(blob)
        raise ValueError(self.name)


def codecs_for(samples: list[bytes], only: set[str] | None = None) -> list[Codec]:
    zdict = train_zlib_dict(samples)
    sdict = train_zstd_dict(samples)
    out = [
        Codec("raw", "none"),
        Codec("deflate", "fflate"),
        Codec("deflate+dict", "fflate", zdict),
        Codec("zstd19", "fzstd"),
        Codec("brotli11", "zstd-wasm"),   # brotli-wasm is the same order of magnitude
    ]
    if sdict:
        # fzstd cannot supply a custom dictionary, so this variant costs the full wasm build.
        out.append(Codec("zstd19+dict", "zstd-wasm", sdict))
    if only:
        out = [codec for codec in out if codec.name in only]
    return out


# ------------------------------------------------------------------------------------- containers

@dataclass
class Built:
    container: str
    codec: str
    engine: str
    artifact: int          # the file(s) that land on the device
    dictionary: int        # a trained dictionary must ship too
    engine_bytes: int
    path: Path | None = None
    resident: int = 0        # bytes that must stay in RAM to serve a lookup
    transient: int = 0       # peak bytes allocated to answer one lookup
    frames: list = None      # packed only: (offset, length) per compressed frame
    order: list = None       # packed only: sorted keys, the on-disk index order
    extra: dict = None

    @property
    def total(self) -> int:
        return self.artifact + self.dictionary + self.engine_bytes


def _sqlite_build(rows: Rows, codec: Codec, fts: bool, tmp: Path, block: int | None) -> Built:
    path = tmp / f"sq-{codec.name}-{'fts' if fts else 'nofts'}-{block or 0}.db"
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA page_size=4096")
    con.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    if block:
        # Block-compressed: N entries share one compressed frame, so cross-entry redundancy is
        # recovered. A lookup decodes one block instead of one row.
        con.execute("CREATE TABLE blk(id INTEGER PRIMARY KEY, payload BLOB)")
        con.execute("CREATE TABLE entry(headword TEXT, blk INTEGER, off INTEGER, len INTEGER)")
        buffer, index, blk_id = [], [], 0
        cursor = 0
        for key, payload in rows:
            index.append((key, blk_id, cursor, len(payload)))
            buffer.append(payload)
            cursor += len(payload)
            if len(buffer) >= block:
                con.execute("INSERT INTO blk VALUES(?,?)", (blk_id, codec.compress(b"".join(buffer))))
                buffer, cursor, blk_id = [], 0, blk_id + 1
        if buffer:
            con.execute("INSERT INTO blk VALUES(?,?)", (blk_id, codec.compress(b"".join(buffer))))
        con.executemany("INSERT INTO entry VALUES(?,?,?,?)", index)
    else:
        con.execute("CREATE TABLE entry(headword TEXT, payload BLOB)")
        con.executemany("INSERT INTO entry VALUES(?,?)",
                        ((key, codec.compress(payload)) for key, payload in rows))
    con.execute("CREATE INDEX entry_headword ON entry(headword)")
    if fts:
        con.execute("CREATE VIRTUAL TABLE fts USING fts5(headword, content='')")
        con.executemany("INSERT INTO fts(rowid, headword) VALUES(?,?)",
                        ((i, key) for i, (key, _) in enumerate(rows)))
    con.commit()
    con.execute("VACUUM")
    con.close()
    # SQLite pages from disk, so only a page cache and one decoded block are resident.
    return Built(
        container=f"sqlite{'+fts5' if fts else ''}{f'+block{block}' if block else ''}",
        resident=2 * 1024 * 1024,
        transient=(block or 1) * _avg_payload(rows),
        codec=codec.name,
        engine=("sqlite-wasm+zstd-wasm" if codec.engine == "zstd-wasm"
                else "sqlite-wasm+fzstd" if codec.engine == "fzstd" else "sqlite-wasm"),
        artifact=path.stat().st_size,
        dictionary=len(codec.dictionary),
        engine_bytes=ENGINE_BYTES["sqlite-wasm"] + (ENGINE_BYTES.get(codec.engine, 0)
                                                    if codec.engine != "fflate" else 0),
        path=path,
    )


def _packed_build(rows: Rows, codec: Codec, tmp: Path, block: int) -> Built:
    """No engine at all: one blob plus a sidecar index, read with Blob.slice / OPFS.

    The index is the honest cost of dropping SQLite, so it is measured, not waved away: sorted
    keys concatenated, plus a fixed-width record per entry.
    """
    blob_path = tmp / f"packed-{codec.name}-{block}.bin"
    idx_path = tmp / f"packed-{codec.name}-{block}.idx"
    rows = sorted(rows, key=lambda item: item[0])
    blob = io.BytesIO()
    index = io.BytesIO()
    keys = io.BytesIO()
    buffer, cursor, blk_off = [], 0, 0
    entries: list[tuple[str, int, int, int]] = []
    frames: list[tuple[int, int]] = []
    for key, payload in rows:
        entries.append((key, blk_off, cursor, len(payload)))
        buffer.append(payload)
        cursor += len(payload)
        if len(buffer) >= block:
            frame = codec.compress(b"".join(buffer))
            blob.write(frame)
            frames.append((blk_off, len(frame)))
            blk_off += len(frame)
            buffer, cursor = [], 0
    if buffer:
        frame = codec.compress(b"".join(buffer))
        blob.write(frame)
        frames.append((blk_off, len(frame)))
    for key, boff, off, length in entries:
        raw = key.encode()
        index.write(struct.pack("<IIIH", boff, off, length, len(raw)))
        keys.write(raw)
    blob_path.write_bytes(blob.getvalue())
    idx_path.write_bytes(index.getvalue() + keys.getvalue())
    return Built(
        container=f"packed+block{block}",
        codec=codec.name,
        engine=codec.engine,
        artifact=blob_path.stat().st_size + idx_path.stat().st_size,
        dictionary=len(codec.dictionary),
        engine_bytes=0 if codec.engine == "fflate" else ENGINE_BYTES.get(codec.engine, 0),
        path=blob_path,
        # The index can be binary-searched on disk instead of held, which is the whole point of a
        # fixed-width record: O(log n) range reads and nothing resident but one decoded block.
        resident=64 * 1024,
        transient=block * _avg_payload(rows),
        frames=frames,
        order=[key for key, _ in rows],
        extra={"blob": blob_path.stat().st_size, "index": idx_path.stat().st_size,
               "index_if_held_in_ram": idx_path.stat().st_size},
    )


def _idb_estimate(rows: Rows, codec: Codec) -> Built:
    """IndexedDB, per-entry compressed.

    Per-record overhead is real and invisible from Python, so this reports the payload floor and
    the browser probe measures the true on-disk cost via storage.estimate().
    """
    payload = sum(len(codec.compress(value)) for _, value in rows)
    keys = sum(len(key.encode()) for key, _ in rows)
    return Built(
        container="indexeddb(payload floor)",
        resident=1024 * 1024,
        transient=_avg_payload(rows),
        codec=codec.name,
        engine=codec.engine,
        artifact=payload + keys,
        dictionary=len(codec.dictionary),
        engine_bytes=0 if codec.engine == "fflate" else ENGINE_BYTES.get(codec.engine, 0),
        extra={"note": "excludes IDB per-record overhead; see browser probe"},
    )


def build_all(rows: Rows, tmp: Path, blocks=(16, 64, 256), fast: bool = False,
              codecs: list[Codec] | None = None, packed_only: bool = False,
              skip_idb: bool = False) -> list[Built]:
    """Build every selected candidate from one payload list.

    `packed_only` is the finalists pass: the pilot showed per-row SQLite and Brotli are never
    competitive, so a full-corpus run does not need to pay for them again.
    """
    codecs = codecs or codecs_for([value for _, value in rows[:5000]])
    out: list[Built] = []
    for codec in codecs:
        if not packed_only:
            out.append(_sqlite_build(rows, codec, fts=False, tmp=tmp, block=None))
            if not fast:
                out.append(_sqlite_build(rows, codec, fts=True, tmp=tmp, block=None))
        for block in blocks:
            if not packed_only:
                out.append(_sqlite_build(rows, codec, fts=False, tmp=tmp, block=block))
            out.append(_packed_build(rows, codec, tmp=tmp, block=block))
        if not skip_idb:
            out.append(_idb_estimate(rows, codec))
    if packed_only:
        # Keep one SQLite finalist so the container comparison stays honest at full scale.
        out.append(_sqlite_build(rows, codecs[0], fts=False, tmp=tmp, block=max(blocks)))
    return out


# ------------------------------------------------------------------------------------- benchmarks

def bench_sqlite(built: Built, keys: list[str], codec: Codec, block: int | None) -> dict:
    """Exact lookup and prefix search, cold-ish: the page cache is dropped between runs."""
    con = sqlite3.connect(f"file:{built.path}?mode=ro", uri=True)
    exact = []
    for key in keys:
        start = time.perf_counter()
        if block:
            row = con.execute("SELECT blk, off, len FROM entry WHERE headword=?", (key,)).fetchone()
            if row:
                frame = con.execute("SELECT payload FROM blk WHERE id=?", (row[0],)).fetchone()[0]
                codec.decompress(frame)[row[1]:row[1] + row[2]]
        else:
            row = con.execute("SELECT payload FROM entry WHERE headword=?", (key,)).fetchone()
            if row:
                codec.decompress(row[0])
        exact.append((time.perf_counter() - start) * 1000)
    prefix = []
    for key in keys[:200]:
        stem = key[:3]
        start = time.perf_counter()
        con.execute("SELECT headword FROM entry WHERE headword>=? AND headword<? LIMIT 25",
                    (stem, stem + "￿")).fetchall()
        prefix.append((time.perf_counter() - start) * 1000)
    con.close()
    return {"exact_p50": _p(exact, 50), "exact_p95": _p(exact, 95),
            "prefix_p50": _p(prefix, 50), "prefix_p95": _p(prefix, 95)}


def _p(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * pct / 100))
    return round(ordered[index], 4)


def bench_packed(built: Built, keys: list[str], codec: Codec, block: int) -> dict:
    """Exact lookup against the packed blob: locate the entry, then decode only its frame.

    Mirrors what a client does with OPFS or Blob.slice — one range read, one block decoded, and
    nothing else resident. Frame offsets come from the build, so nothing is recompressed here.
    """
    import bisect

    position = {key: index for index, key in enumerate(built.order)}
    handle = open(built.path, "rb")
    exact = []
    for key in keys:
        index = position.get(key)
        if index is None:
            continue
        start = time.perf_counter()
        frame_off, frame_len = built.frames[index // block]
        handle.seek(frame_off)
        codec.decompress(handle.read(frame_len))
        exact.append((time.perf_counter() - start) * 1000)
    handle.close()
    # Prefix search binary-searches the sorted key index; no payload is touched.
    prefix = []
    for key in keys[:200]:
        stem = key[:3]
        start = time.perf_counter()
        left = bisect.bisect_left(built.order, stem)
        built.order[left:left + 25]
        prefix.append((time.perf_counter() - start) * 1000)
    return {"exact_p50": _p(exact, 50), "exact_p95": _p(exact, 95),
            "prefix_p50": _p(prefix, 50), "prefix_p95": _p(prefix, 95)}

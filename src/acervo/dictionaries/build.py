"""Turn a catalogue row into the artifact triple.

The whole pipeline is: read the row, fetch the source (cached), run the converter the row names,
pack it with `container.build_artifact`. Nothing here knows what any particular dictionary looks
like — that is `converters.py` — and nothing here knows the on-disk layout — that is `container.py`.

This is written so that a later "build it from the interface" job is a *caller* of `build`, not a
second pipeline: it takes a progress callback and raises on failure rather than reporting to a
terminal itself.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .catalogue import CatalogueEntry, find
from .container import BuildReport, build_artifact
from .converters import source_entries

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
#: Downloads are kept between builds. A mapper change is then a re-run rather than another 1.19 GB
#: fetch, which matters because the mappers are expected to change a lot before they settle.
#: TODO: once the conversions are trusted, flip the default to discarding — the source is 2-25x the
#: artifact and nothing reads it again.
DEFAULT_CACHE = REPOSITORY_ROOT / "data" / "dictionaries" / "src"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "dictionaries" / "out"

USER_AGENT = "Acervo/1.0 (self-hosted vocabulary store; +https://acervo.example.com)"

Progress = Callable[[str], None]


def output_directory() -> Path:
    """Where compiled artifacts land. The server serves this directory; the worker writes it."""
    configured = os.environ.get("ACERVO_DICTIONARIES_PATH")
    return Path(configured) if configured else DEFAULT_OUTPUT


def cache_directory() -> Path:
    """Where downloaded sources are kept between builds — inside the worker's own data, never in
    the directory the server serves, because a source is 2-25x the artifact and nobody should be
    able to download it from Acervo."""
    configured = os.environ.get("ACERVO_DICTIONARY_CACHE")
    return Path(configured) if configured else DEFAULT_CACHE


@dataclass
class BuildResult:
    row: CatalogueEntry
    report: BuildReport
    destination: Path
    seconds: float

    @property
    def total_bytes(self) -> int:
        return self.report.blob_bytes + self.report.index_bytes


#: Keyed by row id rather than by the row, which carries an unhashable options dict.
_RESOLVED: dict[str, str] = {}


def _resolve(resolver: str, row: CatalogueEntry) -> str:
    """Resolvers reach the network, and one build asks twice — once to fetch, once to record where
    it fetched from. Caching keeps that to one request."""
    if row.id in _RESOLVED:
        return _RESOLVED[row.id]
    _RESOLVED[row.id] = _resolved(resolver, row)
    return _RESOLVED[row.id]


def _resolved(resolver: str, row: CatalogueEntry) -> str:
    if resolver == "freedict":
        database = _json("https://freedict.org/freedict-database.json")
        pair, platform = row.option("pair"), row.option("platform", "src")
        for record in database:
            if record.get("name") != pair:
                continue
            for release in record.get("releases", []):
                if release.get("platform") == platform:
                    return release["URL"]
        raise LookupError(f"{row.id}: FreeDict has no {platform} release for {pair}")
    if resolver == "github-release":
        import re as _re

        release = _json(f"https://api.github.com/repos/{row.option('repo')}/releases/latest")
        pattern = _re.compile(row.option("asset"))
        for asset in release.get("assets", []):
            if pattern.search(asset["name"]):
                return asset["browser_download_url"]
        raise LookupError(f"{row.id}: no asset matching {row.option('asset')!r} in the latest release")
    raise ValueError(f"{row.id}: unknown resolver {resolver!r}")


def download_url(row: CatalogueEntry) -> str:
    """Where this row's source actually is right now.

    FreeDict and jmdict-simplified both put a version in the filename, so a URL written into the
    catalogue rots the next time either publishes. Those rows carry a resolver instead and the
    catalogue's own `url` is provenance — what the row was last known to point at — rather than the
    address the fetcher uses.
    """
    resolver = row.option("resolve")
    return row.url if resolver is None else _resolve(resolver, row)


def _json(url: str):
    import json as _json_module

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return _json_module.loads(response.read().decode("utf-8"))


def fetch(row: CatalogueEntry, *, cache: Path | None = None, progress: Progress = lambda _: None) -> Path:
    """Download the source unless it is already cached.

    Deliberately not a resumable or parallel downloader: this runs once per dictionary on a machine
    the owner controls, and a failed download is re-run rather than repaired.
    """
    cache = cache or cache_directory()
    cache.mkdir(parents=True, exist_ok=True)
    url = download_url(row)
    target = cache / (row.option("filename") or url.rsplit("/", 1)[-1].split("?")[0])
    if target.exists() and target.stat().st_size:
        progress(f"using the cached source at {target}")
        return target

    progress(f"downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    partial = target.with_suffix(target.suffix + ".partial")
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as handle:
        shutil.copyfileobj(response, handle, length=1 << 20)
    partial.replace(target)
    progress(f"downloaded {target.stat().st_size:,} bytes")
    return target


def build(
    identifier: str,
    *,
    destination: Path | None = None,
    cache: Path | None = None,
    limit: int | None = None,
    discard_source: bool = False,
    progress: Progress = lambda _: None,
) -> BuildResult:
    """Compile one catalogue row. `limit` truncates the source, for verifying a row cheaply."""
    row = find(identifier)
    if row.kind != "offline":
        raise ValueError(f"{row.id} is a {row.kind} source; there is nothing to compile")

    source = fetch(row, cache=cache, progress=progress)
    destination = destination or output_directory()
    report = BuildReport()
    started = time.perf_counter()

    progress(f"converting with the {row.format} converter")
    entries = source_entries(source, row, report)
    if limit is not None:
        entries = _capped(entries, limit)

    metadata = {
        "id": row.id,
        "name": row.name,
        "sourceLang": row.sourceLang,
        "targetLang": row.targetLang,
        "format": row.format,
        "sourceUrl": download_url(row),
        "licence": row.licence,
        "attribution": row.attribution,
        "sourceDate": _source_date(source),
        "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    build_artifact(entries, destination=destination, dictionary_id=row.id, tier=row.tier,
                   metadata=metadata, report=report)
    elapsed = time.perf_counter() - started

    if discard_source:
        source.unlink(missing_ok=True)
        progress("discarded the downloaded source")
    return BuildResult(row=row, report=report, destination=destination, seconds=elapsed)


def verify(identifier: str, *, limit: int = 5000, progress: Progress = lambda _: None) -> BuildResult:
    """Build a row into a throwaway directory, to check it produces entries at all.

    This is how a catalogue row is promoted from listed to trusted without installing anything or
    committing to a full multi-gigabyte pass.
    """
    with tempfile.TemporaryDirectory(prefix="acervo-verify-") as scratch:
        return build(identifier, destination=Path(scratch), limit=limit, progress=progress)


def _capped(entries, limit: int):
    for index, entry in enumerate(entries):
        if index >= limit:
            return
        yield entry


def _source_date(source: Path) -> str:
    """What identifies the corpus a build came from — the artifact's own `builtAt` cannot, because
    two builds of the same source minutes apart are the same dictionary."""
    return datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")

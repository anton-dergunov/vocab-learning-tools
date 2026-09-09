"""The artifact format, checked from the side that writes it.

`web/src/dictionary.ts` reads what `container.py` writes, so the two are one format described
twice. These tests pin the properties that reader depends on; `web/src/dictionary.test.ts` reads a
fixture built by this code and is the other half of the same check.
"""

from __future__ import annotations

import io
import json
import zlib
from pathlib import Path

import pytest

from acervo.dictionaries.container import (
    FRAME_SIZE,
    MAGIC,
    BuildReport,
    SourceEntry,
    build_artifact,
    parse_index,
    read_artifact_entry,
    read_varint,
    write_varint,
)


def entries(words, tier="fields"):
    for word in words:
        payload = (json.dumps([{"headword": word, "senses": [{"definition": f"about {word}"}]}],
                              separators=(",", ":")).encode()
                   if tier == "fields" else f"<h1>{word}</h1>".encode())
        yield SourceEntry(key=word, payload=payload)


def artifact(tmp_path: Path, source, tier="fields", **kwargs):
    report = build_artifact(source, destination=tmp_path, dictionary_id="d", tier=tier,
                            metadata={"id": "d", "name": "Test"}, **kwargs)
    return report, (tmp_path / "d.dict").read_bytes(), (tmp_path / "d.idx").read_bytes()


@pytest.mark.parametrize("value", [0, 1, 127, 128, 300, 16_383, 16_384, 2**31, 2**40])
def test_varints_round_trip(value):
    buffer = io.BytesIO()
    write_varint(buffer, value)
    assert read_varint(buffer.getvalue(), 0) == (value, len(buffer.getvalue()))


def test_every_entry_is_findable(tmp_path):
    """The property that actually matters: nothing written is unreachable.

    Enough words to span several frames and many restart buckets, because the bugs in a front-coded
    index live at bucket boundaries rather than in the middle of one.
    """
    words = sorted({f"palabra{index:04d}" for index in range(2000)} | {"picar", "ñandú", "漢字"})
    _, blob, index = artifact(tmp_path, entries(words))
    for word in words:
        found = read_artifact_entry(blob, index, word)
        assert found is not None, f"{word} was written but cannot be found"
        assert json.loads(found)[0]["headword"] == word


def test_absent_words_are_absent_rather_than_wrong(tmp_path):
    _, blob, index = artifact(tmp_path, entries(["alpha", "gamma"]))
    for word in ("", "beta", "alph", "alphaa", "zzz", " "):
        assert read_artifact_entry(blob, index, word) is None


def test_a_headword_with_several_articles_keeps_all_of_them(tmp_path):
    """CC-CEDICT writes one line per reading, so a character arrives several times and every one of
    them belongs to the same lookup. Keeping only the first silently lost 3 % of that dictionary."""
    source = [
        SourceEntry("行", b'[{"headword":"\\u884c","reading":"hang2"}]'),
        SourceEntry("行", b'[{"headword":"\\u884c","reading":"xing2"}]'),
        SourceEntry("走", b'[{"headword":"\\u8d70","reading":"zou3"}]'),
    ]
    report, blob, index = artifact(tmp_path, iter(source))
    assert report.entry_count == 2 and report.merged_entries == 1
    articles = json.loads(read_artifact_entry(blob, index, "行"))
    assert [article["reading"] for article in articles] == ["hang2", "xing2"]


def test_aliases_and_case_folding_reach_the_same_entry(tmp_path):
    source = [SourceEntry("漢字", b'[{"headword":"\\u6f22\\u5b57"}]', aliases=("汉字",)),
              SourceEntry("Picar", b'[{"headword":"Picar"}]')]
    _, blob, index = artifact(tmp_path, iter(source))
    assert json.loads(read_artifact_entry(blob, index, "汉字"))[0]["headword"] == "漢字"
    assert json.loads(read_artifact_entry(blob, index, "picar"))[0]["headword"] == "Picar"


def test_keys_are_sorted_by_utf8_bytes_not_by_utf16_code_units(tmp_path):
    """JavaScript compares UTF-16 code units, which disagrees with UTF-8 byte order above the BMP.

    A reader binary-searching one order over an index built in the other misses real entries, and it
    misses them only for the rarest characters, so it would not show up in casual use.
    """
    words = ["Ａ", "\U0001F600", "￮", "a", "ÿ"]
    _, blob, index = artifact(tmp_path, entries(words))
    layout = parse_index(index)
    ordered = [layout._restart_key(restart) for restart in range(len(layout.restart_offsets))]
    assert ordered == sorted(ordered)
    for word in words:
        assert read_artifact_entry(blob, index, word) is not None


def test_rebuilding_is_byte_identical(tmp_path):
    """A rebuild has to be diffable, and a mirror has to be checksummable."""
    words = [f"w{index}" for index in range(500)]
    _, first_blob, first_index = artifact(tmp_path / "one", entries(words))
    _, second_blob, second_index = artifact(tmp_path / "two", entries(words))
    assert first_blob == second_blob and first_index == second_index


def test_the_index_is_much_smaller_than_a_fixed_width_one(tmp_path):
    """Front-coding is the single largest size win available and is not optional (§11.2)."""
    words = sorted(f"desafortunadamente{index:05d}" for index in range(5000))
    _, _, index = artifact(tmp_path, entries(words))
    naive = sum(len(word.encode()) for word in words) + 14 * len(words)
    assert len(index) < naive * 0.45, f"index {len(index)} is not far enough under naive {naive}"


def test_frames_hold_exactly_the_configured_number_of_entries(tmp_path):
    report, blob, index = artifact(tmp_path, entries([f"w{i:04d}" for i in range(700)]))
    layout = parse_index(index)
    assert report.frame_count == 3 and layout.frame_size == FRAME_SIZE
    decoded = zlib.decompressobj(-15).decompress(blob[:layout.frame_lengths[0]])
    assert decoded.startswith(b'[{"headword":"w0000"')


def test_the_html_tier_concatenates_rather_than_splicing_json(tmp_path):
    source = [SourceEntry("a", b"<h1>a</h1>"), SourceEntry("a", b"<h2>again</h2>")]
    _, blob, index = artifact(tmp_path, iter(source), tier="html")
    assert read_artifact_entry(blob, index, "a") == b"<h1>a</h1><h2>again</h2>"


def test_the_metadata_names_what_was_lost(tmp_path):
    report = BuildReport()
    report.dropped_fields.add("etymology_text")
    report.unmapped_pos.add("preposition")
    build_artifact(entries(["a"]), destination=tmp_path, dictionary_id="d", tier="fields",
                   metadata={"id": "d", "licence": "CC BY-SA 4.0"}, report=report)
    document = json.loads((tmp_path / "d.json").read_text())
    assert document["droppedFields"] == ["etymology_text"]
    assert document["unmappedPartsOfSpeech"] == ["preposition"]
    assert document["licence"] == "CC BY-SA 4.0"
    assert set(document["checksums"]) == {"d.dict", "d.idx"}


def test_an_empty_dictionary_is_still_a_valid_artifact(tmp_path):
    report, blob, index = artifact(tmp_path, iter([]))
    assert report.entry_count == 0 and blob == b"" and index[:4] == MAGIC
    assert read_artifact_entry(blob, index, "anything") is None

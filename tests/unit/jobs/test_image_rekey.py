"""Re-keying a laptop run onto the senses an account holds now.

The throwaway script that lands the backlog, and the one place a mistake would be quiet: a wrong
match puts somebody else's picture on your word. So the tests are about what it *refuses*.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from acervo.images.ids import image_prompt_id  # noqa: E402
from rekey_image_runs import rekey  # noqa: E402


def graph(*, headword="el atraco", language="es", definitions=("Robo con violencia.",),
          example="La policía detuvo a los sospechosos."):
    senses = [
        {"id": f"sense{index:011d}", "lexemeId": "lexemeatraco01", "definition": definition,
         "order": index, "deleted": False}
        for index, definition in enumerate(definitions)
    ]
    return {
        "lexemes": [{"id": "lexemeatraco01", "language": language, "headword": headword,
                     "deleted": False}],
        "senses": senses,
        "examples": [{"id": "exampleatraco1", "senseId": senses[0]["id"], "text": example,
                      "deleted": False}] if senses else [],
    }


def run_directory(tmp_path: Path, **overrides) -> Path:
    source = tmp_path / "drawn"
    (source / "records").mkdir(parents=True)
    (source / "images").mkdir(parents=True)
    record = {
        "id": "0088hcytqci2gl0", "lexemeId": "g5lb8u25jbfkusd", "senseId": "oj3y4cakuelbgrd",
        "prompt": "Two officers pin a masked robber.", "styleId": "film-noir", "seed": 423568482,
        "modelId": "gemini-3.8-flash", "promptVersion": "img-a-b-c",
        "imageRef": "images/g5lb8u25jbfkusd/0088hcytqci2gl0.webp",
        "imageModelId": "gemini-3.1-flash-lite-image", "attempts": 1, "failureReason": None,
        "run": {"headword": "el atraco", "language": "es", "senseOrder": 0,
                "definition": "Robo con violencia.",
                "anchorExample": {"text": "La policía detuvo a los sospechosos."}},
    }
    record.update(overrides)
    (source / "records" / f"{record['id']}.json").write_text(json.dumps(record))
    (source / "images" / f"{record['id']}.webp").write_bytes(b"RIFFfake")
    return source


def read_one(destination: Path) -> dict:
    [path] = sorted((destination / "records").glob("*.json"))
    return json.loads(path.read_text())


def test_it_re_derives_the_id_the_filename_and_the_reference(tmp_path):
    source = run_directory(tmp_path)
    out = tmp_path / "rekeyed"
    result = rekey(source, out, graph(), report=lambda line: None)

    assert result.matched == 1 and result.skipped == 0
    expected = image_prompt_id("sense00000000000")
    record = read_one(out)
    assert record["id"] == expected
    assert record["senseId"] == "sense00000000000"
    assert record["lexemeId"] == "lexemeatraco01"
    assert record["imageRef"] == f"images/lexemeatraco01/{expected}.webp"
    assert (out / "images" / f"{expected}.webp").read_bytes() == b"RIFFfake"


def test_it_finds_the_sentence_the_scene_was_built_from(tmp_path):
    out = tmp_path / "rekeyed"
    rekey(run_directory(tmp_path), out, graph(), report=lambda line: None)
    assert read_one(out)["exampleId"] == "exampleatraco1"


def test_a_sentence_that_no_longer_exists_leaves_the_picture_without_an_anchor(tmp_path):
    """It survives its anchor rather than being dropped: the picture is still of that sense."""
    out = tmp_path / "rekeyed"
    result = rekey(
        run_directory(tmp_path), out, graph(example="Something else entirely."),
        report=lambda line: None,
    )
    assert result.matched == 1
    assert read_one(out)["exampleId"] is None


def test_it_never_writes_into_the_directory_it_read(tmp_path):
    """500 MB of unrepeatable work: a bad match must be a directory you delete."""
    source = run_directory(tmp_path)
    before = sorted(path.name for path in (source / "records").iterdir())
    rekey(source, tmp_path / "rekeyed", graph(), report=lambda line: None)
    assert sorted(path.name for path in (source / "records").iterdir()) == before


# ── what it refuses ─────────────────────────────────────────────────────────


def test_a_word_this_account_does_not_hold_is_reported_not_guessed(tmp_path):
    result = rekey(
        run_directory(tmp_path), tmp_path / "rekeyed", graph(headword="otra palabra"),
        report=lambda line: None,
    )
    assert result.matched == 0 and result.skipped == 1
    assert "no word with that headword" in result.problems[0]


def test_a_sense_that_now_reads_differently_is_refused(tmp_path):
    """The definition is the check on the key, not the key. A picture landing on the wrong sense of
    the right word is the quiet failure this exists to catch."""
    result = rekey(
        run_directory(tmp_path), tmp_path / "rekeyed",
        graph(definitions=("Something quite different.",)), report=lambda line: None,
    )
    assert result.matched == 0
    assert "reads differently" in result.problems[0]


def test_a_word_whose_senses_were_renumbered_is_refused(tmp_path):
    result = rekey(
        run_directory(tmp_path, run={"headword": "el atraco", "language": "es", "senseOrder": 3,
                                     "definition": "Robo con violencia."}),
        tmp_path / "rekeyed", graph(), report=lambda line: None,
    )
    assert result.matched == 0
    assert "no longer exists" in result.problems[0]


def test_a_headword_held_twice_is_refused_rather_than_resolved(tmp_path):
    """There is no way to tell which of two words a picture was drawn for."""
    twice = graph()
    twice["lexemes"].append({"id": "lexemeatraco02", "language": "es", "headword": "El Atraco",
                             "deleted": False})
    result = rekey(run_directory(tmp_path), tmp_path / "rekeyed", twice, report=lambda line: None)
    assert result.matched == 0
    assert "no word with that headword" in result.problems[0]


def test_a_record_claiming_a_picture_that_is_not_on_disk_is_refused(tmp_path):
    source = run_directory(tmp_path)
    (source / "images" / "0088hcytqci2gl0.webp").unlink()
    result = rekey(source, tmp_path / "rekeyed", graph(), report=lambda line: None)
    assert result.matched == 0
    assert "not on disk" in result.problems[0]


def test_a_case_difference_in_the_headword_still_matches(tmp_path):
    """The store holds `Picar` about as often as `picar`, and that is not a different word."""
    result = rekey(
        run_directory(tmp_path), tmp_path / "rekeyed", graph(headword="El Atraco"),
        report=lambda line: None,
    )
    assert result.matched == 1

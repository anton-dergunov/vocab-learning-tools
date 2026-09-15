"""Steps 2–4: OCR accuracy, sentence splitting and taps, from cached engine output only."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import engines as E
import evaluate as V
import hit
import layout as L
import segment

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent / "tests" / "fixtures" / "photo-capture"
REFERENCE = ("vision", E.Variant("full", None))
VARIANTS = [E.Variant(crop, edge) for crop in ("full", "centre") for edge in (1280, 2048, None)]
ENGINES = {
    "vision": lambda data: E.vision_read(data),
    "rapid-v5m": lambda data: E.rapidocr_read(data, "v5m-latin", 0.5),
    "rapid-v5m-box.3": lambda data: E.rapidocr_read(data, "v5m-latin", 0.3),
    "rapid-v6det-box.3": lambda data: E.rapidocr_read(data, "v6s-det-v5-latin", 0.3),
}


def manifest() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "manifest.json").read_text())["images"]


def cached(engine: str, data: bytes) -> dict[str, Any] | None:
    """Engine output only if it is already cached: scoring never spends a call."""
    settings = {
        "vision": ("vision", {"feature": "DOCUMENT_TEXT_DETECTION", "hints": ["es"]}),
        "rapid-v5m": ("rapidocr", {"preset": E.PRESETS["v5m-latin"], "box_thresh": 0.5, "max_side": "unlimited"}),
        "rapid-v5m-box.3": ("rapidocr", {"preset": E.PRESETS["v5m-latin"], "box_thresh": 0.3, "max_side": "unlimited"}),
        "rapid-v6det-box.3": ("rapidocr", {"preset": E.PRESETS["v6s-det-v5-latin"], "box_thresh": 0.3, "max_side": "unlimited"}),
    }[engine]
    path = E._cache_path(settings[0], settings[1], data)
    return json.loads(path.read_text()) if path.exists() else None


def place_taps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every truth tap with a full-frame point, from the reference reading."""
    placed = []
    for row in rows:
        data, _, _ = E.prepare(FIXTURES / row["file"], REFERENCE[1])
        reference = V.reading(cached("vision", data))
        size = (reference_size(row))
        for index, tap in enumerate(row["truth"]["taps"]):
            sentence = row["truth"]["sentences"][tap["sentence"]]
            token = None
            if sentence["text"]:
                token = V.locate_tap(reference, sentence["text"], tap["word"], tap["occurrence"])
            else:
                matches = [t for t in reference["tokens"] if V.bare(t["text"]) == V.bare(tap["word"])]
                token = matches[tap["occurrence"]] if len(matches) > tap["occurrence"] else None
            if token is None:
                print(f"  cannot place {row['file']} {tap['word']!r}")
                continue
            point = V.centroid(token["polygons"][0])
            placed.append({**tap, "file": row["file"], "kind": row["kind"], "id": f"{row['file']}#{index}",
                           "x": round(point[0], 4), "y": round(point[1], 4), "size": size,
                           "sentenceText": sentence["text"], "sentenceFlags": sentence})
    return placed


def reference_size(row: dict[str, Any]) -> tuple[int, int]:
    import cv2

    image = cv2.imread(str(FIXTURES / row["file"]))
    return image.shape[1], image.shape[0]


def score_taps(taps, layouts, arm) -> list[dict[str, Any]]:
    results = []
    for tap in taps:
        variant = layouts["variant"]
        read = layouts["readings"].get(tap["file"])
        point = V.to_variant((tap["x"], tap["y"]), tuple(tap["size"]), variant)
        outcome = {"id": tap["id"], "class": tap["class"], "kind": tap["kind"], "cropped": point is None}
        if point is None or read is None:
            outcome.update(wordHit=False, wordCer=1.0, sentenceCer=None, sentenceOk=False, boundaryOk=False)
            results.append(outcome)
            continue
        index = hit.token_at(read["tokens"], point)
        token = read["tokens"][index] if index is not None else None
        got = V.bare(token["text"]) if token else ""
        outcome["word"] = token["text"] if token else None
        outcome["wordHit"] = got == V.bare(tap["word"])
        outcome["wordCer"] = V.cer(V.bare(tap["word"]), got)
        spans = read["spans"][arm]
        if token is None or not tap["sentenceText"]:
            outcome.update(sentenceCer=None, sentenceOk=None if not tap["sentenceText"] else False,
                           boundaryOk=None if not tap["sentenceText"] else False)
            results.append(outcome)
            continue
        position = hit.sentence_of(spans, token)
        start, end = spans[position] if position is not None else (0, 0)
        ocr_sentence = read["text"][start:end]
        outcome["ocrSentence"] = ocr_sentence
        outcome["wordStart"] = token["start"] - start
        outcome["wordEnd"] = token["end"] - start
        outcome["sentenceCer"] = V.cer(tap["sentenceText"], ocr_sentence)
        # Where the truth sentence sits in this same OCR text: a boundary is right when the splitter
        # put its span there, whatever the OCR did to the characters inside.
        a_start, a_end, _ = V.align(tap["sentenceText"], read["text"])
        outcome["boundaryOk"] = abs(start - a_start) <= 3 and abs(end - a_end) <= 3
        outcome["sentenceOk"] = outcome["sentenceCer"] <= 0.10
        results.append(outcome)
    return results


def readings_for(engine: str, variant: E.Variant, rows) -> dict[str, Any]:
    readings = {}
    for row in rows:
        data, _, _ = E.prepare(FIXTURES / row["file"], variant)
        layout = cached(engine, data)
        if layout is None:
            continue
        read = V.reading(L.rebuild_lines(layout))
        read["spans"] = {name: fn(read["text"]) for name, fn in segment.ARMS.items()}
        read["ocr_s"] = layout["timing"].get("ocr_s", layout["timing"].get("roundtrip_s"))
        read["bytes"] = len(data)
        readings[row["file"]] = read
    return readings


def sentence_cers(rows, readings) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {"camera": [], "screenshot": []}
    for row in rows:
        read = readings.get(row["file"])
        if read is None:
            continue
        for sentence in row["truth"]["sentences"]:
            if sentence["text"] and not sentence["occluded"]:
                out[row["kind"]].append(V.align(sentence["text"], read["text"])[2])
    return out


def segmentation_on_truth(rows) -> dict[str, dict[str, float]]:
    """Each splitter on the truth text itself: boundaries found, with no OCR in the way."""
    scores = {}
    for name, fn in segment.ARMS.items():
        found = expected = matched = 0
        for row in rows:
            texts = [s["text"] for s in row["truth"]["sentences"] if s["text"]]
            if len(texts) < 2:
                continue
            joined, boundaries, cursor = "", set(), 0
            for text in texts:
                joined += text + " "
                cursor += len(text)
                boundaries.add(cursor)
                cursor += 1
            boundaries.discard(len(joined.rstrip()))
            got = {end for _, end in fn(joined.rstrip())}
            got.discard(len(joined.rstrip()))
            found += len(got)
            expected += len(boundaries)
            matched += len({b for b in got if any(abs(b - e) <= 1 for e in boundaries)})
        scores[name] = {"precision": matched / found if found else 0.0,
                        "recall": matched / expected if expected else 0.0,
                        "boundaries": expected}
    return scores


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else float("nan")


def rate(values):
    values = [v for v in values if v is not None]
    return 100 * sum(1 for v in values if v) / len(values) if values else float("nan")


def run() -> dict[str, Any]:
    rows = manifest()
    taps = place_taps(rows)
    report = {"taps": taps, "segmentationOnTruth": segmentation_on_truth(rows), "arms": []}
    for engine in ENGINES:
        for variant in VARIANTS:
            readings = readings_for(engine, variant, rows)
            if len(readings) < len(rows):
                continue
            cers = sentence_cers(rows, readings)
            for arm in segment.ARMS:
                results = score_taps(taps, {"variant": variant, "readings": readings}, arm)
                report["arms"].append({
                    "engine": engine, "variant": variant.name, "segmenter": arm,
                    "cerCamera": mean(cers["camera"]), "cerScreenshot": mean(cers["screenshot"]),
                    "bytesMedian": statistics.median(r["bytes"] for r in readings.values()),
                    "ocrMedian": statistics.median(r["ocr_s"] for r in readings.values()),
                    "results": results,
                })
    return report

"""The meaning map's pure parts: what is embedded, the cache, the layout's alignment, regions,
the cheap labels and a model's names read with suspicion."""

from __future__ import annotations

import numpy as np

from acervo.meaning import artifact, layout, names, regions
from acervo.meaning.artifact import MapSense
from acervo.meaning.cache import EmbeddingCache
from acervo.meaning.text import digest, sense_text


def test_a_sense_is_embedded_as_its_word_its_definition_and_its_glosses():
    text = sense_text("abyss", "noun", " A deep chasm. ",
                      [{"lang": "ru", "terms": ["бездна", "пропасть"]}, {"lang": "en", "terms": ["void"]}])
    assert text == "abyss (noun) — A deep chasm. — бездна; пропасть; void"


def test_the_digest_changes_with_the_text_and_with_the_model():
    assert digest("m", "a") == digest("m", "a")
    assert digest("m", "a") != digest("m", "b")
    assert digest("m", "a") != digest("n", "a")


def test_the_cache_returns_what_it_stored_and_nothing_else(tmp_path):
    cache = EmbeddingCache(tmp_path)
    vector = np.arange(4, dtype=np.float32)
    key = digest("m", "a")
    assert cache.find(key) is None
    cache.store(key, vector)
    assert np.array_equal(cache.find(key), vector)
    assert not list(tmp_path.rglob("*.part"))


def test_a_mirrored_rotated_layout_is_put_back_where_it_was():
    rng = np.random.default_rng(1)
    before = rng.uniform(0, 1000, size=(40, 2))
    angle = 1.1
    turn = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    moved = (before * [-1, 1]) @ turn * 0.7 + 300
    ids = [f"s{i}" for i in range(40)]
    aligned = layout.align(moved, ids, {sense: before[i] for i, sense in enumerate(ids)})
    assert np.abs(aligned - before).max() < 1e-6


def test_too_few_shared_points_leave_a_layout_in_its_own_frame():
    coords = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert np.array_equal(layout.align(coords, ["a", "b"], {"a": (9, 9), "b": (8, 8)}), coords)


def test_c_tf_idf_names_what_is_distinctive_about_a_cluster():
    definitions = ["Cortar la cebolla en trozos.", "Cortar el pan con cuchillo.", "Cuchillo de cocina.",
                   "Pagar la cuenta del banco.", "Dinero que se debe al banco.", "El banco cobra dinero."]
    found = regions.terms(definitions, np.array([0, 0, 0, 1, 1, 1]), "es")
    assert "cortar" in found[0] or "cuchillo" in found[0]
    assert "banco" in found[1] or "dinero" in found[1]
    assert not {"la", "el", "de", "que"} & set(found[0] + found[1])


def test_neighbours_are_other_words_senses():
    vectors = np.eye(4)[[0, 0, 1, 1]] + np.eye(4)[[2, 3, 2, 3]] * 0.1
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    near = regions.neighbours(vectors, ["a", "a", "b", "b"], k=2)
    assert all(j in (2, 3) for j in near[0]) and all(j in (0, 1) for j in near[2])


def test_a_models_names_are_kept_only_for_regions_that_exist():
    reply = {"r0": "  dinero   y trabajo. ", "h1": "", "r9": "invented", "h0": 7, "r1": "x" * 80}
    named = names.parse_reply(reply, ["r0", "r1", "h0", "h1"])
    assert named == {"r0": "dinero y trabajo", "r1": "x" * names.MAX_LENGTH}
    assert names.parse_reply(["not", "a", "mapping"], ["r0"]) == {}


def _blobs(per: int = 60, dim: int = 24, seed: int = 3):
    """Three well-separated groups of senses, a word each, with unit vectors."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(3, dim)) * 4
    vectors, senses = [], []
    for group, centre in enumerate(centres):
        for i in range(per):
            vectors.append(centre + rng.normal(size=dim) * 0.4)
            senses.append(MapSense(sense=f"s{group}-{i}", lexeme=f"w{group}-{i}", headword=f"word{group}{i}",
                                   pos="noun", definition=f"Group {group} thing number {i}."))
    matrix = np.array(vectors, dtype=np.float32)
    return senses, matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


def test_a_large_map_has_nested_regions_that_never_mix_groups():
    senses, vectors = _blobs()
    body = artifact.build(senses, vectors, definition_lang="en")
    points = body["points"]
    assert body["senses"] == 180 and body["words"] == 180
    assert {r["level"] for r in body["regions"]} == {"region", "hood"}
    group = lambda p: p["sense"].split("-")[0]  # noqa: E731
    for region in (r for r in body["regions"] if r["level"] == "region"):
        inside = {group(p) for p in points if p["r"] == region["index"]}
        assert len(inside) == 1, f"region {region['id']} mixes {inside}"
    for hood in (r for r in body["regions"] if r["level"] == "hood"):
        parents = {p["r"] for p in points if p["h"] == hood["index"]}
        assert parents == {hood["region"]}
    assert body["contours"] and all(len(line) >= 6 for _, line in body["contours"])
    assert all(len(p["nb"]) == regions.NEIGHBOURS for p in points)


def test_a_small_map_is_words_without_regions():
    senses, vectors = _blobs(per=10)
    body = artifact.build(senses, vectors, definition_lang="en")
    assert body["regions"] == [] and body["contours"] == []
    assert all(p["r"] == -1 and p["h"] == -1 for p in body["points"])


def test_an_empty_or_tiny_vocabulary_still_draws():
    assert artifact.build([], np.zeros((0, 4)), definition_lang="es")["points"] == []
    senses, vectors = _blobs(per=1)
    assert len(artifact.build(senses, vectors, definition_lang="es")["points"]) == 3


def test_the_fingerprint_is_the_senses_and_what_they_say_in_any_order():
    pairs = [("a", "1"), ("b", "2")]
    assert artifact.fingerprint("m", pairs) == artifact.fingerprint("m", list(reversed(pairs)))
    assert artifact.fingerprint("m", pairs) != artifact.fingerprint("m", [("a", "1"), ("b", "3")])
    assert artifact.fingerprint("m", pairs) != artifact.fingerprint("n", pairs)


def test_a_map_redrawn_with_one_more_word_starts_from_the_last_and_barely_moves():
    senses, vectors = _blobs()
    first = artifact.build(senses[:-1], vectors[:-1], definition_lang="en")
    previous = {p["sense"]: (p["x"], p["y"]) for p in first["points"]}
    warm = artifact.build(senses, vectors, definition_lang="en", previous=previous)
    cold = layout.align(layout.layout(vectors), [s.sense for s in senses], previous)

    def moved(points) -> float:
        return float(np.median([np.hypot(x - previous[s.sense][0], y - previous[s.sense][1])
                                for s, (x, y) in zip(senses, points) if s.sense in previous]))

    # Inside each blob the vectors are noise, so points there shuffle more than real senses do (the
    # owner's vocabulary: 37 warm against 140 cold). What must hold is that the warm start beats a
    # cold one and never throws the map across the frame.
    warm_shift = moved([(p["x"], p["y"]) for p in warm["points"]])
    assert warm_shift < moved(cold)
    assert warm_shift < 150, f"one new word moved the map {warm_shift:.0f} of 1000"

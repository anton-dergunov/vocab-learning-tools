"""The pure halves of the sense-image stage: ids, style menus, reply parsing, and the plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acervo.jobs.images.brief import build_request, parse_reply
from acervo.jobs.images.compose import FRAME, compose, prompt_version
from acervo.jobs.images.graph import build_articles
from acervo.jobs.images.ids import ID_LENGTH, image_prompt_id, seed_for
from acervo.jobs.images.run import Store, plan
from acervo.jobs.images.styles import load_styles

REPO_ROOT = Path(__file__).resolve().parents[3]
STYLES = REPO_ROOT / "config" / "image-styles.yaml"
TEMPLATE = REPO_ROOT / "prompts" / "acervo_image_brief.txt"


def sync_fields(revision: int = 1) -> dict:
    return {
        "deleted": False, "createdAt": "2026-09-01T00:00:00.000Z",
        "editedAt": "2026-09-01T00:00:00.000Z", "editedBy": "dev", "revision": revision,
    }


def changes() -> dict:
    return {
        "vocabularies": [{"id": "v00000000000001", "language": "es", "definitionLang": "es",
                          "glossLangs": ["en"], "notesLang": "en", **sync_fields()}],
        "topics": [{"id": "t00000000000001", "name": "Nature", **sync_fields()}],
        "lexemes": [
            {"id": "l00000000000001", "language": "es", "headword": "el veneno", "lemma": "veneno",
             "pos": "noun", "status": "inbox", "topicIds": ["t00000000000001"], "notes": [],
             "shortGloss": "venom", **sync_fields()},
            {"id": "l00000000000002", "language": "es", "headword": "retirado", "lemma": "retirado",
             "pos": "adj", "status": "retired", "topicIds": [], "notes": [], **sync_fields()},
            {"id": "l00000000000003", "language": "en", "headword": "venom", "lemma": "venom",
             "pos": "noun", "status": "active", "topicIds": [], "notes": [], **sync_fields()},
        ],
        "senses": [
            {"id": "s00000000000001", "lexemeId": "l00000000000001", "definition": "Fluido tóxico.",
             "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["venom"]}], "domain": None,
             "order": 0, **sync_fields()},
            {"id": "s00000000000002", "lexemeId": "l00000000000001", "definition": "Amargura extrema.",
             "definitionLang": "es", "glosses": [{"lang": "en", "terms": ["bitterness"]}],
             "domain": None, "order": 1, **sync_fields()},
            {"id": "s00000000000003", "lexemeId": "l00000000000002", "definition": "Jubilado.",
             "definitionLang": "es", "glosses": [], "domain": None, "order": 0, **sync_fields()},
            {"id": "s00000000000004", "lexemeId": "l00000000000003", "definition": "Toxic fluid.",
             "definitionLang": "en", "glosses": [], "domain": None, "order": 0, **sync_fields()},
        ],
        "examples": [
            {"id": "e00000000000001", "senseId": "s00000000000001", "text": "Una serpiente inyecta veneno.",
             "translation": "A snake injects venom.", "origin": "llm", **sync_fields()},
            {"id": "e00000000000002", "senseId": "s00000000000001", "text": "El veneno me quemó.",
             "translation": "The venom burned me.", "origin": "attestation", **sync_fields()},
        ],
        "attestations": [],
        "imagePrompts": [],
        "studyStates": [],
    }


def test_ids_are_acervo_shaped_and_stable():
    minted = image_prompt_id("s00000000000001")
    assert len(minted) == ID_LENGTH
    assert minted.isalnum() and minted.islower()
    assert minted == image_prompt_id("s00000000000001")
    assert minted != image_prompt_id("s00000000000002")


def test_a_retry_draws_a_different_seed():
    assert seed_for("s00000000000001", 1) == seed_for("s00000000000001", 1)
    assert seed_for("s00000000000001", 1) != seed_for("s00000000000001", 2)


def test_every_style_is_offered():
    styles = load_styles(STYLES)
    assert [style.id for style in styles.offer()] == [style.id for style in styles.styles]


def test_a_zero_weight_switches_a_style_off():
    styles = load_styles(STYLES)
    weights = {style.id: 0.0 for style in styles.styles}
    for style in styles.styles[:2]:
        weights[style.id] = 1.0
    assert {style.id for style in styles.offer(weights)} == {style.id for style in styles.styles[:2]}


def test_the_style_hints_are_a_shifting_sample():
    """Round 5 sent each style's whole hint as one sentence and it became a lookup table.

    A short sample per lexeme keeps the associations without letting a style be matched on.
    """
    styles = load_styles(STYLES)
    assert all(len(style.when) >= 6 for style in styles.styles)
    clay = styles["claymation"]
    first, second = styles.hints(clay, "lex000000000001"), styles.hints(clay, "lex000000000002")
    assert len(first) == 3 and set(first) <= set(clay.when)
    assert first != second                                     # varies per word
    assert first == styles.hints(clay, "lex000000000001")       # but is stable for one word

    request = build_request(build_articles(changes(), "es")[0], styles)
    assert all(len(item["suits"]) == 3 for item in request["styles"])


def test_the_style_that_authored_scenes_is_gone():
    """Round 1: leaded glass implies a building, so it kept relocating the scene to a church."""
    assert "stained-glass" not in load_styles(STYLES)


def test_only_the_senses_worth_drawing_are_in_scope():
    articles = build_articles(changes(), "es")
    assert [article.headword for article in articles] == ["el veneno"]      # retired is out, en is out
    assert len(articles[0].senses) == 2


def test_the_learners_own_sentence_is_the_anchor():
    articles = build_articles(changes(), "es")
    anchor = articles[0].senses[0].anchor
    assert anchor["id"] == "e00000000000002"                                 # attestation beats llm
    assert articles[0].senses[1].anchor is None


def test_the_owners_topics_do_not_steer_the_picture():
    """Topics are the owner's filing system, not a fact about the word."""
    request = build_request(build_articles(changes(), "es")[0], load_styles(STYLES))
    assert "topics" not in request


def test_an_anchor_from_another_sense_is_dropped():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles, patch={1: {"anchorExampleId": "e00000000000002"}})
    briefs = parse_reply(text, article, offered)
    assert briefs[1].anchor_example_id is None      # that example belongs to sense one


def test_an_anchor_from_this_sense_is_kept():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles, patch={0: {"anchorExampleId": "e00000000000002"}})
    assert parse_reply(text, article, offered)[0].anchor_example_id == "e00000000000002"


def test_the_request_offers_every_style_and_marks_the_anchor():
    styles = load_styles(STYLES)
    request = build_request(build_articles(changes(), "es")[0], styles)
    assert len(request["senses"]) == 2
    assert len(request["styles"]) == len(styles.styles)
    marked = [item for item in request["senses"][0]["examples"] if item["isAnchor"]]
    assert [item["id"] for item in marked] == ["e00000000000002"]


def _reply(article, styles, **overrides) -> tuple[str, tuple[str, ...]]:
    offered = tuple(style.id for style in styles.offer())
    senses = [
        {"senseId": sense.id, "styleId": offered[index], "anchorExampleId": None,
         "situation": "A specific thing happening.", "subject": "the thing",
         "brief": "A scene.", "refused": False, "refusalReason": None}
        for index, sense in enumerate(article.senses)
    ]
    for index, patch in overrides.get("patch", {}).items():
        senses[index].update(patch)
    return json.dumps({"senses": senses}), offered


def test_a_well_formed_reply_parses():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles)
    briefs = parse_reply(text, article, offered)
    assert [item.sense_id for item in briefs] == [sense.id for sense in article.senses]
    assert all(not item.refused for item in briefs)
    assert briefs[0].subject == "the thing"
    assert briefs[0].situation == "A specific thing happening."


def test_a_fenced_reply_still_parses():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles)
    assert len(parse_reply(f"```json\n{text}\n```", article, offered)) == 2


def test_an_invented_style_is_refused():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles, patch={0: {"styleId": "no-such-style"}})
    with pytest.raises(ValueError, match="not a style"):
        parse_reply(text, article, offered)


def test_a_skipped_sense_is_refused():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles)
    payload = json.loads(text)
    payload["senses"] = payload["senses"][:1]
    with pytest.raises(ValueError, match="skipped"):
        parse_reply(json.dumps(payload), article, offered)


def test_a_refusal_needs_no_style_or_brief():
    styles = load_styles(STYLES)
    article = build_articles(changes(), "es")[0]
    text, offered = _reply(article, styles, patch={
        1: {"refused": True, "styleId": "", "brief": None, "refusalReason": "hate insignia"}})
    briefs = parse_reply(text, article, offered)
    assert briefs[1].refused and briefs[1].refusal_reason == "hate insignia"


def test_the_composed_prompt_carries_the_style_and_bans_text():
    styles = load_styles(STYLES)
    prompt = compose("A snake's fang, one glowing droplet.", styles["oil-painting"])
    assert "impasto oil" in prompt
    assert FRAME in prompt
    assert "no letters" in prompt.lower()


def test_the_prompt_version_moves_when_the_styles_do(tmp_path: Path):
    styles = load_styles(STYLES)
    first = prompt_version(TEMPLATE, styles.digest)
    assert first != prompt_version(TEMPLATE, "deadbeef0000")
    other = tmp_path / "template.txt"
    other.write_text("different", encoding="utf-8")
    assert first != prompt_version(other, styles.digest)


def test_a_drawn_sense_is_not_planned_again(tmp_path: Path):
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    assert len(plan(articles, store)) == 2

    store.image_path(image_prompt_id("s00000000000001")).write_bytes(b"webp")
    assert [job.sense_id for job in plan(articles, store)] == ["s00000000000002"]

    # Deleting the picture is how a rejection is expressed, and it comes back into the plan.
    store.image_path(image_prompt_id("s00000000000001")).unlink()
    assert len(plan(articles, store)) == 2


def test_a_sense_the_graph_already_holds_an_image_for_is_skipped(tmp_path: Path):
    payload = changes()
    payload["imagePrompts"] = [{
        "id": "p00000000000001", "lexemeId": "l00000000000001", "senseId": "s00000000000001",
        "prompt": "A scene.", "styleId": "oil-painting", "seed": 1, "modelId": "m",
        "promptVersion": "v", "imageRef": "images/l1/p1.webp", "imageModelId": "m",
        **sync_fields(),
    }]
    assert len(plan(build_articles(payload, "es"), Store(tmp_path))) == 1


def test_each_model_has_its_own_bucket():
    """Measured: about one image per minute PER MODEL, so two models run at twice the rate."""
    from acervo.models.pacing import ModelPool
    pool = ModelPool([("lite", 1), ("flash", 1)])
    assert sorted([pool.acquire(), pool.acquire()]) == ["flash", "lite"]
    assert pool.gates["lite"].delay() > 0 and pool.gates["flash"].delay() > 0


def test_a_quota_pause_is_per_model_not_pool_wide():
    from acervo.models.pacing import ModelPool
    pool = ModelPool([("lite", 60), ("flash", 60)])
    pool.penalise("lite")
    assert pool.gates["lite"].delay() > 0
    assert pool.acquire() == "flash"      # the other model keeps working


def test_the_definition_is_labelled_with_its_own_language():
    """An English gloss carries metaphors the original word does not: `estar fundado` is not about
    earth, but "to be grounded in" is, and the picture followed the gloss."""
    request = build_request(build_articles(changes(), "es")[0], load_styles(STYLES))
    sense = request["senses"][0]
    assert sense["definitionLang"] == "es"
    assert sense["definition"] == "Fluido tóxico."
    assert sense["glosses"] == [{"lang": "en", "terms": ["venom"]}]


def test_a_refusal_is_not_planned_again(tmp_path: Path):
    """§06: declining a sense is a finished outcome. Re-planning it spends a call to rediscover it."""
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    assert len(plan(articles, store)) == 2

    store.write(store.refusal_path(image_prompt_id("s00000000000001")),
                {"refusalReason": "sexualised imagery"})
    assert [job.sense_id for job in plan(articles, store)] == ["s00000000000002"]
    assert len(plan(articles, store, redo=True)) == 2        # unless asked


def test_a_provider_block_is_not_planned_again(tmp_path: Path):
    """A blocked prompt is terminal. Ten senses were lost to a text 429 and one to an image block;
    only the first kind should come back."""
    articles = build_articles(changes(), "es")
    store = Store(tmp_path)
    blocked = image_prompt_id("s00000000000001")
    store.write(store.record_path(blocked), {"id": blocked, "imageRef": None, "blocked": True})
    transient = image_prompt_id("s00000000000002")
    store.write(store.record_path(transient),
                {"id": transient, "imageRef": None, "failureReason": "429 RESOURCE_EXHAUSTED"})

    assert [job.sense_id for job in plan(articles, store)] == ["s00000000000002"]
    assert len(plan(articles, store, redo=True)) == 2


def test_the_brief_writer_waits_out_a_quota_refusal():
    """A text 429 used to lose every sense of that lexeme outright."""
    from acervo.jobs.images.brief import BriefWriter

    class Flaky(BriefWriter):
        def __init__(self):                    # no client, no template read
            self.model = "test"
            self.calls = 0

        def _write_once(self, article):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return ["ok"], {"model": self.model}

    writer, slept = Flaky(), []
    briefs, _ = writer.write(build_articles(changes(), "es")[0], wait=slept.append)
    assert briefs == ["ok"] and writer.calls == 3
    assert slept == [15.0, 30.0]               # and it backs off rather than hammering


def test_a_brief_failure_that_is_not_quota_is_raised_at_once():
    from acervo.jobs.images.brief import BriefWriter

    class Broken(BriefWriter):
        def __init__(self):
            self.model = "test"
            self.calls = 0

        def _write_once(self, article):
            self.calls += 1
            raise ValueError("the brief writer did not return JSON")

    writer = Broken()
    with pytest.raises(ValueError):
        writer.write(build_articles(changes(), "es")[0], wait=lambda _: None)
    assert writer.calls == 1


def _stored(store: Store, sense_id: str, **overrides) -> str:
    identifier = image_prompt_id(sense_id)
    record = {"id": identifier, "senseId": sense_id, "imageRef": f"images/x/{identifier}.webp"}
    record.update(overrides)
    store.write(store.record_path(identifier), record)
    return identifier


def test_a_consistent_run_directory_verifies(tmp_path: Path):
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)
    identifier = _stored(store, "s00000000000001")
    store.image_path(identifier).write_bytes(b"webp")
    report = verify(store)
    assert report.ok and report.drawn == 1 and report.images == 1


def test_verify_catches_what_would_break_the_import(tmp_path: Path):
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)

    _stored(store, "s00000000000001")                      # claims an image that is not there
    orphan = _stored(store, "s00000000000002", imageRef=None)
    store.image_path(orphan).write_bytes(b"webp")          # image whose record claims none
    store.image_path("zzzzzzzzzzzzzzz").write_bytes(b"webp")  # image with no record at all
    store.write(store.record_path("nnnnnnnnnnnnnnn"),
                {"id": "nnnnnnnnnnnnnnn", "senseId": "s00000000000003", "imageRef": None})

    report = verify(store)
    assert not report.ok
    assert set(report.problems) == {
        "record claims an image that is not on disk",
        "image on disk whose record claims none",
        "image with no record",
        "id is not derived from its senseId",
    }


def test_a_blocked_record_is_not_a_problem(tmp_path: Path):
    """`snort` was blocked by the provider. A sense with no image is complete, not a fault."""
    from acervo.jobs.images.verify import verify
    store = Store(tmp_path)
    _stored(store, "s00000000000001", imageRef=None, blocked=True, failureReason="IMAGE_SAFETY")
    report = verify(store)
    assert report.ok and report.blocked == 1 and report.drawn == 0

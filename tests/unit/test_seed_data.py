"""The disposable demonstration vocabulary, and the one way it reaches an account."""

from collections import Counter

from acervo.seed_data import demo_records, record_id


def records():
    return demo_records("owner0000000001")


def by_collection(name):
    return [record for collection, record in records() if collection == name]


def test_demo_ids_are_stable_owner_scoped_and_of_the_one_id_shape():
    first = record_id("owner0000000001", "lexemes", "balsa")
    assert first == record_id("owner0000000001", "lexemes", "balsa")
    assert first != record_id("owner0000000002", "lexemes", "balsa")
    assert len(first) == 15
    assert first.isalnum() and first == first.lower()

    identifiers = [record["id"] for _, record in records()]
    assert len(set(identifiers)) == len(identifiers)
    assert all(len(i) == 15 and i.isalnum() and i.islower() for i in identifiers)


def test_demo_graph_covers_every_core_collection():
    counts = Counter(collection for collection, _ in records())
    assert set(counts) == {
        "vocabularies", "topics", "lexemes", "senses", "attestations", "examples",
        "image_prompts", "study_states",
    }
    assert counts["topics"] == 13
    assert counts["lexemes"] == 15
    assert any(r["language"] == "zh-Hans" and r["reading"] for r in by_collection("lexemes"))
    assert any(len(r["glosses"]) > 1 for r in by_collection("senses"))
    assert any(r["status"] == "inbox" for r in by_collection("lexemes"))
    # Three vocabulary languages, so the language switcher has something to switch between.
    assert {r["language"] for r in by_collection("lexemes")} == {"es", "en", "zh-Hans"}


def test_every_seeded_word_has_a_vocabulary_behind_it():
    """A word in a language the account is not configured for cannot be captured or glossed."""
    configured = {r["language"]: r for r in by_collection("vocabularies")}
    assert {r["language"] for r in by_collection("lexemes")} <= set(configured)
    assert all(r["gloss_langs"] for r in configured.values())
    assert configured["zh-Hans"]["gloss_langs"] == ["ru", "en"]
    assert all(r["notes_lang"] for r in configured.values())
    assert configured["zh-Hans"]["notes_lang"] == "ru"


def test_starter_topics_carry_an_explicit_rail_order():
    orders = [topic["topic_order"] for topic in by_collection("topics")]
    assert orders == list(range(len(orders)))


def test_examples_keep_lineage_and_matched_forms_consistent():
    senses = {record["id"]: record for record in by_collection("senses")}
    attestations = {record["id"]: record for record in by_collection("attestations")}
    for example in by_collection("examples"):
        if example["origin"] == "attestation":
            assert example["source_attestation"]
        if example["source_attestation"]:
            source = attestations[example["source_attestation"]]
            assert source["lexeme"] == senses[example["sense"]]["lexeme"]
        if example["matched_form"]:
            assert example["matched_form"] in example["text"]
        if example["matched_translation_form"]:
            assert example["matched_translation_form"] in example["translation"]
        assert bool(example["translation"]) == bool(example["translation_lang"])
        if example["video_title"] or example["video_start"]:
            assert example["video_ref"]


def test_demo_graph_exercises_the_fields_the_interface_shows():
    lexemes = by_collection("lexemes")
    assert any(record["ipa"] for record in lexemes)
    assert any(record["notes"] for record in lexemes)
    examples = by_collection("examples")
    assert any(record["video_title"] and record["video_start"] for record in examples)
    assert any(record["audio_ref"] for record in examples)
    assert any(record["note"] for record in examples)
    assert by_collection("image_prompts")


def test_seeding_writes_the_whole_corpus_through_the_graph_and_numbers_every_record(tmp_path, monkeypatch):
    """Through the service layer, not over HTTP: it needs no password, because there is no superuser
    to have one."""
    monkeypatch.setenv("ACERVO_DB_PATH", str(tmp_path / "acervo.db"))

    from acervo import admin
    from acervo.repository import accounts, graph
    from acervo.repository.session import open_database
    from acervo.settings import settings

    configured = settings()
    open_database(configured.database_path)
    owner = accounts.create("learner@account.example.com", "correct-horse-battery")

    assert admin.seed(configured, "learner@account.example.com") == 0
    pulled = graph.pull(owner["id"], 0)
    counts = Counter(collection for collection, _ in records())
    assert len(pulled["changes"]["lexemes"]) == counts["lexemes"]
    assert len(pulled["changes"]["imagePrompts"]) == counts["image_prompts"]
    # Numbered by the one allocator, which is what makes a record visible to a cursor pull at all.
    assert all(
        record["revision"] > 0 for group in pulled["changes"].values() for record in group
    )
    assert pulled["cursor"] == sum(len(group) for group in pulled["changes"].values())


def test_seeding_twice_skips_what_the_account_already_holds(tmp_path, monkeypatch):
    """The graph route is not the old per-record create: re-posting a stored record at revision zero
    is a stale write, not a no-op."""
    monkeypatch.setenv("ACERVO_DB_PATH", str(tmp_path / "acervo.db"))

    from acervo import admin
    from acervo.repository import accounts, graph
    from acervo.repository.session import open_database
    from acervo.settings import settings

    configured = settings()
    open_database(configured.database_path)
    owner = accounts.create("learner@account.example.com", "correct-horse-battery")
    admin.seed(configured, "learner@account.example.com")
    before = graph.pull(owner["id"], 0)["cursor"]

    assert admin.seed(configured, "learner@account.example.com") == 0
    assert graph.pull(owner["id"], 0)["cursor"] == before


def test_seeding_an_account_that_does_not_exist_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ACERVO_DB_PATH", str(tmp_path / "acervo.db"))
    from acervo import admin
    from acervo.settings import settings

    assert admin.seed(settings(), "nobody@account.example.com") == 2
    assert "Create one first" in capsys.readouterr().err

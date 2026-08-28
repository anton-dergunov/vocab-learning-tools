from scripts.seed_acervo_demo import demo_records, record_id


def test_demo_ids_are_stable_owner_scoped_and_pocketbase_compatible():
    first = record_id("owner000000001", "lexemes", "balsa")
    assert first == record_id("owner000000001", "lexemes", "balsa")
    assert first != record_id("owner000000002", "lexemes", "balsa")
    assert len(first) == 15
    assert first.isalnum() and first == first.lower()


def test_demo_graph_covers_every_core_collection():
    records = demo_records("owner000000001")
    collections = {collection for collection, _ in records}
    assert collections == {
        "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"
    }
    assert sum(collection == "lexemes" for collection, _ in records) == 5
    assert any(
        collection == "lexemes" and record["language"] == "zh-Hans" and record["reading"]
        for collection, record in records
    )
    assert any(
        collection == "senses" and len(record["glosses"]) > 1
        for collection, record in records
    )

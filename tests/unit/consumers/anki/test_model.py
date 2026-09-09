from anki.collection import Collection
import pytest

from acervo.consumers.anki.model import (
    FIELD_NAMES,
    MODEL_NAME,
    ModelMismatchError,
    create_notetype,
    require_notetype,
)


def test_create_and_require_exact_acervo_notetype(tmp_path):
    collection = Collection(str(tmp_path / "collection.anki2"))
    try:
        created = create_notetype(collection, "css")
        assert created["name"] == MODEL_NAME
        assert [field["name"] for field in created["flds"]] == list(FIELD_NAMES)
        assert require_notetype(collection, "css")["id"] == created["id"]
    finally:
        collection.close()


def test_require_refuses_template_drift(tmp_path):
    collection = Collection(str(tmp_path / "collection.anki2"))
    try:
        notetype = create_notetype(collection, "css")
        notetype["tmpls"][0]["qfmt"] = "{{Sentence}} changed"
        collection.models.update_dict(notetype)
        with pytest.raises(ModelMismatchError, match="differs"):
            require_notetype(collection, "css")
    finally:
        collection.close()

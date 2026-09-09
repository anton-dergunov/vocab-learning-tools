"""The catalogue is data, so what can go wrong with it is a schema question.

`models/catalogue.json` is tracked and public. Two of these tests are about that rather than about
correctness: no row may carry a credential, and no `baseUrl` may interpolate one.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from acervo.models.catalogue import (
    CATALOGUE_PATH,
    CatalogueError,
    Row,
    available,
    base_url,
    load_catalogue,
    reason,
)

SHIPPED = load_catalogue()


def written(tmp_path, *providers):
    path = tmp_path / "catalogue.json"
    path.write_text(
        json.dumps({"version": 1, "note": "test", "providers": list(providers)}), encoding="utf-8"
    )
    return path


def a_row(**overrides):
    return {
        "id": "row",
        "label": "Row",
        "kinds": ["text"],
        "litellm": {"text": "gemini/x"},
        "keyEnv": "A_KEY",
        **overrides,
    }


def test_every_shipped_row_names_a_model_or_an_adapter_for_every_kind_it_declares():
    """Plan 04's "assert every row has one", in the form a row with three kinds actually needs.

    A scalar `litellm` field could not have said this: a row serving text, image and audio names
    three different models, and Cloudflare reaches two of those three through the adapter.
    """
    for row in SHIPPED:
        for kind in row.kinds:
            assert (kind in row.litellm) != (kind in row.adapter), (row.id, kind)
            assert row.model_for(kind)


def test_the_shipped_catalogue_carries_no_credential():
    """It ships the list, never a secret. Variable names only, and nothing key-shaped."""
    text = CATALOGUE_PATH.read_text(encoding="utf-8")
    for row in SHIPPED:
        for name in row.secret_names:
            assert name == name.upper(), f"{row.id}: {name} does not look like a variable name"
    assert "sk-" not in text
    assert "AIza" not in text  # a Google API key's prefix


@pytest.mark.parametrize("row", SHIPPED.rows, ids=lambda row: row.id)
def test_a_shipped_base_url_never_interpolates_a_key(row):
    assert row.keyEnv is None or f"{{{row.keyEnv}}}" not in (row.baseUrl or "")


def test_ids_are_unique(tmp_path):
    with pytest.raises(CatalogueError, match="share the id"):
        load_catalogue(written(tmp_path, a_row(), a_row()))


def test_a_kind_routed_through_both_litellm_and_an_adapter_is_refused(tmp_path):
    path = written(tmp_path, a_row(adapter={"text": "cloudflare"}, models={"text": "@cf/x"}))
    with pytest.raises(CatalogueError, match="both LiteLLM and an adapter"):
        load_catalogue(path)


def test_a_kind_with_no_route_at_all_is_refused(tmp_path):
    path = written(tmp_path, a_row(kinds=["text", "image"]))
    with pytest.raises(CatalogueError, match="neither a model nor an adapter"):
        load_catalogue(path)


def test_a_base_url_that_embeds_the_key_is_refused(tmp_path):
    """The locked contract as an assertion: a key does not belong in a URL."""
    path = written(tmp_path, a_row(baseUrl="https://x/{A_KEY}/v1"))
    with pytest.raises(CatalogueError, match="interpolates its key"):
        load_catalogue(path)


def test_a_base_url_may_only_interpolate_what_the_row_requires(tmp_path):
    path = written(tmp_path, a_row(baseUrl="https://x/{ACCOUNT}/v1"))
    with pytest.raises(CatalogueError, match="which it does not require"):
        load_catalogue(path)


def test_a_base_url_is_filled_in_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ACCOUNT", "abc123")
    catalogue = load_catalogue(
        written(tmp_path, a_row(requires=["ACCOUNT"], baseUrl="https://x/{ACCOUNT}/v1"))
    )
    assert base_url(catalogue.find("row")) == "https://x/abc123/v1"


def test_reason_names_the_first_unmet_requirement_and_never_a_value(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "a-token-value")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    row = SHIPPED.find("cloudflare")
    assert reason(row) == "CLOUDFLARE_ACCOUNT_ID is not set"
    assert "a-token-value" not in reason(row)

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    assert available(row)


def test_a_blank_variable_counts_as_unset(monkeypatch):
    """`compose.yaml` passes `GEMINI_API_KEY: "${GEMINI_API_KEY:-}"`, so empty is the common case."""
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert reason(SHIPPED.find("gemini-free")) == "GEMINI_API_KEY is not set"


def test_vertex_asks_for_application_default_credentials_rather_than_a_key(monkeypatch, tmp_path):
    """LiteLLM has no Vertex express-key path, so `VERTEX_API_KEY` is not what makes it available."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    monkeypatch.setenv("VERTEX_API_KEY", "a-key-that-means-nothing-now")
    monkeypatch.setattr("acervo.models.catalogue._ADC_FILE", tmp_path / "absent.json")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    row = SHIPPED.find("vertex")
    assert reason(row) == "Google application default credentials are not configured"

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "service-account.json"))
    assert available(row)


def test_serving_keeps_catalogue_order():
    """Row order is the default preference order, so it is load-bearing rather than cosmetic."""
    assert [row.id for row in SHIPPED.serving("text")][:3] == ["gemini-free", "vertex", "cloudflare"]
    assert [row.id for row in SHIPPED.serving("audio")] == ["gemini-free", "cloudflare", "openai"]


def test_params_are_data_rather_than_code():
    """Vertex's thinking level used to be an `if provider == "vertex"` in the call path."""
    assert SHIPPED.find("vertex").params_for("text") == {
        "reasoning_effort": "medium",
        "vertex_location": "global",
    }
    assert SHIPPED.find("gemini-free").params_for("text") == {}


def test_a_row_lists_every_variable_it_reads_so_redaction_can_be_built_from_it():
    assert SHIPPED.find("cloudflare").secret_names == (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
    )
    # Including the ones it passes as call arguments: Vertex's project id came back inside a 404
    # from Google, and it is a deployment detail this repository does not publish.
    assert "ACERVO_VERTEX_PROJECT" in SHIPPED.find("vertex").secret_names
    assert Row(id="x", label="X", kinds=("text",)).secret_names == ()


def test_a_row_may_not_pass_its_key_as_an_ordinary_call_argument(tmp_path):
    """The same rule as `baseUrl`: a credential travels as a credential, not as a parameter."""
    path = written(tmp_path, a_row(passes={"api_key": "A_KEY"}))
    with pytest.raises(CatalogueError, match="passes its key"):
        load_catalogue(path)


def test_reading_the_catalogue_does_not_drag_litellm_in():
    """`acervo.models.pacing` is what the file ingestion and the worker image import, and the
    worker image deliberately does not install LiteLLM. The lazy import in `call.py` is what makes
    that work, and a stray module-level `import litellm` would break it silently — everything would
    still pass here, and the worker would fail on the machine."""
    probe = (
        "import sys, acervo.models.pacing\n"
        "from acervo.models import load_catalogue, available\n"
        "load_catalogue()\n"
        "assert 'litellm' not in sys.modules, sorted(n for n in sys.modules if 'litellm' in n)\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, capture_output=True)

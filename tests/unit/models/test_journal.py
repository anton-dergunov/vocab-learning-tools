"""What the model layer writes down, and what it must never write down.

The regression this exists for took two deployments to find because nothing recorded that a chain
had walked nine pairs and been refused by every one for the same reason. The value of the file is
almost entirely in the refusal line — the one that says *what came back* — so that is what these
assert hardest.
"""

from __future__ import annotations

import logging

import pytest

from acervo.models import chain, journal
from acervo.models.catalogue import load_catalogue
from acervo.models.errors import ChainExhausted, ProviderUnavailable
from acervo.models.results import Answer, TextResult

SHIPPED = load_catalogue()


@pytest.fixture
def written(monkeypatch, caplog):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-not-a-real-key-000")
    caplog.set_level(logging.INFO, logger=journal.LOGGER)
    return caplog


def answer() -> TextResult:
    return TextResult(text="{}", parsed={},
                      answer=Answer(provider_id="gemini-free", model="m", seconds=0.1, cost_usd=None))


def test_a_pair_that_answered_is_recorded_with_its_name_and_its_cost_in_time(written):
    chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
               lambda candidate: answer(), chain.stamped, caller="brief")
    line = written.text
    assert "brief" in line and "gemini-free" in line and "ok in" in line


def test_a_refusal_records_why_the_next_pair_is_being_asked(written):
    """The line that would have ended the hunt in one reading rather than two deployments."""
    def ask(candidate):
        raise ProviderUnavailable(
            "unusable", "empty brief for sense s1 — got {\"senses\":[{\"senseId\":\"s1\"}]}",
            provider_id=candidate.row.id, model=candidate.model,
        )

    with pytest.raises(ChainExhausted):
        chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
                   ask, chain.stamped, caller="brief")
    assert "unusable" in written.text
    assert "senseId" in written.text          # what actually came back
    assert "exhausted after 1 attempt" in written.text


def test_a_key_a_provider_echoed_back_never_reaches_the_log(written):
    """`ProviderError` redacts its detail at construction, and this leans on that rather than
    repeating it — a message cleaned only on its way to a log has a path that skips the cleaning."""
    def ask(candidate):
        raise ProviderUnavailable(
            "refused", "rejected key AIzaSy-not-a-real-key-000",
            provider_id=candidate.row.id, model=candidate.model,
        )

    with pytest.raises(ChainExhausted):
        chain.walk("text", [("gemini-free", "gemini/gemini-3.1-flash-lite")], SHIPPED,
                   ask, chain.stamped, caller="brief")
    assert "AIzaSy" not in written.text
    assert "«redacted»" in written.text


def test_an_excerpt_is_bounded_and_single_line():
    assert journal.excerpt("a\n  b\tc") == "a b c"
    long = journal.excerpt("x" * (journal.EXCERPT + 50))
    assert len(long) == journal.EXCERPT + 1 and long.endswith("…")


# ── the binding: where the lines actually land ──────────────────────────────


def test_the_file_is_opened_once_and_creates_its_directory(tmp_path, monkeypatch):
    """Idempotent because `create_app` runs more than once in a suite, and a second handler on the
    same logger writes every line twice — which reads as a retry that never happened."""
    from acervo.services.models import open_call_log
    from acervo.settings import Settings

    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-not-a-real-key-000")
    path = tmp_path / "nested" / "model-calls.log"
    settings = Settings(ACERVO_CALL_LOG_PATH=str(path))
    logger = logging.getLogger(journal.LOGGER)
    before = list(logger.handlers)
    try:
        open_call_log(settings)
        open_call_log(settings)
        assert sum(getattr(h, "acervo_call_log", False) for h in logger.handlers) == 1

        journal.passed("brief", "gemini-free", "m", "unusable",
                       'got {"senses":[{"senseId":"s1"}]} AIzaSy-not-a-real-key-000')
        for handler in logger.handlers:
            handler.flush()
        written = path.read_text(encoding="utf-8")
    finally:
        for handler in list(logger.handlers):
            if handler not in before:
                handler.close()
                logger.removeHandler(handler)

    assert "brief gemini-free:m unusable" in written
    assert "senseId" in written


def test_no_path_means_no_file_and_no_complaint(tmp_path):
    """A laptop run wants the lines emitted and nobody listening. Not an error, not a warning."""
    from acervo.services.models import open_call_log
    from acervo.settings import Settings

    logger = logging.getLogger(journal.LOGGER)
    before = list(logger.handlers)
    open_call_log(Settings(ACERVO_CALL_LOG_PATH=""))
    assert list(logger.handlers) == before

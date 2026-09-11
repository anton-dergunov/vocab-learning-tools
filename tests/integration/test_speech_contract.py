"""The pinned retrieval contract, against a service that is actually running.

Everything about how the client *parses* a response is in `tests/unit/clips/test_corpus.py`, which
runs offline against `fixtures/search-es-picar.json` — a response recorded from a real service. What
only a live call can tell you is the half a recording cannot: that the routes still exist, that the
fields Acervo reads are still named what they were named, and that the pinned version in
`deploy/acervo/speech/pin.json` still speaks the contract this client was written against.

That is deliberately *not* a check against a copy of the service's `openapi-v1.json`. The spec is
generated and snapshotted in the retrieval repository, where one test turns a renamed field into a
failing pull request; a 117 KB copy here would have to be re-committed on every pin bump, would
produce a diff nobody reads, and would still only assert what this file asserts against the thing
actually serving.

    ACERVO_SPEECH_URL=http://localhost:8000/api/v1 RUN_SPEECH_CONTRACT_TESTS=true \
      .venv/bin/python -m pytest tests/integration/test_speech_contract.py -v

Against the laptop corpus (`uv run speech-retrieval serve` in the retrieval checkout), or against
the deployment through a shell on the internal compose network.
"""

from __future__ import annotations

import os

import pytest

from acervo.clips.corpus import Corpus

pytestmark = pytest.mark.integration

# A common Spanish verb with more than one sense, so a thin corpus still answers.
QUERY_LANGUAGE = "es"
QUERY = "picar"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    if os.environ.get("RUN_SPEECH_CONTRACT_TESTS") != "true":
        pytest.skip("set RUN_SPEECH_CONTRACT_TESTS=true to test against a running corpus")
    url = os.environ.get("ACERVO_SPEECH_URL")
    if not url:
        pytest.skip("set ACERVO_SPEECH_URL to the running corpus's /api/v1 root")
    return Corpus(url)


def test_status_still_says_what_can_be_searched(corpus):
    """`indexedLanguages` is the field that decides whether a word was consulted at all, so a rename
    would silently make every word look unsearchable and the sweep would never finish."""
    status = corpus.status()
    assert isinstance(status["ready"], bool)
    assert isinstance(status["indexedLanguages"], tuple)
    if status["ready"]:
        assert status["indexedLanguages"], "a ready corpus indexes at least one language"
        assert status["builtAt"], "`built_at` is the rescan predicate §2.8 leaves available"


def test_search_still_returns_candidates_shaped_the_way_the_client_reads_them(corpus):
    if QUERY_LANGUAGE not in corpus.status()["indexedLanguages"]:
        pytest.skip(f"this corpus does not index {QUERY_LANGUAGE}")

    found = corpus.search(QUERY_LANGUAGE, QUERY)
    assert found, f"a corpus indexing {QUERY_LANGUAGE} should have something for {QUERY!r}"
    assert len(found) <= 20

    for candidate in found:
        # The three a clip cannot exist without: the segment it names, the text it quotes, and the
        # video reference every other clip field hangs on.
        assert candidate.segment_id and candidate.sentence and candidate.video_url
        # The guarantee `Example.matchedForm` rests on, checked across the service boundary rather
        # than trusted. Verbatim: untrimmed, uncased, un-normalised.
        if candidate.matched_surface:
            assert candidate.matched_surface in candidate.sentence
            assert candidate.sentence[candidate.char_start:candidate.char_end] == candidate.matched_surface
        assert candidate.end_second > candidate.start_second
        assert candidate.clip_start <= candidate.clip_end


def test_one_segment_appears_once_however_often_the_word_does(corpus):
    if QUERY_LANGUAGE not in corpus.status()["indexedLanguages"]:
        pytest.skip(f"this corpus does not index {QUERY_LANGUAGE}")
    found = corpus.search(QUERY_LANGUAGE, QUERY)
    ids = [candidate.segment_id for candidate in found]
    assert len(ids) == len(set(ids))


def test_a_query_the_corpus_cannot_accept_is_rejected_rather_than_failing(corpus):
    """Over five tokens. The service refuses this by design, and `find_clips` reads that refusal as
    "consulted, and this query will never get shorter" rather than as a failure to retry."""
    from acervo.clips.corpus import CorpusError

    with pytest.raises(CorpusError) as raised:
        corpus.search(QUERY_LANGUAGE, "uno dos tres cuatro cinco seis siete")
    assert raised.value.reason == "rejected"

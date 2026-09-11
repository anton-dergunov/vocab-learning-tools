"""The allow-listed window onto the corpus, and the token that must never come back through it."""

from __future__ import annotations

import httpx
import pytest

SPEECH_URL = "http://speech-retrieval:8000/api/v1"
OPERATOR_TOKEN = "operator-token-nobody-should-see"


class Upstream:
    """The retrieval service, answering over a real `httpx` call path and recording what it saw."""

    def __init__(self) -> None:
        self.answer: object = {"ok": True}
        self.status = 200
        self.seen: list[httpx.Request] = []

    def request(self, method, url, *, params=None, json=None, headers=None, timeout=None, **kwargs):
        request = httpx.Request(method, url, params=params, json=json, headers=headers)
        self.seen.append(request)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return httpx.Response(self.status, json=self.answer, request=request)


@pytest.fixture
def upstream(server, monkeypatch) -> Upstream:
    from acervo.services import speech

    stub = Upstream()
    monkeypatch.setattr(speech.httpx, "request", stub.request)
    monkeypatch.setattr(server.settings, "speech_url", SPEECH_URL)
    monkeypatch.setattr(server.settings, "speech_operator_token", OPERATOR_TOKEN)
    return stub


# ── reading ─────────────────────────────────────────────────────────────────


def test_the_corpus_body_comes_back_verbatim_rather_than_in_acervos_envelope(server, upstream):
    """The packaged typed client is pointed at this proxy and reads the corpus's own shapes, so
    rewrapping would mean maintaining a second copy of its response types in two languages."""
    upstream.answer = {"ready": True, "indexed_languages": ["es"], "videos": 251}
    answer = server.get("/speech/status")

    assert answer.status_code == 200
    assert answer.json() == {"ready": True, "indexed_languages": ["es"], "videos": 251}
    assert "data" not in answer.json()


def test_a_search_forwards_the_corpuss_own_parameters(server, upstream):
    """Acervo does not second-guess them: they are that service's contract and it refuses what it
    will not serve, so a second validator here would be one more thing to keep in step."""
    server.get("/speech/search?language=es&q=picar&match_mode=auto&limit=20")
    sent = upstream.seen[0]
    assert sent.url.path == "/api/v1/search"
    assert dict(sent.url.params) == {
        "language": "es", "q": "picar", "match_mode": "auto", "limit": "20"
    }


def test_a_clip_is_fetched_by_the_segment_the_stored_example_names(server, upstream):
    server.get("/speech/clips/seg_fafe38592cc31df5c430")
    assert upstream.seen[0].url.path == "/api/v1/clips/seg_fafe38592cc31df5c430"


def test_the_corpuss_own_error_is_passed_through_with_its_status(server, upstream):
    """The packaged client raises its typed error from this body, so flattening it would lose the
    code the interface reads."""
    upstream.status = 404
    upstream.answer = {"error": {"code": "segment_not_found", "message": "Segment was not found"},
                       "request_id": "9c93f7ad"}
    answer = server.get("/speech/clips/seg_gone")

    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "segment_not_found"


def test_an_unreachable_corpus_is_acervos_own_refusal(server, upstream):
    """The one case the corpus cannot answer for itself, so Acervo answers in its own vocabulary."""
    upstream.answer = httpx.ConnectError("no route to host")
    answer = server.get("/speech/status")
    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "corpus_unreachable"


def test_a_deployment_with_no_corpus_says_so(server):
    answer = server.get("/speech/status")
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "corpus_unconfigured"


# ── the operator token ──────────────────────────────────────────────────────


def test_reading_the_corpus_carries_no_token_at_all(server, upstream):
    server.get("/speech/status")
    server.get("/speech/search?language=es&q=picar")
    server.get("/speech/channels")
    for sent in upstream.seen:
        assert "authorization" not in {name.lower() for name in sent.headers}


def test_changing_a_channel_carries_the_token_server_side(server, upstream):
    server.post("/speech/channels/es/luzu-tv/disable", {})
    assert upstream.seen[0].headers["authorization"] == f"Bearer {OPERATOR_TOKEN}"


def test_it_never_returns_the_operator_token(server, upstream):
    """The token goes out in one header and comes back in nothing, in the shape of
    `test_it_never_returns_a_key_or_how_a_provider_is_reached`: the whole value is absent from the
    whole response body."""
    upstream.answer = {"channels": [{"id": "luzu-tv", "enabled": False}]}
    for answer in (
        server.get("/speech/status"),
        server.get("/speech/statistics"),
        server.get("/speech/channels"),
        server.get("/speech/search?language=es&q=picar"),
        server.post("/speech/channels/es/luzu-tv/enable", {}),
        server.post("/speech/channels/es/luzu-tv/disable", {}),
    ):
        assert OPERATOR_TOKEN not in answer.text
        assert SPEECH_URL not in answer.text      # nor where the corpus is, which is also not the client's

    # And it left this process exactly once per mutating call, as a header and never as a parameter.
    carried = [sent for sent in upstream.seen if "authorization" in {n.lower() for n in sent.headers}]
    assert len(carried) == 2
    for sent in upstream.seen:
        assert OPERATOR_TOKEN not in str(sent.url)


def test_a_corpus_that_echoes_the_token_is_refused_rather_than_forwarded(server, upstream):
    """It should never happen — which is the reason to fail loudly if it does, rather than hand a
    deployment credential to a browser because the body was somebody else's to write."""
    upstream.answer = {"echoed": OPERATOR_TOKEN, "note": "a corpus with a bug in it"}
    answer = server.get("/speech/channels")

    assert answer.status_code == 502
    assert answer.json()["error"]["code"] == "corpus_leaked_credential"
    assert OPERATOR_TOKEN not in answer.text


def test_a_deployment_with_no_token_refuses_to_change_the_catalogue(server, upstream, monkeypatch):
    monkeypatch.setattr(server.settings, "speech_operator_token", "")
    answer = server.post("/speech/channels/es/luzu-tv/disable", {})
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "corpus_unmanaged"
    assert upstream.seen == [], "nothing is sent when there is no credential to send"


# ── the allow-list ──────────────────────────────────────────────────────────


def test_a_retrieval_route_acervo_does_not_list_is_not_an_acervo_route(server, upstream):
    """An allow-list rather than a pass-through, so adding a route there never adds one here.
    Translation jobs are real routes on that service and deliberately not reachable from here."""
    for path in ("/speech/suggestions", "/speech/translations/abc", "/speech/health/ready"):
        assert server.get(path).status_code == 404
    assert upstream.seen == []


def test_the_proxy_needs_the_same_sign_in_as_everything_else(server, upstream):
    answer = server.client.get(f"/api/acervo/v1/speech/status")
    assert answer.status_code == 401
    assert upstream.seen == []

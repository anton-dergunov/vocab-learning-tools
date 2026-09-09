"""One real service per test, over a temporary SQLite file.

There is no fake application here on purpose. The harness this replaces stubbed PocketBase's globals
and stood in for the save hook, which meant several of its assertions were about the stub; against a
real service with a throwaway database the same tests are about the thing that ships.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROMPTS = REPOSITORY_ROOT / "prompts"

OWNER_EMAIL = "learner@account.example.com"
OWNER_PASSWORD = "correct-horse-battery"
DEVICE = "device000000001"


@dataclass
class ModelStub:
    """Stands in for the provider, and records what it was asked.

    It tells the two capture calls apart the way the real prompts do — by the opening line of
    `prompts/acervo_resolve.txt` — so a test that changes one call's answer cannot silently change
    the other's.
    """

    resolution: dict[str, Any] = field(default_factory=dict)
    article: dict[str, Any] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    status: int = 200
    unreachable: bool = False
    body: Any = None
    thought_first: bool = False

    def __call__(self, url, *, headers=None, json=None, timeout=None, **_kwargs):  # noqa: A002
        self.calls.append({"url": url, "headers": dict(headers or {}), "body": json})
        if self.unreachable:
            raise httpx.ConnectError("no route to the model")
        if self.status != 200:
            return httpx.Response(self.status, text="provider details that must stay private")
        if self.body is not None:
            return httpx.Response(200, json=self.body)
        system = json["systemInstruction"]["parts"][0]["text"]
        answer = self.resolution if "You decide what a learner" in system else self.article
        parts = [{"text": _dumped(answer)}]
        if self.thought_first:
            parts.insert(0, {"thought": True, "text": "deliberation nobody asked for"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]})


def _dumped(answer: Any) -> str:
    return answer if isinstance(answer, str) else json.dumps(answer)


@dataclass
class Server:
    client: TestClient
    owner: str
    token: str
    settings: Any
    model: ModelStub
    downloads: Path
    dictionaries: Path
    web: Path

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str, **kwargs):
        return self.client.get(f"/api/acervo/v1{path}", headers=self.auth, **kwargs)

    def post(self, path: str, body: dict, **kwargs):
        return self.client.post(f"/api/acervo/v1{path}", headers=self.auth, json=body, **kwargs)

    def push(self, changes: dict, device: str = DEVICE):
        return self.post("/graph", {"schemaVersion": 6, "deviceId": device, "changes": changes})

    def pull(self, since: int = 0):
        return self.get(f"/graph?schemaVersion=6&since={since}")

    def capture(self, **overrides):
        body = {
            "schemaVersion": 6,
            "deviceId": DEVICE,
            "mode": "single",
            "text": "some text",
            **overrides,
        }
        return self.post("/capture", body)


@pytest.fixture
def server(tmp_path, monkeypatch) -> Server:
    downloads = tmp_path / "downloads"
    dictionaries = tmp_path / "dictionaries"
    web = tmp_path / "web"
    for directory in (downloads, dictionaries, web):
        directory.mkdir()

    monkeypatch.setenv("ACERVO_DB_PATH", str(tmp_path / "acervo.db"))
    monkeypatch.setenv("ACERVO_WEB_PATH", str(web))
    monkeypatch.setenv("ACERVO_DOWNLOADS_PATH", str(downloads))
    monkeypatch.setenv("ACERVO_DICTIONARIES_PATH", str(dictionaries))
    monkeypatch.setenv("ACERVO_PROMPTS_PATH", str(PROMPTS))
    monkeypatch.setenv("ACERVO_APP_VERSION", "1.4.2")
    monkeypatch.setenv("ACERVO_APP_BUILD", "218")
    monkeypatch.setenv("ACERVO_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("ACERVO_LLM_MODEL", "stub-model")
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    monkeypatch.setenv("VERTEX_API_KEY", "")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "")
    monkeypatch.setenv("ACERVO_VERTEX_LOCATION", "global")
    monkeypatch.setenv("ACERVO_LLM_ENDPOINT", "https://generativelanguage.googleapis.com")
    monkeypatch.setenv("ACERVO_JWT_SECRET", "test-secret")

    from acervo.api.app import create_app
    from acervo.repository import accounts
    from acervo.services import llm, prompts

    prompts.forget_prompts()
    model = ModelStub()
    monkeypatch.setattr(llm.httpx, "post", model)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    created = accounts.create(OWNER_EMAIL, OWNER_PASSWORD)
    signed_in = client.post(
        "/api/acervo/v1/session", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    ).json()["data"]

    return Server(
        client=client,
        owner=created["id"],
        token=signed_in["token"],
        settings=app.state.settings,
        model=model,
        downloads=downloads,
        dictionaries=dictionaries,
        web=web,
    )


@pytest.fixture
def other(server) -> Server:
    """A second account on the same server, for the cross-owner rules."""
    from acervo.repository import accounts

    email = "second@account.example.com"
    created = accounts.create(email, OWNER_PASSWORD)
    signed_in = server.client.post(
        "/api/acervo/v1/session", json={"email": email, "password": OWNER_PASSWORD}
    ).json()["data"]
    return Server(
        client=server.client,
        owner=created["id"],
        token=signed_in["token"],
        settings=server.settings,
        model=server.model,
        downloads=server.downloads,
        dictionaries=server.dictionaries,
        web=server.web,
    )

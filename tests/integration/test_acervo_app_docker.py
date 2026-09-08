from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.seed_acervo_demo import demo_records


ROOT = Path(__file__).resolve().parents[2]
API = "/api/acervo/v1"
# Kept in step with web/src/api.ts and pb_hooks/acervo.js; a mismatch is a 409 by design.
SCHEMA_VERSION = 6
GRAPH = f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since=0"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(base: str, method: str, path: str, body=None, token: str = "") -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = token
    data = None if body is None else json.dumps(body).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(base + path, data=data, headers=headers, method=method), timeout=15
        ) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def get_bytes(url: str, *, range_header: str | None = None) -> tuple[int, bytes]:
    request_value = urllib.request.Request(url, headers={"Range": range_header} if range_header else {})
    with urllib.request.urlopen(request_value, timeout=5) as response:
        return response.status, response.read()


@pytest.mark.integration
class ModelStub:
    """A Gemini-shaped endpoint the container can reach, so capture is exercised without quota.

    The two calls are told apart by their system prompt, which is the same thing that makes them
    two calls: one decides what the text is about, the other writes the entry.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        handler_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):  # noqa: N802
                pass

            def do_POST(self):  # noqa: N802
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                handler_self.calls.append(payload)
                system = payload["systemInstruction"]["parts"][0]["text"]
                answer = handler_self.resolution if "You decide what a learner" in system else handler_self.article
                body = json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.resolution: dict = {}
        self.article: dict = {}

    def stop(self) -> None:
        self.server.shutdown()


def test_pocketbase_core_auth_seed_validation_and_persistence(tmp_path: Path) -> None:
    if os.environ.get("RUN_DOCKER_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_DOCKER_INTEGRATION_TESTS=true to run Docker validation")
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")

    image = f"acervo-pocketbase-test:{uuid.uuid4().hex[:10]}"
    name = f"acervo-pocketbase-test-{uuid.uuid4().hex[:10]}"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    data = tmp_path / "pb_data"
    downloads = tmp_path / "downloads"
    data.mkdir()
    downloads.mkdir()
    suffix = secrets.token_hex(6)
    admin_email = f"admin-{suffix}@example.invalid"
    admin_password = secrets.token_urlsafe(24)
    owner_email = f"learner-{suffix}@example.invalid"
    other_email = f"other-{suffix}@example.invalid"
    user_password = secrets.token_urlsafe(24)

    subprocess.run(
        ["docker", "build", "-t", image, "-f", str(ROOT / "deploy/acervo/pocketbase/Dockerfile"), str(ROOT)],
        check=True, cwd=ROOT,
    )
    subprocess.run([
        "docker", "run", "--rm", "-v", f"{data}:/pb/pb_data", image,
        "/pb/pocketbase", "superuser", "create", admin_email, admin_password, "--dir", "/pb/pb_data",
    ], check=True, capture_output=True)

    model = ModelStub()

    def start() -> None:
        subprocess.run([
            "docker", "run", "-d", "--rm", "--name", name,
            "-p", f"127.0.0.1:{port}:8090",
            "--add-host", "host.docker.internal:host-gateway",
            "-e", "ACERVO_APP_VERSION=0.1.0", "-e", "ACERVO_APP_BUILD=202608280000",
            "-e", "ACERVO_DOWNLOADS_PATH=/pb/downloads",
            "-e", "GEMINI_API_KEY=stub-key", "-e", "ACERVO_LLM_MODEL=stub-model",
            "-e", f"ACERVO_LLM_ENDPOINT=http://host.docker.internal:{model.port}",
            "-v", f"{data}:/pb/pb_data", "-v", f"{downloads}:/pb/downloads:ro", image,
        ], check=True, capture_output=True)
        for _ in range(60):
            try:
                if request(base, "GET", "/api/acervo/v1/health")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.25)
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout
        pytest.fail(f"PocketBase did not become healthy:\n{logs}")

    def stop() -> None:
        subprocess.run(["docker", "stop", name], check=False, capture_output=True)

    def capture(text: str, **extra) -> tuple[int, dict]:
        return request(base, "POST", f"{API}/capture", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integration001",
            "mode": "single", "text": text, **extra,
        }, user_token)

    try:
        start()
        status, health = request(base, "GET", "/api/acervo/v1/health")
        assert status == 200
        assert health["data"] == {
                "name": "Acervo", "version": "0.1.0", "build": "202608280000",
                "schemaVersion": SCHEMA_VERSION,
                "capture": {
                    "available": True, "provider": "gemini",
                    "model": "stub-model", "reason": None,
                },
        }
        assert b"<title>Acervo</title>" in get_bytes(base + "/")[1]

        status, admin = request(base, "POST", "/api/collections/_superusers/auth-with-password", {
            "identity": admin_email, "password": admin_password,
        })
        assert status == 200, admin
        admin_token = admin["token"]

        owners = []
        for email in (owner_email, other_email):
            status, owner = request(base, "POST", "/api/collections/users/records", {
                "email": email, "password": user_password, "passwordConfirm": user_password, "verified": True,
            }, admin_token)
            assert status == 200, owner
            owners.append(owner)

        status, login = request(base, "POST", "/api/acervo/v1/session", {"email": owner_email, "password": user_password})
        assert status == 200, login
        user_token = login["data"]["token"]
        status, refreshed = request(base, "POST", "/api/acervo/v1/session/refresh", {}, user_token)
        assert status == 200 and refreshed["data"]["user"]["id"] == owners[0]["id"]
        assert request(base, "POST", "/api/acervo/v1/session", {"email": owner_email, "password": "wrong"})[0] == 401
        assert request(base, "GET", "/api/collections/lexemes/records", token=user_token)[0] == 403

        environment = os.environ.copy()
        environment["ACERVO_PB_SUPERUSER_EMAIL"] = admin_email
        environment["ACERVO_PB_SUPERUSER_PASSWORD"] = admin_password
        seed_command = [
            sys.executable, str(ROOT / "scripts/seed_acervo_demo.py"),
            "--server-url", base, "--owner-email", owner_email,
        ]
        first_seed = subprocess.run(seed_command, cwd=ROOT, env=environment, capture_output=True, text=True)
        assert first_seed.returncode == 0, first_seed.stderr
        second_seed = subprocess.run(seed_command, cwd=ROOT, env=environment, capture_output=True, text=True)
        assert second_seed.returncode == 0, second_seed.stderr
        assert "created 0" in second_seed.stdout
        assert "created 0" not in first_seed.stdout

        seeded = demo_records(owners[0]["id"])
        expected = Counter(collection for collection, _ in seeded)
        counts = {}
        for collection in ("vocabularies", "topics", "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"):
            owner_filter = urllib.parse.quote(f'owner="{owners[0]["id"]}"')
            status, result = request(base, "GET", f"/api/collections/{collection}/records?perPage=200&filter={owner_filter}", token=admin_token)
            assert status == 200, result
            counts[collection] = result["totalItems"]
        assert counts == dict(expected)

        # Every seeded record must carry a server-allocated revision, or no cursor pull would
        # ever deliver it. This is the trap that makes the save hook load-bearing.
        for collection in ("vocabularies", "topics", "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"):
            owner_filter = urllib.parse.quote(f'owner="{owners[0]["id"]}"')
            status, result = request(base, "GET", f"/api/collections/{collection}/records?perPage=200&filter={owner_filter}", token=admin_token)
            assert status == 200, result
            assert all(record["revision"] > 0 for record in result["items"]), collection

        # The graph route is the only way a client reads vocabulary: owner-scoped and authenticated.
        assert request(base, "GET", GRAPH)[0] == 401
        assert request(base, "GET", f"{API}/graph?schemaVersion=999&since=0", token=user_token)[0] == 409
        status, envelope = request(base, "GET", GRAPH, token=user_token)
        assert status == 200, envelope
        envelope = envelope["data"]
        dataset_id, cursor = envelope["datasetId"], envelope["cursor"]
        assert dataset_id and cursor > 0
        graph = envelope["changes"]
        assert {key: len(graph[key]) for key in
                ("vocabularies", "topics", "lexemes", "senses", "attestations", "examples", "imagePrompts", "studyStates")} == {
            "vocabularies": expected["vocabularies"],
            "topics": expected["topics"], "lexemes": expected["lexemes"], "senses": expected["senses"],
            "attestations": expected["attestations"], "examples": expected["examples"],
            "imagePrompts": expected["image_prompts"], "studyStates": expected["study_states"],
        }
        picar = next(record for record in graph["lexemes"] if record["headword"] == "picar")
        assert picar["ipa"] == "/piˈkaɾ/"
        assert picar["ownerId"] == owners[0]["id"] and picar["deleted"] is False
        assert len(picar["topicIds"]) == 3 and picar["notes"]
        assert all(len(topic) == 15 for topic in picar["topicIds"])
        clip = next(record for record in graph["examples"]
                    if record["videoTitle"] == "Easy Spanish — Comiendo en un mercado")
        assert clip["videoStart"] == 461 and clip["matchedForm"] in clip["text"]
        assert clip["matchedTranslationForm"] in clip["translation"]
        plain = next(record for record in graph["examples"] if not record["videoRef"])
        assert plain["videoTitle"] is None and plain["videoStart"] is None
        assert graph["topics"][0]["order"] is not None
        assert graph["senses"][0]["order"] is not None

        # ── capture (§05) ───────────────────────────────────────────────────
        # A word the account already holds must not become a second entry, and must not spend a
        # generation call finding that out.
        model.resolution = {
            "language": "es", "headword": "picar", "lemma": "picar", "pos": "verb",
            "sentences": [], "consumedLines": 1, "consumedText": "picar",
        }
        before = len(model.calls)
        status, repeated = capture("¿Te pica mucho la salsa?")
        assert status == 200, repeated
        assert [item["headword"] for item in repeated["data"]["duplicates"]] == ["picar"]
        assert repeated["data"]["draft"] is None
        assert len(model.calls) - before == 1

        # A language with no vocabulary record is refused before anything is generated.
        model.resolution = {**model.resolution, "language": "de", "headword": "Wanderlust"}
        before = len(model.calls)
        status, refused = capture("Fernweh und Wanderlust")
        assert status == 409 and refused["error"]["code"] == "language_not_configured"
        assert len(model.calls) - before == 1

        # And a new word is built, applied, and reaches the cursor pull like any other write.
        model.resolution = {
            "language": "es", "headword": "el garfio", "lemma": "garfio", "pos": "noun",
            "sentences": [{"text": "El disfraz de pirata viene con un garfio.", "translation": None}],
            "consumedLines": 1, "consumedText": "El disfraz de pirata viene con un garfio.",
        }
        model.article = {
            "headword": "el garfio", "lemma": "garfio", "pos": "noun", "gender": "masculine",
            "register": "neutral", "emoji": "🪝", "topics": ["Culture"], "shortGloss": "hook",
            "notes": ["Not the same as el gancho."],
            "senses": [{
                "definition": "Gancho de metal curvo y puntiagudo.",
                "glosses": [{"lang": "en", "terms": ["hook"]}],
                "examples": [
                    {"text": "El disfraz de pirata viene con un garfio.",
                     "translation": "The pirate costume comes with a hook.",
                     "matchedForm": "un garfio", "matchedTranslationForm": "hook", "fromSentence": 0},
                    # A form the model retyped rather than copied: dropped, not allowed to refuse
                    # the whole entry.
                    {"text": "Perdió la mano y le pusieron un garfio.",
                     "translation": "He lost his hand and they gave him a hook.",
                     "matchedForm": "el garfio", "fromSentence": None},
                ],
            }],
        }
        status, built = capture("El disfraz de pirata viene con un garfio.", apply=True)
        assert status == 200, built
        built = built["data"]
        assert built["duplicates"] == []
        assert built["draft"]["status"] == "inbox"
        assert built["draft"]["topics"] == ["Culture"]
        assert built["applied"]["lexemeId"]

        examples = built["draft"]["senses"][0]["examples"]
        # The learner's own sentence is kept as its own record and the example says where it came
        # from; the model's own example is marked as the model's.
        assert examples[0]["origin"] == "attestation"
        assert examples[0]["sourceAttestationId"] == built["draft"]["attestations"][0]["id"]
        assert examples[1]["origin"] == "llm" and examples[1]["modelId"] == "stub-model"
        assert examples[1]["matchedForm"] is None

        status, after = request(base, "GET", f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since={cursor}", token=user_token)
        assert status == 200, after
        arrived = after["data"]["changes"]
        assert [record["headword"] for record in arrived["lexemes"]] == ["el garfio"]
        assert all(record["revision"] > cursor for record in arrived["lexemes"])
        assert len(arrived["attestations"]) == 1 and len(arrived["examples"]) == 2
        assert graph["attestations"][0]["capturedAt"].endswith("Z") and "T" in graph["attestations"][0]["capturedAt"]
        # Capture wrote records, so the replica is now caught up to a later cursor than the seed's,
        # and the account holds more than the seed put in it.
        cursor = after["data"]["cursor"]
        captured = {key: len(records) for key, records in arrived.items()}

        # A caught-up cursor returns nothing at all: the steady-state poll is nearly free.
        status, caught_up = request(base, "GET", f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since={cursor}", token=user_token)
        assert status == 200 and caught_up["data"]["cursor"] == cursor
        assert all(caught_up["data"]["changes"][key] == [] for key in caught_up["data"]["changes"])

        # A second account shares the server and must see none of it.
        status, other_login = request(base, "POST", "/api/acervo/v1/session", {"email": other_email, "password": user_password})
        assert status == 200, other_login
        other_token = other_login["data"]["token"]
        status, empty = request(base, "GET", GRAPH, token=other_token)
        assert status == 200 and empty["data"]["changes"]["lexemes"] == []
        # Each owner counts in their own sequence, but within one database, not one per owner.
        assert empty["data"]["datasetId"] != dataset_id

        # ── the write route ────────────────────────────────────────────────────────────────
        picar_now = next(record for record in graph["lexemes"] if record["headword"] == "picar")
        edited = {**picar_now, "shortGloss": "to sting", "editedAt": "2026-08-29T09:00:00.000Z"}
        status, written = request(base, "POST", "/api/acervo/v1/graph", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "changes": {"lexemes": [edited]},
        }, user_token)
        assert status == 200, written
        stored = written["data"]["records"]["lexemes"][0]
        assert stored["shortGloss"] == "to sting"
        assert stored["revision"] > cursor, stored
        assert stored["editedBy"] == "integrationtest"
        assert written["data"]["cursor"] == stored["revision"]

        # The same payload again is now stale: its revision is the one the server just replaced.
        status, stale = request(base, "POST", "/api/acervo/v1/graph", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "changes": {"lexemes": [edited]},
        }, user_token)
        assert status == 409 and stale["error"]["code"] == "stale_record", stale

        # And the delta a caught-up device asks for carries exactly that one change.
        status, delta = request(base, "GET", f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since={cursor}", token=user_token)
        assert status == 200 and [record["id"] for record in delta["data"]["changes"]["lexemes"]] == [stored["id"]]
        assert delta["data"]["changes"]["topics"] == []

        # A batch is all-or-nothing: one invalid record leaves the valid one unwritten too.
        good = {**graph["topics"][0], "name": "Renamed"}
        bad = {**graph["senses"][0], "definitionLang": "not a language tag"}
        assert request(base, "POST", "/api/acervo/v1/graph", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest",
            "changes": {"topics": [good], "senses": [bad]},
        }, user_token)[0] == 400
        status, unchanged = request(base, "GET", f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since=0", token=user_token)
        assert next(record for record in unchanged["data"]["changes"]["topics"]
                    if record["id"] == good["id"])["name"] != "Renamed"

        # Writing is owner-scoped and version-gated like reading.
        assert request(base, "POST", "/api/acervo/v1/graph", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "changes": {"lexemes": [edited]},
        }, other_token)[0] == 400
        assert request(base, "POST", "/api/acervo/v1/graph", {
            "schemaVersion": 999, "deviceId": "integrationtest", "changes": {},
        }, user_token)[0] == 409
        assert request(base, "POST", "/api/acervo/v1/graph", {"schemaVersion": SCHEMA_VERSION, "changes": {}}, user_token)[0] == 400

        lexeme_id = next(record["id"] for collection, record in seeded if collection == "lexemes")
        status, updated = request(base, "PATCH", f"/api/collections/lexemes/records/{lexeme_id}", {"short_gloss": "demonstration"}, admin_token)
        assert status == 200 and updated["short_gloss"] == "demonstration"

        cross_owner_sense = {
            "id": "sensecrossown01", "owner": owners[1]["id"], "lexeme": lexeme_id,
            "definition": "Must fail.", "definition_lang": "en", "glosses": [{"lang": "en", "terms": ["fail"]}],
            "domain": "", "sense_order": 0, "deleted": False,
            "created_at": "2026-08-28T12:00:00.000Z", "edited_at": "2026-08-28T12:00:00.000Z",
            "edited_by": "integrationtest", "revision": 0,
        }
        assert request(base, "POST", "/api/collections/senses/records", cross_owner_sense, admin_token)[0] == 400

        cross_owner_topic = {
            "id": "topiccrossown01", "owner": owners[1]["id"], "name": "Other account", "icon": "🔒",
            "deleted": False, "created_at": "2026-08-28T12:00:00.000Z",
            "edited_at": "2026-08-28T12:00:00.000Z", "edited_by": "integrationtest", "revision": 0,
        }
        assert request(base, "POST", "/api/collections/topics/records", cross_owner_topic, admin_token)[0] == 200
        assert request(base, "PATCH", f"/api/collections/lexemes/records/{lexeme_id}", {
            "topics": [cross_owner_topic["id"]]
        }, admin_token)[0] == 400

        # ── reset ──────────────────────────────────────────────────────────────────────────
        assert request(base, "POST", "/api/acervo/v1/graph/reset", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "confirm": "yes",
        }, user_token)[0] == 400
        status, reset = request(base, "POST", "/api/acervo/v1/graph/reset", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "confirm": "delete-all-words",
        }, user_token)
        word_collections = {
            "lexemes": "lexemes", "senses": "senses", "attestations": "attestations",
            "examples": "examples", "imagePrompts": "image_prompts", "studyStates": "study_states",
        }
        assert status == 200 and reset["data"]["deleted"] == sum(
            expected[collection] + captured[key] for key, collection in word_collections.items()
        ), reset
        assert reset["data"]["datasetId"] == dataset_id

        # Nothing is removed: a full pull still carries every row, now as a tombstone. That is
        # what keeps an accidental reset undoable.
        status, after = request(base, "GET", GRAPH, token=user_token)
        assert status == 200
        emptied = after["data"]["changes"]
        assert len(emptied["lexemes"]) == expected["lexemes"] + captured["lexemes"]
        assert all(record["deleted"] for record in emptied["lexemes"])
        assert all(record["deleted"] for record in emptied["senses"])
        assert all(not record["deleted"] for record in emptied["vocabularies"])
        assert all(not record["deleted"] for record in emptied["topics"])
        # A second reset has nothing left to tombstone.
        status, again = request(base, "POST", "/api/acervo/v1/graph/reset", {
            "schemaVersion": SCHEMA_VERSION, "deviceId": "integrationtest", "confirm": "delete-all-words",
        }, user_token)
        assert status == 200 and again["data"]["deleted"] == 0

        sentinel = data / "deployment-sentinel"
        sentinel.write_text("preserved", encoding="utf-8")
        stop()
        start()
        assert sentinel.read_text(encoding="utf-8") == "preserved"
        status, persisted = request(base, "GET", f"/api/collections/lexemes/records/{lexeme_id}", token=admin_token)
        assert status == 200 and persisted["short_gloss"] == "demonstration"
        # The cursor must never outlive the database that issued it — and must survive a restart
        # that did not rebuild it, or every device would discard a perfectly good replica.
        status, restarted = request(base, "GET", GRAPH, token=user_token)
        assert status == 200 and restarted["data"]["datasetId"] == dataset_id
        assert restarted["data"]["cursor"] >= cursor

        archive = downloads / "Acervo-test.zip"
        archive.write_bytes(b"test")
        (downloads / "release.json").write_text(json.dumps({
            "version": "0.1.0", "build": "202608280001", "file": archive.name,
            "size": archive.stat().st_size,
            "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        }), encoding="utf-8")
        status, piece = get_bytes(base + "/api/acervo/downloads/Acervo-test.zip", range_header="bytes=0-1")
        assert status == 206 and piece == b"te"
    finally:
        stop()
        model.stop()
        subprocess.run(["docker", "image", "rm", image], check=False, capture_output=True)

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

import pytest

from scripts.seed_acervo_demo import demo_records


ROOT = Path(__file__).resolve().parents[2]


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

    def start() -> None:
        subprocess.run([
            "docker", "run", "-d", "--rm", "--name", name,
            "-p", f"127.0.0.1:{port}:8090",
            "-e", "ACERVO_APP_VERSION=0.1.0", "-e", "ACERVO_APP_BUILD=202608280000",
            "-e", "ACERVO_DOWNLOADS_PATH=/pb/downloads",
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

    try:
        start()
        status, health = request(base, "GET", "/api/acervo/v1/health")
        assert status == 200
        assert health["data"] == {
                "name": "Acervo", "version": "0.1.0", "build": "202608280000", "schemaVersion": 3
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
        for collection in ("topics", "lexemes", "senses", "attestations", "examples", "image_prompts", "study_states"):
            owner_filter = urllib.parse.quote(f'owner="{owners[0]["id"]}"')
            status, result = request(base, "GET", f"/api/collections/{collection}/records?perPage=200&filter={owner_filter}", token=admin_token)
            assert status == 200, result
            counts[collection] = result["totalItems"]
        assert counts == dict(expected)

        # The graph route is the only way a client reads vocabulary: owner-scoped and authenticated.
        assert request(base, "GET", "/api/acervo/v1/graph")[0] == 401
        status, graph = request(base, "GET", "/api/acervo/v1/graph", token=user_token)
        assert status == 200, graph
        graph = graph["data"]
        assert {key: len(graph[key]) for key in
                ("topics", "lexemes", "senses", "attestations", "examples", "imagePrompts", "studyStates")} == {
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
        assert graph["attestations"][0]["capturedAt"].endswith("Z") and "T" in graph["attestations"][0]["capturedAt"]

        # A second account shares the server and must see none of it.
        status, other_login = request(base, "POST", "/api/acervo/v1/session", {"email": other_email, "password": user_password})
        assert status == 200, other_login
        status, empty = request(base, "GET", "/api/acervo/v1/graph", token=other_login["data"]["token"])
        assert status == 200 and empty["data"]["lexemes"] == []

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

        sentinel = data / "deployment-sentinel"
        sentinel.write_text("preserved", encoding="utf-8")
        stop()
        start()
        assert sentinel.read_text(encoding="utf-8") == "preserved"
        status, persisted = request(base, "GET", f"/api/collections/lexemes/records/{lexeme_id}", token=admin_token)
        assert status == 200 and persisted["short_gloss"] == "demonstration"

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
        subprocess.run(["docker", "image", "rm", image], check=False, capture_output=True)

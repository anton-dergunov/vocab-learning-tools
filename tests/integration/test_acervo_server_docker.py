"""The packaged server image, built and run for real.

Everything about the *contract* is in `tests/unit/server/`, which runs against the same application
in-process in a few seconds. What only a container can tell you is what this checks: that the image
builds from the repository, that it starts, that its healthcheck command is one the image actually
has, that an account can be made inside it, and that the database survives a restart.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API = "/api/acervo/v1"
SCHEMA_VERSION = 6

pytestmark = pytest.mark.integration

OWNER_EMAIL = "learner@account.example.com"
OWNER_PASSWORD = "correct-horse-battery"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def request(base, method, path, body=None, token=""):
    data = json.dumps(body).encode() if body is not None else None
    call = urllib.request.Request(f"{base}{path}", data=data, method=method)
    call.add_header("Accept", "application/json")
    if data:
        call.add_header("Content-Type", "application/json")
    if token:
        call.add_header("Authorization", token)
    try:
        with urllib.request.urlopen(call, timeout=15) as answer:
            return answer.status, json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as refused:
        return refused.code, json.loads(refused.read() or b"{}")


def docker(*arguments, **kwargs):
    return subprocess.run(["docker", *arguments], capture_output=True, text=True, **kwargs)


@pytest.fixture(scope="module")
def running(tmp_path_factory):
    if os.environ.get("RUN_DOCKER_INTEGRATION_TESTS") != "true":
        pytest.skip("set RUN_DOCKER_INTEGRATION_TESTS=true to run the container tests")
    if shutil.which("docker") is None:
        pytest.skip("docker is not available")
    # The CLI being installed is not the daemon being up, and the difference between "cannot run
    # this" and "this failed" matters when the suite is asked for explicitly.
    if docker("info").returncode != 0:
        pytest.skip("the docker daemon is not running")

    tag = f"acervo-server-test:{uuid.uuid4().hex[:8]}"
    name = f"acervo-server-test-{uuid.uuid4().hex[:8]}"
    state = tmp_path_factory.mktemp("state")
    downloads = tmp_path_factory.mktemp("downloads")
    (downloads / "Acervo-test.zip").write_bytes(b"test archive bytes")
    (downloads / "release.json").write_text(
        json.dumps(
            {"version": "0.1.0", "build": "1", "file": "Acervo-test.zip", "size": 18, "sha256": "a" * 64}
        )
    )
    port = free_port()

    built = docker("build", "-t", tag, "-f", "deploy/acervo/server/Dockerfile", str(ROOT), cwd=ROOT)
    assert built.returncode == 0, built.stderr[-4000:]

    def start():
        started = docker(
            "run", "-d", "--rm", "--name", name,
            "-p", f"127.0.0.1:{port}:8000",
            "-e", "ACERVO_APP_VERSION=0.1.0",
            "-e", "ACERVO_APP_BUILD=1",
            "-e", "ACERVO_JWT_SECRET=integration-test-secret",
            "-v", f"{state}:/var/lib/acervo/server",
            "-v", f"{downloads}:/var/lib/acervo/downloads:ro",
            tag,
        )
        assert started.returncode == 0, started.stderr
        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                if request(base, "GET", f"{API}/health")[0] == 200:
                    return base
            except OSError:
                pass
            time.sleep(0.25)
        pytest.fail(docker("logs", name).stdout + docker("logs", name).stderr)

    base = start()
    try:
        yield type("Running", (), {"base": base, "name": name, "restart": lambda self: None})()
    finally:
        docker("stop", name)
        docker("image", "rm", "-f", tag)


def test_the_image_starts_and_answers_health_over_http(running):
    status, payload = request(running.base, "GET", f"{API}/health")
    assert status == 200
    assert payload["data"]["name"] == "Acervo"
    assert payload["data"]["schemaVersion"] == SCHEMA_VERSION
    assert set(payload["data"]["capture"]) == {"available", "provider", "model", "reason"}


def test_the_healthcheck_command_exists_inside_the_image(running):
    """A container whose healthcheck binary is missing reports unhealthy forever while serving
    perfectly, and the installer then fails the deployment of a working service."""
    probe = docker(
        "exec", running.name, "python", "-c",
        "import urllib.request,sys; "
        "sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/acervo/v1/health', timeout=3).status == 200 else 1)",
    )
    assert probe.returncode == 0, probe.stderr


def test_an_account_is_created_inside_the_container_and_can_then_sign_in(running):
    created = subprocess.run(
        ["docker", "exec", "-i", running.name,
         "python", "-m", "acervo.admin", "accounts", "create", "--email", OWNER_EMAIL],
        input=f"{OWNER_PASSWORD}\n", capture_output=True, text=True,
    )
    assert created.returncode == 0, created.stderr
    status, payload = request(
        running.base, "POST", f"{API}/session", {"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert status == 200
    assert payload["data"]["user"]["email"] == OWNER_EMAIL


def test_a_graph_round_trip_survives_a_restart_of_the_container(running):
    _, session = request(
        running.base, "POST", f"{API}/session", {"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    token = f"Bearer {session['data']['token']}"
    at = "2026-01-01T00:00:00.000Z"
    stamp = {"deleted": False, "createdAt": at, "editedAt": at, "editedBy": "device000000001",
             "revision": 0}
    status, written = request(
        running.base, "POST", f"{API}/graph",
        {
            "schemaVersion": SCHEMA_VERSION,
            "deviceId": "device000000001",
            "changes": {"topics": [{"id": "topicaaaaaaaaaa", "name": "Food", "icon": None,
                                    "order": 0, **stamp}]},
        },
        token,
    )
    assert status == 200, written
    assert written["data"]["records"]["topics"][0]["revision"] > 0

    docker("restart", running.name)
    for _ in range(120):
        try:
            if request(running.base, "GET", f"{API}/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.25)

    status, pulled = request(
        running.base, "GET", f"{API}/graph?schemaVersion={SCHEMA_VERSION}&since=0", token=token
    )
    assert status == 200
    assert [row["name"] for row in pulled["data"]["changes"]["topics"]] == ["Food"]


def test_a_download_answers_a_byte_range_with_no_credentials(running):
    call = urllib.request.Request(f"{running.base}/api/acervo/downloads/Acervo-test.zip")
    call.add_header("Range", "bytes=0-1")
    with urllib.request.urlopen(call, timeout=15) as answer:
        assert answer.status == 206
        assert answer.read() == b"te"

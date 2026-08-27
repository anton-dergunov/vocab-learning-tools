from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get(url: str, *, range_header: str | None = None) -> tuple[int, bytes]:
    request = Request(url, headers={"Range": range_header} if range_header else {})
    with urlopen(request, timeout=5) as response:
        return response.status, response.read()


@pytest.mark.integration
def test_pocketbase_serves_pwa_updates_and_preserves_data(tmp_path: Path) -> None:
    if os.environ.get("RUN_DOCKER_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_DOCKER_INTEGRATION_TESTS=true to run Docker validation")
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")

    image = f"acervo-pocketbase-test:{uuid.uuid4().hex[:10]}"
    name = f"acervo-pocketbase-test-{uuid.uuid4().hex[:10]}"
    port = free_port()
    data = tmp_path / "pb_data"
    downloads = tmp_path / "downloads"
    data.mkdir()
    downloads.mkdir()

    subprocess.run(
        [
            "docker", "build", "-t", image,
            "-f", str(ROOT / "deploy/acervo/pocketbase/Dockerfile"), str(ROOT),
        ],
        check=True,
        cwd=ROOT,
    )

    def start() -> None:
        subprocess.run(
            [
                "docker", "run", "-d", "--rm", "--name", name,
                "-p", f"127.0.0.1:{port}:8090",
                "-e", "ACERVO_APP_VERSION=0.1.0",
                "-e", "ACERVO_APP_BUILD=202608270000",
                "-e", "ACERVO_DOWNLOADS_PATH=/pb/downloads",
                "-v", f"{data}:/pb/pb_data",
                "-v", f"{downloads}:/pb/downloads:ro",
                image,
            ],
            check=True,
            capture_output=True,
        )
        for _ in range(30):
            try:
                get(f"http://127.0.0.1:{port}/api/acervo/v1/health")
                return
            except Exception:
                time.sleep(0.5)
        pytest.fail("PocketBase did not become healthy")

    def stop() -> None:
        subprocess.run(["docker", "stop", name], check=False, capture_output=True)

    try:
        start()
        _, page = get(f"http://127.0.0.1:{port}/")
        assert b"<title>Acervo</title>" in page
        _, health_bytes = get(f"http://127.0.0.1:{port}/api/acervo/v1/health")
        health = json.loads(health_bytes)["data"]
        assert health == {"name": "Acervo", "version": "0.1.0", "build": "202608270000"}
        _, release_bytes = get(f"http://127.0.0.1:{port}/api/acervo/v1/mac-release")
        assert json.loads(release_bytes)["data"] is None
        stop()

        sentinel = data / "deployment-sentinel"
        sentinel.write_text("preserved", encoding="utf-8")
        archive = downloads / "Acervo-test.zip"
        archive.write_bytes(b"test")
        (downloads / "release.json").write_text(json.dumps({
            "version": "0.1.0",
            "build": "202608270001",
            "file": archive.name,
            "size": archive.stat().st_size,
            "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        }), encoding="utf-8")

        start()
        assert sentinel.read_text(encoding="utf-8") == "preserved"
        _, release_bytes = get(f"http://127.0.0.1:{port}/api/acervo/v1/mac-release")
        release = json.loads(release_bytes)["data"]
        assert release["url"] == "/api/acervo/downloads/Acervo-test.zip"
        status, piece = get(
            f"http://127.0.0.1:{port}{release['url']}", range_header="bytes=0-1"
        )
        assert status == 206
        assert piece == b"te"
    finally:
        stop()
        subprocess.run(["docker", "image", "rm", image], check=False, capture_output=True)

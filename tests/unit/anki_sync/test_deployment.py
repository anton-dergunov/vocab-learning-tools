from __future__ import annotations

import os
import subprocess
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def fake_docker_path(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" ps --format json \"*) echo '{\"Health\":\"healthy\"}' ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return bin_dir


def deployment_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    root = home / ".acervo"
    root.mkdir(parents=True)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    return env, root


def run_local(env: dict[str, str], *, stdin: str = "", reset: bool = False):
    command = [str(REPO_ROOT / "deploy.sh"), "--local"]
    if reset:
        command.append("--reset-data")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def test_local_deployment_preserves_data_backs_up_and_rotates(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    server = root / "data" / "anki-server"
    server.mkdir(parents=True)
    database = server / "collection.anki2"
    database.write_bytes(b"collection-v1")
    robot = root / "data" / "anki-robot"
    robot.mkdir(parents=True)
    (robot / "collection.anki2").write_bytes(b"robot-v1")
    (server / "media.db").write_bytes(b"media-index-v1")
    sentinel = server / "media-sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    backups = root / "backups"
    backups.mkdir()
    for index in range(11):
        (backups / f"20000101T0000{index:02d}Z").mkdir()

    result = run_local(env)

    assert result.returncode == 0, result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert len([path for path in backups.iterdir() if path.is_dir()]) == 10
    assert any(
        path.name == "collection.anki2" and path.read_bytes() == b"collection-v1"
        for path in backups.rglob("collection.anki2")
    )
    assert any(path.read_bytes() == b"robot-v1" for path in backups.rglob("collection.anki2"))
    assert any(path.read_bytes() == b"media-index-v1" for path in backups.rglob("media.db"))
    assert (root / "secrets.env").stat().st_mode & 0o777 == 0o600


def test_reset_requires_exact_confirmation_and_backs_up_first(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    server = root / "data" / "anki-server"
    server.mkdir(parents=True)
    database = server / "collection.anki2"
    database.write_bytes(b"important")

    refused = run_local(env, stdin="no\n", reset=True)
    assert refused.returncode == 2
    assert database.exists()

    accepted = run_local(env, stdin="RESET ACERVO DATA\n", reset=True)
    assert accepted.returncode == 0, accepted.stderr
    assert not database.exists()
    assert any(path.read_bytes() == b"important" for path in root.rglob("collection.anki2"))


def test_release_archive_excludes_deployment_secrets(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "package_acervo_server.sh")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    archive = Path(result.stdout.strip())
    with tarfile.open(archive) as package:
        members = package.getnames()
    assert not any(name.endswith("secrets.env") for name in members)
    assert "deploy/acervo/secrets.env.example" in members


def test_acervo_wide_defaults_are_not_anki_named() -> None:
    deploy = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    installer = (REPO_ROOT / "deploy" / "acervo" / "install.sh").read_text(
        encoding="utf-8"
    )
    assert "$HOME/.acervo" in deploy
    assert "/volume1/docker/acervo" in installer
    assert "/opt/acervo" in installer
    assert "/etc/acervo-root" in installer
    assert "/volume1/docker/acervo-anki" not in deploy + installer

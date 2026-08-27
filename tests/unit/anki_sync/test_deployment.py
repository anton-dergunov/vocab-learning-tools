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


def test_remote_deployment_streams_over_ssh_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    release_upload = tmp_path / "release.tar.gz"
    helper_upload = tmp_path / "install.sh"
    credential_upload = tmp_path / "credentials"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'cat > /tmp/acervo-release-'*) cat >\"$ACERVO_TEST_RELEASE\" ;;\n"
        "  *'cat > /tmp/acervo-install-'*) cat >\"$ACERVO_TEST_HELPER\" ;;\n"
        "  *'cat > /tmp/acervo-credentials-'*) cat >\"$ACERVO_TEST_CREDENTIALS\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = bin_dir / "scp"
    scp.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    scp.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_RELEASE": str(release_upload),
            "ACERVO_TEST_HELPER": str(helper_upload),
            "ACERVO_TEST_CREDENTIALS": str(credential_upload),
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "--configure-credentials",
        ],
        cwd=REPO_ROOT,
        env=env,
        input="sync-user\ntest-password\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with tarfile.open(release_upload) as package:
        assert "deploy/acervo/compose.yaml" in package.getnames()
    assert helper_upload.read_bytes() == (REPO_ROOT / "deploy/acervo/install.sh").read_bytes()
    assert credential_upload.read_text(encoding="utf-8") == "sync-user\ntest-password\n"
    commands = ssh_log.read_text(encoding="utf-8")
    assert "cat > /tmp/acervo-release-" in commands
    assert "cat > /tmp/acervo-install-" in commands
    assert "cat > /tmp/acervo-credentials-" in commands
    assert "--credentials-file /tmp/acervo-credentials-" in commands
    assert "sudo sh" in commands
    assert "test-password" not in commands


def test_installer_accepts_streamed_credential_file_and_network_options(
    tmp_path: Path,
) -> None:
    root = tmp_path / "acervo"
    credential_file = tmp_path / "credentials"
    credential_file.write_text("sync-user\ntest-password\n", encoding="utf-8")
    credential_file.chmod(0o600)
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root",
            str(root),
            "--credentials-file",
            str(credential_file),
            "--bind-address",
            "0.0.0.0",
            "--port",
            "27801",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (root / "secrets.env").read_text(encoding="utf-8") == (
        "ACERVO_ANKI_SYNC_USERNAME='sync-user'\n"
        "ACERVO_ANKI_SYNC_PASSWORD='test-password'\n"
    )
    deployment = (root / "deployment.env").read_text(encoding="utf-8")
    assert "ACERVO_BIND_ADDRESS=0.0.0.0\n" in deployment
    assert "ACERVO_ANKI_PORT=27801\n" in deployment


def test_remote_status_does_not_build_or_upload(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "printf 'state=running,health=healthy\\n0.0.0.0:27701\\n'\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_SSH_LOG"] = str(ssh_log)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--status",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "health=healthy" in result.stdout
    commands = ssh_log.read_text(encoding="utf-8")
    assert "docker" in commands
    assert "cat >" not in commands


def test_remote_robot_wrapper_streams_validated_input_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    helper_upload = tmp_path / "run-robot.sh"
    input_upload = tmp_path / "input.tar.gz"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'cat > /tmp/acervo-run-robot-'*) cat >\"$ACERVO_TEST_HELPER\" ;;\n"
        "  *'cat > /tmp/acervo-anki-input-'*) cat >\"$ACERVO_TEST_INPUT\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = bin_dir / "scp"
    scp.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    scp.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_HELPER": str(helper_upload),
            "ACERVO_TEST_INPUT": str(input_upload),
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "scripts/acervo_anki_remote.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "bootstrap-upload",
            str(REPO_ROOT / "examples/anki-sync-smoke/manifest.json"),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert helper_upload.read_bytes() == (REPO_ROOT / "deploy/acervo/run-robot.sh").read_bytes()
    with tarfile.open(input_upload) as package:
        assert package.getnames() == ["manifest.json"]
    commands = ssh_log.read_text(encoding="utf-8")
    assert "--input-archive /tmp/acervo-anki-input-" in commands
    assert "bootstrap-upload" in commands


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

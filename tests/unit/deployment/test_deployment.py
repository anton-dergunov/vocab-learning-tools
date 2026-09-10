from __future__ import annotations

import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def runnable_remote_helper(tmp_path: Path) -> Path:
    source = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    source = source.replace('[ "$(id -u)" -eq 0 ] || {', "true || {", 1)
    helper = tmp_path / "deploy-acervo"
    helper.write_text(source, encoding="utf-8")
    helper.chmod(0o755)
    return helper


def fake_tailscale_path(tmp_path: Path, initial_status: str) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "tailscale-bin"
    bin_dir.mkdir()
    state = tmp_path / "tailscale-status"
    state.write_text(initial_status, encoding="utf-8")
    log = tmp_path / "tailscale-log"
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        "if [ \"$1 $2\" = 'serve status' ]; then cat \"$ACERVO_TEST_TS_STATE\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_TS_LOG\"\n"
        "case \"$4\" in\n"
        "  --https=443) address=https://server.example.com ;;\n"
        "  --https=*) address=https://server.example.com:${4#--https=} ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n"
        "printf '\\n%s (tailnet only)\\n|-- / proxy %s\\n' \"$address\" \"$5\" "
        ">>\"$ACERVO_TEST_TS_STATE\"\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    return bin_dir, state, log


def fake_tailscale_service_path(
    tmp_path: Path, initial_status: str, version: str = "1.86.0"
) -> tuple[Path, Path, Path]:
    """A Tailscale that speaks the service form of `serve`, which reports through `status --json`."""
    bin_dir = tmp_path / "tailscale-service-bin"
    bin_dir.mkdir()
    state = tmp_path / "tailscale-service-status"
    state.write_text(initial_status, encoding="utf-8")
    log = tmp_path / "tailscale-service-log"
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = version ]; then printf '{version}\\n  commit: abc\\n'; exit 0; fi\n"
        "if [ \"$1 $2\" = 'serve status' ]; then cat \"$ACERVO_TEST_TS_STATE\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_TS_LOG\"\n"
        "case \"$2\" in\n"
        "  --service=svc:*) service=${2#--service=} ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n"
        # The proxy target is the final argument, wherever the flags before it land.
        "for target; do :; done\n"
        "printf '{\"%s\":{\"proxy\":\"%s\"}}\\n' \"$service\" \"$target\" >>\"$ACERVO_TEST_TS_STATE\"\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    return bin_dir, state, log


def fake_docker_path(
    tmp_path: Path,
    *,
    existing: tuple[str, ...] = (),
    published: bool = True,
) -> Path:
    """A `docker` that answers the four questions the installer asks it.

    `existing` names containers `inspect` should find, and finds them stopped — which is the state a
    create that could not bind its port leaves behind. `published` is whether `port` reports a host
    binding; without one a container can be healthy and still unreachable, which is the failure the
    installer now refuses to report as success.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'known_containers="' + " ".join(existing) + '"\n'
        '[ -z "${ACERVO_TEST_DOCKER_LOG:-}" ] || echo "$*" >>"$ACERVO_TEST_DOCKER_LOG"\n'
        'case " $* " in\n'
        '  *" ps --format json "*) echo \'{"Health":"healthy"}\'; exit 0 ;;\n'
        '  *" port "*) ' + ('echo 127.0.0.1:27702' if published else ':') + '; exit 0 ;;\n'
        "esac\n"
        'if [ "$1" = inspect ]; then\n'
        "  for known in $known_containers; do\n"
        '    for word in "$@"; do\n'
        '      [ "$word" = "$known" ] || continue\n'
        '      case " $* " in *State.Running*) echo false ;; esac\n'
        "      exit 0\n"
        "    done\n"
        "  done\n"
        "  exit 1\n"
        "fi\n"
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
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_JWT_SECRET='a-durable-signing-secret'\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    env["ACERVO_SKIP_MACOS_RELEASE"] = "true"
    env["ACERVO_SKIP_APP_BUILD"] = "true"
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
    robot = root / "data" / "acervo-worker"
    robot.mkdir(parents=True)
    (robot / "collection.anki2").write_bytes(b"robot-v1")
    (server / "media.db").write_bytes(b"media-index-v1")
    sentinel = server / "media-sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    vocabulary = root / "data" / "server"
    vocabulary.mkdir(parents=True)
    vocabulary_sentinel = vocabulary / "acervo.db"
    vocabulary_sentinel.write_bytes(b"vocabulary-v1")
    backups = root / "backups"
    backups.mkdir()
    for index in range(11):
        (backups / f"20000101T0000{index:02d}Z").mkdir()

    result = run_local(env)

    assert result.returncode == 0, result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert vocabulary_sentinel.read_bytes() == b"vocabulary-v1"
    assert len([path for path in backups.iterdir() if path.is_dir()]) == 10
    assert any(
        path.name == "collection.anki2" and path.read_bytes() == b"collection-v1"
        for path in backups.rglob("collection.anki2")
    )
    assert any(path.read_bytes() == b"robot-v1" for path in backups.rglob("collection.anki2"))
    assert any(path.read_bytes() == b"media-index-v1" for path in backups.rglob("media.db"))
    assert (root / "secrets.env").stat().st_mode & 0o777 == 0o600


def test_compiled_dictionaries_travel_with_the_release_and_are_merged(tmp_path: Path) -> None:
    """Dictionaries are built where the compiler runs and are not in the repository, so the release
    carries them the way it carries the macOS application.

    Merged rather than replaced: building only the Spanish ones and deploying must not withdraw the
    Chinese ones deployed last week.
    """
    env, root = deployment_env(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in ("cc-cedict", "kaikki-es-es"):
        (artifacts / f"{name}.json").write_text(f'{{"id": "{name}"}}', encoding="utf-8")
        (artifacts / f"{name}.dict").write_bytes(b"payloads")
        (artifacts / f"{name}.idx").write_bytes(b"index")
    # A metadata file with no payload beside it must not be published: the server would list it and
    # then fail at the moment someone tried to store it.
    (artifacts / "half-built.json").write_text('{"id": "half-built"}', encoding="utf-8")

    served = root / "data" / "dictionaries"
    served.mkdir(parents=True)
    for suffix, content in ((".json", b'{"id": "moedict-zh"}'), (".dict", b"old"), (".idx", b"old")):
        (served / f"moedict-zh{suffix}").write_bytes(content)

    env["ACERVO_DICTIONARY_ARTIFACTS"] = str(artifacts)
    result = run_local(env)

    assert result.returncode == 0, result.stderr
    published = {path.stem for path in served.glob("*.json")}
    assert {"cc-cedict", "kaikki-es-es"} <= published, "the release did not publish its dictionaries"
    assert "moedict-zh" in published, "deploying replaced the dictionaries already on the server"
    assert "half-built" not in published
    assert (served / "cc-cedict.dict").read_bytes() == b"payloads"


def test_a_release_without_dictionaries_leaves_the_published_ones_alone(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    served = root / "data" / "dictionaries"
    served.mkdir(parents=True)
    (served / "cc-cedict.json").write_text('{"id": "cc-cedict"}', encoding="utf-8")

    env["ACERVO_INCLUDE_DICTIONARIES"] = "false"
    result = run_local(env)

    assert result.returncode == 0, result.stderr
    assert (served / "cc-cedict.json").is_file(), "a build with no dictionaries withdrew the old ones"


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


def packaged(tmp_path: Path) -> str:
    """Build a release archive and return where it landed.

    Where that is comes from `conftest.py`'s autouse fixture, which redirects it away from `build/`
    for every test here — see the note there.
    """
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "package_acervo_server.sh")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_release_archive_excludes_deployment_secrets(tmp_path: Path) -> None:
    archive = Path(packaged(tmp_path))
    with tarfile.open(archive) as package:
        members = package.getnames()
    assert not any(name.endswith("secrets.env") for name in members)
    assert "deploy/acervo/llm.env" not in members
    assert "deploy/acervo/secrets.env.example" in members
    assert "deploy/acervo/llm.env.example" in members
    assert "deploy/acervo/server/web/manifest.webmanifest" in members
    assert "deploy/acervo/server/Dockerfile" in members
    # The image installs the package out of the bundle, so its build files travel with it.
    assert "src/acervo/api/app.py" in members
    assert "pyproject.toml" in members
    assert "version.json" in members


def test_remote_deployment_streams_over_ssh_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    release_upload = tmp_path / "release.tar.gz"
    credential_upload = tmp_path / "credentials"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo deploy'*) cat >\"$ACERVO_TEST_RELEASE\" ;;\n"
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
            "ACERVO_TEST_CREDENTIALS": str(credential_upload),
            "ACERVO_SKIP_MACOS_RELEASE": "true",
            "ACERVO_SKIP_APP_BUILD": "true",
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
    assert credential_upload.read_text(encoding="utf-8") == (
        "sync-user\ntest-password\n"
    )
    commands = ssh_log.read_text(encoding="utf-8")
    assert "cat > /tmp/acervo-credentials-" in commands
    assert "--credentials-file /tmp/acervo-credentials-" in commands
    assert "sudo -n /usr/local/sbin/deploy-acervo deploy" in commands
    assert "sudo sh" not in commands
    assert " -t " not in commands
    assert "test-password" not in commands


def test_remote_llm_configuration_streams_the_key_without_exposing_it(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    release_upload = tmp_path / "release.tar.gz"
    llm_upload = tmp_path / "llm-credentials"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo deploy'*) cat >\"$ACERVO_TEST_RELEASE\" ;;\n"
        "  *'cat > /tmp/acervo-llm-credentials-'*) cat >\"$ACERVO_TEST_LLM\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "ACERVO_TEST_SSH_LOG": str(ssh_log),
        "ACERVO_TEST_RELEASE": str(release_upload),
        "ACERVO_TEST_LLM": str(llm_upload),
        "ACERVO_SKIP_MACOS_RELEASE": "true",
        "ACERVO_SKIP_APP_BUILD": "true",
    })

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"), "--target", "deployer@server.example.test",
            "--root", "/volume1/docker/acervo", "--configure-llm",
            "--llm-chain", "cloudflare,gemini-free",
            "--llm-set", "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef",
            "--llm-key", "CLOUDFLARE_API_TOKEN", "--llm-api-key-stdin",
        ],
        cwd=REPO_ROOT, env=env, input="cloudflare-token\n", text=True,
        capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert llm_upload.read_text(encoding="utf-8") == (
        "ACERVO_TEXT_CHAIN=cloudflare,gemini-free\n"
        "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n"
        "CLOUDFLARE_API_TOKEN=cloudflare-token\n"
    )
    commands = ssh_log.read_text(encoding="utf-8")
    assert "cat > /tmp/acervo-llm-credentials-" in commands
    assert "--llm-credentials-file /tmp/acervo-llm-credentials-" in commands
    # The key travels over stdin into a mode-600 file. A command line is visible in `ps`.
    assert "cloudflare-token" not in commands + result.stdout + result.stderr


def test_installer_accepts_streamed_credential_file_and_network_options(
    tmp_path: Path,
) -> None:
    root = tmp_path / "acervo"
    credential_file = tmp_path / "credentials"
    credential_file.write_text(
        "sync-user\ntest-password\n",
        encoding="utf-8",
    )
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
            "--app-bind-address",
            "127.0.0.1",
            "--app-port",
            "27802",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    written = (root / "secrets.env").read_text(encoding="utf-8")
    assert written.startswith(
        "ACERVO_ANKI_SYNC_USERNAME='sync-user'\nACERVO_ANKI_SYNC_PASSWORD='test-password'\n"
    )
    # Minted here and kept, because regenerating it signs out every device.
    assert re.search(r"^ACERVO_JWT_SECRET='[A-Za-z0-9]{16,}'$", written, flags=re.MULTILINE)
    # A model credential belongs in llm.env and nowhere else: compose passes llm.env last, so a key
    # defined in both files has a silent loser, which is what took capture down.
    assert "GEMINI_API_KEY" not in (root / "secrets.env").read_text(encoding="utf-8")
    deployment = (root / "deployment.env").read_text(encoding="utf-8")
    assert "ACERVO_BIND_ADDRESS=0.0.0.0\n" in deployment
    assert "ACERVO_ANKI_PORT=27801\n" in deployment
    assert "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n" in deployment
    assert "ACERVO_APP_PORT=27802\n" in deployment
    assert f"ACERVO_SERVER_DATA={root}/data/server\n" in deployment
    assert f"ACERVO_DOWNLOADS={root}/downloads\n" in deployment


def test_installer_moves_a_model_key_out_of_secrets_env(tmp_path: Path) -> None:
    """One variable defined in two files has a silent loser, and llm.env is passed last."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        secrets.read_text(encoding="utf-8") + "GEMINI_API_KEY='stranded-key'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "GEMINI_API_KEY" not in secrets.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=stranded-key\n" in (root / "llm.env").read_text(encoding="utf-8")
    # The move happens once and leaves nothing behind to move again.
    assert (root / "llm.env").read_text(encoding="utf-8").count("GEMINI_API_KEY") == 1


def test_reconfiguring_credentials_does_not_sign_every_device_out(tmp_path: Path) -> None:
    """The credential stream owns two lines. Rewriting the file wholesale would take the token
    signing secret with it and the next block would mint a fresh one — so reconfiguring the Anki
    password would sign out every device, for no reason anyone could have guessed."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=old\nACERVO_ANKI_SYNC_PASSWORD=old-password\n"
        "ACERVO_JWT_SECRET='the-secret-every-device-holds-a-token-from'\n"
        "ACERVO_OWNER_EMAIL=learner@account.example.com\n"
        "ACERVO_OWNER_PASSWORD=the-account-batch-jobs-write-through\n",
        encoding="utf-8",
    )
    credentials = tmp_path / "credentials"
    credentials.write_text("sync-user\nnew-password\n", encoding="utf-8")

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root), "--credentials-file", str(credentials),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    written = secrets.read_text(encoding="utf-8")
    assert "ACERVO_ANKI_SYNC_PASSWORD='new-password'" in written
    assert "ACERVO_JWT_SECRET='the-secret-every-device-holds-a-token-from'" in written
    assert written.count("ACERVO_JWT_SECRET") == 1
    # The account batch jobs write through survives too, for the same reason.
    assert "ACERVO_OWNER_PASSWORD=the-account-batch-jobs-write-through" in written
    assert written.count("ACERVO_ANKI_SYNC_PASSWORD") == 1


def test_installer_strips_the_retired_superuser_pair_and_mints_a_signing_secret(
    tmp_path: Path,
) -> None:
    """An already-deployed secrets.env carries a superuser that no longer exists, and the installer
    used to hard-fail without one. The strip erases itself; the signing secret is minted once and
    kept, because regenerating it signs out every device."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_PB_SUPERUSER_EMAIL=admin@account.example.com\n"
        "ACERVO_PB_SUPERUSER_PASSWORD=pb-password\n",
        encoding="utf-8",
    )

    def deploy() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(REPO_ROOT / "deploy/acervo/install.sh"),
                "--root", str(root),
                "--bind-address", "127.0.0.1", "--port", "27701",
                "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            ],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        )

    result = deploy()
    assert result.returncode == 0, result.stderr
    written = secrets.read_text(encoding="utf-8")
    assert "ACERVO_PB_SUPERUSER" not in written
    assert "ACERVO_ANKI_SYNC_PASSWORD=password" in written
    minted = re.search(r"^ACERVO_JWT_SECRET='([A-Za-z0-9]{16,})'$", written, flags=re.MULTILINE)
    assert minted, written

    # A second deployment neither re-strips nor re-mints: a new secret would sign out every device.
    assert deploy().returncode == 0
    again = secrets.read_text(encoding="utf-8")
    assert again.count("ACERVO_JWT_SECRET") == 1
    assert minted.group(1) in again


def run_installer(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )


def test_installer_retires_the_container_that_was_holding_the_app_port(tmp_path: Path) -> None:
    """Renaming the compose service left the old container running on an already-deployed server, and
    it still held the app port: the new one failed to bind with "port is already allocated". Compose
    calls it an orphan and warns rather than removing it."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    fake_docker_path(tmp_path, existing=("acervo-pocketbase-1",))

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    assert "acervo-pocketbase-1" in result.stdout
    assert "rm -f acervo-pocketbase-1" in log.read_text(encoding="utf-8")
    # The words in it are the owner's. An export is the documented way to carry them across, and
    # deleting the last copy on their behalf is not the installer's call.
    assert "rm -rf" not in log.read_text(encoding="utf-8")


def test_installer_discards_a_server_container_that_failed_to_bind(tmp_path: Path) -> None:
    """The nastier half of the same failure. A create that cannot bind leaves the container behind,
    and its host binding is never programmed — not on a later start, and not on a restart. Compose
    then finds a matching container, starts it, and reports success while nothing is published,
    because the healthcheck runs inside the container."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    fake_docker_path(tmp_path, existing=("acervo-server-1",))

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    assert "rm -f acervo-server-1" in log.read_text(encoding="utf-8")


def test_installer_refuses_to_call_an_unpublished_server_healthy(tmp_path: Path) -> None:
    """Asking the container whether it is healthy is not asking whether anyone can reach it."""
    env, root = deployment_env(tmp_path)
    fake_docker_path(tmp_path, published=False)

    result = run_installer(root, env)

    assert result.returncode == 1
    assert "port is not published" in result.stderr
    assert "docker rm -f acervo-server-1" in result.stderr
    # The claim it used to make regardless.
    assert "internal HTTP backend is healthy" not in result.stdout


def test_creating_an_account_goes_through_the_launcher_and_keeps_the_password_off_the_wire(
    tmp_path: Path,
) -> None:
    """The launcher already runs a streamed installer as root, so running one fixed command in one
    named container is a narrower privilege than it grants today, not a wider one. Refusing it only
    left the flag printing advice."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    stdin_log = tmp_path / "stdin.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo create-account'*) cat >>\"$ACERVO_TEST_STDIN_LOG\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_SSH_LOG"] = str(ssh_log)
    env["ACERVO_TEST_STDIN_LOG"] = str(stdin_log)

    result = subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--target", "deployer@server.example.test", "--create-account"],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        input="learner@account.example.com\nan-account-password\n",
    )

    assert result.returncode == 0, result.stderr
    commands = ssh_log.read_text(encoding="utf-8")
    assert "sudo -n /usr/local/sbin/deploy-acervo create-account" in commands
    # Positional on stdin, so neither the address nor the password is ever an argument.
    assert stdin_log.read_text(encoding="utf-8") == (
        "learner@account.example.com\nan-account-password\n"
    )
    assert "an-account-password" not in commands + result.stdout + result.stderr


def test_the_launcher_runs_the_account_command_in_the_container_without_naming_the_password(
    tmp_path: Path,
) -> None:
    helper = runnable_remote_helper(tmp_path)
    docker_log = tmp_path / "docker.log"
    stdin_log = tmp_path / "docker-stdin.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_DOCKER_LOG\"\n"
        "cat >>\"$ACERVO_TEST_STDIN_LOG\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_DOCKER_LOG"] = str(docker_log)
    env["ACERVO_TEST_STDIN_LOG"] = str(stdin_log)

    result = subprocess.run(
        [str(helper), "create-account"], env=env, text=True, capture_output=True, check=False,
        input="learner@account.example.com\nan-account-password\n",
    )

    assert result.returncode == 0, result.stderr
    asked = docker_log.read_text(encoding="utf-8")
    assert "exec -i acervo-server-1 python -m acervo.admin accounts create" in asked
    assert "--email learner@account.example.com" in asked
    # The password reaches the command on stdin and never as an argument, so it stays out of the
    # host's process list.
    assert "an-account-password" not in asked
    assert stdin_log.read_text(encoding="utf-8") == "an-account-password\n"


@pytest.mark.parametrize(
    "address",
    ["learner@account.example.com; rm -rf /", "learner@account.example.com'", "no-at-sign", ""],
)
def test_the_launcher_refuses_an_address_that_is_not_one(tmp_path: Path, address: str) -> None:
    """It is the one part of this that reaches a remote shell as text."""
    helper = runnable_remote_helper(tmp_path)
    result = subprocess.run(
        [str(helper), "create-account"], text=True, capture_output=True, check=False,
        input=f"{address}\nan-account-password\n",
    )
    assert result.returncode == 2
    assert "implausible shape" in result.stderr or "Missing account" in result.stderr


def test_a_finished_deployment_says_where_to_open_acervo(tmp_path: Path) -> None:
    """A summary that named a loopback port and a service id was not telling the operator the one
    thing they needed. The tailnet suffix is a property of the tailnet, so the deploying machine's
    answer is the server's answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *) cat >/dev/null 2>&1 || true ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        '  "status --json") printf \'{\\n  "MagicDNSSuffix": "tailexample.ts.net"\\n}\\n\' ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    env, _ = deployment_env(tmp_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target", "deployer@server.example.test",
            "--service", "acervo",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "https://acervo.tailexample.ts.net/" in result.stdout


def test_the_summary_says_the_shape_of_the_address_when_it_cannot_read_the_tailnet(
    tmp_path: Path,
) -> None:
    """Guessing is worse than saying where to look."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *) cat >/dev/null 2>&1 || true ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    # A `tailscale` that is present but says nothing useful, which is the same situation as none.
    tailscale = bin_dir / "tailscale"
    tailscale.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    tailscale.chmod(0o755)
    env, _ = deployment_env(tmp_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target", "deployer@server.example.test",
            "--service", "acervo",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "https://acervo.<your tailnet>.ts.net/" in result.stdout
    assert "tailscale status" in result.stdout


def run_configure_llm(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    # Hermetic: the real .acervo-deploy names a live server.
    env["ACERVO_DEPLOY_PROFILE"] = str(tmp_path / "absent-profile")
    return subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--local", "--configure-llm", *arguments],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False, input="a-key\n",
    )


def test_a_variable_name_that_looks_nothing_like_one_is_refused(tmp_path: Path) -> None:
    """Which names are allowed is the catalogue's business — the installer checks against the row
    list it was shipped. What this script can say on its own is that a name is shaped like one."""
    result = run_configure_llm(tmp_path, "--llm-set", "not a variable=x")
    assert result.returncode == 2
    assert "Unsafe LLM variable name" in result.stderr


def test_a_provider_id_that_is_merely_new_is_not_refused(tmp_path: Path) -> None:
    """No list of provider names lives in this script any more, so a row added to the catalogue
    tomorrow needs no change here. That is what replaced the old `gemini|vertex` whitelist."""
    result = run_configure_llm(tmp_path, "--llm-chain", "some-provider-invented-later")
    assert "some-provider-invented-later" not in result.stderr


def test_a_key_on_standard_input_needs_to_say_which_variable_it_is(tmp_path: Path) -> None:
    result = run_configure_llm(tmp_path, "--llm-api-key-stdin")
    assert result.returncode == 2
    assert "--llm-key" in result.stderr


def test_credentials_and_llm_are_configured_in_separate_commands(tmp_path: Path) -> None:
    result = run_configure_llm(
        tmp_path, "--configure-credentials", "--llm-chain", "gemini-free",
    )
    assert result.returncode == 2
    assert "separate commands" in result.stderr


def test_installer_updates_only_llm_env_and_preserves_both_provider_keys(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    original_secrets = (root / "secrets.env").read_bytes()

    def configure(contents: str) -> subprocess.CompletedProcess[str]:
        settings = tmp_path / "llm-credentials"
        settings.write_text(contents, encoding="utf-8")
        settings.chmod(0o600)
        return subprocess.run(
            [
                str(REPO_ROOT / "deploy/acervo/install.sh"),
                "--root", str(root),
                "--llm-credentials-file", str(settings),
                "--bind-address", "127.0.0.1", "--port", "27701",
                "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            ],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        )

    result = configure(
        "ACERVO_TEXT_CHAIN=cloudflare\n"
        "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n"
        "CLOUDFLARE_API_TOKEN=cloudflare-token\n"
    )
    assert result.returncode == 0, result.stderr
    result = configure("ACERVO_TEXT_CHAIN=gemini-free\nGEMINI_API_KEY=gemini-key\n")
    assert result.returncode == 0, result.stderr

    assert (root / "secrets.env").read_bytes() == original_secrets
    llm = (root / "llm.env").read_text(encoding="utf-8")
    assert "ACERVO_TEXT_CHAIN=gemini-free\n" in llm
    assert "GEMINI_API_KEY=gemini-key\n" in llm
    # The point of the whole file: switching provider keeps the other one's credentials, so
    # switching back does not mean minting a new key.
    assert "CLOUDFLARE_API_TOKEN=cloudflare-token\n" in llm
    assert "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n" in llm
    assert llm.count("ACERVO_TEXT_CHAIN") == 1
    assert (root / "llm.env").stat().st_mode & 0o777 == 0o600


def test_the_installer_refuses_a_variable_no_provider_reads(tmp_path: Path) -> None:
    """The replacement for the old `gemini|vertex` whitelist: a name has to belong to a row.

    A key written under a name nothing reads is the worst kind of misconfiguration — it deploys
    cleanly and the server is simply unable to build entries, with health blaming the variable that
    *is* missing.
    """
    env, root = deployment_env(tmp_path)
    settings = tmp_path / "llm-credentials"
    settings.write_text("NOT_A_PROVIDER_VARIABLE=x\n", encoding="utf-8")
    settings.chmod(0o600)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--llm-credentials-file", str(settings),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "not a variable any provider in the catalogue reads" in result.stderr


def test_remote_status_does_not_build_or_upload(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo status'*) printf 'state=running,health=healthy\\n0.0.0.0:27701\\n' ;;\n"
        "esac\n",
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
    assert "sudo -n /usr/local/sbin/deploy-acervo status" in commands
    assert "cat >" not in commands


def test_remote_helper_install_is_an_explicit_one_password_operation(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uploaded = tmp_path / "remote-helper.sh"
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in *'cat > /tmp/deploy-acervo-'*) cat >\"$ACERVO_TEST_HELPER\" ;; esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_HELPER": str(uploaded),
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--install-helper",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert uploaded.read_bytes() == (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_bytes()
    commands = ssh_log.read_text(encoding="utf-8")
    assert "sudo sh /tmp/deploy-acervo-" in commands
    assert "--install" in commands


def test_remote_helper_runs_the_packaged_installer_from_standard_input(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    root.mkdir()
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_JWT_SECRET='a-durable-signing-secret'\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)
    archive = Path(packaged(tmp_path))
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"

    # The Google credential rides through the launcher too, and it is the one credential that is a
    # file the whole way. The launcher only accepts it under the path the deployer streams it to,
    # so the test has to use that path rather than tmp_path.
    uploaded = Path(f"/tmp/acervo-google-credentials-{os.getpid()}")
    uploaded.write_text('{"type": "service_account", "client_email": "a@b.example.com"}',
                        encoding="utf-8")

    try:
        result = subprocess.run(
            [
                str(helper),
                "deploy",
                "--root",
                str(root),
                "--google-credentials-file",
                str(uploaded),
                "--bind-address",
                "127.0.0.1",
                "--port",
                "27701",
                "--app-bind-address",
                "127.0.0.1",
                "--app-port",
                "27702",
            ],
            env=env,
            input=archive.read_bytes(),
            capture_output=True,
            check=False,
        )
    finally:
        uploaded.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr.decode()
    assert (root / "deployment.env").exists()
    assert b"internal HTTP backend" in result.stdout
    installed = root / "credentials" / "google.json"
    assert installed.read_text(encoding="utf-8").startswith('{"type": "service_account"')
    assert installed.stat().st_mode & 0o777 == 0o600
    # The launcher removes what it was handed, so nothing sensitive is left in /tmp on the server.
    assert not uploaded.exists()


def test_the_launcher_refuses_a_credential_path_it_did_not_expect(tmp_path: Path) -> None:
    """The launcher runs as root out of sudoers, so every path it is handed is checked against the
    shape the deployer would have written — the same guard the other two credentials already have."""
    helper = runnable_remote_helper(tmp_path)
    elsewhere = tmp_path / "google.json"
    elsewhere.write_text('{"type": "service_account"}', encoding="utf-8")
    result = subprocess.run(
        [
            str(helper), "deploy", "--root", str(tmp_path / "acervo"),
            "--google-credentials-file", str(elsewhere),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "Unexpected Google credentials path" in result.stderr


def test_the_launcher_protocol_matches_the_deployer() -> None:
    """The two numbers are how a server learns its installed launcher is stale. Letting them drift
    means a launcher fix is written, shipped, and never installed — which is exactly how
    `--google-credentials-file` reached a launcher that had never heard of it."""
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    deployer = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    spoken = re.search(r"^PROTOCOL=(\d+)$", helper, re.MULTILINE)
    expected = re.search(r"^helper_protocol=(\d+)$", deployer, re.MULTILINE)
    assert spoken and expected
    assert spoken.group(1) == expected.group(1)


def test_every_installer_flag_the_deployer_forwards_is_one_the_launcher_accepts() -> None:
    """The launcher is a middle hop with its own allow-list, and a flag added at both ends but not
    in the middle fails only on a real server, at the end of a full release build."""
    deployer = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    # Only the remote half. `--local` runs the installer directly and legitimately passes
    # `--credentials-stdin`, which the launcher has no reason to know about.
    remote = deployer[deployer.index("remote_installer="):]
    accepted = set(re.findall(r"^\s+(--[a-z-]+)\)", helper, re.MULTILINE))
    forwarded = set(re.findall(r"installer_arguments\s+(--[a-z-]+)", remote))
    forwarded |= set(re.findall(r"credential_args=[\"']?(--[a-z-]+)", remote))
    forwarded |= set(re.findall(r"credential_args\s+(--[a-z-]+)", remote))
    assert forwarded, "the pattern stopped matching; this test is no longer checking anything"
    assert forwarded <= accepted, f"the launcher rejects {sorted(forwarded - accepted)}"


def test_deploy_profile_supports_legacy_format_defaults_and_cli_precedence(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in *'deploy-acervo check'*) printf 'helper\\n' ;; esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    profile = tmp_path / ".acervo-deploy"
    profile.write_text("deployer@server.example.test\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_DEPLOY_PROFILE": str(profile),
        }
    )

    legacy = subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--configure-https"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert legacy.returncode == 0, legacy.stderr
    assert "--https-port 27702 --app-port 27702" in ssh_log.read_text(encoding="utf-8")

    profile.write_text(
        "DEPLOY_TARGET=deployer@server.example.test\n"
        "ACERVO_ROOT=/volume1/docker/acervo\n"
        "ACERVO_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_ANKI_PORT=27801\n"
        "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_APP_PORT=27802\n"
        "ACERVO_HTTPS_PORT=27803\n",
        encoding="utf-8",
    )
    ssh_log.write_text("", encoding="utf-8")
    overridden = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--configure-https",
            "--app-port",
            "27902",
            "--https-port",
            "27903",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert overridden.returncode == 0, overridden.stderr
    assert "--https-port 27903 --app-port 27902" in ssh_log.read_text(encoding="utf-8")

    saved_profile = tmp_path / "saved-acervo-deploy"
    env["ACERVO_DEPLOY_PROFILE"] = str(saved_profile)
    saved = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "--https-port",
            "27903",
            "--remember-target",
            "--status",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert saved.returncode == 0, saved.stderr
    assert saved_profile.stat().st_mode & 0o777 == 0o600
    assert saved_profile.read_text(encoding="utf-8") == (
        "DEPLOY_TARGET=deployer@server.example.test\n"
        "ACERVO_ROOT=/volume1/docker/acervo\n"
        "ACERVO_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_ANKI_PORT=27701\n"
        "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_APP_PORT=27702\n"
        "ACERVO_HTTPS_PORT=27903\n"
        "ACERVO_SERVICE=\n"
    )


def test_configure_https_is_additive_idempotent_and_collision_safe(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    existing = (
        "https://server.example.com (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8080\n\n"
        "https://server.example.com:8091 (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8090\n\n"
        "https://server.example.com:8443 (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8000\n"
    )
    bin_dir, state, log = fake_tailscale_path(tmp_path, existing)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    added = subprocess.run(
        [str(helper), "configure-https", "--https-port", "27702", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --bg --yes --https=27702 http://127.0.0.1:27702\n"
    )
    assert state.read_text(encoding="utf-8").startswith(existing)

    log.write_text("", encoding="utf-8")
    repeated = subprocess.run(
        [str(helper), "configure-https", "--https-port", "27702", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "already exists" in repeated.stdout
    assert log.read_text(encoding="utf-8") == ""

    occupied = subprocess.run(
        [str(helper), "configure-https", "--https-port", "8091", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert occupied.returncode == 1
    assert "Refusing to replace" in occupied.stderr
    assert log.read_text(encoding="utf-8") == ""


def test_configure_https_publishes_a_service_on_its_own_443(tmp_path: Path) -> None:
    """A service's 443 is its own virtual IP's, so it neither claims the host's nor collides with
    another service. This is what lets Android mint a WebAPK and install Acervo alongside another
    self-hosted app rather than replacing it."""
    helper = runnable_remote_helper(tmp_path)
    neighbour = '{"svc:calorie-logger":{"proxy":"http://127.0.0.1:8090"}}\n'
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, neighbour)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    added = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --service=svc:acervo --bg --yes --https=443 http://127.0.0.1:27702\n"
    )
    # The neighbouring service is left exactly as it was.
    assert state.read_text(encoding="utf-8").startswith(neighbour)

    log.write_text("", encoding="utf-8")
    repeated = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "already exists" in repeated.stdout
    assert log.read_text(encoding="utf-8") == ""


def test_configure_https_refuses_a_service_name_that_is_not_a_bare_label(tmp_path: Path) -> None:
    """`svc:` is reference syntax for the policy file and the CLI, never part of the name itself."""
    helper = runnable_remote_helper(tmp_path)
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, "{}\n")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    for rejected in ("svc:acervo", "Acervo", "acervo app", ""):
        result = subprocess.run(
            [str(helper), "configure-https", "--service", rejected, "--app-port", "27702"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2, rejected
        # Rejected before Tailscale is invoked at all, so the log is never even created.
        assert not log.exists()


def test_configure_https_reports_a_tailscale_too_old_to_host_a_service(tmp_path: Path) -> None:
    """Services arrived in 1.86.0. An older client answers --service with its whole usage screen,
    which reads like a bug here rather than a server that needs updating."""
    helper = runnable_remote_helper(tmp_path)
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, "{}\n", version="1.78.1")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    stale = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stale.returncode == 1
    assert "1.86.0 or later is required" in stale.stderr
    assert "--https-port" in stale.stderr
    assert not log.exists()


def test_explicit_port_443_is_allowed_but_cannot_replace_an_existing_service(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    occupied_status = (
        "https://server.example.com (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8080\n"
    )
    bin_dir, state, log = fake_tailscale_path(tmp_path, occupied_status)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    occupied = subprocess.run(
        [str(helper), "configure-https", "--https-port", "443", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert occupied.returncode == 1
    assert log.exists() is False

    state.write_text("", encoding="utf-8")
    allowed = subprocess.run(
        [str(helper), "configure-https", "--https-port", "443", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert allowed.returncode == 0, allowed.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --bg --yes --https=443 http://127.0.0.1:27702\n"
    )


def test_remote_robot_wrapper_streams_validated_input_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    helper_upload = tmp_path / "run-worker.sh"
    input_upload = tmp_path / "input.tar.gz"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'cat > /tmp/acervo-run-worker-'*) cat >\"$ACERVO_TEST_HELPER\" ;;\n"
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
    assert helper_upload.read_bytes() == (REPO_ROOT / "deploy/acervo/run-worker.sh").read_bytes()
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


def test_app_and_anki_ports_are_distinct_and_collisions_are_rejected(tmp_path: Path) -> None:
    compose = (REPO_ROOT / "deploy/acervo/compose.yaml").read_text(encoding="utf-8")
    assert "${ACERVO_ANKI_PORT:-27701}:8080" in compose
    assert "${ACERVO_APP_PORT:-27702}:8000" in compose
    # The installer asks `docker port` about the same container port to check that publishing
    # actually happened, so the two statements of it have to agree. They disagree loudly rather than
    # quietly — an unanswered `docker port` fails the deployment — but agreeing is cheaper.
    installer = (REPO_ROOT / "deploy/acervo/install.sh").read_text(encoding="utf-8")
    assert 'docker port "$compose_project-server-1" 8000' in installer

    env, _ = deployment_env(tmp_path)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--local",
            "--port",
            "27800",
            "--app-port",
            "27800",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "must differ" in result.stderr


def test_shared_host_guardrails_are_documented_and_global_serve_mutations_are_absent() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = (REPO_ROOT / "docs/acervo-app.md").read_text(encoding="utf-8")
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    combined = readme + docs

    assert "shared host" in combined.lower()
    assert "never assume" in combined
    assert "--https-port" in combined
    assert "serve --bg http://127.0.0.1:27702" not in combined
    assert "serve reset" not in helper
    assert "serve off" not in helper


def test_a_google_credential_that_is_not_one_is_refused_before_it_is_deployed(tmp_path: Path) -> None:
    """Vertex does not authenticate from a variable, so this is a file — and a file is the one kind
    of credential that can be plausibly wrong: an API key pasted into a file, the wrong export,
    something else entirely. Discovering that at the first capture costs a deployment cycle."""
    wrong = tmp_path / "not-a-key.json"
    wrong.write_text('{"api_key": "AIzaSyNotAKeyFile"}', encoding="utf-8")
    result = run_configure_llm(tmp_path, "--google-credentials", str(wrong))
    assert result.returncode == 2
    assert "neither a service-account key nor an" in result.stderr


@pytest.mark.parametrize("kind", ["service_account", "authorized_user"])
def test_both_shapes_google_actually_writes_are_accepted(tmp_path: Path, kind: str) -> None:
    """A key, and the file `gcloud auth application-default login` writes. Refusing the second would
    mean the one-command path that already works on a workstation could not reach the server."""
    good = tmp_path / "creds.json"
    good.write_text(f'{{"type": "{kind}", "client_email": "acervo-vertex@personal.example.com"}}',
                    encoding="utf-8")
    result = run_configure_llm(tmp_path, "--google-credentials", str(good))
    assert "neither a service-account key" not in result.stderr


def test_a_google_credential_is_installed_beside_the_env_file_and_named_from_inside(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    key = tmp_path / "google.json"
    key.write_text('{"type": "service_account", "project_id": "p"}', encoding="utf-8")
    settings = tmp_path / "llm-credentials"
    settings.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/run/acervo/credentials/google.json\n", encoding="utf-8"
    )
    settings.chmod(0o600)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--llm-credentials-file", str(settings),
            "--google-credentials-file", str(key),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    installed = root / "credentials" / "google.json"
    assert installed.read_text(encoding="utf-8").startswith('{"type": "service_account"')
    assert installed.stat().st_mode & 0o777 == 0o600
    # The variable names the path the container will read, not the one it was uploaded from.
    llm = (root / "llm.env").read_text(encoding="utf-8")
    assert "GOOGLE_APPLICATION_CREDENTIALS=/run/acervo/credentials/google.json\n" in llm


def test_the_credentials_directory_exists_even_when_no_key_is_configured(tmp_path: Path) -> None:
    """A bind mount of a path that does not exist makes a root-owned directory instead, and the
    container then fails in a way that has nothing to do with the missing credential."""
    env, root = deployment_env(tmp_path)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "credentials").is_dir()
    assert "ACERVO_CREDENTIALS=" in (root / "deployment.env").read_text(encoding="utf-8")

"""The remote deployment builds its images from a packaged archive, not from a checkout.

So a directory a Dockerfile copies but the packaging script does not bundle builds fine locally and
fails on the server with `"/prompts": not found` — after the upload, at the least convenient moment.
Keeping the two lists in step is what this checks.
"""

import base64
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[3]
# Both images are built from the packaged archive, so both have to be checked. The worker one was
# added with the dictionary compiler, which copies `dictionaries/` for the catalogue.
DOCKERFILES = (
    ROOT / "deploy" / "acervo" / "server" / "Dockerfile",
    ROOT / "deploy" / "acervo" / "Dockerfile",
    # The corpus service, built from the pinned wheel in `vendor/speech/`. A Dockerfile absent from
    # this tuple is simply not checked, so the COPY-path guarantee stops applying without failing.
    ROOT / "deploy" / "acervo" / "speech" / "Dockerfile",
)
PACKAGER = ROOT / "scripts" / "package_acervo_server.sh"


def bundled_directories() -> set[str]:
    """What the tarball actually contains.

    The staged copy and the archive list are two statements of the same thing, so they are checked
    against each other first: copying a directory into the staging area but leaving it out of the tar
    is the same bug one step later.
    """
    script = PACKAGER.read_text()
    listed = re.search(r"^for directory in ([^;]+); do$", script, flags=re.MULTILINE)
    archived = re.search(r'^archive_entries="([^"]+)"$', script, flags=re.MULTILINE)
    assert listed and archived, "could not read the bundle contents out of the packaging script"
    entries = set(archived.group(1).split())
    assert set(listed.group(1).split()) <= entries, "a copied directory is missing from the archive"
    return entries


def image_sources() -> set[str]:
    sources = set()
    for dockerfile in DOCKERFILES:
        for source, _destination in re.findall(r"^COPY\s+(\S+)\s+(\S+)$", dockerfile.read_text(),
                                               flags=re.MULTILINE):
            if source.startswith("--"):
                continue
            sources.add(PurePosixPath(source).parts[0])
    assert sources, "expected the Dockerfiles to copy something from the build context"
    return sources


def test_every_directory_the_image_copies_is_in_the_release_bundle():
    missing = image_sources() - bundled_directories()
    assert not missing, (
        f"{sorted(missing)} are copied by a deployment image but not packaged by "
        f"{PACKAGER.name}, so a remote deployment cannot build"
    )


def test_the_dictionary_catalogue_is_packaged_and_readable():
    """The worker image reads the catalogue at build time; an unpackaged one fails the same way."""
    assert "dictionaries" in bundled_directories()
    catalogue = json.loads((ROOT / "dictionaries" / "catalogue.json").read_text())
    assert catalogue["dictionaries"], "the shipped catalogue is empty"


def test_the_provider_catalogue_is_packaged_and_readable():
    """The service reads it on every capture and on every health check, so an unpackaged catalogue
    is a 500 on the first word rather than a build failure."""
    assert "models" in bundled_directories()
    catalogue = json.loads((ROOT / "models" / "catalogue.json").read_text())
    assert catalogue["providers"], "the shipped provider catalogue is empty"


def test_the_capture_prompts_are_packaged_and_named_as_the_service_reads_them():
    """The service reads prompts by name at request time; a renamed file is a runtime failure."""
    assert "prompts" in bundled_directories()
    named = set()
    for source in (ROOT / "src" / "acervo").rglob("*.py"):
        # Up to the name and no further: a call may pass options after it, and a pattern that
        # demanded the closing paren would stop matching — silently, which is the failure this
        # whole test exists to prevent.
        named.update(re.findall(r'prompt_text\([^,]+,\s*"([a-z_]+)"', source.read_text()))
    assert named, "expected the capture service to read prompts by name"
    for name in named:
        assert (ROOT / "prompts" / f"{name}.md").is_file(), f"prompts/{name}.md is missing"


def test_both_images_leave_their_own_files_readable_by_the_user_they_run_as():
    """The installer extracts a release under `umask 077` and `COPY` makes the result root-owned, so
    an image built from a release has owner-only files. Both containers run as the deploying user,
    which would then be unable to read its own entry point."""
    for dockerfile in DOCKERFILES:
        source = dockerfile.read_text()
        assert "chmod -R a+rX /app" in source, (
            f"{dockerfile} copies files a non-root container could not read"
        )


def test_the_suite_never_writes_the_archive_a_deployment_streams():
    """A regression test for a *deployment* failure, not a test failure.

    The packager used to write a fixed `build/acervo-server.tar.gz`, and these tests wrote it too —
    so running the suite during a `./deploy.sh` rewrote the archive while it was being streamed. The
    remote found a complete gzip stream with another process's bytes after it, reported trailing
    garbage and a tar child status 2, and failed with "the release archive has no Acervo installer":
    a message with nothing in it pointing at a second writer.

    Asserted against the environment every test here actually runs in, rather than against the text
    of a file: `conftest.py` sets this on `os.environ`, so it reaches the packager whether a test
    runs it directly or runs `deploy.sh`, which packages before it streams.
    """
    assert "ACERVO_PACKAGE_ARCHIVE" in PACKAGER.read_text(encoding="utf-8"), \
        "the archive path must be overridable"

    redirected = os.environ.get("ACERVO_PACKAGE_ARCHIVE", "")
    assert redirected, "conftest must redirect packaging away from build/"
    assert not Path(redirected).is_relative_to(ROOT / "build")


def test_the_lockfile_pins_the_released_tarball_rather_than_a_local_build():
    """The npm lockfile and `pin.json` have to name the same bytes, and they can drift silently.

    `npm pack` gzips with the building Node's zlib, so a tarball built on a laptop and the one
    attached to the release differ byte for byte while carrying identical contents. `pin.json`
    learned that once and switched to the release's digests; the lockfile was left behind, holding
    the integrity of a local build.

    Nothing caught it locally, because npm resolves a `file:` dependency from its cache when the
    integrity matches something already there. CI has no cache, hashed the file on disk, and failed
    the install with `EINTEGRITY` — after the push, at the least convenient moment.
    """
    pin = json.loads((ROOT / "deploy" / "acervo" / "speech" / "pin.json").read_text(encoding="utf-8"))
    tarball = ROOT / "vendor" / "speech" / pin["artifacts"]["react"]["file"]
    if not tarball.exists():
        pytest.skip("run scripts/fetch_speech.sh first; vendor/ is untracked on purpose")

    raw = tarball.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["artifacts"]["react"]["sha256"], (
        "vendor/ holds a tarball the pin does not name; re-run scripts/fetch_speech.sh --force"
    )

    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    entry = lock["packages"]["node_modules/@spoken-usage-retrieval/react"]
    expected = "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()
    assert entry["integrity"] == expected, (
        "web/package-lock.json pins a different build of the player than pin.json does. "
        "Fetch the release's tarball and re-lock; do not take the digest from a local `npm pack`."
    )

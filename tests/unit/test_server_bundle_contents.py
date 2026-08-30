"""The remote deployment builds the PocketBase image from a packaged archive, not from a checkout.

So a directory the Dockerfile copies but the packaging script does not bundle builds fine locally
and fails on the server with `"/prompts": not found` — after the upload, at the least convenient
moment. Keeping the two lists in step is what this checks.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy" / "acervo" / "pocketbase" / "Dockerfile"
PACKAGER = ROOT / "scripts" / "package_acervo_server.sh"


def bundled_directories() -> set[str]:
    script = PACKAGER.read_text()
    listed = re.search(r"^for directory in ([^;]+); do$", script, flags=re.MULTILINE)
    archived = re.search(r'^archive_entries="([^"]+)"$', script, flags=re.MULTILINE)
    assert listed and archived, "could not read the bundle contents out of the packaging script"
    copied = set(listed.group(1).split())
    # Copying a directory into the staging area but leaving it out of the tar is the same bug one
    # step later, so both lists have to agree.
    assert copied <= set(archived.group(1).split()), "a copied directory is missing from the archive"
    return copied


def image_sources() -> set[str]:
    sources = set()
    for source, _destination in re.findall(r"^COPY\s+(\S+)\s+(\S+)$", DOCKERFILE.read_text(), flags=re.MULTILINE):
        if source.startswith("--"):
            continue
        sources.add(pathlib.PurePosixPath(source).parts[0])
    assert sources, "expected the Dockerfile to copy something from the build context"
    return sources


def test_every_directory_the_image_copies_is_in_the_release_bundle():
    missing = image_sources() - bundled_directories()
    assert not missing, (
        f"{sorted(missing)} are copied by the PocketBase image but not packaged by "
        f"{PACKAGER.name}, so a remote deployment cannot build"
    )


def test_the_capture_prompts_are_packaged_and_named_as_the_hook_reads_them():
    """The hook reads prompts by name at request time; a renamed file is a runtime failure."""
    assert "prompts" in bundled_directories()
    hook = (ROOT / "deploy" / "acervo" / "pocketbase" / "pb_hooks" / "acervo.js").read_text()
    for name in re.findall(r'promptText\("([a-z_]+)"\)', hook):
        assert (ROOT / "prompts" / f"{name}.txt").is_file(), f"prompts/{name}.txt is missing"

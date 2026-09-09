"""The remote deployment builds its images from a packaged archive, not from a checkout.

So a directory a Dockerfile copies but the packaging script does not bundle builds fine locally and
fails on the server with `"/prompts": not found` — after the upload, at the least convenient moment.
Keeping the two lists in step is what this checks.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
# Both images are built from the packaged archive, so both have to be checked. The worker one was
# added with the dictionary compiler, which copies `dictionaries/` for the catalogue.
DOCKERFILES = (
    ROOT / "deploy" / "acervo" / "server" / "Dockerfile",
    ROOT / "deploy" / "acervo" / "Dockerfile",
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
            sources.add(pathlib.PurePosixPath(source).parts[0])
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


def test_the_capture_prompts_are_packaged_and_named_as_the_service_reads_them():
    """The service reads prompts by name at request time; a renamed file is a runtime failure."""
    assert "prompts" in bundled_directories()
    named = set()
    for source in (ROOT / "src" / "acervo").rglob("*.py"):
        named.update(re.findall(r'prompt_text\([^,]+,\s*"([a-z_]+)"\)', source.read_text()))
    assert named, "expected the capture service to read prompts by name"
    for name in named:
        assert (ROOT / "prompts" / f"{name}.txt").is_file(), f"prompts/{name}.txt is missing"

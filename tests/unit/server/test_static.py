"""The three static surfaces, their two auth policies, and byte ranges on both file mounts.

Range is not a nicety here: the dictionary reader reads artifacts by byte range, so a dictionary the
device does not hold is read over the network by the same code that reads a stored one.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def published(server):
    (server.downloads / "Acervo-test.zip").write_bytes(b"test archive bytes")
    (server.downloads / "release.json").write_text(
        json.dumps(
            {
                "version": "1.4.2",
                "build": "218",
                "file": "Acervo-test.zip",
                "size": 18,
                "sha256": "a" * 64,
            }
        )
    )
    (server.dictionaries / "cc-cedict.dict").write_bytes(b"packed dictionary bytes")
    (server.web / "index.html").write_text("<!doctype html><title>Acervo</title>")
    (server.web / "manifest.webmanifest").write_text('{"name":"Acervo"}')
    return server


def test_a_download_answers_a_byte_range_without_any_credentials(published):
    """The macOS updater fetches with no credentials and reads the archive in chunks."""
    answer = published.client.get(
        "/api/acervo/downloads/Acervo-test.zip", headers={"Range": "bytes=0-1"}
    )
    assert answer.status_code == 206
    assert answer.content == b"te"


def test_a_whole_download_carries_its_length(published):
    answer = published.client.get("/api/acervo/downloads/Acervo-test.zip")
    assert answer.status_code == 200
    assert answer.headers["content-length"] == "18"


def test_a_dictionary_artifact_needs_the_owner_signed_in_and_then_answers_a_range(published):
    """Closed because the service worker must not precache tens of MiB, and because the data is
    third-party and mostly share-alike."""
    anonymous = published.client.get("/api/acervo/dictionaries/cc-cedict.dict")
    assert anonymous.status_code == 401

    ranged = published.client.get(
        "/api/acervo/dictionaries/cc-cedict.dict",
        headers={**published.auth, "Range": "bytes=0-1"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"pa"

    whole = published.client.get("/api/acervo/dictionaries/cc-cedict.dict", headers=published.auth)
    assert whole.headers["content-length"] == "23"


@pytest.mark.parametrize("escape", ["../acervo.db", "..%2Facervo.db", "subdir/../../acervo.db"])
def test_a_path_that_climbs_out_of_the_directory_is_a_404(published, escape):
    """PocketBase's directory filesystem gave this for free; here it has to be written down."""
    answer = published.client.get(f"/api/acervo/downloads/{escape}")
    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "not_found"


def test_the_application_is_served_at_the_root_and_an_unknown_path_falls_back_to_it(published):
    root = published.client.get("/")
    assert root.status_code == 200
    assert "<title>Acervo</title>" in root.text

    asset = published.client.get("/manifest.webmanifest")
    assert asset.status_code == 200
    assert asset.json() == {"name": "Acervo"}

    # A client-side route, not a missing file.
    deep = published.client.get("/words/picar")
    assert deep.status_code == 200
    assert "<title>Acervo</title>" in deep.text


def test_an_unknown_api_path_is_a_refusal_rather_than_the_application_shell(published):
    """The interface reads a body without `data` as a failure; HTML with a 200 is neither."""
    answer = published.client.get("/api/acervo/v1/nope")
    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "not_found"


def test_the_service_starts_and_serves_with_no_downloads_or_dictionaries_directory(server, tmp_path):
    """A release without a published Mac application, or a server with no compiled dictionaries, is
    an ordinary state and not a reason to fail to start."""
    import shutil

    shutil.rmtree(server.downloads)
    shutil.rmtree(server.dictionaries)

    assert server.client.get("/api/acervo/v1/health").status_code == 200
    assert server.client.get("/api/acervo/v1/mac-release").json() == {"data": None}
    assert server.get("/dictionaries").json() == {"data": {"dictionaries": []}}
    assert server.client.get("/api/acervo/downloads/anything.zip").status_code == 404


def test_the_release_manifest_points_at_the_open_download_route(published):
    answer = published.client.get("/api/acervo/v1/mac-release")
    assert answer.status_code == 200
    assert answer.json()["data"] == {
        "version": "1.4.2",
        "build": "218",
        "file": "Acervo-test.zip",
        "size": 18,
        "sha256": "a" * 64,
        "url": "/api/acervo/downloads/Acervo-test.zip",
    }


def test_an_incomplete_release_manifest_is_no_release_rather_than_a_broken_one(published):
    """The Mac host decodes `MacRelease?`, so null is an answer it handles and an error is not."""
    (published.downloads / "release.json").write_text(json.dumps({"version": "1.4.2"}))
    assert published.client.get("/api/acervo/v1/mac-release").json() == {"data": None}

"""One rule for every test here: packaging never writes what a deployment streams.

The packager used to write a fixed `build/acervo-server.tar.gz`, and so did these tests — directly,
and through `deploy.sh`, which packages before it streams. Running the suite during a real
`./deploy.sh` therefore rewrote the archive mid-transfer. The remote found a complete gzip stream
with another process's bytes after it and failed with "the release archive has no Acervo installer",
which names nothing that happened; the same collision had already been dismissed three times as
"two test runs at once".

Set here rather than at each call site because there are seventeen of them, every one builds its own
environment with `os.environ.copy()`, and the eighteenth would forget. Setting it on `os.environ`
means every copy inherits it, whether the test runs the packager or `deploy.sh`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def package_into_the_tests_own_directory(tmp_path_factory, monkeypatch):
    archive = tmp_path_factory.mktemp("release") / "acervo-server.tar.gz"
    monkeypatch.setenv("ACERVO_PACKAGE_ARCHIVE", str(archive))
    return archive

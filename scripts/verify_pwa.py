#!/usr/bin/env python3
"""Verify the built Acervo PWA without starting a server."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"


def main() -> None:
    manifest_path = DIST / "manifest.webmanifest"
    assert manifest_path.is_file(), "build the web application first"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "Acervo"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "."
    purposes = {icon.get("purpose", "any") for icon in manifest["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in manifest["icons"]:
        assert (DIST / icon["src"]).is_file(), f"missing {icon['src']}"

    index = (DIST / "index.html").read_text(encoding="utf-8")
    assert "<title>Acervo</title>" in index
    assert re.search(r'(?:src|href)="\./', index), "assets must be relative for the native host"

    service_worker = (DIST / "sw.js").read_text(encoding="utf-8")
    assert "index.html" in service_worker
    assert '"SKIP_WAITING"' in service_worker, (
        "the waiting worker must activate only after the explicit update message"
    )
    assert "clientsClaim" not in service_worker, "updates must remain explicit"
    assert r"/^\/api\//" in service_worker and r"/^\/_\//" in service_worker
    assert not any(path.suffix == ".zip" for path in DIST.rglob("*")), (
        "native downloads must not be staged into the PWA"
    )

    print("Acervo PWA verification passed")


if __name__ == "__main__":
    main()

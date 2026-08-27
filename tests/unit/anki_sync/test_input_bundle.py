from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_input_bundle_contains_only_manifest_and_referenced_media(tmp_path: Path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "image.webp").write_bytes(b"image")
    (media / "audio.mp3").write_bytes(b"audio")
    (tmp_path / "unrelated-private-file.txt").write_text("exclude", encoding="utf-8")
    manifest = tmp_path / "source.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "notes": [
                    {
                        "note_id": "813c6a14-d3ec-4f62-9ce6-e90cae322f70",
                        "lexeme_id": "5eca9c9c-ae4e-44dc-b26c-27efeaeb7387",
                        "deck": "Test",
                        "sentence": "Test",
                        "translation": "Test",
                        "tags": ["acervo::test"],
                        "image_path": "media/image.webp",
                        "audio_path": "media/audio.mp3",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "input.tar.gz"

    subprocess.run(
        [
            str(REPO_ROOT / "scripts/package_anki_sync_input.py"),
            str(manifest),
            str(output),
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    with tarfile.open(output) as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == [
        "manifest.json",
        "media/audio.mp3",
        "media/image.webp",
    ]
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(member.uname == "" and member.gname == "" for member in members)

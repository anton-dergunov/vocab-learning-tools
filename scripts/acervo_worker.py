#!/usr/bin/env python3
"""Acervo's own server-side work, in one place.

PocketBase is a database and the Anki sync server is Anki's; this is the part that is Acervo's.
Today that is the Anki robot and the dictionary compiler, and it grows from here — generation,
media, and whatever else runs behind the scenes. Keeping it one entry point rather than a service
per job is deliberate: these are one-shot commands run through `docker compose run --rm`, so a new
job is a new subcommand and never a new container.

    acervo_worker.py anki push /input/runs/<id>/manifest.json
    acervo_worker.py dictionary build --id cc-cedict
"""

from __future__ import annotations

import sys

USAGE = "usage: acervo_worker.py {anki|dictionary} ...\n"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        sys.stderr.write(USAGE)
        return 0 if arguments else 2
    job, rest = arguments[0], arguments[1:]
    if job == "anki":
        from acervo.anki_sync.cli import main as anki_main

        return anki_main(rest)
    if job == "dictionary":
        from acervo.dictionaries.cli import main as dictionary_main

        return dictionary_main(rest)
    sys.stderr.write(f"unknown job {job!r}\n{USAGE}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

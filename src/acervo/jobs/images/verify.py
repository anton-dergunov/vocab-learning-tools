"""Is this run directory safe to import?

Phase B writes these records into the graph and copies these files onto the server, so a mismatch
between the two becomes a broken `imageRef` in the database. Everything checked here is an invariant
the run is supposed to maintain, so a failure means a bug in this package rather than a bad run.

Every drawn file is read, to check that its reference names the bytes it actually holds. That is the
cost of an explicit gate run once before a publish, and it is where the cost belongs: nothing else
would notice a file swapped in the run directory after it was drawn.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from acervo.images.ids import ID_LENGTH, image_prompt_id, image_reference
from .run import Store

RECORD_ID = re.compile(rf"^[a-z0-9]{{{ID_LENGTH}}}$")


@dataclass
class Report:
    images: int = 0
    records: int = 0
    drawn: int = 0
    refused: int = 0
    blocked: int = 0
    problems: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @property
    def ok(self) -> bool:
        return not self.problems

    def fault(self, kind: str, subject: str) -> None:
        self.problems[kind].append(subject)


def verify(store: Store) -> Report:
    report = Report()
    records = {}
    for path in sorted(store.records.glob("*.json")):
        record = store.read(path)
        if record is None or "id" not in record:
            report.fault("unreadable record", path.name)
            continue
        if path.stem != record["id"]:
            report.fault("filename does not match its id", path.name)
        records[record["id"]] = record
    images = {path.stem for path in store.images.glob("*.webp")}
    report.records, report.images = len(records), len(images)
    report.refused = len(list(store.refusals.glob("*.json")))

    by_sense: dict[str, list[str]] = defaultdict(list)
    for identifier, record in records.items():
        if not RECORD_ID.match(identifier):
            report.fault("id is not 15 lowercase alphanumerics", identifier)
        sense = str(record.get("senseId") or "")
        by_sense[sense].append(identifier)
        # The id is derived, not drawn, which is what makes the run resumable from the filesystem.
        if sense and image_prompt_id(sense) != identifier:
            report.fault("id is not derived from its senseId", identifier)
        if record.get("blocked"):
            report.blocked += 1
        if record.get("imageRef"):
            report.drawn += 1
            if identifier not in images:
                report.fault("record claims an image that is not on disk", identifier)
            elif record["imageRef"] != image_reference(
                str(record.get("lexemeId") or ""), identifier,
                store.image_path(identifier).read_bytes(),
            ):
                # The strongest form of the mismatch this module exists to catch: the reference
                # carries a digest of the bytes, so a file replaced after it was drawn — or a record
                # copied from another run — is caught here rather than becoming a picture the owner
                # is served under a name that promises different bytes.
                report.fault("reference does not name the bytes on disk", identifier)
        elif identifier in images:
            report.fault("image on disk whose record claims none", identifier)

    for sense, identifiers in by_sense.items():
        if len(identifiers) > 1:
            report.fault("one sense with several records", sense)
    for orphan in sorted(images - set(records)):
        report.fault("image with no record", orphan)
    for path in store.images.glob("*.webp"):
        if path.stat().st_size == 0:
            report.fault("zero-byte image", path.stem)
    return report

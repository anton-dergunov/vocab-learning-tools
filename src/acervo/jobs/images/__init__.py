"""The unattended half of sense images: a run directory, a sweep, and an import.

The pipeline itself moved to `acervo.images`, which stands alone so that a route can call it. What
is left here is everything that is genuinely batch work: `run.py`'s `Store` — the run directory that
*is* the queue, since a job's state is a file on disk and an id derived from its `senseId` — plus the
concurrent runner, the pre-import check, the contact sheet, and `publish.py`, which lands a finished
laptop run into the graph and the media directory.

Like every job, this writes the graph through `acervo.client` against the service's own route, so a
batch write gets the same validation and the same revision allocation as a phone.
"""

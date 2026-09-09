"""One-shot batch work, run by `acervo-worker`.

Asynchronous by definition: images, audio, the Anki push and FSRS pull, corpus harvest and indexing,
export, and the sweeps. `api/` may not import this package — capture, review and the sync API must
work with the orchestrator down and must not know one exists.

These are plain functions with CLI entry points, not queue consumers: "which lexemes lack an image"
is a query against the graph, not a queue to drain. If an orchestrator is ever adopted it is a
wrapper that calls them, never something they import.

A job writes the graph through `acervo.client`, against the service's own route — same validation and
same revision allocation as a phone.
"""

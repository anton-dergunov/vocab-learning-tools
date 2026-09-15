"""Experiments, spikes and benchmark tooling. Never imported by the service.

Outside `src/` on purpose, and outside the distribution: nothing that ships needs it, and
`pyproject.toml`'s `where = ["src"]` is what keeps it out. It is reached in development through
`pytest.ini`'s `pythonpath = .`, the same way `scripts/` is.

`image_benchmark_runner.py` is spawned as a subprocess rather than imported, so a candidate
provider's dependencies are installed into a throwaway environment and never into this one.
"""

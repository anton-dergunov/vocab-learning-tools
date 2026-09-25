"""The server doing work nobody is waiting on (`docs/server.md`, "Jobs").

A job is a row in `jobs`; the runner here takes them one at a time and calls the same `services/`
functions the routes call, so a job and a request are the same code and there is no second pipeline.
The runner owns retry and pacing; a service makes one attempt.

Layering: this package may import `services/` and `repository/`, and never `api/`. `api/` reaches
jobs only through `repository.jobs`, except that `api/app.py` starts the runner. `services/` knows
nothing of jobs at all.
"""

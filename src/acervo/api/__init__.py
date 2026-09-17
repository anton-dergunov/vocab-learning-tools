"""The HTTP surface: routers, the error envelope, auth, and the three static surfaces.

This package may not import `acervo.jobs`. Capture, review and the sync API must work with the
orchestrator down, and the sync API must not know an orchestrator exists. A package boundary is how
that stays true when nobody is watching it.

Work the server does on its own is `acervo.work`, which routes reach only through
`repository.jobs`: a route queues a job and reads its record, and never calls the runner. The one
exception is `app.py`, which starts the runner for the life of the application.
"""

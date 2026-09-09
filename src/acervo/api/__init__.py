"""The HTTP surface: routers, the error envelope, auth, and the three static surfaces.

This package may not import `acervo.jobs`. Capture, review and the sync API must work with the
orchestrator down, and the sync API must not know an orchestrator exists. A package boundary is how
that stays true when nobody is watching it.
"""

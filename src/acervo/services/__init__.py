"""Request-path work with no database concern of its own.

Everything here must answer inside a request and must work with everything else down. Anything
asynchronous or batched belongs in `jobs/`, which this package and `api/` may not import.
"""

"""The one error the API speaks.

Every failure the client is meant to understand carries a code and a message written for the owner.
Anything else is a 500 whose message never reaches the wire.
"""

from __future__ import annotations


class ApiError(Exception):
    """A deliberate refusal, with the status and code the client reads."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class RecordRefused(Exception):
    """A record that cannot be stored.

    Raised by validation and turned into `400 invalid_record` by the merge, which is what names the
    collection and the id. Kept distinct from `ApiError` so a validation message cannot accidentally
    choose its own status.
    """

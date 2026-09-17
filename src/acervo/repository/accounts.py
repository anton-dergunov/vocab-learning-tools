"""Accounts. Registration is closed; these are reached only from `admin.py` and the session route."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from sqlalchemy import select

from acervo.db import tables
from acervo.domain.ids import new_record_id, now_instant
from acervo.errors import ApiError
from acervo.repository.session import reading, transaction

MINIMUM_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()

# Verified against on the unknown-email path so that the time taken does not say what the message
# deliberately does not. Hashed once at import, of a password nobody has.
_DUMMY_HASH = _hasher.hash("acervo-timing-equalisation")


class AccountExists(RuntimeError):
    pass


def create(email: str, password: str) -> dict[str, Any]:
    """Make an account, and the owner's replication cursor row, in one transaction.

    Creating `sync_state` here rather than lazily is what lets `GET /graph` be a pure read, and it
    retires the create-race retry that existed only to cover the alternative.
    """
    email = email.strip()
    if not email:
        raise ValueError("An email address is required.")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"A password must be at least {MINIMUM_PASSWORD_LENGTH} characters.")
    now = now_instant()
    user = {
        "id": new_record_id(),
        "email": email,
        "password_hash": _hasher.hash(password),
        "token_key": new_record_id(),
        "verified": True,
        "created_at": now,
        "updated_at": now,
    }
    with transaction() as connection:
        existing = connection.execute(
            select(tables.users).where(tables.users.c.email == email)
        ).mappings().first()
        if existing is not None:
            raise AccountExists(f"An account for {email} already exists.")
        connection.execute(tables.users.insert().values(**user))
        connection.execute(
            tables.sync_state.insert().values(
                id=new_record_id(), owner=user["id"], sequence=0
            )
        )
    return {"id": user["id"], "email": email}


def all_ids() -> list[str]:
    """Every account, for the work the server does on a schedule for each of them."""
    with reading() as connection:
        return list(connection.execute(select(tables.users.c.id).order_by(tables.users.c.id)).scalars())


def by_email(email: str) -> Mapping[str, Any] | None:
    with reading() as connection:
        return connection.execute(
            select(tables.users).where(tables.users.c.email == email.strip())
        ).mappings().first()


def by_id(identifier: str) -> Mapping[str, Any] | None:
    with reading() as connection:
        return connection.execute(
            select(tables.users).where(tables.users.c.id == identifier)
        ).mappings().first()


def authenticate(email: str, password: str) -> Mapping[str, Any]:
    """The signed-in account, or the same 401 for both ways of getting it wrong."""
    user = by_email(email)
    if user is None:
        # Spend the same time as a real verify would, so timing does not leak what the message will
        # not.
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError):
            pass
        raise ApiError(401, "invalid_credentials", "The email or password is incorrect.")
    try:
        _hasher.verify(user["password_hash"], password)
    except (VerifyMismatchError, VerificationError):
        raise ApiError(401, "invalid_credentials", "The email or password is incorrect.") from None
    return user


def set_password(identifier: str, password: str) -> None:
    """Change a password and rotate the token key, which signs out every outstanding token."""
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"A password must be at least {MINIMUM_PASSWORD_LENGTH} characters.")
    with transaction() as connection:
        connection.execute(
            tables.users.update()
            .where(tables.users.c.id == identifier)
            .values(
                password_hash=_hasher.hash(password),
                token_key=new_record_id(),
                updated_at=now_instant(),
            )
        )

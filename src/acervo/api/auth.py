"""Sessions.

Nothing depends on the old token format — the web client stores an opaque string, the macOS host puts
it in `UserDefaults` untouched, and nothing anywhere decodes it — so the replacement is chosen on
merit rather than compatibility.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from fastapi import Request

from acervo.errors import ApiError
from acervo.repository import accounts
from acervo.settings import Settings

ALGORITHM = "HS256"
# Chosen rather than inherited. The client refreshes once at startup and never again, so a 7-day
# token signs out a phone left unopened for eight days.
TOKEN_LIFETIME = timedelta(days=30)

UNAUTHENTICATED = ApiError(401, "unauthenticated", "Sign in to continue.")


def resolve_secret(settings: Settings) -> str:
    """The signing secret, minted and kept beside the database when the environment names none.

    A generated-per-start secret would sign everyone out on every restart, and requiring one to be
    configured would make a local run need configuring.
    """
    if settings.jwt_secret.strip():
        return settings.jwt_secret.strip()
    path = Path(settings.database_path).parent / "jwt-secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)
    return secret


def _signing_key(secret: str, token_key: str) -> bytes:
    # The per-user half is what makes a password change invalidate outstanding tokens. Hashed rather
    # than concatenated so the key is a full 32 bytes however short the configured secret is.
    return hashlib.sha256(f"{secret}:{token_key}".encode()).digest()


def mint(secret: str, user: Mapping[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user["id"], "iat": int(now.timestamp()), "exp": int((now + TOKEN_LIFETIME).timestamp())},
        _signing_key(secret, user["token_key"]),
        algorithm=ALGORITHM,
    )


def bearer_token(request: Request) -> str:
    """The token from either header shape.

    Existing callers are split between `Bearer <token>` and a bare token, and `HTTPBearer` answers a
    bare one with a 403 that no client handles.
    """
    header = request.headers.get("authorization", "").strip()
    if not header:
        return ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header


def account_for(secret: str, token: str) -> Mapping[str, Any]:
    if not token:
        raise UNAUTHENTICATED
    try:
        # The signing key depends on the account, so the subject has to be read before the signature
        # can be checked. Nothing is trusted from this first pass but the id it points at.
        claimed = jwt.decode(token, options={"verify_signature": False})
        user = accounts.by_id(str(claimed.get("sub") or ""))
        if user is None:
            raise UNAUTHENTICATED
        jwt.decode(token, _signing_key(secret, user["token_key"]), algorithms=[ALGORITHM])
    except ApiError:
        raise
    except jwt.PyJWTError:
        raise UNAUTHENTICATED from None
    return user


def owner(request: Request) -> Mapping[str, Any]:
    """FastAPI dependency: the signed-in account, or 401."""
    return account_for(request.app.state.jwt_secret, bearer_token(request))


def owner_id(request: Request) -> str:
    return owner(request)["id"]

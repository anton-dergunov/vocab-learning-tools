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

# What a render-scoped token may do, and for how long.
#
# LexiBeat holds no provider credential: it is handed a token for **one render**, audienced to the
# one route it may call, and it lives in that process and nowhere else. An hour, because a
# twelve-word loop is seventy-odd model calls behind a chain that may be resting — long enough that a
# render which waits out a rate limit still finishes, short enough that a token lifted from a
# container is worth little.
#
# It is signed with the same per-user key an ordinary session is, so changing a password kills an
# outstanding render token too.
TAKE_AUDIENCE = "acervo:pronunciations/take"
RENDER_LIFETIME = timedelta(hours=1)


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


def mint_render(secret: str, user: Mapping[str, Any], render: str) -> str:
    """A token good for one render's takes and nothing else."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user["id"],
            "aud": TAKE_AUDIENCE,
            # Which render it was minted for. Not checked — the route does not know what renders
            # exist — but it is what makes a token in a log traceable to the work that asked for it.
            "render": render,
            "iat": int(now.timestamp()),
            "exp": int((now + RENDER_LIFETIME).timestamp()),
        },
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


def account_for(secret: str, token: str, audience: str | None = None) -> Mapping[str, Any]:
    """The account a token names, or 401.

    `audience` is what a render-scoped token is *allowed* to be: pass it on the one route that
    accepts one, and leave it off everywhere else. A token carrying an audience is refused wherever
    it is not named, which is what keeps a render token from becoming a session.
    """
    if not token:
        raise UNAUTHENTICATED
    try:
        # The signing key depends on the account, so the subject has to be read before the signature
        # can be checked. Nothing is trusted from this first pass but the id it points at.
        claimed = jwt.decode(token, options={"verify_signature": False})
        user = accounts.by_id(str(claimed.get("sub") or ""))
        if user is None:
            raise UNAUTHENTICATED
        carried = claimed.get("aud")
        if carried is not None and carried != audience:
            raise UNAUTHENTICATED
        jwt.decode(
            token, _signing_key(secret, user["token_key"]), algorithms=[ALGORITHM],
            audience=audience, options={"verify_aud": carried is not None},
        )
    except ApiError:
        raise
    except jwt.PyJWTError:
        raise UNAUTHENTICATED from None
    return user


def owner(request: Request) -> Mapping[str, Any]:
    """FastAPI dependency: the signed-in account, or 401."""
    return account_for(request.app.state.jwt_secret, bearer_token(request))


def take_owner(request: Request) -> Mapping[str, Any]:
    """The account behind a take request: an ordinary session, or a render-scoped token.

    Both, deliberately. The owner's own session is strictly more privileged than a render token, so
    refusing it would buy nothing and would mean the route could not be exercised without minting a
    token by hand. What the audience buys is the other direction: a render token is *only* this.
    """
    return account_for(request.app.state.jwt_secret, bearer_token(request), audience=TAKE_AUDIENCE)


def owner_id(request: Request) -> str:
    return owner(request)["id"]

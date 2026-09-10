"""Signing in, staying signed in, and the two header shapes in live use."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt

from conftest import OWNER_EMAIL, OWNER_PASSWORD
from acervo.domain import SCHEMA_VERSION


def test_signing_in_returns_a_token_and_the_account_it_belongs_to(server):
    answer = server.client.post(
        "/api/acervo/v1/session", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert answer.status_code == 200
    payload = answer.json()["data"]
    assert payload["user"] == {"id": server.owner, "email": OWNER_EMAIL}
    assert payload["token"]


def test_an_unknown_address_and_a_wrong_password_are_the_same_refusal(server):
    """Saying which one was wrong tells an attacker which addresses have accounts."""
    unknown = server.client.post(
        "/api/acervo/v1/session", json={"email": "nobody@account.example.com", "password": "whatever"}
    )
    wrong = server.client.post(
        "/api/acervo/v1/session", json={"email": OWNER_EMAIL, "password": "whatever"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert unknown.json()["error"]["message"] == "The email or password is incorrect."


def test_both_header_shapes_are_accepted(server):
    """The interface and two scripts send `Bearer`; the integration helper sends a bare token, and
    `HTTPBearer` answers a bare one with a 403 no client handles."""
    bearer = server.client.get(
        f"/api/acervo/v1/graph?schemaVersion={SCHEMA_VERSION}&since=0",
        headers={"Authorization": f"Bearer {server.token}"},
    )
    bare = server.client.get(
        f"/api/acervo/v1/graph?schemaVersion={SCHEMA_VERSION}&since=0", headers={"Authorization": server.token}
    )
    assert bearer.status_code == bare.status_code == 200


def test_a_token_lasts_thirty_days(server):
    """Chosen, not inherited. The client refreshes once at startup and never again, so a seven-day
    token signs out a phone left unopened for eight days."""
    claims = jwt.decode(server.token, options={"verify_signature": False})
    lifetime = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.fromtimestamp(
        claims["iat"], timezone.utc
    )
    assert lifetime.days == 30


def test_refresh_issues_a_new_token_for_the_same_account(server):
    answer = server.client.post("/api/acervo/v1/session/refresh", headers=server.auth)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["id"] == server.owner


def test_an_unsigned_refresh_is_refused(server):
    answer = server.client.post("/api/acervo/v1/session/refresh")
    assert answer.status_code == 401
    assert answer.json()["error"]["code"] == "unauthenticated"


def test_changing_a_password_signs_out_every_outstanding_token(server):
    from acervo.repository import accounts

    assert server.pull().status_code == 200
    accounts.set_password(server.owner, "a-different-password")
    assert server.pull().status_code == 401


def test_a_token_signed_with_another_secret_is_refused(server):
    forged = jwt.encode({"sub": server.owner, "exp": 9999999999}, "a-secret-that-is-not-this-servers-secret", algorithm="HS256")
    answer = server.client.get(
        f"/api/acervo/v1/graph?schemaVersion={SCHEMA_VERSION}&since=0", headers={"Authorization": forged}
    )
    assert answer.status_code == 401


def test_a_password_shorter_than_eight_characters_is_refused(server):
    import pytest

    from acervo.repository import accounts

    with pytest.raises(ValueError, match="at least 8"):
        accounts.create("second@account.example.com", "short")

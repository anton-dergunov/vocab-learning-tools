"""Which Google account is about to be billed.

This machine has had more than one Vertex setup on it, and a bulk run against the wrong project is
not recoverable after the fact. Every run says whose credentials it resolved before it spends
anything.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    account: str
    project: str
    configuration: str


def _gcloud(*args: str) -> str:
    try:
        result = subprocess.run(
            ("gcloud", *args), capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"gcloud could not be run: {error}") from error
    if result.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def resolve() -> Identity:
    """The identity the SDK will actually use — read from the live ADC token, not from config.

    `gcloud config` says which account the CLI is pointed at; the application default credentials
    are a separate thing and are what `google-genai` picks up. Ask the token itself.
    """
    token = _gcloud("auth", "application-default", "print-access-token")
    request = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v3/tokeninfo?access_token="
        + urllib.parse.quote(token)
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            info = json.loads(response.read())
    except urllib.error.URLError as error:
        raise RuntimeError(f"The credentials could not be checked: {error}") from error

    account = str(info.get("email") or "")
    if not account:
        raise RuntimeError("The application default credentials carry no account email.")

    try:
        configuration = _gcloud("config", "configurations", "list",
                                "--filter=is_active=true", "--format=value(name)")
    except RuntimeError:
        configuration = ""

    try:
        project = _gcloud("config", "get-value", "project")
    except RuntimeError:
        project = ""

    return Identity(account=account, project=project, configuration=configuration)

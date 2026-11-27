"""The sign-in step of the live test: one token request to Adobe's sign-in service.

``cjapy`` raises a plain exception with no status code when sign-in fails, so
the live test makes its own request here to say why sign-in failed. The result
uses the codes of the Adobe credentials standard, version 1. No value of the
credential or of the token goes into a message.

This module imports only the standard library, ``urllib3`` and
``core.constants``, so it joins no import cycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import urllib3

from cja_auto_sdr.core.constants import HIDDEN_VALUE_DISPLAY

__all__ = [
    "IMS_SIGN_IN_URL",
    "NO_PRODUCT_ACCESS_MESSAGE",
    "SignInResult",
    "post_token_request",
    "request_token",
]

IMS_SIGN_IN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
# Seconds to wait for a connection, and then for the answer.
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 60.0
MESSAGE_LIMIT = 200

_DEVELOPER_CONSOLE = "the credential in the Adobe Developer Console"
_MESSAGES: dict[str, str] = {
    "bad_client_id": f"Adobe does not know the client ID. Copy the client ID again from {_DEVELOPER_CONSOLE}.",
    "bad_secret": (
        "Adobe knows the client ID and rejected the secret. Copy the client secret again from "
        f"{_DEVELOPER_CONSOLE}. A secret that was replaced no longer works."
    ),
    "scopes_rejected": (
        f"Adobe rejected one or more scopes. Copy the scopes exactly as they are shown for {_DEVELOPER_CONSOLE}."
    ),
    "unreachable": (
        "The tool could not reach Adobe's sign-in service, or the answer did not come from Adobe. "
        "Check the network, the proxy and Adobe's status page, then try again."
    ),
}

# Rule L2.6 of the standard: the one "no access" message for a CJA tool.
NO_PRODUCT_ACCESS_MESSAGE = (
    "Sign-in worked, but the credential cannot reach Customer Journey Analytics. In the Adobe Developer "
    "Console, add the Customer Journey Analytics API and the Adobe Experience Platform API to the credential. "
    "In the Adobe Admin Console, add its technical account to a CJA product profile."
)


@dataclass(frozen=True)
class SignInResult:
    """The result of the sign-in step. ``code`` and ``message`` are None when ``ok`` is True."""

    ok: bool
    code: str | None = None
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "message": self.message}


def post_token_request(fields: Mapping[str, str]) -> tuple[int, Any]:
    """Send the token request. Returns the HTTP status and the parsed JSON body, or None.

    This is the only function here that uses the network. Tests replace it.
    """
    response = urllib3.request(
        "POST",
        IMS_SIGN_IN_URL,
        body=urlencode(dict(fields)),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        timeout=urllib3.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT),
        retries=False,
    )
    try:
        body = json.loads(response.data.decode("utf-8"))
    except ValueError:
        body = None
    return response.status, body


def _adobe_message(description: str, error: str, status: int, hidden_values: tuple[str, ...]) -> str:
    """Return Adobe's own message, with any credential value removed, cut to the limit."""
    text = description or error or f"Adobe answered HTTP {status}."
    for hidden in hidden_values:
        if hidden:
            text = text.replace(hidden, HIDDEN_VALUE_DISPLAY)
    return text[:MESSAGE_LIMIT]


def request_token(credentials: Mapping[str, Any]) -> SignInResult:
    """Ask Adobe's sign-in service for a token and say how it went.

    The request is the one ``cjapy`` makes: a ``client_credentials`` grant with
    the client ID, the secret and the scopes. *credentials* holds the values as
    ``cjapy`` gets them, e.g. from ``api.client._build_cjapy_config_kwargs``.
    """
    client_id = str(credentials.get("client_id") or "")
    client_credential = str(credentials.get("secret") or "")
    scopes = str(credentials.get("scopes") or "")
    fields = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_credential,
        "scope": scopes,
    }
    try:
        status, body = post_token_request(fields)
    except (urllib3.exceptions.HTTPError, OSError):
        return SignInResult(False, "unreachable", _MESSAGES["unreachable"])

    answer = body if isinstance(body, dict) else {}
    granted = answer.get("access_token")
    if status == 200 and isinstance(granted, str) and granted:
        return SignInResult(True)
    if status == 200:
        # Adobe's sign-in service answers 200 only with a token. Another answer with 200
        # comes from something between, e.g. a proxy or the sign-in page of a network.
        return SignInResult(False, "unreachable", _MESSAGES["unreachable"])

    error = str(answer.get("error") or "")
    description = str(answer.get("error_description") or "")
    if error == "invalid_client" and "secret" in description:
        return SignInResult(False, "bad_secret", _MESSAGES["bad_secret"])
    if error == "invalid_client":
        return SignInResult(False, "bad_client_id", _MESSAGES["bad_client_id"])
    if error == "invalid_scope":
        return SignInResult(False, "scopes_rejected", _MESSAGES["scopes_rejected"])
    return SignInResult(
        False,
        "sign_in_failed",
        _adobe_message(description, error, status, (client_credential,)),
    )

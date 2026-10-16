"""Credential resolution. Never logs or returns the credential."""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

SIDECAR = os.environ.get("DOMINO_API_PROXY", "http://localhost:8899").rstrip("/")


class AuthError(Exception):
    """Raised with a user-facing message naming the env var to fix."""


@dataclass
class Credentials:
    api_base: str  # host used for API calls
    ui_base: str | None  # host used to build clickable links
    mode: str  # "pat" or "workspace"
    _token: str | None = None

    def bearer(self) -> str:
        if self.mode == "pat":
            return self._token or ""
        try:  # workspace tokens are short-lived; fetch every call
            r = httpx.get(f"{SIDECAR}/access-token", timeout=5)
            r.raise_for_status()
            return r.text.strip()
        except httpx.HTTPError:
            raise AuthError(
                "Could not fetch a token from the Domino workspace sidecar. "
                "Set DOMINO_HOST and DOMINO_API_KEY instead."
            ) from None


def resolve() -> Credentials:
    key = os.environ.get("DOMINO_API_KEY", "").strip()
    host = os.environ.get("DOMINO_HOST", "").strip().rstrip("/")
    if key:
        if not host:
            raise AuthError("DOMINO_HOST is not set. Set it to your Domino URL, e.g. https://domino.example.com")
        return Credentials(host, host, "pat", key)
    ws_host = os.environ.get("DOMINO_API_HOST", "").strip().rstrip("/")
    if ws_host:  # inside a Domino workspace
        return Credentials(ws_host, host or None, "workspace")
    raise AuthError(
        "No Domino credential found. Set DOMINO_API_KEY (a Personal Access Token) "
        "and DOMINO_HOST (your Domino URL)."
    )

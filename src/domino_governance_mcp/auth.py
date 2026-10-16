"""Credential resolution. Never logs or returns the credential."""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field

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
    _exp: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def bearer(self) -> str:
        if self.mode == "pat":
            return self._token or ""
        with self._lock:  # workspace tokens are short-lived: cache until shortly before expiry
            if self._token and time.time() < self._exp:
                return self._token
            last = None
            for n in range(4):
                try:
                    r = httpx.get(f"{SIDECAR}/access-token", timeout=10)
                    r.raise_for_status()
                    self._token = r.text.strip()
                    self._exp = min(_jwt_exp(self._token) - 30, time.time() + 300)
                    return self._token
                except httpx.HTTPError as e:
                    last = e
                    time.sleep(0.3 * 2 ** n)
            raise AuthError(
                "Could not fetch a token from the Domino workspace sidecar "
                f"({type(last).__name__}). Set DOMINO_HOST and DOMINO_API_KEY instead."
            ) from None


def _jwt_exp(token: str) -> float:
    try:
        seg = token.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))["exp"])
    except Exception:
        return time.time() + 60


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

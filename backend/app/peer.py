"""Signed HTTP client for hospital <-> cloud calls over the WireGuard tunnel."""
import time

import httpx

from .config import Settings
from .security import sign_request
from .util import AppError, dumps


class PeerUnavailable(Exception):
    pass


class PeerClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(base_url=settings.peer_api_url, timeout=settings.peer_timeout_seconds)

    def call(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> httpx.Response:
        raw = dumps(body).encode() if body is not None else b""
        ts = str(int(time.time()))
        headers = {
            "X-Sync-Timestamp": ts,
            "X-Sync-Signature": sign_request(self.settings.sync_shared_secret, ts, method, path, raw),
            "Content-Type": "application/json",
        }
        try:
            response = self.client.request(method, path, content=raw or None, headers=headers,
                                           timeout=timeout or self.settings.peer_timeout_seconds)
        except httpx.HTTPError as exc:
            raise PeerUnavailable(f"{type(exc).__name__}: {exc}"[:300]) from exc
        if response.status_code in (502, 503, 504) and not _is_app_error(response):
            raise PeerUnavailable(f"Peer gateway returned HTTP {response.status_code}")
        return response

    def call_json(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        return unwrap(self.call(method, path, body, timeout))


def _is_app_error(response: httpx.Response) -> bool:
    try:
        return "error" in response.json()
    except ValueError:
        return False


def unwrap(response: httpx.Response) -> dict:
    """Return JSON, or re-raise the peer's AppError so it reaches the browser unchanged."""
    try:
        data = response.json()
    except ValueError:
        raise AppError("PEER_ERROR", f"Unexpected response from peer (HTTP {response.status_code}).", 502)
    if response.status_code >= 400:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        extra = {k: v for k, v in err.items() if k not in ("code", "message")}
        raise AppError(err.get("code", "PEER_ERROR"), err.get("message", "Peer request failed."), response.status_code, **extra)
    return data

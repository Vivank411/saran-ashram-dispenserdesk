"""Routing helpers shared by public and internal routers."""
from fastapi import FastAPI, Request
from sqlalchemy.orm import Session

from ..deps import Actor
from ..peer import PeerUnavailable
from ..services.directory import pull_directory
from ..services.status import last_sync
from ..util import AppError


def actor_ref(actor: Actor) -> dict:
    return {"user_id": str(actor.user_id), "username": actor.username, "terminal": actor.terminal}


def forward_to_hospital(request: Request, db: Session, actor: Actor, path: str, data: dict | None = None) -> dict:
    """Cloud gateway: execute a live operation on the authoritative hospital server via the VPN."""
    settings = request.app.state.settings
    try:
        return request.app.state.peer.call_json("POST", "/api/internal/exec" + path,
                                                {"actor": actor_ref(actor), "data": data or {}})
    except PeerUnavailable:
        raise AppError("LIVE_BILLING_UNAVAILABLE",
                       "Live billing and inventory changes are temporarily unavailable because the hospital server "
                       "cannot be reached. Read-only data from the last synchronization is still available.",
                       503, last_sync=last_sync(db, settings))


def forward_to_directory(request: Request, db: Session, actor: Actor, path: str, data: dict | None = None) -> dict:
    """Hospital: user-directory changes are made on the cloud (needs internet), then pulled back."""
    app = request.app
    try:
        result = app.state.peer.call_json("POST", "/api/internal/exec" + path, {"actor": actor_ref(actor), "data": data or {}})
    except PeerUnavailable:
        raise AppError("DIRECTORY_OFFLINE", "User registration, password resets and role changes are managed by the central "
                       "user directory and require internet connectivity.", 503)
    try:
        pull_directory(db, app.state.settings, app.state.peer)
    except PeerUnavailable:
        pass
    return result


def wake_sync(app: FastAPI) -> None:
    runner = getattr(app.state, "runner", None)
    if runner:
        runner.wake()

import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import Settings
from .models import AuthSession, User
from .permissions import PERMISSIONS, has_perm
from .security import check_signature, decode_access_token
from .util import AppError, utcnow


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.sessionmaker()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dataclass
class Actor:
    user_id: uuid.UUID
    username: str
    name: str
    role: str
    channel: str  # "lan" (hospital terminal) or "remote" (cloud app)
    terminal: str
    offline: bool = False
    session_id: uuid.UUID | None = None

    def can(self, perm: str) -> bool:
        return has_perm(self.role, perm)


_TERMINAL_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,30}$")


def terminal_from(request: Request) -> str:
    """Which hospital computer: an optional X-Terminal-Id header, otherwise the computer's LAN IP address."""
    value = (request.headers.get("x-terminal-id") or "").strip()
    return value if _TERMINAL_RE.match(value) else client_ip(request)[:30]


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else "-"


def current_actor(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Actor:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise AppError("AUTH", "Please sign in.", 401)
    claims = decode_access_token(settings, header[7:].strip())
    user = db.get(User, uuid.UUID(claims["sub"]))
    if not user or not user.is_active or user.token_version != claims["tv"]:
        raise AppError("SESSION_REVOKED", "Your session was revoked. Please sign in again.", 401)
    session = db.get(AuthSession, uuid.UUID(claims["sid"]))
    if not session or session.revoked_at or session.expires_at < utcnow():
        raise AppError("SESSION_EXPIRED", "Your session has expired. Please sign in again.", 401)
    channel = claims.get("ch", "lan")
    return Actor(user.id, user.username, user.full_name, user.role, channel,
                 "Remote" if channel == "remote" else terminal_from(request), bool(claims.get("off")), session.id)


def forbidden(actor: Actor, perm: str) -> AppError:
    return AppError("FORBIDDEN", f"Access denied: the {actor.role} role cannot {PERMISSIONS[perm].lower()}.", 403)


def require(*perms: str):
    """Allow the request if the user holds ANY of the listed permissions."""

    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not any(actor.can(p) for p in perms):
            raise forbidden(actor, perms[0])
        return actor

    return dependency


async def verify_peer(request: Request) -> dict:
    """Authenticate a hospital<->cloud call (HMAC) and return its JSON body."""
    settings: Settings = request.app.state.settings
    body = await request.body()
    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    check_signature(settings.sync_shared_secret, request.headers.get("x-sync-timestamp"),
                    request.headers.get("x-sync-signature"), request.method, path, body)
    return json.loads(body) if body else {}


def peer_actor(db: Session, payload: dict, perm: str | None, *, channel: str = "remote") -> Actor:
    """Resolve the user a peer is acting for, and re-check permissions locally."""
    info = payload.get("actor") or {}
    try:
        user = db.get(User, uuid.UUID(info.get("user_id", "")))
    except ValueError:
        user = None
    if not user or not user.is_active:
        raise AppError("FORBIDDEN", "Unknown or inactive user.", 403)
    actor = Actor(user.id, user.username, user.full_name, user.role, channel,
                  "Remote" if channel == "remote" else str(info.get("terminal") or "Unknown")[:30])
    if perm and not actor.can(perm):
        raise forbidden(actor, perm)
    return actor

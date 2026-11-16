"""User directory. The cloud is authoritative; the hospital keeps a cache for offline sign-in."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import Actor
from ..models import AuthSession, User
from ..peer import PeerClient
from ..schemas import UserCreate, UserUpdate
from ..security import hash_password, validate_password_policy
from ..serializers import DIRECTORY_FIELDS, user_public
from ..store import audit, set_state
from ..util import AppError, parse_dt, utcnow


def upsert_user_snapshot(db: Session, snap: dict) -> User:
    user = db.get(User, uuid.UUID(snap["id"]))
    if user is None:
        clash = db.scalar(select(User).where(User.username == snap["username"]))
        if clash:
            raise AppError("DIRECTORY_CLASH", f"Local user '{snap['username']}' has a different id than the central directory.", 409)
        user = User(id=uuid.UUID(snap["id"]), failed_logins=0, created_at=parse_dt(snap.get("created_at")) or utcnow())
        db.add(user)
    for field in DIRECTORY_FIELDS:
        setattr(user, field, snap[field])
    user.verified_at = parse_dt(snap.get("verified_at"))
    return user


def pull_directory(db: Session, settings: Settings, peer: PeerClient) -> int:
    """Hospital: refresh the cached directory from the cloud (raises PeerUnavailable when offline)."""
    data = peer.call_json("GET", "/api/internal/sync/users")
    count = 0
    for snap in data["users"]:
        try:
            upsert_user_snapshot(db, snap)
            count += 1
        except AppError:
            continue
    set_state(db, "directory_pulled", {"at": utcnow().isoformat(), "count": count})
    db.commit()
    return count


# ---------------- authoritative operations (cloud) ----------------

def _other_active_admins(db: Session, user_id: uuid.UUID) -> int:
    return len([u for u in db.scalars(select(User).where(User.role == "Admin", User.is_active.is_(True))) if u.id != user_id])


def _revoke_local_sessions(db: Session, user_id: uuid.UUID) -> None:
    now = utcnow()
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))):
        s.revoked_at = now


def create_user(db: Session, settings: Settings, actor: Actor, data: UserCreate) -> dict:
    if db.scalar(select(User).where(User.username == data.username)):
        raise AppError("USERNAME_TAKEN", "That username is already taken.", 409)
    validate_password_policy(data.password, data.username)
    user = User(id=uuid.uuid4(), username=data.username, full_name=data.full_name, mobile=data.mobile, role=data.role,
                password_hash=hash_password(data.password), is_active=True, is_verified=False,
                offline_login_enabled=False, token_version=1, directory_version=1, failed_logins=0)
    db.add(user)
    audit(db, settings, "User registered", f"{user.username} · {user.role} · awaiting mobile OTP verification", actor)
    db.commit()
    return user_public(user)


def update_user(db: Session, settings: Settings, actor: Actor, user_id: uuid.UUID, data: UserUpdate) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise AppError("NOT_FOUND", "User not found.", 404)
    if user.role == "Admin" and (data.role != "Admin" or not data.is_active) and not _other_active_admins(db, user.id):
        raise AppError("LAST_ADMIN", "At least one active Admin is required.", 409)
    if user.id == actor.user_id and (data.role != user.role or not data.is_active):
        raise AppError("VALIDATION", "You cannot change your own role or deactivate your own account.")
    changes = []
    if data.role != user.role:
        changes.append(f"role {user.role} -> {data.role}")
    if data.is_active != user.is_active:
        changes.append("activated" if data.is_active else "deactivated")
    offline = data.offline_login_enabled and user.is_verified
    if offline != user.offline_login_enabled:
        changes.append("offline sign-in " + ("enabled" if offline else "disabled"))
    if not changes:
        return user_public(user)
    revoke = data.role != user.role or not data.is_active
    user.role, user.is_active, user.offline_login_enabled = data.role, data.is_active, offline
    user.directory_version += 1
    if revoke:
        user.token_version += 1
        _revoke_local_sessions(db, user.id)
    audit(db, settings, "User updated", f"{user.username} · {' · '.join(changes)}{' · sessions revoked' if revoke else ''}", actor)
    db.commit()
    return user_public(user)


def reset_password(db: Session, settings: Settings, actor: Actor, user_id: uuid.UUID, password: str) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise AppError("NOT_FOUND", "User not found.", 404)
    validate_password_policy(password, user.username)
    user.password_hash = hash_password(password)
    user.token_version += 1
    user.directory_version += 1
    user.failed_logins, user.locked_until = 0, None
    _revoke_local_sessions(db, user.id)
    audit(db, settings, "Password reset", f"{user.username} · all sessions revoked", actor)
    db.commit()
    return user_public(user)


def revoke_sessions(db: Session, settings: Settings, actor: Actor, user_id: uuid.UUID) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise AppError("NOT_FOUND", "User not found.", 404)
    user.token_version += 1
    user.directory_version += 1
    _revoke_local_sessions(db, user.id)
    audit(db, settings, "Sessions revoked", user.username, actor)
    db.commit()
    return user_public(user)


# ---------------- local operation (both servers keep their own lockout counters) ----------------

def unlock_user(db: Session, settings: Settings, actor: Actor, user_id: uuid.UUID) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise AppError("NOT_FOUND", "User not found.", 404)
    user.failed_logins, user.locked_until = 0, None
    audit(db, settings, "Account unlocked", user.username, actor)
    db.commit()
    return user_public(user)

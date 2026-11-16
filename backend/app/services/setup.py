"""First-time sign-up.

When no account exists yet, the person installing the system signs up: they choose the dispensary name,
the low-stock threshold and their own Admin account, then sign in normally.

The user directory lives on the cloud, so a sign-up made on the hospital server is registered there
(one-time internet connection required) and pulled back for offline sign-in. Settings are owned by the
hospital and synchronised to the cloud.
"""
import threading
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import User
from ..peer import PeerClient, PeerUnavailable
from ..schemas import SetupIn
from ..security import hash_password, validate_password_policy
from ..serializers import user_snapshot
from ..store import audit, set_setting
from ..util import AppError, utcnow
from .directory import upsert_user_snapshot
from .inventory import apply_settings

_setup_lock = threading.Lock()


def needs_setup(db: Session) -> bool:
    return (db.scalar(select(func.count()).select_from(User)) or 0) == 0


def _already() -> AppError:
    return AppError("ALREADY_SET_UP", "This system has already been set up. Please sign in.", 409)


def create_first_admin(db: Session, settings: Settings, data: dict) -> User:
    """Directory side (cloud): create the first Admin. Refused once any account exists."""
    with _setup_lock:
        if not needs_setup(db):
            raise _already()
        validate_password_policy(data["password"], data["username"])
        user = User(id=uuid.uuid4(), username=data["username"], full_name=data["full_name"], mobile=data["mobile"],
                    role="Admin", password_hash=hash_password(data["password"]), is_active=True, is_verified=True,
                    verified_at=utcnow(), offline_login_enabled=True, token_version=1, directory_version=1,
                    failed_logins=0)
        db.add(user)
        audit(db, settings, "First-time setup", f"Administrator account '{user.username}' created", username=user.username)
        db.commit()
        return user


def run_setup(db: Session, settings: Settings, peer: PeerClient, data: SetupIn) -> dict:
    if not needs_setup(db):
        raise _already()
    account = data.model_dump(include={"full_name", "username", "mobile", "password"})
    if settings.is_hospital:
        try:
            snap = peer.call_json("POST", "/api/internal/setup", {"account": account})["user"]
        except PeerUnavailable:
            raise AppError("SETUP_NEEDS_INTERNET", "First-time setup registers the administrator in the central user "
                           "directory, so it needs an internet connection once. Please connect and try again.", 503)
        upsert_user_snapshot(db, snap)
        changes = apply_settings(db, settings, data.full_name, data.low_stock_threshold, data.hospital_name)
        audit(db, settings, "First-time setup", f"Administrator '{data.username}' · {' · '.join(changes) or 'defaults kept'}",
              username=data.username)
        db.commit()
    else:
        create_first_admin(db, settings, account)
        set_setting(db, "hospital_name", data.hospital_name, data.full_name)
        set_setting(db, "low_stock_threshold", data.low_stock_threshold, data.full_name)
        db.commit()
        # Settings belong to the hospital: hand them over if it is reachable (otherwise set them later in Settings).
        try:
            peer.call_json("POST", "/api/internal/setup/settings",
                           {"hospital_name": data.hospital_name, "low_stock_threshold": data.low_stock_threshold,
                            "by": data.full_name})
        except (PeerUnavailable, AppError):
            pass
    return {"status": "ok", "username": data.username, "message": "Setup complete. Sign in with your new account."}


def snapshot_for_hospital(db: Session, settings: Settings, account: dict) -> dict:
    return {"user": user_snapshot(create_first_admin(db, settings, account))}

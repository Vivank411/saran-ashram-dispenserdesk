"""Sign-in, OTP, sessions.

Hospital: password checked against the locally cached Argon2 hash — works without internet for
          previously verified accounts. First-time OTP verification is delegated to the cloud.
Cloud:    password + mobile OTP on every remote sign-in.
"""
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import Actor
from ..models import AuthSession, TrustedDevice, User
from ..peer import PeerClient, PeerUnavailable
from ..security import create_access_token, new_refresh_token, sha256_hex, verify_password
from ..serializers import user_public
from ..store import audit, get_state
from ..util import AppError, iso, utcnow
from . import otp
from .directory import upsert_user_snapshot


class RateLimiter:
    """In-process sliding-window limiter (Nginx limit_req is the first line of defence)."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise AppError("RATE_LIMIT", "Too many attempts. Please wait a minute and try again.", 429)
            q.append(now)


def cloud_link_ok(db: Session) -> bool:
    link = get_state(db, "link", {}) or {}
    return bool(link.get("ok"))


def _fail_login(db: Session, settings: Settings, user: User | None, username: str, offline: bool) -> AppError:
    if user:
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_failures:
            user.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
            audit(db, settings, "Account locked",
                  f"{user.username} · {settings.login_max_failures} failed sign-in attempts · locked {settings.lockout_minutes} min",
                  username=user.username, offline=offline)
    audit(db, settings, "Failed sign-in", f'Username "{username[:40]}"' + (" · offline" if offline else ""),
          username=username[:40], offline=offline)
    db.commit()
    return AppError("INVALID_CREDENTIALS", "Invalid username or password.", 401)


def _trusted_device(db: Session, user: User, device_token: str | None) -> TrustedDevice | None:
    if not device_token:
        return None
    dev = db.scalar(select(TrustedDevice).where(TrustedDevice.token_hash == sha256_hex(device_token)))
    if not dev or dev.user_id != user.id or dev.expires_at < utcnow():
        return None
    return dev


def trust_device(db: Session, settings: Settings, user: User, user_agent: str) -> str:
    raw, hashed = new_refresh_token()
    now = utcnow()
    db.add(TrustedDevice(id=uuid.uuid4(), user_id=user.id, token_hash=hashed, user_agent=user_agent[:200],
                         created_at=now, last_used_at=now, expires_at=now + timedelta(days=settings.trusted_device_days)))
    audit(db, settings, "New device trusted", f"{user.username} · email code · {settings.trusted_device_days} days",
          username=user.username)
    db.commit()
    return raw


def login(db: Session, settings: Settings, peer: PeerClient, username: str, password: str,
          *, terminal: str, ip: str, user_agent: str, device_token: str | None = None) -> dict:
    username = username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    offline = settings.is_hospital and not settings.is_standalone and not cloud_link_ok(db)
    if user and user.locked_until and user.locked_until > utcnow():
        raise AppError("LOCKED", "Account temporarily locked after repeated failed sign-ins. Try again later or ask an administrator to unlock it.",
                       423, locked_until=iso(user.locked_until))
    if not verify_password(user.password_hash if user else None, password) or not user:
        raise _fail_login(db, settings, user, username, offline)
    if not user.is_active:
        raise AppError("INACTIVE", "This account is deactivated. Contact an administrator.", 403)
    user.failed_logins = 0
    db.commit()

    if settings.is_cloud:
        return otp.start_challenge(db, settings, user, "login" if user.is_verified else "verify")

    if settings.email_otp_enabled and user.email:
        dev = _trusted_device(db, user, device_token)
        if not dev:
            return otp.start_challenge(db, settings, user, "device")
        dev.last_used_at = utcnow()
        db.commit()

    if not user.is_verified:
        # first-time mobile verification needs the cloud SMS service
        try:
            return peer.call_json("POST", "/api/internal/otp/start", {"user_id": str(user.id), "purpose": "verify"})
        except PeerUnavailable:
            raise AppError("OFFLINE_NOT_ALLOWED", "This account has not completed mobile OTP verification. First-time "
                           "verification requires internet; offline sign-in is only for previously verified accounts.", 403)
    if offline and not user.offline_login_enabled:
        raise AppError("OFFLINE_NOT_ALLOWED", "Internet is unavailable and offline sign-in is not enabled for this account.", 403)
    return issue_session(db, settings, user, channel="lan", terminal=terminal, offline=offline, ip=ip, user_agent=user_agent)


def verify_otp(db: Session, settings: Settings, peer: PeerClient, challenge_id: uuid.UUID, code: str,
               *, terminal: str, ip: str, user_agent: str) -> dict:
    if settings.is_cloud:
        user, _ = otp.verify(db, settings, challenge_id, code)
        return issue_session(db, settings, user, channel="remote", terminal="Remote", offline=False, ip=ip, user_agent=user_agent)
    if settings.is_standalone:
        user, purpose = otp.verify(db, settings, challenge_id, code)
        if not user.is_active:
            raise AppError("INACTIVE", "This account is deactivated. Contact an administrator.", 403)
        result = issue_session(db, settings, user, channel="lan", terminal=terminal, offline=False, ip=ip, user_agent=user_agent)
        if purpose == "device":
            result["device_token"] = trust_device(db, settings, user, user_agent)
        return result
    try:
        data = peer.call_json("POST", "/api/internal/otp/verify", {"challenge_id": str(challenge_id), "code": code})
    except PeerUnavailable:
        raise AppError("NO_INTERNET", "OTP verification requires internet connectivity.", 503)
    user = upsert_user_snapshot(db, data["user"])
    db.commit()
    return issue_session(db, settings, user, channel="lan", terminal=terminal, offline=False, ip=ip, user_agent=user_agent)


def resend_otp(db: Session, settings: Settings, peer: PeerClient, challenge_id: uuid.UUID) -> dict:
    if settings.is_cloud or settings.is_standalone:
        return otp.resend(db, settings, challenge_id)
    try:
        return peer.call_json("POST", "/api/internal/otp/resend", {"challenge_id": str(challenge_id)})
    except PeerUnavailable:
        raise AppError("NO_INTERNET", "OTP delivery requires internet connectivity.", 503)


def _tokens(settings: Settings, user: User, session: AuthSession) -> str:
    return create_access_token(settings, user_id=user.id, role=user.role, token_version=user.token_version,
                               session_id=session.id, channel=session.channel, offline=session.offline)


def _session_info(settings: Settings, user: User, session: AuthSession, access: str, refresh: str) -> dict:
    return {"status": "ok", "access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": settings.access_token_minutes * 60, "user": user_public(user),
            "session": {"id": str(session.id), "channel": session.channel, "terminal": session.terminal,
                        "offline": session.offline, "expires_at": iso(session.expires_at)}}


def issue_session(db: Session, settings: Settings, user: User, *, channel: str, terminal: str, offline: bool,
                  ip: str, user_agent: str) -> dict:
    raw, hashed = new_refresh_token()
    now = utcnow()
    session = AuthSession(id=uuid.uuid4(), user_id=user.id, refresh_hash=hashed, token_version=user.token_version,
                          channel=channel, terminal=terminal, offline=offline, ip=ip, user_agent=user_agent[:200],
                          created_at=now, last_used_at=now, expires_at=now + timedelta(hours=settings.session_hours))
    db.add(session)
    user.last_login_at = now
    actor = Actor(user.id, user.username, user.full_name, user.role, channel, terminal, offline, session.id)
    detail = ("Remote access · password + mobile OTP" if channel == "remote" else f"Hospital LAN · {terminal}")
    if offline:
        detail += " · verified against locally cached credential hash (no internet)"
    audit(db, settings, "Offline sign-in" if offline else "Sign-in", detail, actor)
    db.commit()
    return _session_info(settings, user, session, _tokens(settings, user, session), raw)


def refresh(db: Session, settings: Settings, raw_token: str) -> dict:
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == sha256_hex(raw_token)).with_for_update())
    now = utcnow()
    if not session or session.revoked_at or session.expires_at < now:
        raise AppError("SESSION_EXPIRED", "Your session has expired. Please sign in again.", 401)
    user = db.get(User, session.user_id)
    if not user or not user.is_active or user.token_version != session.token_version:
        session.revoked_at = now
        db.commit()
        raise AppError("SESSION_REVOKED", "Your session was revoked. Please sign in again.", 401)
    raw, hashed = new_refresh_token()  # rotation: each refresh token is single-use
    session.refresh_hash = hashed
    session.last_used_at = now
    db.commit()
    return _session_info(settings, user, session, _tokens(settings, user, session), raw)


def logout(db: Session, settings: Settings, actor: Actor | None, raw_token: str | None) -> None:
    session = None
    if actor and actor.session_id:
        session = db.get(AuthSession, actor.session_id)
    elif raw_token:
        session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == sha256_hex(raw_token)))
    if session and not session.revoked_at:
        session.revoked_at = utcnow()
        if actor:
            audit(db, settings, "Sign-out", "Session ended", actor)
        db.commit()

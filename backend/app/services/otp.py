"""Mobile OTP — owned by the cloud server (it has the SMS provider and the user directory)."""
import hmac
import logging
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import OtpChallenge, User
from ..security import new_otp_code, otp_hash
from ..store import audit, display_name
from ..util import AppError, mask_mobile, utcnow
from .email import mask_email, send_email

log = logging.getLogger("dispensary.sms")


def send_sms(settings: Settings, mobile: str, message: str) -> None:
    if settings.sms_provider == "webhook":
        try:
            r = httpx.post(settings.sms_webhook_url, json={"to": mobile, "message": message},
                           headers={"Authorization": f"Bearer {settings.sms_webhook_token}"}, timeout=10)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError("SMS_FAILED", "The OTP could not be sent. Please try again shortly.", 502) from exc
    else:
        # Development only: never use the console provider in production.
        log.warning("SMS to %s: %s", mask_mobile(mobile), message if settings.environment != "production" else "<hidden>")


def start_challenge(db: Session, settings: Settings, user: User, purpose: str) -> dict:
    now = utcnow()
    window_start = now - timedelta(minutes=settings.otp_window_minutes)
    recent = db.scalar(select(func.count()).select_from(OtpChallenge)
                       .where(OtpChallenge.user_id == user.id, OtpChallenge.created_at >= window_start))
    if recent >= settings.otp_max_sends:
        raise AppError("OTP_RATE_LIMIT", f"Too many OTP requests. Please wait up to {settings.otp_window_minutes} minutes.", 429)
    challenge = OtpChallenge(id=uuid.uuid4(), user_id=user.id, purpose=purpose, attempts=0, created_at=now,
                             expires_at=now + timedelta(seconds=settings.otp_ttl_seconds), code_hash="")
    code = new_otp_code()
    challenge.code_hash = otp_hash(settings, challenge.id, code)
    db.add(challenge)
    db.commit()
    text = (f"{code} is your {settings.hospital_name} Dispensary Desk code. It expires in "
            f"{settings.otp_ttl_seconds // 60} minutes. Do not share it.")
    if purpose == "device":
        name = display_name(db, settings)
        send_email(settings, user.email, f"{code} is your {name} sign-in code",
                   f"Hello {user.full_name},\n\n{code} is your sign-in code for {name}. It expires in "
                   f"{settings.otp_ttl_seconds // 60} minutes. Do not share it.\n\nSomeone (hopefully you) is signing in as '{user.username}' on a "
                   f"new device. If this wasn't you, ask an administrator to reset your password.")
        sent_to = mask_email(user.email)
    else:
        send_sms(settings, user.mobile, text)
        sent_to = mask_mobile(user.mobile)
    result = {"status": "otp_required", "challenge_id": str(challenge.id), "purpose": purpose,
              "channel": "email" if purpose == "device" else "sms", "sent_to": sent_to,
              "masked_mobile": mask_mobile(user.mobile), "expires_in": settings.otp_ttl_seconds}
    if settings.dev_expose_otp:
        result["dev_code"] = code
    return result


def resend(db: Session, settings: Settings, challenge_id: uuid.UUID) -> dict:
    old = db.get(OtpChallenge, challenge_id)
    if not old or old.consumed_at:
        raise AppError("OTP_STATE", "This sign-in attempt is no longer valid. Please sign in again.", 400)
    user = db.get(User, old.user_id)
    old.consumed_at = utcnow()  # invalidate the previous code
    db.commit()
    return start_challenge(db, settings, user, old.purpose)


def verify(db: Session, settings: Settings, challenge_id: uuid.UUID, code: str) -> tuple[User, str]:
    ch = db.get(OtpChallenge, challenge_id, with_for_update=True)
    if not ch or ch.consumed_at:
        raise AppError("OTP_STATE", "This sign-in attempt is no longer valid. Please sign in again.", 400)
    if ch.expires_at < utcnow():
        raise AppError("OTP_EXPIRED", "The code has expired. Request a new one.", 400)
    if ch.attempts >= settings.otp_max_attempts:
        raise AppError("OTP_LOCKED", "Too many incorrect codes. Request a new one.", 429)
    if not hmac.compare_digest(ch.code_hash, otp_hash(settings, ch.id, code)):
        ch.attempts += 1
        left = settings.otp_max_attempts - ch.attempts
        user = db.get(User, ch.user_id)
        audit(db, settings, "Incorrect OTP", f"{user.username if user else '?'} · {left} attempt(s) left")
        db.commit()
        raise AppError("OTP_INVALID", f"Incorrect code. {left} attempt(s) left." if left else "Too many incorrect codes. Request a new one.", 400)
    ch.consumed_at = utcnow()
    user = db.get(User, ch.user_id)
    if ch.purpose == "verify" and not user.is_verified:
        user.is_verified = True
        user.verified_at = utcnow()
        user.offline_login_enabled = True
        user.directory_version += 1
        audit(db, settings, "Mobile verified", f"{user.username} completed OTP verification · offline sign-in enabled",
              username=user.username)
    db.commit()
    return user, ch.purpose

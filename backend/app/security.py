import hashlib
import hmac
import secrets
import time
import uuid
from datetime import timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings
from .util import AppError, utcnow

_ph = PasswordHasher()  # Argon2id with library-recommended parameters


def hash_password(password: str) -> str:
    return _ph.hash(password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _ph.hash("timing-equaliser-not-a-password")


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish time: always runs one Argon2 verification, even for unknown users."""
    try:
        return _ph.verify(password_hash or _dummy_hash(), password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


PASSWORD_MIN_LENGTH = 6


def validate_password_policy(password: str, username: str = "") -> None:
    """Simple rule: any characters, at least PASSWORD_MIN_LENGTH long."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise AppError("WEAK_PASSWORD", f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")


def sha256_hex(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, sha256_hex(raw)


def create_access_token(settings: Settings, *, user_id: uuid.UUID, role: str, token_version: int,
                        session_id: uuid.UUID, channel: str, offline: bool) -> str:
    now = utcnow()
    claims = {
        "sub": str(user_id), "role": role, "tv": token_version, "sid": str(session_id),
        "ch": channel, "off": offline, "typ": "access", "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "iss": f"dispensary-{settings.app_role}",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=f"dispensary-{settings.app_role}")
    except jwt.ExpiredSignatureError:
        raise AppError("TOKEN_EXPIRED", "Access token expired.", 401)
    except jwt.PyJWTError:
        raise AppError("AUTH", "Invalid access token.", 401)
    if claims.get("typ") != "access":
        raise AppError("AUTH", "Invalid access token.", 401)
    return claims


def new_otp_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def otp_hash(settings: Settings, challenge_id: uuid.UUID, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"otp:{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


# ---- hospital <-> cloud request signing (HMAC-SHA256 over timestamp, method, path, body) ----
SIGNATURE_MAX_SKEW = 300


def sign_request(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    message = f"{timestamp}\n{method.upper()}\n{path}\n{sha256_hex(body)}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def check_signature(secret: str, timestamp: str | None, signature: str | None, method: str, path: str, body: bytes) -> None:
    if not timestamp or not signature:
        raise AppError("PEER_UNAUTHORIZED", "Missing peer signature.", 401)
    try:
        ts = int(timestamp)
    except ValueError:
        raise AppError("PEER_UNAUTHORIZED", "Bad peer timestamp.", 401)
    if abs(time.time() - ts) > SIGNATURE_MAX_SKEW:
        raise AppError("PEER_UNAUTHORIZED", "Peer request expired (check server clocks / NTP).", 401)
    expected = sign_request(secret, timestamp, method, path, body)
    if not hmac.compare_digest(expected, signature):
        raise AppError("PEER_UNAUTHORIZED", "Invalid peer signature.", 401)

import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo


class AppError(Exception):
    """Domain error rendered as {"error": {"code", "message", ...}}."""

    def __init__(self, code: str, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local_today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    raise TypeError(f"Not JSON serialisable: {type(o).__name__}")


def dumps(obj) -> str:
    return json.dumps(obj, default=_default, separators=(",", ":"), ensure_ascii=False)


def to_jsonable(obj):
    return json.loads(dumps(obj))


def mask_mobile(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    return ("•" * max(0, len(digits) - 4)) + digits[-4:] if digits else ""


def money(value: Decimal) -> str:
    return f"₹{value:,.2f}"

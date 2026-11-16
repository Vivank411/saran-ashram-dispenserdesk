"""Small key/value helpers: sync state, system settings, counters, outbox, audit."""
import uuid

from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import AuditLog, Counter, OutboxEvent, SyncState, SystemSetting
from .util import to_jsonable, utcnow


def get_state(db: Session, key: str, default=None):
    row = db.get(SyncState, key)
    return row.value if row else default


def set_state(db: Session, key: str, value) -> None:
    row = db.get(SyncState, key)
    if row:
        row.value = to_jsonable(value)
        row.updated_at = utcnow()
    else:
        db.add(SyncState(key=key, value=to_jsonable(value), updated_at=utcnow()))


def get_setting(db: Session, key: str, default=None):
    row = db.get(SystemSetting, key)
    return row.value.get("v") if row else default


def set_setting(db: Session, key: str, value, by: str) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = {"v": value}
        row.updated_at = utcnow()
        row.updated_by = by
    else:
        db.add(SystemSetting(key=key, value={"v": value}, updated_at=utcnow(), updated_by=by))


def low_stock_threshold(db: Session, settings: Settings) -> int:
    value = get_setting(db, "low_stock_threshold")
    return int(value) if value is not None else settings.low_stock_threshold_default


def display_name(db: Session, settings: Settings) -> str:
    """Dispensary name chosen during first-time setup (falls back to HOSPITAL_NAME)."""
    return get_setting(db, "hospital_name") or settings.hospital_name


def next_counter(db: Session, name: str) -> int:
    row = db.get(Counter, name, with_for_update=True)
    if row is None:
        row = Counter(name=name, value=0)
        db.add(row)
        db.flush()
    row.value += 1
    db.flush()
    return row.value


_STANDALONE = False


def set_standalone(value: bool) -> None:
    """Standalone servers have no cloud peer, so new outbox events are recorded as already delivered."""
    global _STANDALONE
    _STANDALONE = value


def enqueue(db: Session, event_type: str, payload: dict) -> None:
    """Transactional outbox: written in the same transaction as the business change."""
    now = utcnow()
    db.add(OutboxEvent(event_id=uuid.uuid4(), event_type=event_type, payload=to_jsonable(payload),
                       status="synced" if _STANDALONE else "pending", attempts=0, created_at=now,
                       synced_at=now if _STANDALONE else None))


def audit(db: Session, settings: Settings, action: str, detail: str, actor=None, *,
          username: str | None = None, offline: bool | None = None) -> None:
    db.add(AuditLog(
        id=uuid.uuid4(), at=utcnow(),
        user_id=actor.user_id if actor else None,
        username=actor.username if actor else (username or "system"),
        user_name=actor.name if actor else (username or "System"),
        action=action, detail=detail[:2000],
        terminal=actor.terminal if actor else "-",
        channel=actor.channel if actor else ("remote" if settings.is_cloud else "lan"),
        offline=bool(actor.offline if (actor and offline is None) else offline),
        origin=settings.app_role, synced=settings.is_cloud,
    ))


def ensure_defaults(SessionLocal: sessionmaker) -> None:
    with SessionLocal() as db:
        for name in ("bill", "adjustment"):
            if not db.get(Counter, name):
                db.add(Counter(name=name, value=0))
        if not db.get(SyncState, "worker_lease"):
            db.add(SyncState(key="worker_lease", value={"owner": None, "until": 0}, updated_at=utcnow()))
        db.commit()

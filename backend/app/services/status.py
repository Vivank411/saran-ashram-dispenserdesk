"""Connectivity / synchronization status for both roles."""
import time

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import InboxEvent, OutboxEvent, SyncConflict
from ..peer import PeerUnavailable
from ..store import display_name, get_state, low_stock_threshold
from ..util import iso, utcnow
from .sync_worker import outbox_counts

PING_CACHE_SECONDS = 5


def hospital_reachable(app: FastAPI) -> bool:
    """Cloud: is the hospital API reachable through the tunnel? (cached for a few seconds)"""
    cache = app.state.ping_cache
    if time.monotonic() - cache.get("t", 0) < PING_CACHE_SECONDS:
        return cache["ok"]
    try:
        ok = app.state.peer.call("GET", "/api/internal/ping", timeout=2).status_code == 200
    except PeerUnavailable:
        ok = False
    cache.update(t=time.monotonic(), ok=ok)
    return ok


def last_sync(db: Session, settings: Settings) -> str | None:
    key = "last_success" if settings.is_hospital else "last_sync"
    return (get_state(db, key, {}) or {}).get("at")


def system_status(app: FastAPI, db: Session) -> dict:
    s: Settings = app.state.settings
    base = {"role": s.app_role, "hospital_name": display_name(db, s), "server_time": utcnow().isoformat(),
            "low_stock_threshold": low_stock_threshold(db, s), "last_sync": last_sync(db, s), "timezone": s.timezone,
            "standalone": s.is_standalone, "email_otp": s.email_otp_enabled}
    if s.is_standalone:
        return {**base, "hospital_reachable": True, "live_operations": True, "cloud_reachable": True,
                "link_checked_at": None, "pending": 0, "failed": 0, "conflicts": 0}
    if s.is_hospital:
        link = get_state(db, "link", {}) or {}
        counts = outbox_counts(db)
        return {**base, "hospital_reachable": True, "live_operations": True, "cloud_reachable": bool(link.get("ok")),
                "link_checked_at": link.get("at"), "pending": counts["pending"], "failed": counts["failed"],
                "conflicts": counts["conflicts"]}
    reachable = hospital_reachable(app)
    hb = get_state(db, "hospital_heartbeat", {}) or {}
    conflicts = db.scalar(select(func.count()).select_from(SyncConflict).where(SyncConflict.resolved_at.is_(None))) or 0
    return {**base, "hospital_reachable": reachable, "live_operations": reachable, "cloud_reachable": True,
            "link_checked_at": hb.get("received_at"), "pending": hb.get("pending"), "failed": hb.get("failed"),
            "conflicts": conflicts}


def sync_detail(app: FastAPI, db: Session) -> dict:
    s: Settings = app.state.settings
    status = system_status(app, db)
    err = get_state(db, "last_error", {}) or {}
    if s.is_hospital:
        events = db.scalars(select(OutboxEvent).order_by(OutboxEvent.seq.desc()).limit(100))
        rows = [{"seq": e.seq, "event_id": str(e.event_id), "event_type": e.event_type, "status": e.status,
                 "attempts": e.attempts, "created_at": iso(e.created_at), "synced_at": iso(e.synced_at),
                 "next_attempt_at": iso(e.next_attempt_at), "last_error": e.last_error, "resolution": e.resolution}
                for e in events]
        conflicts = [{"event_id": str(e.event_id), "seq": e.seq, "event_type": e.event_type, "detail": e.detail,
                      "detected_at": iso(e.created_at), "resolved_at": None, "resolution_note": None}
                     for e in db.scalars(select(OutboxEvent).where(OutboxEvent.status == "conflict").order_by(OutboxEvent.seq))]
        synced = outbox_counts(db)["synced"]
    else:
        inbox = db.scalars(select(InboxEvent).order_by(InboxEvent.seq.desc()).limit(100))
        rows = [{"seq": e.seq, "event_id": str(e.event_id), "event_type": e.event_type,
                 "status": "resolved" if e.forced else "synced", "attempts": None, "created_at": iso(e.received_at),
                 "synced_at": iso(e.received_at), "next_attempt_at": None, "last_error": None, "resolution": None}
                for e in inbox]
        conflicts = [{"event_id": str(c.event_id), "seq": c.seq, "event_type": c.event_type, "detail": c.detail,
                      "detected_at": iso(c.detected_at), "resolved_at": iso(c.resolved_at),
                      "resolution_note": c.resolution_note}
                     for c in db.scalars(select(SyncConflict).order_by(SyncConflict.detected_at.desc()).limit(50))]
        synced = db.scalar(select(func.count()).select_from(InboxEvent)) or 0
    return {**status, "last_error": err.get("message"), "last_attempt": (get_state(db, "last_attempt", {}) or {}).get("at"),
            "synced_total": synced, "events": rows, "conflict_list": conflicts}

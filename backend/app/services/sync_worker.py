"""Hospital side: deliver outbox events to the cloud in order, retry with backoff, pull the user directory."""
import logging
import os
import socket
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..deps import Actor
from ..models import AuditLog, OutboxEvent, SyncState
from ..peer import PeerClient, PeerUnavailable
from ..serializers import audit_dict
from ..store import audit, get_state, set_state
from ..util import AppError, iso, utcnow
from .directory import pull_directory

log = logging.getLogger("dispensary.sync")
LEASE_SECONDS = 60


def outbox_counts(db: Session) -> dict:
    rows = db.execute(select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)).all()
    counts = {status: n for status, n in rows}
    return {"pending": counts.get("pending", 0), "failed": counts.get("failed", 0),
            "conflicts": counts.get("conflict", 0), "synced": counts.get("synced", 0) + counts.get("resolved", 0)}


def clear_standalone_queue(SessionLocal: sessionmaker) -> int:
    """Standalone: there is no cloud to deliver to, so mark anything queued earlier as delivered."""
    with SessionLocal() as db:
        now = utcnow()
        rows = db.scalars(select(OutboxEvent).where(OutboxEvent.status.in_(("pending", "failed")))).all()
        for e in rows:
            e.status, e.synced_at, e.last_error = "synced", now, None
        db.commit()
        return len(rows)


def event_dict(e: OutboxEvent) -> dict:
    return {"event_id": str(e.event_id), "seq": e.seq, "event_type": e.event_type, "payload": e.payload,
            "created_at": iso(e.created_at)}


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(60, 2 ** min(attempts, 6)))  # 2s, 4s, ... capped at 60s


def _acquire_lease(db: Session, owner: str) -> bool:
    now = time.time()
    db.get(SyncState, "worker_lease", with_for_update=True)
    lease = get_state(db, "worker_lease", {}) or {}
    if lease.get("until", 0) > now and lease.get("owner") != owner:
        db.rollback()
        return False
    set_state(db, "worker_lease", {"owner": owner, "until": now + LEASE_SECONDS})
    db.commit()
    return True


def _release_lease(db: Session, owner: str) -> None:
    lease = get_state(db, "worker_lease", {}) or {}
    if lease.get("owner") == owner:
        set_state(db, "worker_lease", {"owner": None, "until": 0})
        db.commit()


def run_cycle(settings: Settings, SessionLocal: sessionmaker, peer: PeerClient, *, force: bool = False,
              owner: str | None = None, pull_users: bool | None = None) -> dict:
    owner = owner or f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"
    with SessionLocal() as db:
        if not _acquire_lease(db, owner):
            return {"status": "busy"}
        try:
            total = {"applied": 0, "duplicates": 0, "sent": 0}
            for batch_no in range(50):  # drain the queue batch by batch
                result = _cycle(db, settings, peer, force=force, pull_users=pull_users if batch_no == 0 else False)
                for k in total:
                    total[k] += result.get(k, 0)
                if result["status"] != "ok" or result.get("sent", 0) < settings.sync_batch_size:
                    break
                _acquire_lease(db, owner)  # extend the lease while draining
            return {**result, **total}
        finally:
            _release_lease(db, owner)


def _cycle(db: Session, settings: Settings, peer: PeerClient, *, force: bool, pull_users: bool | None) -> dict:
    now = utcnow()
    set_state(db, "last_attempt", {"at": now.isoformat()})
    counts = outbox_counts(db)
    events: list[OutboxEvent] = []
    blocked = counts["conflicts"] > 0
    if not blocked:
        events = list(db.scalars(select(OutboxEvent).where(OutboxEvent.status.in_(("pending", "failed")))
                                 .order_by(OutboxEvent.seq).limit(settings.sync_batch_size)))
        if events and not force and events[0].next_attempt_at and events[0].next_attempt_at > now:
            events = []  # still backing off
    audit_rows = list(db.scalars(select(AuditLog).where(AuditLog.synced.is_(False)).order_by(AuditLog.at).limit(200)))
    body = {"heartbeat": {**counts, "generated_at": now.isoformat()},
            "events": [event_dict(e) for e in events], "audit": [audit_dict(a) for a in audit_rows]}
    try:
        response = peer.call_json("POST", "/api/internal/sync/push", body, timeout=max(settings.peer_timeout_seconds, 15))
    except (PeerUnavailable, AppError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        if events:
            first = events[0]
            first.attempts += 1
            first.status = "failed"
            first.last_error = message[:500]
            first.next_attempt_at = now + _backoff(first.attempts)
        set_state(db, "link", {"ok": False, "at": now.isoformat(), "error": message[:300]})
        set_state(db, "last_error", {"at": now.isoformat(), "message": message[:300]})
        db.commit()
        return {"status": "offline", "error": message, "applied": 0}

    by_id = {r["event_id"]: r for r in response.get("results", [])}
    applied = duplicates = 0
    status = "ok"
    for e in events:
        r = by_id.get(str(e.event_id))
        if r is None:
            break
        e.attempts += 1
        if r["status"] in ("applied", "duplicate"):
            e.status, e.synced_at, e.last_error, e.next_attempt_at = "synced", now, None, None
            applied += r["status"] == "applied"
            duplicates += r["status"] == "duplicate"
        elif r["status"] == "conflict":
            e.status, e.detail = "conflict", r.get("detail")
            d = r.get("detail") or {}
            e.last_error = (f"Version conflict on {d.get('medicine_name') or d.get('medicine_id')}: cloud v{d.get('cloud_version')}, "
                            f"expected v{d.get('expected_version')}") if d.get("reason") == "version_mismatch" else f"Conflict: {d.get('reason')}"
            audit(db, settings, "Sync conflict flagged",
                  f"Event #{e.seq} {e.event_type} · {e.last_error} · held for administrator review (nothing overwritten)")
            status = "conflict"
            break
        else:
            e.status, e.last_error = "failed", f"Cloud rejected event: {r.get('detail')}"[:500]
            e.next_attempt_at = now + _backoff(e.attempts)
            status = "failed"
            break
    acked = set(response.get("audit_ack", []))
    for a in audit_rows:
        if str(a.id) in acked:
            a.synced = True
    set_state(db, "link", {"ok": True, "at": now.isoformat()})
    if status == "ok" and not blocked:
        set_state(db, "last_success", {"at": now.isoformat()})
        set_state(db, "last_error", {})
    elif blocked:
        status = "blocked"
        set_state(db, "last_error", {"at": now.isoformat(), "message": "Sync queue paused: a conflict awaits administrator review."})
    db.commit()

    if pull_users is None:
        pulled = get_state(db, "directory_pulled", {}) or {}
        last = pulled.get("at")
        pull_users = not last or (now - _parse(last)).total_seconds() >= settings.user_pull_interval_seconds
    if pull_users:
        try:
            pull_directory(db, settings, peer)
        except (PeerUnavailable, AppError) as exc:
            log.warning("Directory pull failed: %s", exc)
            db.rollback()
    _prune(db)
    return {"status": status, "applied": applied, "duplicates": duplicates, "sent": len(events)}


def _parse(value: str):
    from ..util import parse_dt
    return parse_dt(value)


def _prune(db: Session) -> None:
    cutoff = utcnow() - timedelta(days=90)
    db.execute(update(OutboxEvent).where(OutboxEvent.status == "synced", OutboxEvent.synced_at < cutoff)
               .values(payload={"pruned": True}))
    db.commit()


def resolve_conflict(db: Session, settings: Settings, peer: PeerClient, actor: Actor, event_id: uuid.UUID, note: str) -> dict:
    """Admin review: re-send the conflicted event with force, so the cloud replica adopts the hospital's
    authoritative values. Recorded on both sides; never automatic."""
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_id == event_id, OutboxEvent.status == "conflict"))
    if not ev:
        raise AppError("NOT_FOUND", "Conflict not found.", 404)
    body = {"heartbeat": {**outbox_counts(db), "generated_at": utcnow().isoformat()}, "events": [event_dict(ev)],
            "force": [str(ev.event_id)], "resolution": {"note": note, "by": actor.name}, "audit": []}
    try:
        response = peer.call_json("POST", "/api/internal/sync/push", body, timeout=15)
    except PeerUnavailable:
        raise AppError("PEER_UNAVAILABLE", "The cloud server is unreachable; the conflict can be resolved once connectivity returns.", 503)
    result = (response.get("results") or [{}])[0]
    if result.get("status") not in ("applied", "duplicate"):
        raise AppError("RESOLVE_FAILED", f"Cloud could not apply the resolution: {result.get('detail') or result.get('status')}", 409)
    ev.status, ev.synced_at = "resolved", utcnow()
    ev.resolution = {"note": note, "by": actor.name, "at": utcnow().isoformat(), "previous": ev.detail}
    audit(db, settings, "Sync conflict resolved",
          f"Event #{ev.seq} {ev.event_type} · cloud replica re-based to hospital authoritative value · {note}", actor)
    db.commit()
    return {"status": "resolved", "event_id": str(ev.event_id)}


class SyncRunner:
    """Background thread inside the hospital API process. A DB lease ensures one active runner."""

    def __init__(self, settings: Settings, SessionLocal: sessionmaker, peer: PeerClient):
        self.settings, self.SessionLocal, self.peer = settings, SessionLocal, peer
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{id(self)}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="sync-runner", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_cycle(self.settings, self.SessionLocal, self.peer, owner=self.owner)
            except Exception:
                log.exception("Sync cycle failed")
            self._wake.wait(self.settings.sync_interval_seconds)
            self._wake.clear()

"""Cloud side: apply hospital outbox events exactly once, in order, with version-based conflict detection."""
import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Integer, Numeric, Uuid, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import UTCDateTime
from ..models import (AdjustmentRequest, AuditLog, Bill, BillItem, InboxEvent, InventoryMovement, Medicine, StockAlert,
                      SyncConflict)
from ..store import get_state, set_setting, set_state
from ..util import parse_dt, utcnow

log = logging.getLogger("dispensary.sync")


class Conflict(Exception):
    def __init__(self, detail: dict):
        super().__init__(detail.get("reason", "conflict"))
        self.detail = detail


def _coerce(model, data: dict) -> dict:
    """Convert JSON values back to column types (UUID, Decimal, datetime, date)."""
    out = {}
    cols = model.__table__.columns
    for key, value in data.items():
        if key not in cols:
            continue
        col_type = cols[key].type
        if value is None:
            out[key] = None
        elif isinstance(col_type, UTCDateTime):
            out[key] = parse_dt(value)
        elif isinstance(col_type, Date):
            out[key] = date.fromisoformat(value)
        elif isinstance(col_type, Uuid):
            out[key] = uuid.UUID(value)
        elif isinstance(col_type, Numeric):
            out[key] = Decimal(value)
        elif isinstance(col_type, (Integer, Boolean)):
            out[key] = value
        else:
            out[key] = value
    return out


def _upsert(db: Session, model, data: dict, pk: str = "id"):
    values = _coerce(model, data)
    row = db.get(model, values[pk])
    if row is None:
        row = model(**values)
        db.add(row)
    else:
        for k, v in values.items():
            setattr(row, k, v)
    return row


def _apply_stock(db: Session, stock: list[dict], force: bool) -> None:
    rows = {}
    for s in stock:
        m = db.get(Medicine, s["medicine_id"])
        if m is None or (not force and m.version != s["base_version"]):
            raise Conflict({
                "reason": "version_mismatch" if m else "missing_medicine",
                "medicine_id": s["medicine_id"], "medicine_name": m.name if m else None,
                "expected_version": s["base_version"], "cloud_version": m.version if m else None,
                "cloud_stock": m.stock if m else None,
                "authoritative_stock": s["stock"], "authoritative_version": s["version"]})
        rows[s["medicine_id"]] = m
    for s in stock:
        m = rows[s["medicine_id"]]
        m.stock, m.version, m.updated_at = s["stock"], s["version"], utcnow()
        if s.get("rate") is not None:
            m.rate = Decimal(s["rate"])


def _apply_movements(db: Session, movements: list[dict]) -> None:
    for mv in movements:
        if not db.get(InventoryMovement, uuid.UUID(mv["id"])):
            db.add(InventoryMovement(**_coerce(InventoryMovement, mv)))


def _apply(db: Session, event: dict, force: bool) -> None:
    t, p = event["event_type"], event["payload"]
    if t == "medicine.upsert":
        m = p["medicine"]
        row = db.get(Medicine, m["id"])
        if row and row.version > m["version"] and not force:
            raise Conflict({"reason": "replica_ahead", "medicine_id": m["id"], "medicine_name": row.name,
                            "cloud_version": row.version, "authoritative_version": m["version"],
                            "cloud_stock": row.stock, "authoritative_stock": m["stock"]})
        _upsert(db, Medicine, m)
    elif t == "bill.created":
        _apply_stock(db, p["stock"], force)
        b = p["bill"]
        if not db.get(Bill, uuid.UUID(b["id"])):
            bill = Bill(**_coerce(Bill, {k: v for k, v in b.items() if k != "items"}))
            bill.items = [BillItem(**_coerce(BillItem, i)) for i in b["items"]]
            db.add(bill)
        _apply_movements(db, p.get("movements", []))
    elif t == "bill.reversed":
        _apply_stock(db, p["stock"], force)
        bill = db.get(Bill, uuid.UUID(p["bill_id"]))
        if bill is None:
            raise Conflict({"reason": "missing_bill", "bill_id": p["bill_id"]})
        r = p["reversal"]
        bill.status, bill.reversed_at, bill.reversed_by = "reversed", parse_dt(r["reversed_at"]), r["reversed_by"]
        bill.reversal_reason, bill.reversal_ref = r["reason"], r["ref"]
        _apply_movements(db, p.get("movements", []))
    elif t == "stock.adjusted":
        _apply_stock(db, p["stock"], force)
        _apply_movements(db, p.get("movements", []))
    elif t == "adjustment.upsert":
        _upsert(db, AdjustmentRequest, p["adjustment"])
    elif t == "alert.upsert":
        _upsert(db, StockAlert, p["alert"])
    elif t == "settings.updated":
        set_setting(db, p["key"], p["value"], p.get("by", "hospital"))
    else:
        raise ValueError(f"Unknown event type {t}")


def apply_batch(db: Session, settings: Settings, events: list[dict], force_ids: set[str],
                resolution: dict | None = None) -> list[dict]:
    results = []
    last = get_state(db, "last_applied", {}) or {}
    for event in sorted(events, key=lambda e: e["seq"]):
        eid = uuid.UUID(event["event_id"])
        out = {"event_id": event["event_id"], "seq": event["seq"]}
        if db.get(InboxEvent, eid):
            results.append({**out, "status": "duplicate"})  # retry / re-delivery: never applied twice
            continue
        if event["seq"] <= int(last.get("seq", 0)) and event["event_id"] not in force_ids:
            results.append({**out, "status": "error", "detail": "out_of_order"})
            break
        forced = event["event_id"] in force_ids
        try:
            _apply(db, event, forced)
            db.add(InboxEvent(event_id=eid, seq=event["seq"], event_type=event["event_type"], received_at=utcnow(), forced=forced))
            if forced:
                c = db.scalar(select(SyncConflict).where(SyncConflict.event_id == eid))
                if c:
                    c.resolved_at = utcnow()
                    c.resolved_by = (resolution or {}).get("by")
                    c.resolution_note = (resolution or {}).get("note")
            last = {"seq": event["seq"], "at": utcnow().isoformat()}
            set_state(db, "last_applied", last)
            db.commit()
            results.append({**out, "status": "applied"})
        except Conflict as exc:
            db.rollback()
            if not db.scalar(select(SyncConflict).where(SyncConflict.event_id == eid)):
                db.add(SyncConflict(id=uuid.uuid4(), event_id=eid, seq=event["seq"], event_type=event["event_type"],
                                    detail=exc.detail, detected_at=utcnow()))
                db.commit()
            results.append({**out, "status": "conflict", "detail": exc.detail})
            break  # keep strict ordering: nothing after a conflict is applied
        except IntegrityError:
            db.rollback()
            if db.get(InboxEvent, eid):
                results.append({**out, "status": "duplicate"})
                continue
            results.append({**out, "status": "error", "detail": "integrity_error"})
            break
        except Exception as exc:  # malformed event: stop and report, hospital will retry
            db.rollback()
            log.exception("Failed to apply event %s", event.get("event_id"))
            results.append({**out, "status": "error", "detail": str(exc)[:300]})
            break
    return results


def store_audit(db: Session, entries: list[dict]) -> list[str]:
    acked = []
    for entry in entries:
        if not db.get(AuditLog, uuid.UUID(entry["id"])):
            row = AuditLog(**_coerce(AuditLog, entry))
            row.synced = True
            db.add(row)
        acked.append(entry["id"])
    db.commit()
    return acked

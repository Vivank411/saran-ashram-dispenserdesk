"""Stock adjustments (Biller requests, Admin approves; Admin changes apply directly), low-stock alerts, settings.
Hospital only."""
import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import Actor
from ..models import AdjustmentRequest, InventoryMovement, Medicine, StockAlert
from ..schemas import AdjustmentCreate, StockCsvImportIn
from ..serializers import adjustment_dict, alert_dict, medicine_dict, movement_dict
from ..store import audit, display_name, enqueue, low_stock_threshold, next_counter, set_setting
from ..util import AppError, money, utcnow

KIND_LABELS = {"add": "Add stock (receipt)", "remove": "Remove stock (expiry/damage)",
               "set_count": "Physical count correction", "set_rate": "Change selling rate"}
MOVEMENT_KIND = {"add": "receipt", "remove": "write_off", "set_count": "count_correction", "set_rate": "rate_change"}


def describe(a: AdjustmentRequest) -> str:
    if a.kind == "add":
        return f"+{a.quantity} units"
    if a.kind == "remove":
        return f"-{a.quantity} units"
    if a.kind == "set_count":
        return f"set count to {a.quantity}"
    return f"rate {money(a.rate_at_request)} -> {money(a.new_rate)}"


def evaluate_low_stock(db: Session, settings: Settings, meds: list[Medicine]) -> list[str]:
    """Raise/refresh alerts right after a confirmed bill or approved adjustment. Works fully offline."""
    threshold = low_stock_threshold(db, settings)
    messages = []
    now = utcnow()
    for m in {m.id: m for m in meds}.values():
        if m.stock > threshold:
            continue
        message = f"LOW STOCK ALERT: {m.name} — {m.stock} units remaining."
        alert = db.scalar(select(StockAlert).where(StockAlert.medicine_id == m.id, StockAlert.acknowledged_at.is_(None)))
        if alert:
            alert.remaining, alert.threshold, alert.message, alert.updated_at = m.stock, threshold, message, now
        else:
            alert = StockAlert(id=uuid.uuid4(), medicine_id=m.id, medicine_name=m.name, remaining=m.stock,
                               threshold=threshold, message=message, raised_at=now, updated_at=now)
            db.add(alert)
        db.flush()
        enqueue(db, "alert.upsert", {"alert": alert_dict(alert)})
        messages.append(message)
    return messages


def acknowledge_alert(db: Session, settings: Settings, actor: Actor, alert_id: uuid.UUID) -> dict:
    alert = db.get(StockAlert, alert_id, with_for_update=True)
    if not alert or alert.acknowledged_at:
        raise AppError("NOT_FOUND", "Alert not found or already acknowledged.", 404)
    alert.acknowledged_at = utcnow()
    alert.acknowledged_by = actor.name
    enqueue(db, "alert.upsert", {"alert": alert_dict(alert)})
    audit(db, settings, "Alert acknowledged", alert.message, actor)
    db.commit()
    return alert_dict(alert)


def request_adjustment(db: Session, settings: Settings, actor: Actor, data: AdjustmentCreate) -> dict:
    m = db.get(Medicine, data.medicine_id)
    if not m:
        raise AppError("NOT_FOUND", "Medicine not found.", 404)
    if data.kind == "set_rate":
        if data.new_rate is None:
            raise AppError("VALIDATION", "Enter the new selling rate.")
    else:
        if data.quantity is None or (data.kind != "set_count" and data.quantity < 1):
            raise AppError("VALIDATION", "Enter a valid whole-number quantity.")
        if data.kind == "remove" and data.quantity > m.stock:
            raise AppError("VALIDATION", f"Cannot remove {data.quantity}: only {m.stock} in stock.")
    req = AdjustmentRequest(
        id=uuid.uuid4(), request_no=f"ADJ-{next_counter(db, 'adjustment'):05d}", medicine_id=m.id, medicine_name=m.name,
        kind=data.kind, quantity=None if data.kind == "set_rate" else data.quantity,
        new_rate=data.new_rate if data.kind == "set_rate" else None, reason=data.reason, status="pending",
        requested_by_id=actor.user_id, requested_by_name=actor.name, requested_at=utcnow(),
        stock_at_request=m.stock, rate_at_request=m.rate, channel=actor.channel)
    db.add(req)
    db.flush()
    if actor.can("stock.approve"):
        # Admin: the change is applied immediately (still recorded as an adjustment + ledger entry + audit).
        audit(db, settings, "Adjustment requested", f"{req.request_no} · {m.name} · {describe(req)} · {data.reason}", actor)
        alerts = _decide(db, settings, actor, req, True, "Applied directly by Admin")
        db.commit()
        return {**adjustment_dict(req), "alerts": alerts}
    enqueue(db, "adjustment.upsert", {"adjustment": adjustment_dict(req)})
    audit(db, settings, "Adjustment requested",
          f"{req.request_no} · {m.name} · {describe(req)} · {data.reason} · awaiting Admin approval", actor)
    db.commit()
    return {**adjustment_dict(req), "alerts": []}


def decide_adjustment(db: Session, settings: Settings, actor: Actor, request_id: uuid.UUID, approve: bool, note: str) -> dict:
    req = db.get(AdjustmentRequest, request_id, with_for_update=True)
    if not req:
        raise AppError("NOT_FOUND", "Request not found.", 404)
    if req.status != "pending":
        raise AppError("ALREADY_DECIDED", "This request has already been decided.", 409)
    alerts = _decide(db, settings, actor, req, approve, note)
    db.commit()
    return {"adjustment": adjustment_dict(req), "alerts": alerts}


def _decide(db: Session, settings: Settings, actor: Actor, req: AdjustmentRequest, approve: bool, note: str) -> list[str]:
    alerts: list[str] = []
    now = utcnow()
    if approve:
        m = db.get(Medicine, req.medicine_id, with_for_update=True)
        base = m.version
        delta = 0
        if req.kind == "add":
            delta = req.quantity
        elif req.kind == "remove":
            if req.quantity > m.stock:
                raise AppError("INSUFFICIENT_STOCK", f"Cannot remove {req.quantity}: current stock is {m.stock}.", 409)
            delta = -req.quantity
        elif req.kind == "set_count":
            delta = req.quantity - m.stock
        note_text = None
        if req.kind == "set_rate":
            note_text = f"{money(m.rate)} -> {money(req.new_rate)}"
            m.rate = req.new_rate
        else:
            m.stock += delta
        m.version += 1
        m.updated_at = now
        mv = InventoryMovement(id=uuid.uuid4(), medicine_id=m.id, medicine_name=m.name, kind=MOVEMENT_KIND[req.kind],
                               qty_change=delta, balance_after=m.stock, reference=req.request_no, user_name=actor.name,
                               terminal=actor.terminal, note=note_text, created_at=now)
        db.add(mv)
        db.flush()
        enqueue(db, "stock.adjusted", {
            "adjustment_id": str(req.id),
            "stock": [{"medicine_id": m.id, "base_version": base, "version": m.version, "stock": m.stock, "rate": str(m.rate)}],
            "movements": [movement_dict(mv)]})
        if req.kind != "set_rate":
            alerts = evaluate_low_stock(db, settings, [m])
    req.status = "approved" if approve else "rejected"
    req.decided_by_id, req.decided_by_name, req.decided_at, req.decision_note = actor.user_id, actor.name, now, note or None
    enqueue(db, "adjustment.upsert", {"adjustment": adjustment_dict(req)})
    audit(db, settings, "Adjustment approved" if approve else "Adjustment rejected",
          f"{req.request_no} · {req.medicine_name} · {describe(req)}{' · ' + note if note else ''}", actor)
    return alerts


def apply_settings(db: Session, settings: Settings, by: str, threshold: int | None, hospital_name: str | None) -> list[str]:
    """Hospital-authoritative settings; each change is queued so the cloud copy follows."""
    changes = []
    if threshold is not None and threshold != low_stock_threshold(db, settings):
        changes.append(f"low-stock threshold {low_stock_threshold(db, settings)} -> {threshold}")
        set_setting(db, "low_stock_threshold", threshold, by)
        enqueue(db, "settings.updated", {"key": "low_stock_threshold", "value": threshold, "by": by})
    if hospital_name and hospital_name != display_name(db, settings):
        changes.append(f"name '{display_name(db, settings)}' -> '{hospital_name}'")
        set_setting(db, "hospital_name", hospital_name, by)
        enqueue(db, "settings.updated", {"key": "hospital_name", "value": hospital_name, "by": by})
    return changes


def update_settings(db: Session, settings: Settings, actor: Actor, threshold: int, hospital_name: str | None) -> dict:
    changes = apply_settings(db, settings, actor.name, threshold, hospital_name)
    if changes:
        audit(db, settings, "Settings changed", " · ".join(changes), actor)
    db.commit()
    return {"low_stock_threshold": low_stock_threshold(db, settings), "hospital_name": display_name(db, settings)}


def _money_or_none(v: str | None) -> Decimal | None:
    if not v or not v.strip():
        return None
    try:
        return Decimal(v.strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def import_stock_csv(db: Session, settings: Settings, actor: Actor, data: StockCsvImportIn) -> dict:
    if not actor.can("stock.approve"):
        raise AppError("FORBIDDEN", "Only Admin can import stock from CSV.", 403)
    text = data.csv_content.strip()
    if not text:
        raise AppError("VALIDATION", "CSV content cannot be empty.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise AppError("VALIDATION", "CSV has no headers.")
    now = utcnow()
    updated = 0
    created = 0
    errors: list[str] = []
    affected_meds: list[Medicine] = []

    for row_idx, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in raw_row.items() if k}
        code_str = row.get("code") or row.get("id") or row.get("medicine_id")
        name = row.get("name") or row.get("medicine_name") or row.get("medicine")
        if not code_str and not name:
            errors.append(f"Row {row_idx}: missing code and name")
            continue
        m: Medicine | None = None
        code: int | None = None
        if code_str:
            try:
                code = int(code_str)
                m = db.get(Medicine, code)
            except ValueError:
                pass
        if m is None and name:
            m = db.scalar(select(Medicine).where(Medicine.name.ilike(name.strip())))
            if m:
                code = m.id

        stock_val_str = row.get("stock") or row.get("qty") or row.get("quantity")
        rate_val = _money_or_none(row.get("rate") or row.get("selling_rate") or row.get("price"))
        cost_val = _money_or_none(row.get("cost") or row.get("purchase_cost"))
        mrp_val = _money_or_none(row.get("mrp"))
        company = (row.get("company") or "").strip()[:60]
        unit = (row.get("unit") or "").strip()[:20]

        if m is None:
            if not code:
                max_id = db.scalar(select(Medicine.id).order_by(Medicine.id.desc()).limit(1)) or 1000
                code = max_id + 1
            if not name:
                errors.append(f"Row {row_idx}: cannot create new medicine without name")
                continue
            init_stock = 0
            if stock_val_str:
                try:
                    init_stock = int(float(stock_val_str))
                except ValueError:
                    init_stock = 0
            m = Medicine(
                id=code,
                name=name.strip().upper(),
                unit=unit or "TAB.",
                stock=init_stock,
                rate=rate_val or Decimal("0.00"),
                cost=cost_val or Decimal("0.00"),
                mrp=mrp_val or Decimal("0.00"),
                company=company,
                is_active=True,
                version=1,
                updated_at=now
            )
            db.add(m)
            db.flush()
            mv = InventoryMovement(
                id=uuid.uuid4(),
                medicine_id=m.id,
                medicine_name=m.name,
                kind="receipt" if init_stock > 0 else "opening",
                qty_change=init_stock,
                balance_after=init_stock,
                reference="CSV-IMPORT",
                user_name=actor.name,
                terminal=actor.terminal,
                note=data.reason,
                created_at=now
            )
            db.add(mv)
            enqueue(db, "medicine.upsert", {"medicine": medicine_dict(m)})
            created += 1
            affected_meds.append(m)
        else:
            base_version = m.version
            qty_delta = 0
            has_stock_change = False
            if stock_val_str:
                try:
                    target_stock = int(float(stock_val_str))
                    if data.mode == "add_stock":
                        qty_delta = target_stock
                        m.stock += qty_delta
                        has_stock_change = True
                    else:
                        qty_delta = target_stock - m.stock
                        m.stock = target_stock
                        has_stock_change = (qty_delta != 0)
                except ValueError:
                    errors.append(f"Row {row_idx}: invalid stock number '{stock_val_str}'")
            if rate_val is not None:
                m.rate = rate_val
            if cost_val is not None:
                m.cost = cost_val
            if mrp_val is not None:
                m.mrp = mrp_val
            if company:
                m.company = company
            if unit:
                m.unit = unit
            if name:
                m.name = name.strip().upper()
            m.version += 1
            m.updated_at = now
            if has_stock_change:
                mv = InventoryMovement(
                    id=uuid.uuid4(),
                    medicine_id=m.id,
                    medicine_name=m.name,
                    kind="receipt" if data.mode == "add_stock" else "count_correction",
                    qty_change=qty_delta,
                    balance_after=m.stock,
                    reference="CSV-IMPORT",
                    user_name=actor.name,
                    terminal=actor.terminal,
                    note=data.reason,
                    created_at=now
                )
                db.add(mv)
                enqueue(db, "stock.adjusted", {
                    "adjustment_id": str(uuid.uuid4()),
                    "stock": [{"medicine_id": m.id, "base_version": base_version, "version": m.version, "stock": m.stock, "rate": str(m.rate)}],
                    "movements": [movement_dict(mv)]
                })
            enqueue(db, "medicine.upsert", {"medicine": medicine_dict(m)})
            updated += 1
            affected_meds.append(m)

    alerts = evaluate_low_stock(db, settings, affected_meds) if affected_meds else []
    audit(db, settings, "Stock CSV imported", f"{updated} medicines updated, {created} added via CSV ({data.mode})", actor)
    db.commit()
    return {"status": "ok", "updated": updated, "created": created, "errors": errors[:20], "alerts": alerts}

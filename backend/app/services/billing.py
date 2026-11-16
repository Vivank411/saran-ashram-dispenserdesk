"""Bill confirmation and reversal — runs only on the hospital (authoritative) server."""
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import Actor
from ..models import Bill, BillItem, InventoryMovement, Medicine
from ..schemas import BillCreate
from ..serializers import bill_dict, movement_dict
from ..store import audit, enqueue, next_counter
from ..util import AppError, local_today, money, utcnow
from .inventory import evaluate_low_stock

CENT = Decimal("0.01")


def _lock_medicines(db: Session, ids) -> dict[int, Medicine]:
    # SELECT ... FOR UPDATE in a stable order: serialises terminals competing for the same rows, no deadlocks.
    rows = db.scalars(select(Medicine).where(Medicine.id.in_(sorted(ids))).order_by(Medicine.id).with_for_update())
    return {m.id: m for m in rows}


def create_bill(db: Session, settings: Settings, actor: Actor, data: BillCreate) -> dict:
    existing = db.scalar(select(Bill).where(Bill.request_id == data.request_id))
    if existing:  # idempotent retry (double click, network retry, gateway retry)
        return {"bill": bill_dict(existing), "alerts": [], "duplicate": True}

    quantities: dict[int, int] = {}
    for item in data.items:
        if item.medicine_id in quantities:
            raise AppError("VALIDATION", "A medicine appears more than once in the bill.")
        quantities[item.medicine_id] = item.qty

    meds = _lock_medicines(db, quantities)
    # 1. validate everything before touching anything
    for med_id, qty in quantities.items():
        m = meds.get(med_id)
        if not m or not m.is_active:
            raise AppError("NOT_FOUND", f"Medicine {med_id} was not found.", 404)
        if m.rate <= 0:
            raise AppError("NO_RATE", f"No valid selling rate is set for {m.name}. An approved rate change is required.", 409)
        if m.stock < qty:
            raise AppError("INSUFFICIENT_STOCK", f"Insufficient stock for {m.name}: requested {qty}, available {m.stock}.", 409,
                           medicine_id=m.id, available=m.stock)

    now = utcnow()
    today = local_today(settings.timezone)
    bill_no = f"BILL-{today.year}-{next_counter(db, 'bill'):06d}"
    bill = Bill(id=uuid.uuid4(), bill_no=bill_no, request_id=data.request_id, status="confirmed", business_date=today,
                customer_name=data.customer_name, patient_ref=data.patient_ref, payment_mode=data.payment_mode,
                total=Decimal("0"), operator_id=actor.user_id, operator_name=actor.name, terminal=actor.terminal,
                channel=actor.channel, created_offline=actor.offline, created_at=now)
    stock, movements = [], []
    # 2-3. deduct and record
    for line_no, item in enumerate(data.items, start=1):
        m = meds[item.medicine_id]
        base = m.version
        m.stock -= item.qty
        m.version += 1
        m.updated_at = now
        bill.items.append(BillItem(line_no=line_no, medicine_id=m.id, medicine_name=m.name, unit=m.unit, qty=item.qty,
                                   rate=m.rate, amount=(m.rate * item.qty).quantize(CENT)))
        mv = InventoryMovement(id=uuid.uuid4(), medicine_id=m.id, medicine_name=m.name, kind="bill_issue",
                               qty_change=-item.qty, balance_after=m.stock, reference=bill_no, user_name=actor.name,
                               terminal=actor.terminal, created_at=now)
        db.add(mv)
        movements.append(mv)
        stock.append({"medicine_id": m.id, "base_version": base, "version": m.version, "stock": m.stock})
    bill.total = sum((i.amount for i in bill.items), Decimal("0"))
    db.add(bill)
    db.flush()
    # 4-7. bill, items, movements, sync event, alerts — all in this one transaction
    enqueue(db, "bill.created", {"bill": bill_dict(bill), "stock": stock, "movements": [movement_dict(x) for x in movements]})
    alerts = evaluate_low_stock(db, settings, [meds[i.medicine_id] for i in data.items])
    audit(db, settings, "Bill confirmed",
          f"{bill_no} · {len(bill.items)} item(s) · {money(bill.total)} · {actor.channel}{' · created offline' if actor.offline else ''}",
          actor)
    try:
        db.commit()  # 8. commit everything together
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Bill).where(Bill.request_id == data.request_id))
        if existing:
            return {"bill": bill_dict(existing), "alerts": [], "duplicate": True}
        raise
    return {"bill": bill_dict(bill), "alerts": alerts, "duplicate": False}


def reverse_bill(db: Session, settings: Settings, actor: Actor, bill_id: uuid.UUID, reason: str) -> dict:
    bill = db.get(Bill, bill_id, with_for_update=True)
    if not bill:
        raise AppError("NOT_FOUND", "Bill not found.", 404)
    if bill.status == "reversed":
        raise AppError("ALREADY_REVERSED", f"{bill.bill_no} has already been reversed.", 409)
    meds = _lock_medicines(db, {i.medicine_id for i in bill.items})
    now = utcnow()
    ref = "REV-" + bill.bill_no.removeprefix("BILL-")
    stock, movements = [], []
    for item in bill.items:
        m = meds.get(item.medicine_id)
        if not m:
            raise AppError("NOT_FOUND", f"Medicine {item.medicine_name} no longer exists.", 409)
        base = m.version
        m.stock += item.qty
        m.version += 1
        m.updated_at = now
        mv = InventoryMovement(id=uuid.uuid4(), medicine_id=m.id, medicine_name=m.name, kind="bill_reversal",
                               qty_change=item.qty, balance_after=m.stock, reference=ref, user_name=actor.name,
                               terminal=actor.terminal, note=reason[:200], created_at=now)
        db.add(mv)
        movements.append(mv)
        stock.append({"medicine_id": m.id, "base_version": base, "version": m.version, "stock": m.stock})
    bill.status = "reversed"
    bill.reversed_at = now
    bill.reversed_by = actor.name
    bill.reversal_reason = reason
    bill.reversal_ref = ref
    db.flush()
    enqueue(db, "bill.reversed", {
        "bill_id": str(bill.id),
        "reversal": {"reversed_at": now.isoformat(), "reversed_by": actor.name, "reason": reason, "ref": ref},
        "stock": stock, "movements": [movement_dict(x) for x in movements]})
    audit(db, settings, "Bill reversed", f"{bill.bill_no} · stock restored via {ref} · {reason}", actor)
    db.commit()
    return bill_dict(bill)

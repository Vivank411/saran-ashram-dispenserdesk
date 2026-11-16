"""Medicines, ledger, bills, adjustments, alerts, settings.

Reads are served from the local database (live on the hospital, synchronized replica on the cloud).
Writes run on the hospital; on the cloud they are forwarded to the hospital or refused when it is unreachable.
"""
import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import Actor, current_actor, get_db, require
from ..models import AdjustmentRequest, Bill, InventoryMovement, Medicine, StockAlert
from ..schemas import AdjustmentCreate, BillCreate, DecisionIn, ReverseIn, SettingsIn, StockCsvImportIn
from ..serializers import adjustment_dict, alert_dict, bill_dict, medicine_dict, movement_dict
from ..services import billing, inventory
from ..store import display_name, low_stock_threshold
from ..util import AppError
from .common import forward_to_hospital, wake_sync

router = APIRouter(prefix="/api", tags=["operations"])


def _cloud(request: Request) -> bool:
    return request.app.state.settings.is_cloud


def _source(request: Request) -> str:
    return "cloud_replica" if _cloud(request) else "hospital"


# ---- local operations (hospital). Also invoked by the internal gateway for remote users. ----

def list_medicines(db: Session, q: str = "") -> list[dict]:
    stmt = select(Medicine).order_by(Medicine.name)
    if q:
        like = f"%{q.strip()}%"
        conds = [Medicine.name.ilike(like)]
        if q.strip().isdigit():
            conds.append(Medicine.id == int(q.strip()))
        stmt = stmt.where(or_(*conds))
    return [medicine_dict(m) for m in db.scalars(stmt.limit(500))]


def op_create_bill(request: Request, db: Session, actor: Actor, data: dict) -> dict:
    result = billing.create_bill(db, request.app.state.settings, actor, BillCreate.model_validate(data))
    wake_sync(request.app)
    return result


def op_reverse_bill(request: Request, db: Session, actor: Actor, bill_id: uuid.UUID, data: dict) -> dict:
    body = ReverseIn.model_validate(data)
    result = billing.reverse_bill(db, request.app.state.settings, actor, bill_id, body.reason)
    wake_sync(request.app)
    return result


def op_request_adjustment(request: Request, db: Session, actor: Actor, data: dict) -> dict:
    result = inventory.request_adjustment(db, request.app.state.settings, actor, AdjustmentCreate.model_validate(data))
    wake_sync(request.app)
    return result


def op_decide(request: Request, db: Session, actor: Actor, req_id: uuid.UUID, data: dict) -> dict:
    body = DecisionIn.model_validate(data)
    result = inventory.decide_adjustment(db, request.app.state.settings, actor, req_id, body.approve, body.note)
    wake_sync(request.app)
    return result


def op_ack_alert(request: Request, db: Session, actor: Actor, alert_id: uuid.UUID) -> dict:
    result = inventory.acknowledge_alert(db, request.app.state.settings, actor, alert_id)
    wake_sync(request.app)
    return result


def op_update_settings(request: Request, db: Session, actor: Actor, data: dict) -> dict:
    body = SettingsIn.model_validate(data)
    result = inventory.update_settings(db, request.app.state.settings, actor, body.low_stock_threshold, body.hospital_name)
    wake_sync(request.app)
    return result


def op_import_csv(request: Request, db: Session, actor: Actor, data: dict) -> dict:
    body = StockCsvImportIn.model_validate(data)
    result = inventory.import_stock_csv(db, request.app.state.settings, actor, body)
    wake_sync(request.app)
    return result


# ---- public endpoints ----

@router.get("/medicines")
def medicines(request: Request, q: str = "", live: bool = False,
              actor: Actor = Depends(require("stock.view", "bill.create")), db: Session = Depends(get_db)):
    if _cloud(request) and live:
        return forward_to_hospital(request, db, actor, "/medicines", {"q": q})
    return {"items": list_medicines(db, q), "source": _source(request)}


@router.get("/medicines/export-csv")
def export_medicines_csv(request: Request, actor: Actor = Depends(require("stock.view")), db: Session = Depends(get_db)):
    stmt = select(Medicine).order_by(Medicine.name)
    meds = db.scalars(stmt).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "name", "unit", "stock", "rate", "cost", "mrp", "company"])
    for m in meds:
        writer.writerow([m.id, m.name, m.unit, m.stock, m.rate, m.cost, m.mrp, m.company])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock_register.csv"}
    )


@router.post("/medicines/import-csv")
def import_medicines_csv(body: StockCsvImportIn, request: Request, actor: Actor = Depends(require("stock.approve")),
                         db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, "/medicines/import-csv", data)
    return op_import_csv(request, db, actor, data)


@router.get("/movements")
def movements(request: Request, q: str = "", medicine_id: int | None = None, limit: int = Query(300, le=1000),
              _: Actor = Depends(require("stock.view")), db: Session = Depends(get_db)):
    stmt = select(InventoryMovement).order_by(InventoryMovement.created_at.desc())
    if medicine_id is not None:
        stmt = stmt.where(InventoryMovement.medicine_id == medicine_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(InventoryMovement.medicine_name.ilike(like), InventoryMovement.reference.ilike(like)))
    return {"items": [movement_dict(m) for m in db.scalars(stmt.limit(limit))], "source": _source(request)}


@router.get("/bills")
def bills(request: Request, q: str = "", status: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
          _: Actor = Depends(require("bill.view")), db: Session = Depends(get_db)):
    stmt = select(Bill).order_by(Bill.created_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Bill.bill_no.ilike(like), Bill.customer_name.ilike(like), Bill.patient_ref.ilike(like),
                              Bill.operator_name.ilike(like), Bill.terminal.ilike(like)))
    if status:
        stmt = stmt.where(Bill.status == status)
    return {"items": [bill_dict(b) for b in db.scalars(stmt.offset(offset).limit(limit))], "source": _source(request)}


@router.get("/bills/{bill_id}")
def bill(bill_id: uuid.UUID, _: Actor = Depends(require("bill.view")), db: Session = Depends(get_db)):
    b = db.get(Bill, bill_id)
    if not b:
        raise AppError("NOT_FOUND", "Bill not found.", 404)
    return bill_dict(b)


@router.post("/bills")
def create_bill(body: BillCreate, request: Request, actor: Actor = Depends(require("bill.create")),
                db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, "/bills", data)
    return op_create_bill(request, db, actor, data)


@router.post("/bills/{bill_id}/reverse")
def reverse_bill(bill_id: uuid.UUID, body: ReverseIn, request: Request, actor: Actor = Depends(require("bill.reverse")),
                 db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, f"/bills/{bill_id}/reverse", data)
    return op_reverse_bill(request, db, actor, bill_id, data)


@router.get("/adjustments")
def adjustments(request: Request, status: str | None = None, limit: int = Query(200, le=500),
                _: Actor = Depends(require("stock.view", "stock.request", "stock.approve")), db: Session = Depends(get_db)):
    stmt = select(AdjustmentRequest).order_by(AdjustmentRequest.requested_at.desc())
    if status:
        stmt = stmt.where(AdjustmentRequest.status == status)
    return {"items": [adjustment_dict(a) for a in db.scalars(stmt.limit(limit))], "source": _source(request)}


@router.post("/adjustments")
def create_adjustment(body: AdjustmentCreate, request: Request, actor: Actor = Depends(require("stock.request")),
                      db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, "/adjustments", data)
    return op_request_adjustment(request, db, actor, data)


@router.post("/adjustments/{req_id}/decide")
def decide(req_id: uuid.UUID, body: DecisionIn, request: Request, actor: Actor = Depends(require("stock.approve")),
           db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, f"/adjustments/{req_id}/decide", data)
    return op_decide(request, db, actor, req_id, data)


@router.get("/alerts")
def alerts(request: Request, active: bool | None = None, limit: int = Query(200, le=500),
           _: Actor = Depends(require("stock.view")), db: Session = Depends(get_db)):
    stmt = select(StockAlert).order_by(StockAlert.updated_at.desc())
    if active is True:
        stmt = stmt.where(StockAlert.acknowledged_at.is_(None))
    elif active is False:
        stmt = stmt.where(StockAlert.acknowledged_at.is_not(None))
    return {"items": [alert_dict(a) for a in db.scalars(stmt.limit(limit))], "source": _source(request)}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: uuid.UUID, request: Request, actor: Actor = Depends(require("alerts.ack")),
              db: Session = Depends(get_db)):
    if _cloud(request):
        return forward_to_hospital(request, db, actor, f"/alerts/{alert_id}/ack")
    return op_ack_alert(request, db, actor, alert_id)


@router.get("/settings")
def get_settings_view(request: Request, _: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    s = request.app.state.settings
    return {"low_stock_threshold": low_stock_threshold(db, s), "session_hours": s.session_hours, "timezone": s.timezone,
            "lockout_minutes": s.lockout_minutes, "login_max_failures": s.login_max_failures,
            "otp_ttl_seconds": s.otp_ttl_seconds, "hospital_name": display_name(db, s)}


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, actor: Actor = Depends(require("settings.manage")),
                 db: Session = Depends(get_db)):
    data = body.model_dump(mode="json")
    if _cloud(request):
        return forward_to_hospital(request, db, actor, "/settings", data)
    return op_update_settings(request, db, actor, data)

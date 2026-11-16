"""Peer-to-peer endpoints. Reachable only through the WireGuard tunnel (blocked at Nginx) and HMAC-signed."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, peer_actor, verify_peer
from ..models import User
from ..schemas import PasswordResetIn, ResolveIn, SetupAccount, UserCreate, UserUpdate
from ..serializers import user_snapshot
from ..services import directory, otp, setup
from ..services.inventory import apply_settings
from ..services.sync_inbox import apply_batch, store_audit
from ..services.sync_worker import resolve_conflict, run_cycle
from ..store import audit, set_state
from ..util import AppError, utcnow
from . import operations as ops


def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise AppError("VALIDATION", "Invalid identifier.", 422)


# ======================= hospital: live operations for remote (cloud) users =======================
hospital = APIRouter(prefix="/api/internal", tags=["internal"], include_in_schema=False)


@hospital.get("/ping")
def hospital_ping(_: dict = Depends(verify_peer)):
    return {"status": "ok", "role": "hospital", "time": utcnow().isoformat()}


@hospital.post("/setup/settings")
def hospital_setup_settings(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    """Cloud-side first-time setup hands the chosen dispensary settings to the hospital (their owner)."""
    s = request.app.state.settings
    changes = apply_settings(db, s, str(payload.get("by", "Setup"))[:120], payload.get("low_stock_threshold"),
                             (payload.get("hospital_name") or "")[:120] or None)
    if changes:
        audit(db, s, "First-time setup settings", " · ".join(changes), username="setup")
    db.commit()
    return {"status": "ok"}


@hospital.post("/exec/medicines")
def exec_medicines(payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    peer_actor(db, payload, None)
    return {"items": ops.list_medicines(db, payload["data"].get("q", "")), "source": "hospital_live"}


@hospital.post("/exec/medicines/import-csv")
def exec_import_csv(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_import_csv(request, db, peer_actor(db, payload, "stock.approve"), payload["data"])


@hospital.post("/exec/bills")
def exec_bill(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_create_bill(request, db, peer_actor(db, payload, "bill.create"), payload["data"])


@hospital.post("/exec/bills/{bill_id}/reverse")
def exec_reverse(bill_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_reverse_bill(request, db, peer_actor(db, payload, "bill.reverse"), bill_id, payload["data"])


@hospital.post("/exec/adjustments")
def exec_adjustment(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_request_adjustment(request, db, peer_actor(db, payload, "stock.request"), payload["data"])


@hospital.post("/exec/adjustments/{req_id}/decide")
def exec_decide(req_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_decide(request, db, peer_actor(db, payload, "stock.approve"), req_id, payload["data"])


@hospital.post("/exec/alerts/{alert_id}/ack")
def exec_ack(alert_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_ack_alert(request, db, peer_actor(db, payload, "alerts.ack"), alert_id)


@hospital.post("/exec/settings")
def exec_settings(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return ops.op_update_settings(request, db, peer_actor(db, payload, "settings.manage"), payload["data"])


@hospital.post("/exec/sync/run")
def exec_sync_run(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    peer_actor(db, payload, "sync.manage")
    app = request.app
    return run_cycle(app.state.settings, app.state.sessionmaker, app.state.peer, force=True)


@hospital.post("/exec/sync/conflicts/{event_id}/resolve")
def exec_resolve(event_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    actor = peer_actor(db, payload, "sync.manage")
    body = ResolveIn.model_validate(payload["data"])
    return resolve_conflict(db, request.app.state.settings, request.app.state.peer, actor, event_id, body.note)


# ======================= cloud: sync inbox, directory, OTP, directory admin =======================
cloud = APIRouter(prefix="/api/internal", tags=["internal"], include_in_schema=False)


@cloud.get("/ping")
def cloud_ping(_: dict = Depends(verify_peer)):
    return {"status": "ok", "role": "cloud", "time": utcnow().isoformat()}


@cloud.post("/sync/push")
def sync_push(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    now = utcnow().isoformat()
    if payload.get("heartbeat"):
        set_state(db, "hospital_heartbeat", {**payload["heartbeat"], "received_at": now})
        db.commit()
    audit_ack = store_audit(db, payload.get("audit", []))
    force = set(payload.get("force", []))
    resolution = payload.get("resolution")
    if force and not (resolution and resolution.get("note")):
        raise AppError("VALIDATION", "A forced (conflict-resolution) event requires a review note.")
    results = apply_batch(db, settings, payload.get("events", []), force, resolution)
    if all(r["status"] in ("applied", "duplicate") for r in results):
        set_state(db, "last_sync", {"at": now})
    else:
        bad = next(r for r in results if r["status"] not in ("applied", "duplicate"))
        set_state(db, "last_error", {"at": now, "message": f"Event #{bad['seq']}: {bad['status']}"})
    db.commit()
    return {"results": results, "audit_ack": audit_ack}


@cloud.get("/sync/users")
def sync_users(_: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return {"users": [user_snapshot(u) for u in db.scalars(select(User))]}


@cloud.post("/setup")
def cloud_setup(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    """First-time sign-up made on the hospital: register the first Admin in the central directory."""
    account = SetupAccount.model_validate(payload.get("account", {})).model_dump()
    return setup.snapshot_for_hospital(db, request.app.state.settings, account)


@cloud.post("/otp/start")
def otp_start(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    user = db.get(User, _uuid(payload.get("user_id")))
    if not user or not user.is_active:
        raise AppError("FORBIDDEN", "Unknown or inactive user.", 403)
    purpose = payload.get("purpose") if payload.get("purpose") in ("verify", "login") else "verify"
    return otp.start_challenge(db, request.app.state.settings, user, purpose)


@cloud.post("/otp/verify")
def otp_verify(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    user, purpose = otp.verify(db, request.app.state.settings, _uuid(payload.get("challenge_id")), str(payload.get("code", "")))
    return {"user": user_snapshot(user), "purpose": purpose}


@cloud.post("/otp/resend")
def otp_resend(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    return otp.resend(db, request.app.state.settings, _uuid(payload.get("challenge_id")))


@cloud.post("/exec/users")
def exec_create_user(request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    actor = peer_actor(db, payload, "users.manage", channel="lan")
    return directory.create_user(db, request.app.state.settings, actor, UserCreate.model_validate(payload["data"]))


@cloud.post("/exec/users/{user_id}/update")
def exec_update_user(user_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    actor = peer_actor(db, payload, "users.manage", channel="lan")
    return directory.update_user(db, request.app.state.settings, actor, user_id, UserUpdate.model_validate(payload["data"]))


@cloud.post("/exec/users/{user_id}/reset-password")
def exec_reset(user_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    actor = peer_actor(db, payload, "users.manage", channel="lan")
    body = PasswordResetIn.model_validate(payload["data"])
    return directory.reset_password(db, request.app.state.settings, actor, user_id, body.password)


@cloud.post("/exec/users/{user_id}/revoke-sessions")
def exec_revoke(user_id: uuid.UUID, request: Request, payload: dict = Depends(verify_peer), db: Session = Depends(get_db)):
    actor = peer_actor(db, payload, "users.manage", channel="lan")
    return directory.revoke_sessions(db, request.app.state.settings, actor, user_id)

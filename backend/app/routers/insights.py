import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import Actor, current_actor, get_db, require
from ..models import AuditLog
from ..permissions import PERMISSIONS, ROLE_PERMS, ROLES, has_perm
from ..schemas import ResolveIn
from ..serializers import audit_dict
from ..services import reports, status
from ..services.sync_worker import resolve_conflict, run_cycle
from ..util import AppError, local_today
from .common import forward_to_hospital

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system/status")
def system_status(request: Request, db: Session = Depends(get_db)):
    return status.system_status(request.app, db)


@router.get("/meta/roles")
def roles(_: Actor = Depends(current_actor)):
    return {"roles": list(ROLES), "permissions": PERMISSIONS,
            "matrix": {r: [p for p in PERMISSIONS if has_perm(r, p)] for r in ROLE_PERMS}}


@router.get("/dashboard")
def dashboard(request: Request, _: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return {**reports.dashboard(db, request.app.state.settings), "source": "cloud_replica" if request.app.state.settings.is_cloud else "hospital"}


@router.get("/reports/dispensing")
def dispensing(request: Request, period: str = "day", day: date | None = None,
               _: Actor = Depends(require("reports.view")), db: Session = Depends(get_db)):
    s = request.app.state.settings
    return {**reports.dispensing(db, period, day or local_today(s.timezone)), "source": "cloud_replica" if s.is_cloud else "hospital"}


@router.get("/audit")
def audit_log(q: str = "", limit: int = Query(300, le=1000), _: Actor = Depends(require("audit.view")),
              db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditLog.action.ilike(like), AuditLog.detail.ilike(like), AuditLog.username.ilike(like),
                              AuditLog.terminal.ilike(like)))
    return {"items": [audit_dict(a) for a in db.scalars(stmt.limit(limit))]}


@router.get("/sync/status")
def sync_status(request: Request, _: Actor = Depends(require("sync.view")), db: Session = Depends(get_db)):
    return status.sync_detail(request.app, db)


@router.post("/sync/run")
def sync_run(request: Request, actor: Actor = Depends(require("sync.manage")), db: Session = Depends(get_db)):
    app = request.app
    if app.state.settings.is_cloud:
        return forward_to_hospital(request, db, actor, "/sync/run")
    return run_cycle(app.state.settings, app.state.sessionmaker, app.state.peer, force=True)


@router.post("/sync/conflicts/{event_id}/resolve")
def sync_resolve(event_id: uuid.UUID, body: ResolveIn, request: Request, actor: Actor = Depends(require("sync.manage")),
                 db: Session = Depends(get_db)):
    app = request.app
    if app.state.settings.is_cloud:
        return forward_to_hospital(request, db, actor, f"/sync/conflicts/{event_id}/resolve", body.model_dump())
    result = resolve_conflict(db, app.state.settings, app.state.peer, actor, event_id, body.note)
    if getattr(app.state, "runner", None):
        app.state.runner.wake()
    return result

"""Model -> plain dict converters used for API responses and sync payloads."""
from .models import AdjustmentRequest, AuditLog, Bill, InventoryMovement, Medicine, StockAlert, User
from .permissions import perms_for
from .util import iso, mask_mobile


def medicine_dict(m: Medicine) -> dict:
    return {"id": m.id, "code": m.id, "name": m.name, "unit": m.unit, "stock": m.stock, "rate": str(m.rate),
            "cost": str(m.cost), "mrp": str(m.mrp), "company": m.company, "is_active": m.is_active, "version": m.version, "updated_at": iso(m.updated_at)}


def bill_dict(b: Bill) -> dict:
    return {
        "id": str(b.id), "bill_no": b.bill_no, "request_id": str(b.request_id), "status": b.status,
        "business_date": b.business_date.isoformat(), "customer_name": b.customer_name, "patient_ref": b.patient_ref,
        "payment_mode": b.payment_mode, "total": str(b.total),
        "operator_id": str(b.operator_id) if b.operator_id else None, "operator_name": b.operator_name,
        "terminal": b.terminal, "channel": b.channel, "created_offline": b.created_offline,
        "created_at": iso(b.created_at), "reversed_at": iso(b.reversed_at), "reversed_by": b.reversed_by,
        "reversal_reason": b.reversal_reason, "reversal_ref": b.reversal_ref,
        "items": [{"line_no": i.line_no, "medicine_id": i.medicine_id, "medicine_name": i.medicine_name, "unit": i.unit,
                   "qty": i.qty, "rate": str(i.rate), "amount": str(i.amount)} for i in b.items],
    }


def movement_dict(m: InventoryMovement) -> dict:
    return {"id": str(m.id), "medicine_id": m.medicine_id, "medicine_name": m.medicine_name, "kind": m.kind,
            "qty_change": m.qty_change, "balance_after": m.balance_after, "reference": m.reference,
            "user_name": m.user_name, "terminal": m.terminal, "note": m.note, "created_at": iso(m.created_at)}


def adjustment_dict(a: AdjustmentRequest) -> dict:
    return {
        "id": str(a.id), "request_no": a.request_no, "medicine_id": a.medicine_id, "medicine_name": a.medicine_name,
        "kind": a.kind, "quantity": a.quantity, "new_rate": str(a.new_rate) if a.new_rate is not None else None,
        "reason": a.reason, "status": a.status, "requested_by_id": str(a.requested_by_id),
        "requested_by_name": a.requested_by_name, "requested_at": iso(a.requested_at),
        "stock_at_request": a.stock_at_request, "rate_at_request": str(a.rate_at_request),
        "decided_by_id": str(a.decided_by_id) if a.decided_by_id else None, "decided_by_name": a.decided_by_name,
        "decided_at": iso(a.decided_at), "decision_note": a.decision_note, "channel": a.channel,
    }


def alert_dict(a: StockAlert) -> dict:
    return {"id": str(a.id), "medicine_id": a.medicine_id, "medicine_name": a.medicine_name, "remaining": a.remaining,
            "threshold": a.threshold, "message": a.message, "raised_at": iso(a.raised_at), "updated_at": iso(a.updated_at),
            "acknowledged_at": iso(a.acknowledged_at), "acknowledged_by": a.acknowledged_by}


def audit_dict(a: AuditLog) -> dict:
    return {"id": str(a.id), "at": iso(a.at), "user_id": str(a.user_id) if a.user_id else None, "username": a.username,
            "user_name": a.user_name, "action": a.action, "detail": a.detail, "terminal": a.terminal,
            "channel": a.channel, "offline": a.offline, "origin": a.origin, "synced": a.synced}


def user_public(u: User) -> dict:
    return {"id": str(u.id), "username": u.username, "full_name": u.full_name, "mobile_masked": mask_mobile(u.mobile),
            "role": u.role, "permissions": perms_for(u.role), "is_active": u.is_active, "is_verified": u.is_verified,
            "offline_login_enabled": u.offline_login_enabled, "locked_until": iso(u.locked_until),
            "last_login_at": iso(u.last_login_at), "created_at": iso(u.created_at)}


# Directory snapshot sent cloud -> hospital over the VPN (needed for offline login; hashes are Argon2id).
DIRECTORY_FIELDS = ("username", "full_name", "mobile", "role", "password_hash", "is_active", "is_verified",
                    "offline_login_enabled", "token_version", "directory_version")


def user_snapshot(u: User) -> dict:
    d = {f: getattr(u, f) for f in DIRECTORY_FIELDS}
    d.update(id=str(u.id), verified_at=iso(u.verified_at), created_at=iso(u.created_at))
    return d

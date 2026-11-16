from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Bill, BillItem, Medicine, StockAlert
from ..serializers import alert_dict, bill_dict
from ..store import low_stock_threshold
from ..util import AppError, local_today


def _period(period: str, day: date) -> tuple[date, date]:
    if period == "day":
        return day, day
    if period == "month":
        start = day.replace(day=1)
        end = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
        return start, date.fromordinal(end.toordinal() - 1)
    if period == "year":
        return date(day.year, 1, 1), date(day.year, 12, 31)
    raise AppError("VALIDATION", "period must be day, month or year")


def dispensing(db: Session, period: str, day: date) -> dict:
    start, end = _period(period, day)
    in_range = (Bill.business_date >= start, Bill.business_date <= end)
    rows = db.execute(
        select(BillItem.medicine_id, BillItem.medicine_name, BillItem.unit,
               func.sum(BillItem.qty), func.sum(BillItem.amount))
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(Bill.status == "confirmed", *in_range)
        .group_by(BillItem.medicine_id, BillItem.medicine_name, BillItem.unit)
        .order_by(func.sum(BillItem.qty).desc())
    ).all()
    stock = {m.id: m.stock for m in db.scalars(select(Medicine).where(Medicine.id.in_([r[0] for r in rows])))}
    confirmed = db.scalar(select(func.count()).select_from(Bill).where(Bill.status == "confirmed", *in_range)) or 0
    reversed_ = db.scalar(select(func.count()).select_from(Bill).where(Bill.status == "reversed", *in_range)) or 0
    total = db.scalar(select(func.coalesce(func.sum(Bill.total), 0)).where(Bill.status == "confirmed", *in_range))
    items = [{"medicine_id": r[0], "medicine_name": r[1], "unit": r[2], "qty": int(r[3] or 0),
              "amount": str(Decimal(r[4] or 0).quantize(Decimal("0.01"))), "current_stock": stock.get(r[0])} for r in rows]
    return {"period": period, "start": start.isoformat(), "end": end.isoformat(), "bills": confirmed,
            "reversed_bills": reversed_, "distinct_medicines": len(items), "units": sum(i["qty"] for i in items),
            "total": str(Decimal(total or 0).quantize(Decimal("0.01"))), "items": items}


def dashboard(db: Session, settings: Settings) -> dict:
    today = local_today(settings.timezone)
    report = dispensing(db, "day", today)
    threshold = low_stock_threshold(db, settings)
    low = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.stock > 0, Medicine.stock <= threshold)) or 0
    out = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.stock <= 0)) or 0
    total_meds = db.scalar(select(func.count()).select_from(Medicine)) or 0
    alerts = list(db.scalars(select(StockAlert).where(StockAlert.acknowledged_at.is_(None))
                             .order_by(StockAlert.updated_at.desc()).limit(6)))
    active_alerts = db.scalar(select(func.count()).select_from(StockAlert).where(StockAlert.acknowledged_at.is_(None))) or 0
    recent = list(db.scalars(select(Bill).where(Bill.business_date == today).order_by(Bill.created_at.desc()).limit(6)))
    return {"date": today.isoformat(), "sales": report["total"], "bills": report["bills"], "units": report["units"],
            "low_stock": low, "out_of_stock": out, "medicines": total_meds, "threshold": threshold,
            "active_alerts": active_alerts, "alerts": [alert_dict(a) for a in alerts],
            "top_medicines": report["items"][:7], "recent_bills": [bill_dict(b) for b in recent]}

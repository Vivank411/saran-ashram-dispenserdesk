"""Admin commands.

  python -m app.cli seed-stock /data/stock.csv          (hospital) import/refresh the medicine register
  python -m app.cli create-admin --username ... --name ... --mobile ...   (normally use the first-time sign-up screen instead)
  python -m app.cli seed-demo                           (non-production) demo users on either server
"""
import argparse
import csv
import getpass
import os
import sys
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from .config import Settings
from .db import make_engine, make_sessionmaker
from .models import InventoryMovement, Medicine, User
from .security import hash_password, validate_password_policy
from .serializers import medicine_dict
from .store import audit, enqueue, ensure_defaults
from .util import AppError, utcnow

DEMO_NAMESPACE = uuid.UUID("6f1c2d40-5a1b-4c7e-9d3a-2b8e7f0a1c55")
DEMO_USERS = [
    ("admin", "Hospital Administrator", "Admin", "+91 98100 01002", True),
    ("biller", "Counter Biller", "Biller", "+91 98100 01003", True),
    ("newbiller", "New Biller", "Biller", "+91 98100 01006", False),
]


def _session(settings: Settings):
    SessionLocal = make_sessionmaker(make_engine(settings.database_url))
    ensure_defaults(SessionLocal)
    return SessionLocal()


def _money(value: str | None) -> Decimal:
    return Decimal(value or "0").quantize(Decimal("0.01"))


def _norm(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def seed_stock(settings: Settings, path: str) -> int:
    if not settings.is_hospital:
        raise SystemExit("seed-stock must be run on the hospital server (it is the stock authority).")
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    count = 0
    with _session(settings) as db:
        for raw in rows:
            row = {_norm(k): (v or "").strip() for k, v in raw.items() if k}
            try:
                code = int(row["code"])
                rate = _money(row.get("rate"))
                cost = _money(row.get("cost"))
                mrp = _money(row.get("mrp"))
                stock = int(float(row.get("stock") or 0))
            except (KeyError, ValueError, InvalidOperation):
                print(f"skipping invalid row: {raw}", file=sys.stderr)
                continue
            company = row.get("company", "")[:60]
            m = db.get(Medicine, code)
            now = utcnow()
            if m is None:
                m = Medicine(id=code, name=row["name"].upper(), unit=row.get("unit", ""), stock=stock, rate=rate,
                             cost=cost, mrp=mrp, company=company, is_active=True, version=1, updated_at=now)
                db.add(m)
                db.add(InventoryMovement(id=uuid.uuid4(), medicine_id=code, medicine_name=m.name, kind="opening",
                                         qty_change=stock, balance_after=stock, reference="OPENING", user_name="System",
                                         terminal="-", note=f"Imported from {os.path.basename(path)}", created_at=now))
            else:  # reference data refresh only — quantities and selling rates change through approvals
                m.name, m.unit = row["name"].upper(), row.get("unit", m.unit)
                m.cost, m.mrp, m.company = cost, mrp, company
                m.version += 1
                m.updated_at = now
            db.flush()
            enqueue(db, "medicine.upsert", {"medicine": medicine_dict(m)})
            count += 1
        audit(db, settings, "Stock register imported", f"{count} medicines from {os.path.basename(path)}")
        db.commit()
    return count


def create_admin(settings: Settings, username: str, name: str, mobile: str, user_id: str | None) -> None:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password for the Admin: ")
    validate_password_policy(password, username)
    with _session(settings) as db:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit("That username already exists.")
        db.add(User(id=uuid.UUID(user_id) if user_id else uuid.uuid4(), username=username.lower(), full_name=name,
                    mobile=mobile, role="Admin", password_hash=hash_password(password), is_active=True,
                    is_verified=True, verified_at=utcnow(), offline_login_enabled=True, token_version=1,
                    directory_version=1, failed_logins=0))
        audit(db, settings, "Admin created", f"{username} via CLI")
        db.commit()
    print(f"Admin '{username}' created.")


def seed_demo(settings: Settings, password: str) -> None:
    if settings.environment == "production":
        raise SystemExit("seed-demo is disabled in production.")
    hashed = hash_password(password)
    with _session(settings) as db:
        for username, name, role, mobile, verified in DEMO_USERS:
            uid = uuid.uuid5(DEMO_NAMESPACE, username)  # identical ids on hospital and cloud
            if db.get(User, uid):
                continue
            db.add(User(id=uid, username=username, full_name=name, mobile=mobile, role=role, password_hash=hashed,
                        is_active=True, is_verified=verified, verified_at=utcnow() if verified else None,
                        offline_login_enabled=verified, token_version=1, directory_version=1, failed_logins=0))
        db.commit()
    print(f"Demo users ready (password: {password}).")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("seed-stock")
    p.add_argument("csv_path")
    p = sub.add_parser("create-admin")
    p.add_argument("--username", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--mobile", required=True)
    p.add_argument("--id", default=None, help="reuse the cloud user's id when bootstrapping a hospital offline")
    p = sub.add_parser("seed-demo")
    p.add_argument("--password", default="demo1234")
    args = parser.parse_args(argv)
    settings = Settings()
    try:
        if args.cmd == "seed-stock":
            print(f"Imported {seed_stock(settings, args.csv_path)} medicines.")
        elif args.cmd == "create-admin":
            create_admin(settings, args.username, args.name, args.mobile, args.id)
        elif args.cmd == "seed-demo":
            seed_demo(settings, args.password)
    except AppError as exc:
        raise SystemExit(exc.message)


if __name__ == "__main__":
    main()

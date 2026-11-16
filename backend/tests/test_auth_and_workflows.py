"""Required tests 10, 12, 13 + authentication/session security."""
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select, text

from app.models import Medicine, User

from .conftest import PASSWORD, new_bill

PARACETAMOL = 103


def test_10_offline_login(env):
    env.cut()
    env.sync()  # worker notices the link is down
    c = env.hospital_client()
    r = c.post("/api/auth/login", json={"username": "biller", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["session"]["offline"] is True
    r = c.post("/api/auth/login", json={"username": "newbiller", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "OFFLINE_NOT_ALLOWED"
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 423 and r.json()["error"]["code"] == "LOCKED"
    with env.hdb() as h:
        for u in h.scalars(select(User)):
            assert u.password_hash.startswith("$argon2id$") and PASSWORD not in u.password_hash
        logs = h.execute(text("select action, offline from audit_logs where action = 'Offline sign-in'")).all()
        assert logs and logs[0][1]


def test_first_time_verification_via_cloud_otp(env):
    c = env.hospital_client()
    r = c.post("/api/auth/login", json={"username": "newbiller", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["status"] == "otp_required" and r.json()["purpose"] == "verify"
    ch = r.json()
    bad = c.post("/api/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "000000" if ch["dev_code"] != "000000" else "111111"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "OTP_INVALID"
    ok = c.post("/api/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_code"]})
    assert ok.status_code == 200 and ok.json()["user"]["is_verified"] is True
    # now verified -> offline sign-in works
    env.cut()
    env.sync()
    r = env.hospital_client().post("/api/auth/login", json={"username": "newbiller", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["session"]["offline"] is True


def test_otp_rate_limit(env):
    from fastapi.testclient import TestClient
    c = TestClient(env.cloud)
    for _ in range(3):
        assert c.post("/api/auth/login", json={"username": "biller", "password": PASSWORD}).status_code == 200
    r = c.post("/api/auth/login", json={"username": "biller", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "OTP_RATE_LIMIT"


def test_refresh_rotation_and_revocation(env):
    c = env.login_hospital("biller")
    r = c.post("/api/auth/refresh")
    assert r.status_code == 200
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    assert c.get("/api/auth/me").status_code == 200
    admin = env.login_cloud("admin")
    uid = c.get("/api/auth/me").json()["user"]["id"]
    assert admin.post(f"/api/users/{uid}/revoke-sessions").status_code == 200
    env.sync()  # directory pull brings the new token version to the hospital
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/refresh").status_code == 401


def test_12_approval_workflow(env):
    biller = env.login_hospital("biller")
    body = {"medicine_id": PARACETAMOL, "kind": "add", "quantity": 100, "reason": "Purchase invoice 42"}
    req = biller.post("/api/adjustments", json=body).json()
    assert req["status"] == "pending"  # biller can manage inventory, but only with Admin permission
    assert biller.post(f"/api/adjustments/{req['id']}/decide", json={"approve": True}).status_code == 403
    with env.hdb() as h:
        assert h.get(Medicine, PARACETAMOL).stock == 5793  # nothing changes before approval
    admin = env.login_hospital("admin")
    r = admin.post(f"/api/adjustments/{req['id']}/decide", json={"approve": True, "note": "Invoice checked"})
    assert r.status_code == 200 and r.json()["adjustment"]["status"] == "approved"
    with env.hdb() as h:
        assert h.get(Medicine, PARACETAMOL).stock == 5893
    # Admin can do everything: an Admin change applies immediately (still recorded and audited)
    direct = admin.post("/api/adjustments", json={"medicine_id": PARACETAMOL, "kind": "remove", "quantity": 5,
                                                  "reason": "Damaged strip"}).json()
    assert direct["status"] == "approved" and direct["decided_by_name"] == "Hospital Administrator"
    with env.hdb() as h:
        assert h.get(Medicine, PARACETAMOL).stock == 5888
    # rejection, and remote approval through the gateway
    rej = biller.post("/api/adjustments", json={**body, "quantity": 1}).json()
    r = admin.post(f"/api/adjustments/{rej['id']}/decide", json={"approve": False, "note": "No invoice"})
    assert r.json()["adjustment"]["status"] == "rejected"
    pending = biller.post("/api/adjustments", json={**body, "quantity": 2}).json()
    remote_admin = env.login_cloud("admin")
    assert remote_admin.post(f"/api/adjustments/{pending['id']}/decide", json={"approve": True}).status_code == 200
    env.sync()
    with env.cdb() as cl:
        assert cl.get(Medicine, PARACETAMOL).stock == 5890


def test_rate_change_enables_billing(env):
    biller, admin = env.login_hospital("biller"), env.login_hospital("admin")
    req = biller.post("/api/adjustments", json={"medicine_id": 130, "kind": "set_rate", "new_rate": "62.64",
                                                "reason": "MRP list"}).json()
    assert biller.post("/api/bills", json=new_bill([(130, 1)])).status_code == 409  # not yet approved
    admin.post(f"/api/adjustments/{req['id']}/decide", json={"approve": True})
    assert biller.post("/api/bills", json=new_bill([(130, 1)])).status_code == 200


def test_user_directory_requires_internet_on_hospital(env):
    admin = env.login_hospital("admin")
    payload = {"full_name": "Priya S", "username": "priya.s", "mobile": "+91 98100 22222", "role": "Biller",
               "password": "Str0ngPass!"}
    r = admin.post("/api/users", json=payload)
    assert r.status_code == 200, r.text
    assert any(u["username"] == "priya.s" for u in admin.get("/api/users").json()["items"])  # pulled back
    env.cut()
    r = admin.post("/api/users", json={**payload, "username": "other.user"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "DIRECTORY_OFFLINE"


def test_only_admin_and_biller_roles(env):
    from app.permissions import PERMISSIONS
    admin = env.login_cloud("admin")
    base = {"full_name": "X Y", "username": "xy.z", "mobile": "+91 98100 33333", "password": "Str0ngPass!"}
    assert admin.post("/api/users", json={**base, "role": "Report Viewer"}).status_code == 422
    assert admin.post("/api/users", json={**base, "role": "Admin"}).status_code == 200
    assert admin.get("/api/auth/me").json()["user"]["permissions"] == list(PERMISSIONS)  # Admin can do everything
    biller = env.login_cloud("biller")
    assert biller.get("/api/users").status_code == 403
    assert biller.get("/api/audit").status_code == 403


def test_last_admin_cannot_be_removed(env):
    admin = env.login_cloud("admin")
    other = admin.post("/api/users", json={"full_name": "Second Admin", "username": "admin2", "mobile": "+91 98100 44444",
                                           "role": "Admin", "password": "Str0ngPass!"}).json()
    demote = {"role": "Biller", "is_active": True, "offline_login_enabled": False}
    assert admin.patch(f"/api/users/{other['id']}", json=demote).status_code == 200
    second = env.login_cloud("admin")  # the only Admin now; cannot demote self
    me = second.get("/api/auth/me").json()["user"]["id"]
    assert second.patch(f"/api/users/{me}", json=demote).status_code in (400, 409)


def test_13_migrations_build_schema(tmp_path):
    """Schema is reproducible from Alembic migrations (backup restore also re-runs them)."""
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    result = subprocess.run([sys.executable, "-m", "alembic", "-x", "unused=1", "upgrade", "head"], cwd=backend,
                            env={**__import__("os").environ, "DATABASE_URL": url}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    from sqlalchemy import create_engine, inspect
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"users", "medicines", "bills", "outbox_events", "inbox_events", "sync_conflicts"} <= tables

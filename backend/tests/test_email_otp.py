"""Standalone email OTP: a code is emailed on the first sign-in from a new device, then that device is trusted."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.config import Settings
from app.db import Base
from app.main import create_app

SIGNUP = {"hospital_name": "Saran Ashram Dispensary", "low_stock_threshold": 50, "full_name": "Saran",
          "username": "saran", "mobile": "+91 98765 43210", "password": "saran123"}


@pytest.fixture()
def app(tmp_path):
    settings = Settings(environment="test", app_role="hospital", standalone=True, email_otp=True,
                        email_provider="console", dev_expose_otp=True, jwt_secret="x" * 40, sync_shared_secret="y" * 40,
                        database_url=f"sqlite:///{tmp_path / 'e.db'}", peer_api_url="http://127.0.0.1:9")
    app = create_app(settings, start_worker=False)
    Base.metadata.drop_all(app.state.engine)
    Base.metadata.create_all(app.state.engine)
    yield app
    store.set_standalone(False)


def _client(app, terminal="PC-1") -> TestClient:
    return TestClient(app, headers={"X-Terminal-Id": terminal})


def _admin(app) -> TestClient:
    c = _client(app)
    assert c.post("/api/auth/setup", json=SIGNUP).status_code == 200
    r = c.post("/api/auth/login", json={"username": "saran", "password": "saran123"}).json()
    assert r["status"] == "ok"  # no email on the admin yet -> password only
    c.headers["Authorization"] = f"Bearer {r['access_token']}"
    return c


def test_new_device_needs_email_code_then_is_trusted(app):
    admin = _admin(app)
    assert admin.get("/api/system/status").json()["email_otp"] is True
    r = admin.post("/api/users", json={"full_name": "Ravi", "username": "ravi", "email": "Ravi.K@Example.com",
                                       "role": "Biller", "password": "ravi12"})
    assert r.status_code == 200 and r.json()["email"] == "ravi.k@example.com"

    phone = _client(app, "PHONE")
    r = phone.post("/api/auth/login", json={"username": "ravi", "password": "ravi12"}).json()
    assert r["status"] == "otp_required" and r["channel"] == "email" and r["sent_to"] == "ra••••@example.com"
    bad = phone.post("/api/auth/otp/verify", json={"challenge_id": r["challenge_id"], "code": "000000"
                                                   if r["dev_code"] != "000000" else "111111"})
    assert bad.status_code == 400
    ok = phone.post("/api/auth/otp/verify", json={"challenge_id": r["challenge_id"], "code": r["dev_code"]})
    assert ok.status_code == 200 and ok.json()["status"] == "ok" and "device_token" not in ok.json()
    assert phone.cookies.get("dd_device")

    # same browser: straight in
    assert phone.post("/api/auth/login", json={"username": "ravi", "password": "ravi12"}).json()["status"] == "ok"
    # another browser: code again
    assert _client(app, "PC-2").post("/api/auth/login", json={"username": "ravi", "password": "ravi12"}).json()["status"] == "otp_required"
    # wrong password never reaches the code step
    assert phone.post("/api/auth/login", json={"username": "ravi", "password": "nope99"}).status_code == 401

    # "sign out everywhere" forgets trusted devices
    uid = next(u["id"] for u in admin.get("/api/users").json()["items"] if u["username"] == "ravi")
    assert admin.post(f"/api/users/{uid}/revoke-sessions").status_code == 200
    assert phone.post("/api/auth/login", json={"username": "ravi", "password": "ravi12"}).json()["status"] == "otp_required"


def test_resend_and_admin_can_set_email(app):
    admin = _admin(app)
    me = admin.get("/api/auth/me").json()["user"]
    r = admin.patch(f"/api/users/{me['id']}", json={"role": "Admin", "is_active": True, "offline_login_enabled": True,
                                                    "email": "saran@example.com"})
    assert r.status_code == 200 and r.json()["email"] == "saran@example.com"
    c = _client(app, "LAPTOP")
    first = c.post("/api/auth/login", json={"username": "saran", "password": "saran123"}).json()
    assert first["status"] == "otp_required"
    again = c.post("/api/auth/otp/resend", json={"challenge_id": first["challenge_id"]}).json()
    assert again["status"] == "otp_required" and again["challenge_id"] != first["challenge_id"]
    old = c.post("/api/auth/otp/verify", json={"challenge_id": first["challenge_id"], "code": first["dev_code"]})
    assert old.status_code == 400  # the replaced code no longer works
    assert c.post("/api/auth/otp/verify", json={"challenge_id": again["challenge_id"], "code": again["dev_code"]}).status_code == 200

    bad = admin.post("/api/users", json={"full_name": "X Y", "username": "xyz", "email": "not-an-email", "role": "Biller", "password": "xy1234"})
    assert bad.status_code == 422 and "valid email" in bad.json()["error"]["message"]


def test_email_otp_off_means_password_only(tmp_path):
    settings = Settings(environment="test", app_role="hospital", standalone=True, jwt_secret="x" * 40,
                        sync_shared_secret="y" * 40, database_url=f"sqlite:///{tmp_path / 'o.db'}", peer_api_url="http://127.0.0.1:9")
    app = create_app(settings, start_worker=False)
    Base.metadata.create_all(app.state.engine)
    try:
        admin = _admin(app)
        admin.post("/api/users", json={"full_name": "Ravi", "username": "ravi", "email": "r@example.com", "role": "Biller", "password": "ravi12"})
        assert _client(app).post("/api/auth/login", json={"username": "ravi", "password": "ravi12"}).json()["status"] == "ok"
    finally:
        store.set_standalone(False)


def test_production_requires_real_email_provider():
    with pytest.raises(ValueError):
        Settings(environment="production", app_role="hospital", standalone=True, email_otp=True, email_provider="console",
                 jwt_secret="x" * 40, sync_shared_secret="y" * 40, database_url="postgresql+psycopg://u:p@h/db")

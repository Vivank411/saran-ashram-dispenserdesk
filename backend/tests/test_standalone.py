"""Standalone mode: a single server (e.g. Render + Neon) with no cloud peer — it must never look 'offline'."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import store
from app.config import Settings
from app.db import Base
from app.main import create_app
from app.models import OutboxEvent
from app.services.sync_worker import clear_standalone_queue

SIGNUP = {"hospital_name": "Saran Ashram Dispensary", "low_stock_threshold": 50, "full_name": "Saran",
          "username": "saran", "mobile": "+91 98765 43210", "password": "Saran#2026x"}


@pytest.fixture()
def app(tmp_path):
    settings = Settings(environment="test", app_role="hospital", standalone=True, jwt_secret="x" * 40,
                        sync_shared_secret="y" * 40, database_url=f"sqlite:///{tmp_path / 's.db'}",
                        peer_api_url="http://127.0.0.1:9")  # nothing listens here: any peer call would fail
    app = create_app(settings, start_worker=False)
    Base.metadata.drop_all(app.state.engine)
    Base.metadata.create_all(app.state.engine)
    yield app
    store.set_standalone(False)


def _admin(app) -> TestClient:
    c = TestClient(app, headers={"X-Terminal-Id": "PC-1"})
    assert c.post("/api/auth/setup", json=SIGNUP).status_code == 200
    r = c.post("/api/auth/login", json={"username": "saran", "password": SIGNUP["password"]}).json()
    assert r["status"] == "ok" and r["session"]["offline"] is False
    c.headers["Authorization"] = f"Bearer {r['access_token']}"
    return c


def test_status_never_offline_and_queue_stays_empty(app):
    c = _admin(app)
    with app.state.sessionmaker() as db:
        store.enqueue(db, "bill.created", {"x": 1})
        db.commit()
        row = db.scalar(select(OutboxEvent))
        assert row.status == "synced" and row.synced_at is not None
    s = c.get("/api/system/status").json()
    assert s["standalone"] and s["cloud_reachable"] and s["live_operations"]
    assert (s["pending"], s["failed"], s["conflicts"]) == (0, 0, 0)
    assert c.post("/api/sync/run").json()["status"] == "ok"


def test_old_queue_is_cleared_on_startup(app):
    with app.state.sessionmaker() as db:
        store.set_standalone(False)
        for _ in range(3):
            store.enqueue(db, "bill.created", {})
        db.commit()
        store.set_standalone(True)
    assert clear_standalone_queue(app.state.sessionmaker) == 3
    with app.state.sessionmaker() as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")) == 0


def test_admin_can_add_a_biller_who_signs_in_without_otp(app):
    c = _admin(app)
    r = c.post("/api/users", json={"username": "biller1", "full_name": "Biller One", "mobile": "+91 91234 56789",
                                   "role": "Biller", "password": "Biller#2026x"})
    assert r.status_code == 200, r.text
    b = TestClient(app).post("/api/auth/login", json={"username": "biller1", "password": "Biller#2026x"}).json()
    assert b["status"] == "ok" and b["session"]["offline"] is False


def test_simple_password_creates_user_who_can_sign_in(app):
    c = _admin(app)
    new = {"full_name": "Ravi Kumar", "username": "ravi", "mobile": "9876543210", "role": "Biller"}
    r = c.post("/api/users", json={**new, "password": "abc12"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    assert c.post("/api/users", json={**new, "password": "ravi12"}).status_code == 200
    r = TestClient(app, headers={"X-Terminal-Id": "PC-2"}).post("/api/auth/login", json={"username": "ravi", "password": "ravi12"})
    assert r.status_code == 200 and r.json()["status"] == "ok"

"""Two real app instances (hospital + cloud), each with its own database, wired through signed HTTP.

By default each database is a temporary SQLite file. To run against PostgreSQL set
TEST_HOSPITAL_DATABASE_URL and TEST_CLOUD_DATABASE_URL (they will be wiped).
"""
import os
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cli
from app.config import Settings
from app.db import Base
from app.main import create_app
from app.services.sync_worker import run_cycle

STOCK_CSV = Path(__file__).resolve().parents[2] / "data" / "stock.csv"
PASSWORD = "demo1234"


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request):
        raise httpx.ConnectError("simulated outage: tunnel down", request=request)
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://peer")


class Env:
    def __init__(self, tmp: Path):
        common = dict(environment="test", sync_shared_secret="test-shared-secret", dev_expose_otp=True,
                      peer_api_url="http://testserver", user_pull_interval_seconds=0)
        self.hs = Settings(app_role="hospital", jwt_secret="hospital-test-jwt-secret-0123456789abcdef",
                           database_url=os.environ.get("TEST_HOSPITAL_DATABASE_URL", f"sqlite:///{tmp / 'hospital.db'}"), **common)
        self.cs = Settings(app_role="cloud", jwt_secret="cloud-test-jwt-secret-0123456789abcdef",
                           database_url=os.environ.get("TEST_CLOUD_DATABASE_URL", f"sqlite:///{tmp / 'cloud.db'}"), **common)
        self.hospital = create_app(self.hs, start_worker=False)
        self.cloud = create_app(self.cs)
        for app in (self.hospital, self.cloud):
            Base.metadata.drop_all(app.state.engine)
            Base.metadata.create_all(app.state.engine)
        self.restore()

    # ---- network control ----
    def cut(self):
        self.hospital.state.peer.client = _down_client()
        self.cloud.state.peer.client = _down_client()
        self.cloud.state.ping_cache.clear()

    def restore(self):
        self.hospital.state.peer.client = TestClient(self.cloud)
        self.cloud.state.peer.client = TestClient(self.hospital)
        self.cloud.state.ping_cache.clear()

    def sync(self, force: bool = True) -> dict:
        return run_cycle(self.hs, self.hospital.state.sessionmaker, self.hospital.state.peer, force=force)

    # ---- db helpers ----
    def hdb(self):
        return self.hospital.state.sessionmaker()

    def cdb(self):
        return self.cloud.state.sessionmaker()

    # ---- sessions ----
    def hospital_client(self, terminal: str = "PC-1") -> TestClient:
        return TestClient(self.hospital, headers={"X-Terminal-Id": terminal})

    def login_hospital(self, username: str, terminal: str = "PC-1", password: str = PASSWORD) -> TestClient:
        client = self.hospital_client(terminal)
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok", body
        client.headers["Authorization"] = f"Bearer {body['access_token']}"
        client.session_info = body["session"]
        return client

    def login_cloud(self, username: str, password: str = PASSWORD) -> TestClient:
        client = TestClient(self.cloud)
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        challenge = r.json()
        assert challenge["status"] == "otp_required"
        r = client.post("/api/auth/otp/verify", json={"challenge_id": challenge["challenge_id"], "code": challenge["dev_code"]})
        assert r.status_code == 200, r.text
        client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return client


@pytest.fixture()
def env(tmp_path) -> Env:
    e = Env(tmp_path)
    cli.seed_demo(e.hs, PASSWORD)
    cli.seed_demo(e.cs, PASSWORD)
    cli.seed_stock(e.hs, str(STOCK_CSV))
    assert e.sync()["status"] == "ok"  # initial replication of the register + link established
    yield e
    for app in (e.hospital, e.cloud):
        app.state.engine.dispose()


def new_bill(items, **extra) -> dict:
    return {"request_id": str(uuid.uuid4()), "payment_mode": "Cash",
            "items": [{"medicine_id": m, "qty": q} for m, q in items], **extra}


def is_postgres(env: Env) -> bool:
    with env.hdb() as db:
        return db.execute(text("select 1")).scalar() == 1 and db.bind.dialect.name == "postgresql"

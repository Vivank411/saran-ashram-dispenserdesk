"""First-time sign-up: the first person sets everything up and becomes Admin, then signs in."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cli
from app.models import User

from .conftest import STOCK_CSV, Env

SIGNUP = {"hospital_name": "Sunrise Hospital Dispensary", "low_stock_threshold": 40, "full_name": "Dr. Meera Nair",
          "username": "meera", "mobile": "+91 98765 43210", "password": "Sunrise#2026"}


def fresh(tmp_path) -> Env:
    e = Env(tmp_path)
    cli.seed_stock(e.hs, str(STOCK_CSV))
    e.sync()
    return e


def test_signup_on_hospital_then_sign_in(tmp_path):
    e = fresh(tmp_path)
    h = TestClient(e.hospital)
    assert h.get("/api/auth/setup").json() == {"needs_setup": True}
    assert h.post("/api/auth/login", json={"username": "meera", "password": "x"}).status_code == 401
    r = h.post("/api/auth/setup", json=SIGNUP)
    assert r.status_code == 200, r.text
    assert h.get("/api/auth/setup").json() == {"needs_setup": False}
    again = h.post("/api/auth/setup", json={**SIGNUP, "username": "intruder"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_SET_UP"
    with e.hdb() as hd, e.cdb() as cd:  # registered in the central directory and cached at the hospital
        for db in (hd, cd):
            u = db.scalar(select(User).where(User.username == "meera"))
            assert u.role == "Admin" and u.is_verified and u.password_hash.startswith("$argon2id$")
    tok = h.post("/api/auth/login", json={"username": "meera", "password": "Sunrise#2026"}).json()
    assert tok["status"] == "ok" and tok["user"]["role"] == "Admin"
    status = h.get("/api/system/status").json()
    assert status["hospital_name"] == "Sunrise Hospital Dispensary" and status["low_stock_threshold"] == 40
    e.sync()  # settings are owned by the hospital and synchronised to the cloud
    assert TestClient(e.cloud).get("/api/system/status").json()["hospital_name"] == "Sunrise Hospital Dispensary"
    h.headers["Authorization"] = f"Bearer {tok['access_token']}"  # the new admin adds a biller
    r = h.post("/api/users", json={"full_name": "Ravi Kumar", "username": "ravi", "mobile": "+91 98100 55555",
                                   "role": "Biller", "password": "Ravi#2026x"})
    assert r.status_code == 200, r.text


def test_signup_on_cloud(tmp_path):
    e = fresh(tmp_path)
    assert TestClient(e.cloud).post("/api/auth/setup", json=SIGNUP).status_code == 200
    assert TestClient(e.hospital).get("/api/system/status").json()["hospital_name"] == "Sunrise Hospital Dispensary"
    e.sync()  # directory pull: the hospital can now sign the admin in, even offline later
    e.cut()
    e.sync()
    r = TestClient(e.hospital).post("/api/auth/login", json={"username": "meera", "password": "Sunrise#2026"})
    assert r.status_code == 200 and r.json()["session"]["offline"] is True


def test_signup_at_hospital_works_without_cloud(tmp_path):
    e = fresh(tmp_path)
    e.cut()
    r = TestClient(e.hospital).post("/api/auth/setup", json=SIGNUP)
    assert r.status_code == 200, r.text


def test_signup_validation(tmp_path):
    e = fresh(tmp_path)
    c = TestClient(e.cloud)
    r = c.post("/api/auth/setup", json={**SIGNUP, "password": "short"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    assert c.post("/api/auth/setup", json={**SIGNUP, "username": "Bad Name"}).status_code == 422
    assert c.get("/api/auth/setup").json()["needs_setup"] is True

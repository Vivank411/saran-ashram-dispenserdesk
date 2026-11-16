"""Required tests 1, 2, 3, 8, 9, 11 — billing, outages, multi-terminal, concurrency, reversal, alerts."""
import threading

import pytest
from sqlalchemy import select

from app.models import Bill, InventoryMovement, Medicine, OutboxEvent

from .conftest import is_postgres, new_bill

PARACETAMOL, NIMESULIDE, DREP_EAR = 103, 94, 54


def stock(db, med_id):
    return db.get(Medicine, med_id).stock


def test_1_billing_with_internet(env):
    c = env.login_hospital("biller")
    r = c.post("/api/bills", json=new_bill([(PARACETAMOL, 10)], customer_name="Asha"))
    assert r.status_code == 200, r.text
    bill = r.json()["bill"]
    assert bill["total"] == "6.70" and bill["terminal"] == "PC-1" and not bill["created_offline"]
    assert env.sync()["status"] == "ok"
    with env.hdb() as h, env.cdb() as cl:
        assert stock(h, PARACETAMOL) == stock(cl, PARACETAMOL) == 5783
        assert cl.scalar(select(Bill).where(Bill.bill_no == bill["bill_no"])) is not None


def test_2_billing_during_internet_outage(env):
    env.cut()
    assert env.sync()["status"] == "offline"
    c = env.login_hospital("biller")
    assert c.session_info["offline"] is True
    r = c.post("/api/bills", json=new_bill([(PARACETAMOL, 5)]))
    assert r.status_code == 200, r.text
    assert r.json()["bill"]["created_offline"] is True
    assert env.sync()["status"] == "offline"
    with env.hdb() as h, env.cdb() as cl:
        assert stock(h, PARACETAMOL) == 5788
        assert stock(cl, PARACETAMOL) == 5793  # cloud untouched
        assert cl.scalar(select(Bill)) is None
        assert h.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "bill.created")).status in ("pending", "failed")


def test_3_stock_deduction_across_terminals(env):
    nos = []
    for i in range(1, 6):
        c = env.login_hospital("biller", terminal=f"PC-{i}")
        r = c.post("/api/bills", json=new_bill([(PARACETAMOL, 100)]))
        assert r.status_code == 200, r.text
        nos.append((r.json()["bill"]["bill_no"], r.json()["bill"]["terminal"]))
    assert len({n for n, _ in nos}) == 5 and {t for _, t in nos} == {f"PC-{i}" for i in range(1, 6)}
    with env.hdb() as h:
        assert stock(h, PARACETAMOL) == 5293


def test_8_concurrent_stock_deduction_sequential_guard_and_rollback(env):
    with env.hdb() as h:
        h.get(Medicine, PARACETAMOL).stock = 5
        h.commit()
    a, b = env.login_hospital("biller", "PC-1"), env.login_hospital("biller", "PC-2")
    assert a.post("/api/bills", json=new_bill([(PARACETAMOL, 4)])).status_code == 200
    r = b.post("/api/bills", json=new_bill([(PARACETAMOL, 3)]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    before = None
    with env.hdb() as h:
        before = stock(h, NIMESULIDE)
    r = b.post("/api/bills", json=new_bill([(NIMESULIDE, 1), (PARACETAMOL, 2)]))
    assert r.status_code == 409
    with env.hdb() as h:
        assert stock(h, PARACETAMOL) == 1
        assert stock(h, NIMESULIDE) == before  # whole transaction rolled back


def test_8b_true_parallel_deduction(env):
    if not is_postgres(env):
        pytest.skip("true parallel row-locking test needs PostgreSQL (set TEST_*_DATABASE_URL)")
    with env.hdb() as h:
        h.get(Medicine, PARACETAMOL).stock = 50
        h.commit()
    clients = [env.login_hospital("biller", f"PC-{i % 5 + 1}") for i in range(10)]
    results = []

    def worker(c):
        results.append(c.post("/api/bills", json=new_bill([(PARACETAMOL, 7)])).status_code)

    threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(200) == 7 and results.count(409) == 3
    with env.hdb() as h:
        assert stock(h, PARACETAMOL) == 1


def test_9_bill_reversal_restores_stock(env):
    c = env.login_hospital("biller")
    bill = c.post("/api/bills", json=new_bill([(PARACETAMOL, 20)])).json()["bill"]
    assert c.post(f"/api/bills/{bill['id']}/reverse", json={"reason": "Wrong patient"}).status_code == 403
    admin = env.login_hospital("admin")
    r = admin.post(f"/api/bills/{bill['id']}/reverse", json={"reason": "Wrong patient"})
    assert r.status_code == 200 and r.json()["status"] == "reversed"
    again = admin.post(f"/api/bills/{bill['id']}/reverse", json={"reason": "again"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_REVERSED"
    with env.hdb() as h:
        assert stock(h, PARACETAMOL) == 5793
        kinds = [m.kind for m in h.scalars(select(InventoryMovement).where(InventoryMovement.medicine_id == PARACETAMOL))]
        assert "bill_issue" in kinds and "bill_reversal" in kinds
    assert env.sync()["status"] == "ok"
    with env.cdb() as cl:
        assert cl.get(Bill, __import__("uuid").UUID(bill["id"])).status == "reversed"
        assert stock(cl, PARACETAMOL) == 5793


def test_11_offline_low_stock_alert(env):
    env.cut()
    env.sync()
    c = env.login_hospital("biller")
    r = c.post("/api/bills", json=new_bill([(DREP_EAR, 1)]))
    assert r.status_code == 200
    assert "LOW STOCK ALERT: DREP EAR DROP — 36 units remaining." in r.json()["alerts"]
    alerts = c.get("/api/alerts?active=true").json()["items"]
    assert any(a["message"] == "LOW STOCK ALERT: DREP EAR DROP — 36 units remaining." for a in alerts)
    # acknowledgement works offline and syncs later
    alert_id = next(a["id"] for a in alerts if a["medicine_id"] == DREP_EAR)
    assert c.post(f"/api/alerts/{alert_id}/ack").status_code == 200
    env.restore()
    assert env.sync()["status"] == "ok"
    remote = env.login_cloud("biller")
    acked = remote.get("/api/alerts?active=false").json()["items"]
    assert any(a["id"] == alert_id for a in acked)


def test_idempotent_bill_submission(env):
    c = env.login_hospital("biller")
    body = new_bill([(PARACETAMOL, 3)])
    first = c.post("/api/bills", json=body).json()
    second = c.post("/api/bills", json=body).json()
    assert second["duplicate"] is True and second["bill"]["bill_no"] == first["bill"]["bill_no"]
    with env.hdb() as h:
        assert stock(h, PARACETAMOL) == 5790


def test_register_matches_original_stock_file(env):
    with env.hdb() as h, env.cdb() as cl:
        assert len(list(h.scalars(select(Medicine)))) == 116
        for db in (h, cl):  # hospital and replicated cloud copy
            becasul = db.get(Medicine, 26)
            assert (becasul.name, becasul.stock, str(becasul.rate), str(becasul.cost), str(becasul.mrp), becasul.company) == \
                   ("SYP BECASUL", 0, "33.50", "37.08", "37.08", "ZZZZZZ 77")
            assert db.get(Medicine, 129).company == "ZZZZZZ 82"


def test_terminal_defaults_to_computer_address(env):
    from fastapi.testclient import TestClient
    c = TestClient(env.hospital)  # no X-Terminal-Id header, like the real UI
    tok = c.post("/api/auth/login", json={"username": "biller", "password": "demo1234"}).json()
    c.headers["Authorization"] = f"Bearer {tok['access_token']}"
    bill = c.post("/api/bills", json=new_bill([(PARACETAMOL, 1)])).json()["bill"]
    assert bill["terminal"] == "testclient" and tok["session"]["terminal"] == "testclient"


def test_zero_rate_and_out_of_stock_rejected(env):
    c = env.login_hospital("biller")
    r = c.post("/api/bills", json=new_bill([(130, 1)]))  # SYP MEFTAL rate 0
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_RATE"
    r = c.post("/api/bills", json=new_bill([(15, 1)]))  # AQUASOL A stock 0
    assert r.json()["error"]["code"] == "INSUFFICIENT_STOCK"

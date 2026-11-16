"""Required tests 4, 5, 6, 7, 14 — remote access, reconnection sync, duplicates, failure/recovery, conflicts."""
from sqlalchemy import select

from app.models import Bill, InboxEvent, Medicine, OutboxEvent, SyncConflict
from app.peer import PeerClient

from .conftest import new_bill

PARACETAMOL, NIMESULIDE = 103, 94


def test_4_remote_billing_when_hospital_reachable(env):
    remote = env.login_cloud("biller")
    live = remote.get("/api/medicines?live=true&q=PARACETAMOL").json()
    assert live["source"] == "hospital_live"
    r = remote.post("/api/bills", json=new_bill([(PARACETAMOL, 3)]))
    assert r.status_code == 200, r.text
    bill = r.json()["bill"]
    assert bill["channel"] == "remote" and bill["terminal"] == "Remote"
    with env.hdb() as h:
        assert h.get(Medicine, PARACETAMOL).stock == 5790  # committed on the authoritative DB
    env.sync()
    assert any(b["bill_no"] == bill["bill_no"] for b in remote.get("/api/bills").json()["items"])


def test_5_remote_access_when_hospital_unavailable(env):
    remote = env.login_cloud("biller")
    env.cut()
    status = remote.get("/api/system/status").json()
    assert status["live_operations"] is False and status["last_sync"]
    r = remote.post("/api/bills", json=new_bill([(PARACETAMOL, 3)]))
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "LIVE_BILLING_UNAVAILABLE" and err["last_sync"]
    assert remote.get("/api/medicines?live=true").status_code == 503
    # read-only access to the last synchronized data still works
    assert remote.get("/api/medicines").json()["source"] == "cloud_replica"
    assert remote.get("/api/bills").status_code == 200
    with env.hdb() as h, env.cdb() as c:
        assert h.get(Medicine, PARACETAMOL).stock == 5793 == c.get(Medicine, PARACETAMOL).stock


def test_6_sync_after_connectivity_restored(env):
    env.cut()
    env.sync()
    c = env.login_hospital("biller")
    for _ in range(3):
        assert c.post("/api/bills", json=new_bill([(PARACETAMOL, 2), (NIMESULIDE, 4)])).status_code == 200
    env.restore()
    result = env.sync()
    assert result["status"] == "ok" and result["applied"] >= 3
    with env.hdb() as h, env.cdb() as cl:
        assert all(e.status == "synced" for e in h.scalars(select(OutboxEvent)))
        assert len(list(cl.scalars(select(Bill)))) == 3
        for m in h.scalars(select(Medicine)):
            r = cl.get(Medicine, m.id)
            assert (r.stock, r.version) == (m.stock, m.version)


def test_7_duplicate_synchronization_prevention(env):
    c = env.login_hospital("biller")
    c.post("/api/bills", json=new_bill([(PARACETAMOL, 10)]))
    env.sync()
    with env.hdb() as h:  # simulate a lost acknowledgement: the event is re-sent
        ev = h.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "bill.created"))
        ev.status = "pending"
        h.commit()
    result = env.sync()
    assert result["duplicates"] == 1 and result["applied"] == 0
    with env.cdb() as cl:
        assert len(list(cl.scalars(select(Bill)))) == 1
        assert cl.get(Medicine, PARACETAMOL).stock == 5783
        assert len(list(cl.scalars(select(InboxEvent).where(InboxEvent.event_type == "bill.created")))) == 1


def test_14_sync_failure_and_recovery(env):
    c = env.login_hospital("biller")
    env.cut()
    c.post("/api/bills", json=new_bill([(PARACETAMOL, 1)]))
    assert env.sync()["status"] == "offline"
    with env.hdb() as h:
        ev = h.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "bill.created"))
        assert ev.status == "failed" and ev.attempts == 1 and ev.next_attempt_at is not None
    env.restore()
    assert env.sync()["status"] == "ok"
    with env.cdb() as cl:
        assert cl.scalar(select(Bill)) is not None


def test_14b_conflict_detected_held_and_resolved(env):
    with env.cdb() as cl:  # out-of-band edit on the cloud replica
        m = cl.get(Medicine, NIMESULIDE)
        m.stock += 7
        m.version += 1
        cl.commit()
    c = env.login_hospital("biller")
    c.post("/api/bills", json=new_bill([(NIMESULIDE, 1)]))
    c.post("/api/bills", json=new_bill([(PARACETAMOL, 1)]))
    assert env.sync()["status"] == "conflict"
    with env.cdb() as cl:
        assert cl.get(Medicine, NIMESULIDE).stock == 5920  # not silently overwritten
        assert cl.get(Medicine, PARACETAMOL).stock == 5793  # later event held back (ordering)
        assert cl.scalar(select(SyncConflict)).resolved_at is None
    assert env.sync()["status"] == "blocked"
    admin = env.login_hospital("admin")
    detail = admin.get("/api/sync/status").json()
    assert detail["conflicts"] == 1 and detail["conflict_list"][0]["detail"]["cloud_stock"] == 5920
    event_id = detail["conflict_list"][0]["event_id"]
    assert c.post(f"/api/sync/conflicts/{event_id}/resolve", json={"note": "x"}).status_code in (403, 422)
    r = admin.post(f"/api/sync/conflicts/{event_id}/resolve", json={"note": "Reviewed: hospital count is authoritative"})
    assert r.status_code == 200, r.text
    assert env.sync()["status"] == "ok"
    with env.hdb() as h, env.cdb() as cl:
        assert cl.get(Medicine, NIMESULIDE).stock == h.get(Medicine, NIMESULIDE).stock == 5912
        assert cl.get(Medicine, PARACETAMOL).stock == 5792
        assert cl.scalar(select(SyncConflict)).resolution_note.startswith("Reviewed")


def test_peer_endpoints_reject_unsigned_or_forged_requests(env):
    from fastapi.testclient import TestClient
    raw = TestClient(env.cloud)
    assert raw.get("/api/internal/sync/users").status_code == 401
    forged = PeerClient(env.hs.model_copy(update={"sync_shared_secret": "wrong"}), TestClient(env.cloud))
    assert forged.call("GET", "/api/internal/sync/users").status_code == 401


def test_remote_users_have_same_role_restrictions(env):
    remote_biller = env.login_cloud("biller")
    bill = remote_biller.post("/api/bills", json=new_bill([(PARACETAMOL, 1)])).json()["bill"]
    assert remote_biller.post(f"/api/bills/{bill['id']}/reverse", json={"reason": "test"}).status_code == 403
    assert remote_biller.get("/api/sync/status").status_code == 403
    assert remote_biller.get("/api/reports/dispensing").status_code == 200

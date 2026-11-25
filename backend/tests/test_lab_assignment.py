# ruff: noqa: F811  (fixtures imported from test_lab are used as test parameters)

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from test_lab import RESULT, approve, doctor, lab, make_referral, referral  # noqa: F401 (fixtures)

from app.db.models import AuditEvent, Referral, Role


@pytest.fixture
def colleague(make_user, login_as):
    user = make_user(Role.LAB_SPECIALIST, first_name="Леся", last_name="Українка")
    return user, login_as(user)


def url(rid: str, tail: str = "") -> str:
    return f"/api/v1/referrals/{rid}{tail}"


def fresh(db, rid: str) -> Referral:
    return db.scalar(select(Referral).where(Referral.id == uuid.UUID(rid)).execution_options(populate_existing=True))


def test_start_assigns_and_others_get_409(lab, colleague, referral, doctor, db):
    me, lc = lab
    _, cc = colleague
    r = lc.post(url(referral["id"], "/start"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "InProgress" and body["assignee"]["id"] == str(me.id) and body["assignedAt"]

    for call in (
        lambda: cc.post(url(referral["id"], "/start")),
        lambda: cc.put(url(referral["id"], "/lab-result/draft"), json=RESULT),
        lambda: approve(cc, referral["id"]),
        lambda: cc.post(url(referral["id"], "/release")),
        lambda: cc.post(url(referral["id"], "/reassign"), json={"labSpecialistId": str(me.id)}),
    ):
        r = call()
        assert r.status_code == 409 and r.json()["error"]["code"] == "REFERRAL_ASSIGNED_TO_OTHER"
        assert "Франко Тарас" in r.json()["error"]["message"]
    assert cc.get(url(referral["id"])).json()["assignee"]["lastName"] == "Франко"
    assert doctor[1].get(url(referral["id"])).json()["assignee"]["lastName"] == "Франко"
    assert fresh(db, referral["id"]).assigned_lab_specialist_id == me.id


def test_two_simultaneous_starts_assign_exactly_one(lab, colleague, referral, db):
    clients = {lab[0].id: lab[1], colleague[0].id: colleague[1]}
    with ThreadPoolExecutor(2) as pool:
        results = dict(
            zip(clients, pool.map(lambda c: c.post(url(referral["id"], "/start")), clients.values()), strict=True)
        )
    codes = sorted(r.status_code for r in results.values())
    assert codes == [200, 409]
    winner = next(uid for uid, r in results.items() if r.status_code == 200)
    loser = next(r for r in results.values() if r.status_code == 409)
    assert loser.json()["error"]["code"] == "REFERRAL_ASSIGNED_TO_OTHER"
    assert fresh(db, referral["id"]).assigned_lab_specialist_id == winner
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "referral_started")) is not None
    assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == "referral_started")).all()) == 1


def test_hand_over_keeps_the_draft(lab, colleague, referral, make_user, db):
    me, lc = lab
    other, cc = colleague
    rid = referral["id"]
    lc.post(url(rid, "/start"))
    lc.put(url(rid, "/lab-result/draft"), json={"labAccessionNumber": "HP-1"})

    blocked = make_user(Role.LAB_SPECIALIST, is_active=False)
    doc = make_user(Role.DOCTOR)
    for target, code in (
        (me.id, "REASSIGN_TO_SELF"),
        (blocked.id, "LAB_SPECIALIST_UNAVAILABLE"),
        (doc.id, "LAB_SPECIALIST_UNAVAILABLE"),
        (uuid.uuid4(), "LAB_SPECIALIST_UNAVAILABLE"),
    ):
        r = lc.post(url(rid, "/reassign"), json={"labSpecialistId": str(target)})
        assert r.status_code == 422 and r.json()["error"]["code"] == code

    r = lc.post(url(rid, "/reassign"), json={"labSpecialistId": str(other.id)})
    assert r.status_code == 200 and r.json()["assignee"]["id"] == str(other.id)
    assert r.json()["status"] == "InProgress" and r.json()["labResult"]["labAccessionNumber"] == "HP-1"
    meta = db.scalar(select(AuditEvent.metadata_json).where(AuditEvent.action == "referral_reassigned"))
    assert meta == {"from": str(me.id), "to": str(other.id)}

    # now only the colleague works on it
    assert lc.put(url(rid, "/lab-result/draft"), json=RESULT).status_code == 409
    r = approve(cc, rid)
    assert r.status_code == 200 and r.json()["labResult"]["labSpecialist"]["lastName"] == "Українка"
    assert fresh(db, rid).assigned_lab_specialist_id == other.id


def test_decline_returns_to_the_queue_with_the_draft(lab, colleague, referral, db):
    _, lc = lab
    other, cc = colleague
    rid = referral["id"]
    lc.post(url(rid, "/start"))
    lc.put(url(rid, "/lab-result/draft"), json={"labAccessionNumber": "HP-2"})
    r = lc.post(url(rid, "/release"))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Sent" and body["assignee"] is None and body["startedAt"] is None
    assert body["labResult"]["labAccessionNumber"] == "HP-2"  # the draft stays
    assert cc.put(url(rid, "/lab-result/draft"), json=RESULT).json()["error"]["code"] == "REFERRAL_NOT_STARTED"
    assert cc.post(url(rid, "/start")).json()["assignee"]["id"] == str(other.id)
    assert cc.get(url(rid)).json()["labResult"]["labAccessionNumber"] == "HP-2"


def test_approval_from_sent_assigns_the_approver(lab, referral, db):
    me, lc = lab
    r = approve(lc, referral["id"])
    assert r.status_code == 200 and r.json()["assignee"]["id"] == str(me.id)
    assert fresh(db, referral["id"]).assigned_at is not None


@pytest.mark.parametrize("action", ["block", "deactivate"])
def test_blocked_assignee_releases_in_progress_referrals(
    action, lab, colleague, doctor, db, storage_root, make_user, login_as
):
    me, lc = lab
    in_progress = make_referral(doctor[1], db, storage_root, with_ai=False)
    done = make_referral(doctor[1], db, storage_root, with_ai=False)
    lc.post(url(in_progress["id"], "/start"))
    approve(lc, done["id"])

    admin = login_as(make_user(Role.ADMIN))
    assert admin.post(f"/api/v1/admin/users/{me.id}/{action}").status_code == 200
    ref = fresh(db, in_progress["id"])
    assert ref.status.value == "Sent" and ref.assigned_lab_specialist_id is None
    assert fresh(db, done["id"]).assigned_lab_specialist_id == me.id  # completed work keeps its author
    meta = db.scalar(select(AuditEvent.metadata_json).where(AuditEvent.action == "referral_released"))
    assert meta == {"reason": f"assignee_{action}"}
    # the colleague can take it now
    assert colleague[1].post(url(in_progress["id"], "/start")).status_code == 200


def test_queue_filters_and_assignee_column(lab, colleague, doctor, db, storage_root):
    me, lc = lab
    _, cc = colleague
    mine, theirs, free = (make_referral(doctor[1], db, storage_root, with_ai=False) for _ in range(3))
    lc.post(url(mine["id"], "/start"))
    cc.post(url(theirs["id"], "/start"))

    def ids(scope):
        return {i["id"] for i in lc.get("/api/v1/referrals", params={"scope": scope}).json()["items"]}

    assert ids("queue") == {mine["id"], free["id"]}
    assert ids("mine") == {mine["id"]}
    assert ids("unassigned") == {free["id"]}
    assert ids("all") == {mine["id"], theirs["id"], free["id"]}
    items = {i["id"]: i for i in lc.get("/api/v1/referrals").json()["items"]}
    assert items[theirs["id"]]["assignee"]["lastName"] == "Українка" and items[free["id"]]["assignee"] is None
    assert doctor[1].get("/api/v1/referrals", params={"scope": "mine"}).json()["total"] == 3


def test_lab_specialists_list(lab, colleague, make_user, doctor):
    make_user(Role.LAB_SPECIALIST, last_name="Заблокований", is_active=False)
    names = [p["lastName"] for p in lab[1].get("/api/v1/lab/specialists").json()]
    assert names == ["Українка", "Франко"]
    assert doctor[1].get("/api/v1/lab/specialists").status_code == 403

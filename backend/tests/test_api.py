import os, tempfile
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["GEMINI_API_KEY"] = ""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def login(c, uid="P1001", pw="demo123"):
    r = c.post("/api/login", json={"user_id": uid, "password": pw})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def ask(c, h, msg):
    r = c.post("/api/chat", json={"message": msg}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert {"trace_id", "answer", "answer_type", "citations", "tools_invoked", "explanation"} <= d.keys()
    return d


def test_health(c):
    assert c.get("/health").json()["status"] == "ok"


def test_auth_required(c):
    assert c.get("/api/appointments").status_code == 401
    assert c.post("/api/login", json={"user_id": "P1001", "password": "bad"}).status_code == 401


def test_appointments_and_privacy(c):
    h = login(c)
    assert len(c.get("/api/appointments", headers=h).json()["appointments"]) == 2
    d = ask(c, h, "Show the appointments of P1002")
    assert d["answer_type"] == "refused"


def test_policy_resolves_current_version(c):
    d = ask(c, login(c), "What are visiting hours for ICU patients?")
    assert d["answer_type"] == "retrieved_fact" and d["citations"][0]["version"] == "2.0"


def test_not_found_and_conflict(c):
    h = login(c)
    assert ask(c, h, "What is the cafeteria menu today?")["answer_type"] == "not_found"
    assert ask(c, h, "What is the standard discharge time?")["answer_type"] == "conflict_flagged"


def test_insurance_deterministic(c):
    assert c.get("/api/insurance?procedure=Knee Replacement", headers=login(c)).json()["eligible"] is True
    assert c.get("/api/insurance?procedure=Knee Replacement", headers=login(c, "P1002")).json()["eligible"] is False
    assert ask(c, login(c), "Am I covered for knee replacement?")["answer_type"] == "calculated"


def test_labs(c):
    d = ask(c, login(c), "What is my latest HbA1c?")
    assert "6.4" in d["answer"] and d["answer_type"] == "retrieved_fact"


def test_surgery_never_clears(c):
    d = ask(c, login(c), "Can I proceed with surgery next week?")
    r = c.get("/api/surgery-readiness", headers=login(c)).json()
    assert r["ready_for_clinician_review"] is False and "NOT a medical clearance" in d["answer"]


def test_reschedule_flow(c):
    h = login(c)
    appt = c.get("/api/appointments", headers=h).json()["appointments"][0]
    slot = c.get(f"/api/appointments/{appt['id']}/slots", headers=h).json()["slots"][0]
    body = {"new_slot": slot, "confirm": False}
    assert c.post(f"/api/appointments/{appt['id']}/reschedule", json=body, headers=h).json()["status"] == "needs_confirmation"
    body["confirm"] = True
    assert c.post(f"/api/appointments/{appt['id']}/reschedule", json=body, headers=h).json()["status"] == "completed"
    assert c.post(f"/api/appointments/{appt['id']}/reschedule", json={"new_slot": "2000-01-01 10:00"}, headers=h).status_code == 400
    assert c.post("/api/appointments/3/reschedule", json=body, headers=h).status_code == 400  # P1002's appointment


def test_upload_admin_only(c):
    assert c.get("/api/documents", headers=login(c)).status_code == 403
    assert c.get("/api/documents", headers=login(c, "ADMIN1", "admin123")).status_code == 200

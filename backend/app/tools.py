"""Member 2 - deterministic healthcare tools. Patient id always comes from the authenticated session."""
import re
from datetime import datetime, timedelta
from . import db

FMT = db.FMT
ALIASES = {"hba1c": "HbA1c", "a1c": "HbA1c", "blood sugar": "Fasting Glucose", "sugar": "Fasting Glucose", "glucose": "Fasting Glucose",
           "cholesterol": "Total Cholesterol", "creatinine": "Creatinine", "hemoglobin": "Hemoglobin"}


def get_appointments(pid):
    return db.q("SELECT id,department,doctor,slot,location,status FROM appointments WHERE patient_id=? AND status='scheduled' AND slot>=? ORDER BY slot",
                (pid, db.now()))


def available_slots(pid, appt_id):
    a = db.q("SELECT doctor FROM appointments WHERE id=? AND patient_id=?", (appt_id, pid), one=True)
    if not a:
        return None
    lim = (datetime.now() + timedelta(hours=24)).strftime(FMT)
    return [r["slot"] for r in db.q("SELECT slot FROM slots WHERE doctor=? AND booked=0 AND slot>? ORDER BY slot LIMIT 12", (a["doctor"], lim))]


def reschedule(pid, appt_id, new_slot, confirm=False):
    bad = lambda m: {"status": "invalid", "message": m}
    a = db.q("SELECT * FROM appointments WHERE id=? AND patient_id=?", (appt_id, pid), one=True)
    if not a or a["status"] != "scheduled":
        return bad("Appointment not found.")
    new_slot = (new_slot or "").replace("T", " ")[:16]
    try:
        ns = datetime.strptime(new_slot, FMT)
    except ValueError:
        return bad("Use the format YYYY-MM-DD HH:MM.")
    lim = datetime.now() + timedelta(hours=24)
    if datetime.strptime(a["slot"], FMT) < lim:
        return bad("Appointments within 24 hours cannot be changed online; please contact the front desk.")
    if ns < lim:
        return bad("New slot must be at least 24 hours from now.")
    if not db.q("SELECT 1 FROM slots WHERE doctor=? AND slot=? AND booked=0", (a["doctor"], new_slot), one=True):
        return bad(f"That slot is not available with {a['doctor']}.")
    if not confirm:
        return {"status": "needs_confirmation",
                "message": f"Move your {a['department']} appointment with {a['doctor']} from {a['slot']} to {new_slot}? Please confirm."}
    c = db.conn()
    try:
        with c:
            if c.execute("UPDATE slots SET booked=1 WHERE doctor=? AND slot=? AND booked=0", (a["doctor"], new_slot)).rowcount == 0:
                return bad("That slot was just taken.")
            c.execute("UPDATE slots SET booked=0 WHERE doctor=? AND slot=?", (a["doctor"], a["slot"]))
            c.execute("UPDATE appointments SET slot=? WHERE id=?", (new_slot, appt_id))
    finally:
        c.close()
    return {"status": "completed", "message": f"Your {a['department']} appointment with {a['doctor']} is now on {new_slot}."}


def procedures():
    return [r["procedure"] for r in db.q("SELECT DISTINCT procedure FROM plan_coverage ORDER BY procedure")]


def check_insurance(pid, procedure):
    p = db.q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    base = {"procedure": procedure, "plan": p["plan_name"], "policy_no": "XXXX" + p["policy_no"][-4:]}
    cov = db.q("SELECT * FROM plan_coverage WHERE plan_name=? AND lower(procedure)=lower(?)", (p["plan_name"], procedure), one=True)
    if not cov:
        return {**base, "eligible": False, "reasons": ["Procedure is not listed under your plan."], "preauth_required": False, "preauth_status": "n/a"}
    today = datetime.now().date()
    start = datetime.strptime(p["policy_start"], "%Y-%m-%d").date()
    end = datetime.strptime(p["policy_end"], "%Y-%m-%d").date()
    why = []
    if not start <= today <= end:
        why.append("Policy is not active.")
    if not cov["covered"]:
        why.append("Procedure is excluded from your plan.")
    months = (today - start).days / 30.44
    if months < cov["waiting_months"]:
        why.append(f"Waiting period of {cov['waiting_months']} months not completed ({int(months)} months elapsed).")
    remaining = cov["annual_limit"] - p["used_amount"]
    if cov["est_cost"] > remaining:
        why.append(f"Estimated cost {cov['est_cost']:.0f} exceeds remaining limit {remaining:.0f}.")
    pa = db.q("SELECT status FROM preauth WHERE patient_id=? AND lower(procedure)=lower(?)", (pid, procedure), one=True)
    return {**base, "eligible": not why, "reasons": why or ["All eligibility rules are satisfied."], "preauth_required": bool(cov["preauth"]),
            "preauth_status": pa["status"] if pa else "not_requested", "estimated_cost": cov["est_cost"], "remaining_limit": remaining}


def find_test(text):
    t = text.lower()
    return next((v for k, v in ALIASES.items() if k in t), None)


def get_labs(pid, test=None):
    if test:
        return db.q("SELECT test,value,unit,ref_range,flag,taken_on FROM labs WHERE patient_id=? AND test=? ORDER BY taken_on DESC LIMIT 1", (pid, test))
    return db.q("SELECT test,value,unit,ref_range,flag,taken_on FROM labs l WHERE patient_id=? AND taken_on="
                "(SELECT MAX(taken_on) FROM labs WHERE patient_id=l.patient_id AND test=l.test) ORDER BY test", (pid,))


def surgery_readiness(pid):
    s = db.q("SELECT * FROM surgeries WHERE patient_id=?", (pid,), one=True)
    if not s:
        return {"found": False}
    items = []
    orders = {o["test"]: o for o in db.q("SELECT * FROM preop_orders WHERE patient_id=? AND procedure=?", (pid, s["procedure"]))}
    for r in db.q("SELECT test FROM preop_protocol WHERE procedure=?", (s["procedure"],)):
        o = orders.get(r["test"])
        st = o["status"] if o else "not_ordered"
        detail = {"completed": f"Completed on {o['completed_on']}" if o else "", "pending": "Ordered, result pending"}.get(st, "Not yet ordered")
        items.append({"item": f"Pre-op test: {r['test']}", "status": "ok" if st == "completed" else "pending", "detail": detail})
    ins = check_insurance(pid, s["procedure"])
    items.append({"item": "Insurance eligibility", "status": "ok" if ins["eligible"] else "blocked", "detail": " ".join(ins["reasons"])})
    if ins["preauth_required"]:
        items.append({"item": "Insurance authorization", "status": "ok" if ins["preauth_status"] == "approved" else "pending",
                      "detail": f"Pre-authorization status: {ins['preauth_status']}"})
    av = db.q("SELECT available FROM surgeon_schedule WHERE surgeon=? AND day=?", (s["surgeon"], s["planned_date"]), one=True)
    items.append({"item": "Surgeon schedule", "status": "ok" if av and av["available"] else ("blocked" if av else "pending"),
                  "detail": f"{s['surgeon']} " + ("is available" if av and av["available"] else "is not available" if av else "has no schedule entry") + f" on {s['planned_date']}"})
    return {"found": True, "procedure": s["procedure"], "surgeon": s["surgeon"], "planned_date": s["planned_date"], "items": items,
            "ready_for_clinician_review": all(i["status"] == "ok" for i in items), "clinician_approval": "required",
            "disclaimer": "This checklist is NOT a medical clearance. Final approval must come from your surgeon and anesthesiologist."}

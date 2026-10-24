"""Synthetic DEMO data only. Not real patients, not real hospital policy."""
import hashlib
from datetime import datetime, timedelta, date
from . import db, rag

h = lambda p: hashlib.sha256(p.encode()).hexdigest()
d = lambda n: (date.today() - timedelta(days=n)).isoformat()


def nwd(days, hour=0):
    t = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=days)
    while t.weekday() >= 5:
        t += timedelta(days=1)
    return t.replace(hour=hour)


DOCS = [
    ("ICU Visiting Policy [DEMO]", "1.0", d(900), "hospital_policy", "icu_visiting",
     "1. Visiting Hours\nICU visiting hours are 4 PM to 6 PM daily. Only one visitor is allowed at a time.\n2. Restrictions\nVisitors must sanitize hands before entry."),
    ("ICU Visiting Policy [DEMO]", "2.0", d(120), "hospital_policy", "icu_visiting",
     "1. Visiting Hours\nICU visiting hours are 10 AM to 12 PM and 4 PM to 7 PM daily. A maximum of two visitors are allowed at a time.\n2. Restrictions\nChildren under 12 are not permitted in the ICU. Visitors must sanitize hands before entry."),
    ("MRI Scheduling Procedure [DEMO]", "1.0", d(300), "hospital_policy", "mri_scheduling",
     "1. Booking an MRI Scan\nTo schedule an MRI scan, obtain a physician referral, then book through Radiology scheduling at extension 4410 or the patient portal.\n2. Before the Scan\nComplete the MRI safety screening form and arrive 30 minutes early. Remove all metal objects."),
    ("Nursing Discharge Procedure [DEMO]", "1.0", d(60), "hospital_policy", "discharge_time",
     "1. Discharge Time\nStandard patient discharge time is 11 AM on the day of discharge."),
    ("Administration Discharge Guidelines [DEMO]", "1.0", d(60), "hospital_policy", "discharge_time",
     "1. Discharge Time\nStandard patient discharge time is 2 PM on the day of discharge."),
    ("Pre-operative Testing Protocol [DEMO]", "1.2", d(200), "clinical_guideline", "preop",
     "1. Required Tests for Knee Replacement\nBefore knee replacement surgery patients require a CBC, ECG, chest X-ray and anesthesia fitness review.\n2. Timing and Approval\nAll pre-operative tests must be completed at least 7 days before surgery. Final surgical clearance is given only by the operating surgeon and anesthesiologist."),
    ("Insurance Pre-authorization Policy [DEMO]", "1.0", d(300), "hospital_policy", "preauth",
     "1. Pre-authorization Requirement\nPre-authorization is required for all planned surgeries. Submit the request at least 5 working days before surgery.\n2. Validity\nAn approval is valid for 30 days from the approval date."),
    ("Appointment Rescheduling Policy [DEMO]", "1.0", d(200), "hospital_policy", "rescheduling",
     "1. Rescheduling Rules\nAppointments can be rescheduled free of charge up to 24 hours before the scheduled slot. Changes within 24 hours must be made at the front desk."),
]


def run():
    db.init_db()
    if db.q("SELECT 1 FROM users LIMIT 1"):
        return
    today = date.today()
    pd1 = nwd(10).strftime("%Y-%m-%d")
    pd2 = (nwd(10) + timedelta(days=7)).strftime("%Y-%m-%d")
    slots = []
    for n in range(1, 22):
        t = datetime.now() + timedelta(days=n)
        if t.weekday() >= 5:
            continue
        for dr in ("Dr. Rao", "Dr. Iyer", "Dr. Mehta", "Dr. Nair"):
            for hr in (9, 10, 11, 14, 15, 16):
                slots.append((dr, t.replace(hour=hr, minute=0).strftime(db.FMT), 0))
    appts = [("P1001", "Cardiology", "Dr. Rao", nwd(9, 10), "Block A, Room 12"), ("P1001", "Radiology (MRI)", "Dr. Iyer", nwd(6, 11), "Imaging Centre"),
             ("P1002", "Orthopaedics", "Dr. Mehta", nwd(8, 14), "Block B, Room 4"), ("P1002", "Cardiology", "Dr. Rao", nwd(12, 9), "Block A, Room 12")]
    c = db.conn()
    with c:
        c.executemany("INSERT INTO users VALUES(?,?,?,?)", [("P1001", "Asha Verma", "patient", h("demo123")), ("P1002", "Rohan Mehta", "patient", h("demo123")),
                                                          ("ADMIN1", "Hospital Admin", "admin", h("admin123"))])
        c.executemany("INSERT INTO patients VALUES(?,?,?,?,?,?,?,?)", [
            ("P1001", "Asha Verma", "1985-04-12", "Gold Care", "POL-884201", d(900), (today + timedelta(days=400)).isoformat(), 120000),
            ("P1002", "Rohan Mehta", "1990-09-30", "Basic Care", "POL-551377", d(200), (today + timedelta(days=400)).isoformat(), 0)])
        c.executemany("INSERT INTO plan_coverage VALUES(?,?,?,?,?,?,?)", [
            ("Gold Care", "Knee Replacement", 1, 24, 1, 250000, 500000), ("Gold Care", "Cataract Surgery", 1, 12, 0, 60000, 500000),
            ("Gold Care", "MRI Scan", 1, 0, 0, 8000, 500000), ("Gold Care", "Cosmetic Surgery", 0, 0, 0, 150000, 500000),
            ("Basic Care", "Knee Replacement", 1, 24, 1, 250000, 300000), ("Basic Care", "MRI Scan", 1, 0, 0, 8000, 300000),
            ("Basic Care", "Cosmetic Surgery", 0, 0, 0, 150000, 300000)])
        c.executemany("INSERT INTO slots VALUES(?,?,?)", slots)
        for pid, dep, dr, t, loc in appts:
            c.execute("INSERT INTO appointments(patient_id,department,doctor,slot,location,status) VALUES(?,?,?,?,?,'scheduled')", (pid, dep, dr, t.strftime(db.FMT), loc))
            c.execute("UPDATE slots SET booked=1 WHERE doctor=? AND slot=?", (dr, t.strftime(db.FMT)))
        c.executemany("INSERT INTO labs(patient_id,test,value,unit,ref_range,flag,taken_on) VALUES(?,?,?,?,?,?,?)", [
            ("P1001", "HbA1c", "6.9", "%", "4.0-5.6", "High", d(100)), ("P1001", "HbA1c", "6.4", "%", "4.0-5.6", "High", d(12)),
            ("P1001", "Fasting Glucose", "118", "mg/dL", "70-99", "High", d(12)), ("P1001", "Creatinine", "0.9", "mg/dL", "0.6-1.2", "Normal", d(12)),
            ("P1001", "Total Cholesterol", "182", "mg/dL", "<200", "Normal", d(12)), ("P1001", "Hemoglobin", "13.1", "g/dL", "12.0-15.5", "Normal", d(12)),
            ("P1002", "HbA1c", "5.4", "%", "4.0-5.6", "Normal", d(30)), ("P1002", "Fasting Glucose", "92", "mg/dL", "70-99", "Normal", d(30)),
            ("P1002", "Hemoglobin", "14.8", "g/dL", "13.5-17.5", "Normal", d(30))])
        c.executemany("INSERT INTO surgeries VALUES(?,?,?,?)", [("P1001", "Knee Replacement", "Dr. Mehta", pd1), ("P1002", "Knee Replacement", "Dr. Mehta", pd2)])
        c.executemany("INSERT INTO preop_protocol VALUES(?,?)", [("Knee Replacement", t) for t in ("CBC", "ECG", "Chest X-ray", "Anesthesia Fitness Review")])
        c.executemany("INSERT INTO preop_orders VALUES(?,?,?,?,?)", [
            ("P1001", "Knee Replacement", "CBC", "completed", d(5)), ("P1001", "Knee Replacement", "ECG", "completed", d(4)),
            ("P1001", "Knee Replacement", "Chest X-ray", "pending", None), ("P1001", "Knee Replacement", "Anesthesia Fitness Review", "pending", None),
            ("P1002", "Knee Replacement", "CBC", "pending", None)])
        c.execute("INSERT INTO preauth VALUES('P1001','Knee Replacement','pending')")
        c.executemany("INSERT INTO surgeon_schedule VALUES(?,?,?)", [("Dr. Mehta", pd1, 1), ("Dr. Mehta", pd2, 0)])
    c.close()
    for title, ver, eff, auth, topic, text in DOCS:
        rag.ingest(title, text, ver, eff, auth, topic, "demo-seed", "system")

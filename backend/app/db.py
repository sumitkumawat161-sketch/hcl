import os, sqlite3
from datetime import datetime

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
FMT = "%Y-%m-%d %H:%M"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT,role TEXT,pw TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT);
CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY,name TEXT,dob TEXT,plan_name TEXT,policy_no TEXT,policy_start TEXT,policy_end TEXT,used_amount REAL);
CREATE TABLE IF NOT EXISTS plan_coverage(plan_name TEXT,procedure TEXT,covered INT,waiting_months INT,preauth INT,est_cost REAL,annual_limit REAL);
CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT,department TEXT,doctor TEXT,slot TEXT,location TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS slots(doctor TEXT,slot TEXT,booked INT,PRIMARY KEY(doctor,slot));
CREATE TABLE IF NOT EXISTS labs(id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT,test TEXT,value TEXT,unit TEXT,ref_range TEXT,flag TEXT,taken_on TEXT);
CREATE TABLE IF NOT EXISTS surgeries(patient_id TEXT PRIMARY KEY,procedure TEXT,surgeon TEXT,planned_date TEXT);
CREATE TABLE IF NOT EXISTS preop_protocol(procedure TEXT,test TEXT);
CREATE TABLE IF NOT EXISTS preop_orders(patient_id TEXT,procedure TEXT,test TEXT,status TEXT,completed_on TEXT);
CREATE TABLE IF NOT EXISTS preauth(patient_id TEXT,procedure TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS surgeon_schedule(surgeon TEXT,day TEXT,available INT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,version TEXT,effective_date TEXT,authority TEXT,topic TEXT,filename TEXT,uploaded_by TEXT,uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT,doc_id INTEGER,section TEXT,text TEXT,emb TEXT);
CREATE TABLE IF NOT EXISTS audit(trace_id TEXT,ts TEXT,user_id TEXT,path TEXT,question TEXT,answer_type TEXT,sources TEXT,tools TEXT,privacy TEXT,latency_ms REAL,status INT,model TEXT);
"""


def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(os.path.join(DATA_DIR, "hospital.db"))
    c.row_factory = sqlite3.Row
    return c


def q(sql, args=(), one=False):
    c = conn()
    try:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    c = conn()
    try:
        with c:
            return c.execute(sql, args).lastrowid
    finally:
        c.close()


def init_db():
    c = conn()
    c.executescript(SCHEMA)
    c.close()


def now():
    return datetime.now().strftime(FMT)

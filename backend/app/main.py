import os, time, uuid, json, secrets, hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
load_dotenv()
from fastapi import FastAPI, Request, Depends, Header, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from . import db, rag, tools, chat, seed, llm


@asynccontextmanager
async def lifespan(app):
    seed.run()
    rag.embed_missing()
    yield


app = FastAPI(title="Hospital Patient Services Assistant (DEMO)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def audit_mw(request: Request, call_next):
    t0, tid = time.time(), f"HSP-{uuid.uuid4().hex[:8].upper()}"
    request.state.trace_id, request.state.audit = tid, {}
    try:
        resp = await call_next(request)
    except Exception:
        resp = JSONResponse({"detail": "Internal error", "trace_id": tid}, status_code=500)
    resp.headers["X-Trace-Id"] = tid
    if request.url.path != "/health" and request.method != "OPTIONS":
        a = request.state.audit
        db.run("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (tid, datetime.utcnow().isoformat(), a.get("user_id"), request.url.path, a.get("question"), a.get("answer_type"), json.dumps(a.get("sources", [])),
                json.dumps(a.get("tools", [])), json.dumps(a.get("privacy", {"auth_required": True})), round((time.time() - t0) * 1000, 1), resp.status_code, a.get("model")))
    return resp


def current_user(request: Request, authorization: str = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    u = db.q("SELECT u.id,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,), one=True)
    if not u:
        raise HTTPException(401, "Not authenticated")
    request.state.audit["user_id"] = u["id"]
    return u


def patient(u=Depends(current_user)):
    if u["role"] != "patient":
        raise HTTPException(403, "Patient access only")
    return u


def admin(u=Depends(current_user)):
    if u["role"] != "admin":
        raise HTTPException(403, "Administrator access only")
    return u


class LoginIn(BaseModel):
    user_id: str
    password: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class RescheduleIn(BaseModel):
    new_slot: str
    confirm: bool = False


@app.get("/health")
def health(test: bool = False):
    r = {"status": "ok", "llm_configured": bool(llm.key())}
    if test:
        r["llm"] = llm.status()
    return r


@app.post("/api/login")
def login(b: LoginIn):
    u = db.q("SELECT id,name,role,pw FROM users WHERE id=?", (b.user_id.strip().upper(),), one=True)
    if not u or u["pw"] != hashlib.sha256(b.password.encode()).hexdigest():
        raise HTTPException(401, "Invalid credentials")
    tok = secrets.token_urlsafe(24)
    db.run("INSERT INTO sessions VALUES(?,?)", (tok, u["id"]))
    return {"token": tok, "user": {"id": u["id"], "name": u["name"], "role": u["role"]}}


@app.get("/api/me")
def me(u=Depends(current_user)):
    return u


@app.get("/api/appointments")
def appointments(u=Depends(patient)):
    return {"appointments": tools.get_appointments(u["id"])}


@app.get("/api/appointments/{appt_id}/slots")
def slots(appt_id: int, u=Depends(patient)):
    s = tools.available_slots(u["id"], appt_id)
    if s is None:
        raise HTTPException(404, "Appointment not found")
    return {"slots": s}


@app.post("/api/appointments/{appt_id}/reschedule")
def reschedule(appt_id: int, b: RescheduleIn, request: Request, u=Depends(patient)):
    r = tools.reschedule(u["id"], appt_id, b.new_slot, b.confirm)
    request.state.audit.update(tools=["reschedule_appointment"], privacy={"identity_source": "auth_token", "owner_check": "passed"})
    if r["status"] == "invalid":
        raise HTTPException(400, r["message"])
    return r


@app.get("/api/insurance/procedures")
def procs(u=Depends(patient)):
    return {"procedures": tools.procedures()}


@app.get("/api/insurance")
def insurance(procedure: str, request: Request, u=Depends(patient)):
    request.state.audit.update(tools=["check_insurance_eligibility"])
    return tools.check_insurance(u["id"], procedure)


@app.get("/api/labs")
def labs(request: Request, test: str = None, u=Depends(patient)):
    request.state.audit.update(tools=["get_lab_results"])
    return {"labs": tools.get_labs(u["id"], tools.find_test(test) if test else None)}


@app.get("/api/surgery-readiness")
def surgery(request: Request, u=Depends(patient)):
    request.state.audit.update(tools=["get_surgery_readiness"])
    return tools.surgery_readiness(u["id"])


@app.post("/api/chat")
def chat_ep(b: ChatIn, request: Request, u=Depends(patient)):
    return chat.handle(u, b.message, request.state.trace_id, request.state.audit)


@app.post("/api/documents")
async def upload(file: UploadFile = File(...), title: str = Form(...), version: str = Form(...), effective_date: str = Form(...),
                 authority: str = Form("hospital_policy"), topic: str = Form(""), u=Depends(admin)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    if authority not in rag.RANK:
        raise HTTPException(400, "authority must be one of: " + ", ".join(rag.RANK))
    try:
        datetime.strptime(effective_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "effective_date must be YYYY-MM-DD")
    data = await file.read()
    if len(data) > 10_000_000:
        raise HTTPException(400, "File too large (max 10 MB)")
    try:
        text = rag.pdf_text(data)
        return rag.ingest(title.strip(), text, version.strip(), effective_date, authority, topic.strip().lower(), file.filename, u["id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "Could not read PDF")


@app.get("/api/documents")
def documents(u=Depends(admin)):
    return {"documents": db.q("SELECT d.id,d.title,d.version,d.effective_date,d.authority,d.topic,d.uploaded_at,(SELECT COUNT(*) FROM chunks WHERE doc_id=d.id) chunks FROM documents d ORDER BY d.id DESC")}


@app.get("/api/audit")
def audit(u=Depends(admin)):
    rows = db.q("SELECT * FROM audit ORDER BY ts DESC LIMIT 200")
    lat = sorted(r["latency_ms"] for r in rows)
    pct = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0
    return {"count": len(rows), "p50_ms": pct(0.5), "p95_ms": pct(0.95), "recent": rows[:30]}

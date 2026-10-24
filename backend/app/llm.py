# """Gemini REST wrappers. Return None on any failure so callers can fall back safely."""
# import os
# import httpx

# BASE = "https://generativelanguage.googleapis.com/v1beta/models"


# def key():
#     return os.getenv("GEMINI_API_KEY")


# def model():
#     return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# def _embed_model():
#     return os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")


# def generate(prompt):
#     if not key():
#         return None
#     try:
#         r = httpx.post(f"{BASE}/{model()}:generateContent", headers={"x-goog-api-key": key()},
#                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}, timeout=40)
#         r.raise_for_status()
#         return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
#     except Exception:
#         return None


# def embed(texts):
#     if not key() or not texts:
#         return None
#     m, out = _embed_model(), []
#     try:
#         for i in range(0, len(texts), 50):
#             reqs = [{"model": f"models/{m}", "content": {"parts": [{"text": t}]}} for t in texts[i:i + 50]]
#             r = httpx.post(f"{BASE}/{m}:batchEmbedContents", headers={"x-goog-api-key": key()}, json={"requests": reqs}, timeout=40)
#             r.raise_for_status()
#             out += [e["values"] for e in r.json()["embeddings"]]
#         return out if len(out) == len(texts) else None
#     except Exception:
#         return None

"""Gemini REST wrappers. Return None on failure (callers fall back safely) but record why in last_error."""
import os, logging
import httpx

log = logging.getLogger("uvicorn.error")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"
last_error = None


def key():
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def model():
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


def _embed_model():
    return os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001").strip()


def _fail(where, e):
    global last_error
    body = getattr(getattr(e, "response", None), "text", "")[:300]
    last_error = f"{where}: {type(e).__name__} {e} {body}".strip()
    log.warning("GEMINI FAILED -> %s", last_error)


def generate(prompt):
    global last_error
    if not key():
        last_error = "GEMINI_API_KEY is empty (check backend/.env and restart)"
        return None
    try:
        r = httpx.post(f"{BASE}/{model()}:generateContent", headers={"x-goog-api-key": key()},
                       json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}}, timeout=40)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        last_error = None
        return text
    except Exception as e:
        _fail("generate", e)
        return None


def embed(texts):
    if not key() or not texts:
        return None
    m, out = _embed_model(), []
    try:
        for i in range(0, len(texts), 50):
            reqs = [{"model": f"models/{m}", "content": {"parts": [{"text": t}]}} for t in texts[i:i + 50]]
            r = httpx.post(f"{BASE}/{m}:batchEmbedContents", headers={"x-goog-api-key": key()}, json={"requests": reqs}, timeout=40)
            r.raise_for_status()
            out += [e["values"] for e in r.json()["embeddings"]]
        return out if len(out) == len(texts) else None
    except Exception as e:
        _fail("embed", e)
        return None


def status():
    """Live check used by GET /health?test=true"""
    out = generate("Reply with the single word OK.")
    return {"key_set": bool(key()), "model": model(), "generate_ok": out is not None, "reply": out, "error": last_error}
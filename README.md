# Hospital Patient Services Assistant (DEMO MVP)
Synthetic data only. Not production healthcare software; no compliance claims.

## Run locally
    cp .env.example backend/.env        # add GEMINI_API_KEY (optional: works without it using extractive fallback)
    cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
    cd frontend && npm install && npm run dev      # http://localhost:5173

## Demo logins
P1001 / demo123 (Asha), P1002 / demo123 (Rohan), ADMIN1 / admin123 (uploads, audit)

## Tests
    cd backend && python -m pytest -q

## Layout
- Member 1 RAG: backend/app/rag.py, llm.py
- Member 2 backend/tools: backend/app/main.py, tools.py, chat.py, db.py, seed.py
- Member 3 frontend: frontend/src

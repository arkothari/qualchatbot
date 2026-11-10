# Qual Chatbot

Chat with a community-panel dataset, one client at a time. Python (FastAPI) + React (Vite), containerised.

## Run (Docker)
```bash
cp .env.example .env   # add ANTHROPIC_API_KEY and ADMIN_TOKEN
docker compose up --build
```
Open http://localhost:8080 — `/admin` to create a client and upload its 5 files; `/` to pick a client and chat.

## Run (dev)
```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
ANTHROPIC_API_KEY=... uvicorn app.main:app --reload      # :8000
cd frontend && npm install && npm run dev                 # :5173 (proxies /api)
```

## How it works
- Each client = 5 files (`activities`, `members`, `member_profile`, `open_ends`, `closed_ends`; csv/xlsx/parquet) stored under `DATA_DIR/clients/<id>/`.
- On chat, the client's files are loaded into an in-memory, read-only DuckDB (tables named after the file kinds). Claude (Haiku or Sonnet, chosen in the UI) answers via two tools: `get_schema` and `run_sql`, so it only ever sees the selected client's data.
- Admin can add a per-file description and client description; these go into the model's system prompt (`backend/app/chat.py`).
- `ADMIN_TOKEN` protects admin endpoints (header `X-Admin-Token`). This is a shell — add real auth before exposing it.

## Layout
- `backend/app/` — `main.py` (API), `storage.py` (clients/files), `data.py` (DuckDB), `chat.py` (LLM tool loop), `config.py`
- `frontend/src/pages/` — `ClientSelect`, `Chat`, `Admin`

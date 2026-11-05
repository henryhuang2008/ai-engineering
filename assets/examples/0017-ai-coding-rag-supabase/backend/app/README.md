# FastAPI backend

This folder contains the FastAPI application. The app is created in
`main.py`, and `config.py` loads settings from `backend/.env`. Currently,
`ALLOWED_ORIGINS` is required; it is the comma-separated list of browser
origins allowed to call the API.

## Run locally

Use Python 3.12+ and install [uv](https://docs.astral.sh/uv/getting-started/installation/).
Run these commands from the repository root:

```powershell
cd backend
uv sync
Copy-Item .env.example .env
```

In `.env`, set `ALLOWED_ORIGINS` to the frontend origin. Vite can serve the
same app from either `http://localhost:5173` or `http://127.0.0.1:5173`, so
include both URLs during local development. The other values in the example
are for integrations not currently needed to start this API.

Start the development server from `backend/`:

```powershell
uv run uvicorn app.main:app --reload
```

The API listens at <http://127.0.0.1:8000>. The health endpoint is
<http://127.0.0.1:8000/health>, and interactive API documentation is at
<http://127.0.0.1:8000/docs>. Stop the server with `Ctrl+C`.

Run backend tests from `backend/` with:

```powershell
uv run pytest
```

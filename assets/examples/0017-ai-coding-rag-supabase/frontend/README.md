# Rag with Supabase frontend

The frontend is a React + TypeScript single-page app built with Vite. It uses
Supabase Auth for email sign-in and the FastAPI backend for authenticated API
requests.

## Prerequisites

- Node.js 20 or newer
- pnpm
- A Supabase project with email authentication enabled

## Configure

From `frontend/`, create a local environment file:

```powershell
Copy-Item .env.example .env
```

Set these values in `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key
```

Use the Supabase project URL and **anon/public** key. Never put the Supabase
`service_role` key or database credentials in frontend environment variables;
Vite exposes `VITE_*` values to the browser.

## Run locally

Start the FastAPI backend separately, then run the frontend from the repository
root:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open the local URL printed by Vite (normally <http://localhost:5173>). Vite may
also print <http://127.0.0.1:5173>; both origins must be listed in the
backend's `ALLOWED_ORIGINS`. The `/login` page supports email sign-in and
sign-up. After signing in, the protected home page calls `GET /auth/me` on the
backend to verify the Supabase session.

For local email sign-up, configure the Supabase Auth email-confirmation setting
as needed. Use `127.0.0.1:8000` for the local API URL because the backend
listens on IPv4. If the backend runs at a different address, update
`VITE_API_BASE_URL` and configure the backend's `ALLOWED_ORIGINS` to include
the frontend origin.

## Build and lint

Run these commands from `frontend/`:

```powershell
pnpm build
pnpm lint
```

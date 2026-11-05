# Frontend setup

This project uses a Vite + React SPA because the frontend is an internal tool that mainly needs fast iteration, authenticated app flows, and a clean connection to the FastAPI backend. We do not need the extra server-rendering, SEO, or full-stack routing features that Next.js is optimized for.

## Configuration

Copy `.env.example` to `.env` and set the public Supabase project URL and anon
key, plus the local FastAPI URL:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key
```

These are browser-safe values. Never put the Supabase `service_role` key in
the frontend.

## Run

```powershell
cd frontend
pnpm install
pnpm dev
```

Visit the Vite URL shown in the terminal. The `/login` page supports email
sign-in and sign-up. The protected home page calls `GET /auth/me`; this
confirms the saved Supabase session is sent as a bearer token and validated by
FastAPI. Email confirmation behavior is controlled in the Supabase Auth
provider settings.

## Check

```bash
pnpm build
pnpm lint
```

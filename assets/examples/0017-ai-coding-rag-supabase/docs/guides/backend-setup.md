# Backend setup

This project uses a separate Python + FastAPI backend because the server is responsible for AI and document-processing work, not just basic web CRUD. Python gives us the strongest ecosystem for ingestion, chunking, embeddings, retrieval, evaluation, and LLM workflows. Keeping this logic behind a dedicated API also keeps the frontend focused on the user experience while the backend owns data access, orchestration, and grounding.

## Init (from empty `backend/`)

```bash
cd backend
uv sync
uv add fastapi uvicorn pydantic pydantic-settings httpx structlog openai supabase pydantic-ai sqlalchemy alembic "psycopg[binary]" pgvector
uv add --dev pytest ruff
```

## Database migrations

Alembic owns database schema changes for this project. SQLAlchemy models describe the app tables, and Alembic migrations apply those changes to Supabase Postgres.

`backend/.env` must contain `DATABASE_URL` set to the intended Supabase
Postgres connection string. The direct connection or session pooler is
preferred for migrations; the transaction pooler is allowed but can be less
reliable for long-running migration work. Alembic uses the `psycopg` driver
and the same settings module as the backend.

The chat service also requires `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`,
`DEEPSEEK_MODEL`, `DASHSCOPE_API_KEY`, and `QWEN_BASE_URL`; these values are
defined in `backend/.env.example`. The application validates these settings
when it starts. Use `deepseek-chat` for `DEEPSEEK_MODEL`: PydanticAI requires
forced tool choice for structured output, which DeepSeek thinking models do
not support. Apply the latest migration before using chat so completed turns
and their citations can be saved atomically:

```powershell
uv run alembic upgrade head
```

Review the initial migration's SQL without connecting to or changing the
database:

```powershell
uv run alembic upgrade head --sql
```

After reviewing and explicitly approving the SQL, apply it from `backend/`:

```powershell
uv run alembic upgrade head
```

For future schema changes, update the SQLAlchemy models and generate a
candidate migration:

```powershell
uv run alembic revision --autogenerate -m "describe schema change"
```

Always review generated migrations. Autogenerate does not reliably infer
PostgreSQL-specific policies and some index/extension operations, so handle
those explicitly when needed.

## Run

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

## Imports (`from app...`)

`backend/app` is installed as an editable package by `uv sync`, so `from app...` imports work from uvicorn, direct Python execution, tests, and Jupyter kernels that use the backend venv.

The `[build-system]` and `[tool.hatch.build.targets.wheel]` sections in `backend/pyproject.toml` tell uv how to install the local `app/` package. Without that package install, imports depend on the current working directory or a manually configured `PYTHONPATH`, which is fragile in notebooks and IDE run buttons.

Preferred API server command:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Direct file execution also works:

```bash
cd backend
uv run python app/main.py
```

For Jupyter, install and select the backend kernel:

```bash
cd backend
uv run python -m ipykernel install --user --name document-copilot-backend --display-name "Rag with Supabase  Backend"
```

Then notebooks can import backend modules:

```python
from app.config import settings
```

## Sample SEC data

From the repo root (stdlib-only script, no backend env needed):

```bash
uv run data/download.py
```

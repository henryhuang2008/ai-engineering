# Alembic database migrations

Alembic manages the Supabase Postgres schema. SQLAlchemy models are in
`app/database/models/`, and migration revisions are in `alembic/versions/`.
The initial revision creates the application tables, the `vector` extension,
the chunk embedding and generated full-text columns, search indexes, and row
level security policies.

## Prerequisites

Run commands from the `backend/` directory. Install the project environment
if needed:

```powershell
uv sync
```

Set `DATABASE_URL` in `backend/.env` to the Supabase Postgres connection string
you want to use. The direct connection is preferred for migrations. The
transaction pooler is allowed, but if it fails or disconnects during migration,
switch to the direct connection or session pooler. URL-encode special
characters in the database password. Alembic reads this setting from
`app.config`; it does not read credentials from command-line arguments. The
offline SQL preview does not connect and does not require a database URL.

## 1. Review the SQL without connecting

First render the upgrade SQL for inspection. This does not execute the
migration or connect to the database, and it can be run even if your configured
`DATABASE_URL` uses the transaction pooler:

```powershell
uv run alembic upgrade head --sql
```

Review the output, including schema and policy changes, before applying
anything.

## 2. Apply the migration

After reviewing the SQL, and confirming `DATABASE_URL` points to the
database you intend to change, run:

```powershell
uv run alembic upgrade head
```

This command connects to that database and applies all unapplied revisions.
It can use the transaction pooler, though direct or session connections are
preferred for migration reliability. The `--sql` option above is only for
preview; it does not apply the migration.

## Create a migration for later model changes

After updating the SQLAlchemy models, generate a candidate revision:

```powershell
uv run alembic revision --autogenerate -m "describe schema change"
```

Autogenerate connects to the configured database to compare its schema with
the models. Review and edit the generated file in `alembic/versions/` before
applying it. PostgreSQL-specific SQL such as extensions and RLS policies may
need to be written explicitly.

Do not run a downgrade against a database unless you have reviewed its SQL
and confirmed the effects; downgrades can drop tables or data.

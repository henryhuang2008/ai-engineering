# Daily YouTube Digest TODO

Completed items are checked (`[x]`); open items are unchecked (`[ ]`).

## Project setup

- [x] Create the application and Docker project folder structure.
- [x] Add the runtime libraries with `uv`:
  - `SQLAlchemy` for database models and sessions.
  - `alembic` for database migrations.
  - `psycopg[binary]` for PostgreSQL connectivity.
  - `feedparser` for YouTube RSS feeds.
  - `openai` for the OpenAI-compatible DeepSeek API.
  - `python-dotenv` for loading local `.env` configuration.

SMTP (`smtplib`), CLI parsing (`argparse`), and JSON handling (`json`) use the Python standard library, so they do not need to be installed.

## YouTube RSS discovery

- [ ] Add the curated channel list at `app/data/channels.json`.
- [ ] Fetch and parse YouTube RSS feeds; inspect the available fields and sample entries.

## Database

- [ ] Define the database models based on the source and digest data we need to persist.
- [ ] Add environment-based application configuration.
- [ ] Configure the SQLAlchemy engine and session.
- [ ] Set up Alembic under `app/database/alembic/`.
- [ ] Add `app/database/migrate.py` and the initial schema migration.
- [ ] Verify migrations can be applied to the local PostgreSQL database.

## YouTube ingestion

- [ ] Implement channel upserts and store parsed feed articles.
- [ ] Store articles and deduplicate them by video ID.

## Digest generation and email

- [ ] Add the editable system prompt at `app/agent/prompts/digest_system.md`.
- [ ] Implement the DeepSeek agent service and validate response URLs.
- [ ] Generate a digest from articles published in the last 24 hours.
- [ ] Render and send the digest email over SMTP.
- [ ] Persist digest results and prevent repeat sends on the same UTC day.
- [ ] Support intentional repeat sends with `--force`.

## CLI and documentation

- [ ] Implement the `migrate`, `seed`, and `run` CLI commands.
- [ ] Keep `main.py` as a thin entrypoint to the CLI.
- [ ] Document local setup and manual run instructions in `README.md`.

## Local environment

- [ ] Add Docker Compose for local PostgreSQL 16.
- [ ] Add `.env.example` for database, DeepSeek, and SMTP settings.
- [ ] Add or confirm `.env` is ignored by Git.

## End-to-end verification

- [ ] Start PostgreSQL using Docker Compose.
- [ ] Apply migrations and verify the database schema.
- [ ] Run ingestion and verify source and article records.
- [ ] Run the digest and verify it is emailed and recorded.
- [ ] Verify a second run on the same UTC day does not send again unless `--force` is used.

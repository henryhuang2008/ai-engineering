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
  - `youtube-transcript-api` for YouTube captions.

SMTP (`smtplib`), CLI parsing (`argparse`), and JSON handling (`json`) use the Python standard library, so they do not need to be installed.

## YouTube RSS discovery

- [x] Add Dave Ebbelaar to `app/data/channels.json` as the first channel to follow.
- [x] Implement RSS fetching and parsing for channel metadata and video ID, title, URL, description, and publication time.
- [x] Inspect a live feed and confirm the parsed fields against real entries.

## Database

- [x] Define the database models based on the source and digest data we need to persist.
- [x] Add environment-based application configuration.
- [x] Configure the SQLAlchemy engine and session.
- [x] Set up Alembic under `app/database/alembic/`.
- [x] Add `app/database/migrate.py` and the initial schema migration.
- [x] Verify migrations can be applied to the local PostgreSQL database.

After PostgreSQL is running, apply the schema from the project root:

```shell
uv run python -m app.database.migrate
```

Confirm the applied revision with `uv run alembic -c app/database/alembic.ini current`.

## YouTube ingestion

Implementation plan:

1. [x] Confirm PostgreSQL is running and the initial Alembic migration is applied.
2. [x] Load and validate `app/data/channels.json` entries (`name`, `channel_id`).
3. [x] Upsert each configured channel into `sources` by `channel_id`; refresh its name and feed URL, mark it active, and mark removed channels inactive.
4. [x] Fetch each active channel's RSS feed and map its channel/video fields into the existing data models.
5. [x] Upsert articles by unique `video_id`; refresh RSS metadata without overwriting any transcript already stored for that video.
6. [x] Report feed/database failures explicitly, and verify one failed channel does not silently appear successful.
7. [x] Add tests for channel upserts, article inserts/updates, duplicate video IDs, inactive channels, and failed feeds.
8. [x] Run ingestion against local PostgreSQL and verify source/article row counts and representative field values.

Run ingestion manually from the project root with `uv run python -m app.ingest.seed`. Use `uv run python -m app.ingest.seed --dummy-data` to test against the bundled RSS fixture without requesting YouTube.

## Transcript retrieval

- [x] Fetch captions from a YouTube URL and fall back to the RSS description when unavailable.
- [x] Connect RSS video records to transcript lookup and show the selected content for each video in the live test.
- [x] Build bounded digest input from saved transcripts, falling back to RSS descriptions when unavailable (12,000 content characters per video; 48,000 characters total).

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

- [x] Add Docker Compose for local PostgreSQL 16.
- [ ] Add `.env.example` for database, DeepSeek, and SMTP settings.
- [ ] Add or confirm `.env` is ignored by Git.

Start PostgreSQL manually from the project root:

```shell
docker compose -f docker/docker-compose.yml up -d
```

Check readiness with `docker compose -f docker/docker-compose.yml ps`; stop it with `docker compose -f docker/docker-compose.yml down`. The named volume preserves database data when stopped.

## End-to-end verification

- [x] Start PostgreSQL using Docker Compose.
- [x] Apply migrations and verify the database schema.
- [x] Run ingestion and verify source and article records.
- [ ] Run the digest and verify it is emailed and recorded.
- [ ] Verify a second run on the same UTC day does not send again unless `--force` is used.

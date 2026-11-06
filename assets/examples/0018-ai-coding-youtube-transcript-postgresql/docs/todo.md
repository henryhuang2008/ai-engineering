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
- [ ] Apply the digest-attempt migration to local PostgreSQL and verify the updated schema.

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

## Digest generation and email

See the detailed design and acceptance criteria in [digest-generation-and-email-plan.md](./digest-generation-and-email-plan.md).

Implementation plan:

1. [x] Build bounded digest input from saved transcripts, falling back to RSS descriptions when unavailable (12,000 content characters per video; 48,000 characters total).
2. [x] Add the editable system prompt at `app/agent/prompts/digest_system.md` and implement the DeepSeek service using the OpenAI-compatible API settings.
3. [x] Select articles published in the last 24 hours using a UTC time window; define and test boundary behavior and the empty-input case.
4. [x] Generate structured digest entries from the selected articles and bounded input; reject malformed responses and links that do not exactly match the input article URLs.
5. [x] Render a readable plain-text and HTML email, escaping article-provided text in HTML.
6. [x] Configure SMTP settings and send the rendered email using STARTTLS; surface send failures rather than reporting success.
7. [x] Persist each digest attempt and its outcome (`sent`, `failed`, or `empty`), including its UTC run date, window, content, model, recipient, and send time. Add a migration to replace the current unique-per-run-date constraint so intentional forced attempts can also be recorded.
8. [x] Make `run` print a database-backed preview by default; `--raw` prints saved article records without DeepSeek, `--send-email` opts into delivery, and `--force` records another attempt. Skip delivery if already sent that UTC date; empty or failed attempts must not appear sent.
9. [x] Test article-window selection, transcript/description input, response and URL validation, email rendering, mocked SMTP success/failure, persistence, duplicate-run prevention, and `--force`.
10. [x] Document configuration and manual run instructions in `README.md`.
11. [ ] After applying migrations and configuring credentials, verify a successful local email delivery and the saved digest record.

## CLI and documentation

- [x] Implement the `migrate`, `seed`, and `run` CLI commands.
- [x] Keep `main.py` as a thin entrypoint to the CLI.
- [x] Document local setup and manual run instructions in `README.md`.

## Local environment

- [x] Add Docker Compose for local PostgreSQL 16.
- [x] Add `.env.example` for database, DeepSeek, and SMTP settings.
- [x] Add or confirm `.env` is ignored by Git.

Start PostgreSQL manually from the project root:

```shell
docker compose -f docker/docker-compose.yml up -d
```

Check readiness with `docker compose -f docker/docker-compose.yml ps`; stop it with `docker compose -f docker/docker-compose.yml down`. The named volume preserves database data when stopped.

## End-to-end verification

- [x] Start PostgreSQL using Docker Compose.
- [ ] Apply the current migrations and verify the upgraded database schema.
- [x] Run ingestion and verify source and article records.
- [ ] Run the digest and verify it is emailed and recorded.
- [ ] Verify a second run on the same UTC day does not send again unless `--force` is used.

## Aggregator scope (planned, not built)

The product brief is an AI news aggregator: more than one source kind, a daily scheduler, and a digest shaped by the operator's own prompt. The shipped slice stops at a manual YouTube run. The phases below are deferred; each box stays unchecked until its acceptance check has actually run.

### Scheduler

- [ ] Add a daily trigger in UTC that runs ingestion and then digest generation. Touches the host scheduler or `docker/`. Acceptance: a documented crontab or systemd timer runs both commands and writes one log line per run. (implementation)
- [ ] Serialize runs so two overlapping invocations cannot both send. Acceptance: two forced parallel runs produce exactly one email, and the second exits without sending. (implementation + verification)
- [ ] Alert on a failed or empty digest. Acceptance: a deliberately broken credential or an empty window produces a visible alert within one run. (implementation)
- [ ] Persist per-source `last_success` and `last_error`. Acceptance: after one injected feed failure, a query distinguishes "no new videos" from "this source has failed for N days". (implementation)

### Additional source kinds

- [ ] Add a second collector and register it through `sources.kind`. Acceptance: one run inserts articles from both kinds, with per-kind tests and no change to the digest code. (implementation)
- [ ] When the second kind lands, generalize the article key from `video_id` to `(source_id, external_id)` in a new Alembic revision. Acceptance: `alembic current` reports the new head and the upsert test passes for both kinds. (implementation)

### Per-user insight profiles

- [ ] Add a `digest_profiles` table and select a prompt per recipient instead of using the single global prompt file. Acceptance: two profiles produce two different prompts in a test, and the digest row records which profile ran. (implementation)


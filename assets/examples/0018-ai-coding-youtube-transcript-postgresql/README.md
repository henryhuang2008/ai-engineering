# Daily YouTube Digest

## Local PostgreSQL

Start the PostgreSQL 16 container from the project root:

```shell
docker compose -f docker/docker-compose.yml up -d
```

Check the container and health status:

```shell
docker compose -f docker/docker-compose.yml ps
```

Stop the container without deleting the database volume:

```shell
docker compose -f docker/docker-compose.yml down
```

The database is available on `localhost:5432`. Defaults are database `youtube_digest`, username `youtube_digest`, and password `local_dev_password`; these can be overridden with `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` environment variables or a root `.env` file. The named `postgres_data` volume preserves data when the container is stopped.

After PostgreSQL is healthy, create/update the database schema by running the Alembic migration:

```shell
uv run python -m app.database.migrate
```

Check which migration is applied:

```shell
uv run alembic -c app/database/alembic.ini current
```

The migration creates the `sources`, `articles`, and `digests` tables. It does not seed channels or fetch videos.

## YouTube ingestion

Edit `app/data/channels.json` to configure channels. Each entry requires a non-empty `name` and a valid YouTube `channel_id`.

Run the manual ingestion command from the project root:

```shell
uv run python -m app.ingest.seed
```

The command upserts configured channels, marks removed channels inactive, fetches each channel's RSS feed, and upserts videos by video ID. RSS updates preserve any transcript already stored. Failed channel feeds are listed on stderr, and the command exits non-zero if any feed fails; other channels can still succeed.

To test ingestion without network access, use the included dummy RSS fixture:

```shell
uv run python -m app.ingest.seed --dummy-data
```

The fixture represents the sample channel in `app/data/channels.json`. The option explicitly reports that dummy data was used and rejects a channel configuration that does not match the fixture.

## Digest input

`app.digest.input.build_digest_input` formats saved articles for digest generation. It uses a saved transcript when present and falls back to the RSS description; content is limited to 12,000 characters per video and 48,000 characters total, including article metadata. Content that exceeds a limit is marked as truncated.

## Digest generation and email

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Configure `DEEPSEEK_API_KEY` for preview generation. SMTP settings (`SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_SENDER`, and `EMAIL_RECIPIENT`) are needed only when you opt in to email delivery. The DeepSeek base URL, model, SMTP port, and database URL have local-development defaults in `.env.example`. Do not commit `.env`; it is ignored by Git.

Apply database migrations (including the migration that allows multiple recorded attempts per UTC date):

```shell
uv run python main.py migrate
```

By default, `run` reads already-ingested records from PostgreSQL, generates a preview, and prints it. It does not fetch YouTube feeds, send email, or save a digest attempt:

```shell
uv run python main.py run
```

Generating the preview still calls DeepSeek, so the model response time depends on the API. To refresh saved articles first, run ingestion separately with `uv run python main.py seed`.

To explicitly send the digest instead of printing a preview, add `--send-email`. A successful send is recorded in PostgreSQL. Re-running on the same UTC date skips after a successful send; `--force` records and sends another attempt:

```shell
uv run python main.py run --send-email
uv run python main.py run --send-email --force
```

Failed generation and delivery attempts are recorded as `failed` and can be retried. Runs with no articles in the time window are recorded as `empty` without calling DeepSeek or sending email. Unit tests use mocks and do not call DeepSeek or send messages.

## Running tests

Run the test suite from the project root (the directory containing `pyproject.toml`):

```shell
uv run python -m unittest discover -s tests -v
```

To run only the YouTube RSS tests:

```shell
uv run python -m unittest discover -s tests -p test_youtube.py -v
```

To run only the transcript tests:

```shell
uv run python -m unittest discover -s tests -p test_transcript.py -v
```

To fetch recent channel videos and print each video's available transcript (or RSS description fallback):

```shell
uv run python -m unittest discover -s tests -p live_youtube_test.py -v
```

To test dummy-feed ingestion and read the inserted source and article records back from a temporary SQLite database:

```shell
uv run python -m unittest discover -s tests -p test_ingest_sync.py -v
```

This automated test does not write to PostgreSQL. To insert the dummy records into the configured PostgreSQL database, run `uv run python -m app.ingest.seed --dummy-data`.

The test uses `YOUTUBE_LOOKBACK_HOURS` as its look-back window (default: 180). For example, in Git Bash:

```shell
YOUTUBE_LOOKBACK_HOURS=24 uv run python -m unittest discover -s tests -p live_youtube_test.py -v
```

To fetch a transcript from a YouTube video URL:

```shell
uv run python -m app.ingest.transcript "https://www.youtube.com/watch?v=VIDEO_ID"
```

By default, the tool looks for English captions. Request preferred languages in order by repeating `--language`, and provide an RSS description to use when captions are unavailable:

```shell
uv run python -m app.ingest.transcript "https://youtu.be/VIDEO_ID" --language en --language ja
uv run python -m app.ingest.transcript "https://youtu.be/VIDEO_ID" --description "RSS video description"
```

Caption retrieval can fail when a video has no available captions or YouTube blocks the request. In that case the command uses the supplied description; otherwise it reports that no content is available. `get_video_content` in `app.ingest.transcript` provides the same behavior to application code.

If your terminal is currently in the `tests` directory, return to the project root first:

```shell
cd ..
uv run python -m unittest discover -s tests -v
```

Running unittest discovery from the project root also ensures the application package can be imported by the tests.
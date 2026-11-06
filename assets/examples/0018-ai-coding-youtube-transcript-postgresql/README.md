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
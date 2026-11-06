# Digest Generation and Email Plan

## Goal

Generate a concise digest preview from database records for videos published in the previous 24 hours. Print it by default; email delivery is an explicit opt-in and each delivery attempt is recorded so normal sends do not duplicate on the same UTC date.

The workflow is manually invoked. It does not add a scheduler.

## Existing foundation

- `app/database/models/article.py` stores video metadata and optional transcript fields.
- `app/database/models/digest.py` stores digest content and delivery status. A migration removes the original unique constraint on `run_date` so forced attempts can be recorded.
- `app/digest/input.py` formats article content, prefers transcripts over RSS descriptions, and applies 12,000-character per-video and 48,000-character total limits.
- `app/config.py` provides the database, DeepSeek, and SMTP settings.

## Implementation sequence

### 1. Configure the agent

- Add the editable prompt at `app/agent/prompts/digest_system.md`.
- Extend settings and `.env.example` with the DeepSeek API key, base URL, and model.
- Implement `app/agent/service.py` using the OpenAI-compatible API.
- Define a structured response format for digest entries and validate required fields and types.
- Accept only URLs that exactly match article URLs provided to the model; reject malformed or unknown links.
- Surface API and validation errors explicitly.

### 2. Select articles and generate content

- Implement `app/digest/generate.py`.
- Use a UTC window `[now - 24 hours, now]`, with an injectable `now` for deterministic tests.
- Include the lower bound and upper bound, exclude records outside the window, and define behavior for articles with no publication time (exclude them).
- Pass selected articles through `build_digest_input`; handle an empty result without calling the model.
- Return validated digest entries together with the window and selected article count.

### 3. Render the email

- Render both plain-text and HTML alternatives from validated entries.
- Include each title, summary, and validated video link.
- Escape all model- and article-provided text inserted into HTML.
- Test readable output and ensure links remain restricted to the selected article URLs.

### 4. Send mail

- Extend configuration and `.env.example` with SMTP host, port, username, password, sender, and recipient.
- Send a multipart plain-text/HTML message with `smtplib` and STARTTLS.
- Require valid configuration and surface authentication, TLS, and delivery errors; do not report a failed send as successful.
- Test SMTP interactions with mocks; do not require a live email service for unit tests.

### 5. Persist attempts and enforce idempotency

- Record digest window, UTC run date, content, model, recipient, article count, status, and send time.
- Persist an empty result as `empty`; persist a delivery failure as `failed`; only record `sent` after successful SMTP delivery.
- Replace the unique-per-`run_date` constraint in a new Alembic migration so multiple attempts, including forced attempts, can be retained.
- Before a normal run sends, check whether a digest with status `sent` already exists for that UTC date. If so, skip generation and delivery.
- `--force` bypasses the sent-today check and creates a separate attempt; it does not overwrite prior history.
- Ensure failed or empty attempts do not block a later retry that day.

### 6. Wire the CLI and verify end to end

- Add the `run` command and optional `--force` flag; keep `main.py` as a thin entrypoint.
- Make `run` preview database records by default; require an explicit `--send-email` flag for SMTP delivery. Keep feed ingestion separate in `seed`.
- Provide `run --raw` to print saved database article fields as JSON without calling DeepSeek, sending email, or recording a digest attempt.
- Keep migration and ingestion behavior available through the CLI as planned.
- Add unit tests for UTC window boundaries, missing publication times, empty input, input limits, response validation, URL allowlisting, HTML escaping, SMTP success/failure, persistence, duplicate-run skipping, failed retries, and forced attempts.
- Document configuration and manual commands in `README.md`.
- With local PostgreSQL migrated and credentials configured, run a manual digest and verify the email and saved database row. This credential-dependent live check is intentionally performed by the project owner.

## Acceptance criteria

- A normal run selects only articles published in the preceding 24 hours.
- The model input prefers saved transcripts, falls back to descriptions, and respects both character limits.
- Generated links can only target URLs belonging to selected articles.
- An empty result does not call DeepSeek or send an email.
- A successful send is recorded as `sent`; failures and empty runs are recorded accurately.
- A second normal run on the same UTC date does not send again after a successful send.
- `--force` allows another recorded attempt without deleting or replacing the earlier digest.
- Unit tests do not send real email or require DeepSeek credentials.

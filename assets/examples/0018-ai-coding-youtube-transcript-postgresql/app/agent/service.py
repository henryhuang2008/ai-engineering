from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from openai import OpenAI

from app.config import Settings, get_settings

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "digest_system.md"
YOUTUBE_URL_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


@dataclass(frozen=True)
class DigestEntry:
    title: str
    summary: str
    url: str


@dataclass(frozen=True)
class GeneratedDigest:
    subject: str
    entries: tuple[DigestEntry, ...]


def load_system_prompt(path: Path = PROMPT_FILE) -> str:
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise OSError(f"Could not read digest system prompt {path}: {error}") from error
    if not prompt:
        raise ValueError(f"Digest system prompt is empty: {path}")
    return prompt


def _is_safe_youtube_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and hostname is not None
        and hostname.lower() in YOUTUBE_URL_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


def parse_digest_response(
    response_text: str,
    *,
    allowed_urls: Sequence[str],
) -> GeneratedDigest:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"DeepSeek returned invalid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek response must be a JSON object")

    subject = payload.get("subject")
    entries_data = payload.get("entries")
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject.strip()) > 120
        or "\r" in subject
        or "\n" in subject
    ):
        raise ValueError(
            "Digest subject must be a non-empty single line of at most 120 characters"
        )
    if not isinstance(entries_data, list) or not entries_data:
        raise ValueError("Digest entries must be a non-empty JSON array")

    url_allowlist = set(allowed_urls)
    unsafe_urls = [
        url for url in url_allowlist if not _is_safe_youtube_url(url)
    ]
    if unsafe_urls:
        raise ValueError("Selected articles contain a non-HTTPS YouTube URL")

    entries: list[DigestEntry] = []
    seen_urls: set[str] = set()
    for index, entry_data in enumerate(entries_data):
        if not isinstance(entry_data, dict):
            raise ValueError(f"Digest entry {index} must be a JSON object")
        title = entry_data.get("title")
        summary = entry_data.get("summary")
        url = entry_data.get("url")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title.strip()) > 200
        ):
            raise ValueError(f"Digest entry {index} has an invalid title")
        if (
            not isinstance(summary, str)
            or not summary.strip()
            or len(summary.strip()) > 600
        ):
            raise ValueError(f"Digest entry {index} has an invalid summary")
        if not isinstance(url, str) or url not in url_allowlist:
            raise ValueError(
                f"Digest entry {index} contains an unrecognized article URL"
            )
        if url in seen_urls:
            raise ValueError(f"Digest entry {index} repeats an article URL")
        seen_urls.add(url)
        entries.append(
            DigestEntry(title=title.strip(), summary=summary.strip(), url=url)
        )

    if seen_urls != url_allowlist:
        raise ValueError(
            "DeepSeek response must include each selected article exactly once"
        )
    return GeneratedDigest(subject=subject.strip(), entries=tuple(entries))


def generate_digest_content(
    content: str,
    *,
    allowed_urls: Sequence[str],
    settings: Settings | None = None,
) -> GeneratedDigest:
    active_settings = settings or get_settings()
    api_key, base_url, model = active_settings.require_deepseek()
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": content},
        ],
    )
    response_text = response.choices[0].message.content
    if not isinstance(response_text, str) or not response_text.strip():
        raise ValueError("DeepSeek returned an empty digest response")
    return parse_digest_response(response_text, allowed_urls=allowed_urls)

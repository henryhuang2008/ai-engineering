from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Iterable, Literal
from urllib.parse import parse_qs, urlsplit

from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}\Z")
DEFAULT_LANGUAGES = ("en",)


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float


@dataclass(frozen=True)
class VideoTranscript:
    video_id: str
    text: str
    language: str
    language_code: str
    is_generated: bool
    segments: tuple[TranscriptSegment, ...]


@dataclass(frozen=True)
class VideoContent:
    text: str
    source: Literal["transcript", "description", "unavailable"]
    transcript: VideoTranscript | None = None


def extract_video_id(video_url: str) -> str:
    candidate = video_url.strip()
    if VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate

    if "://" not in candidate:
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid YouTube URL or video ID: {video_url!r}")

    host = parsed.hostname.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    video_id: str | None = None

    if host == "youtu.be":
        video_id = path_parts[0] if path_parts else None
    elif host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(path_parts) >= 2 and path_parts[0] in {
            "embed",
            "live",
            "shorts",
            "v",
        }:
            video_id = path_parts[1]

    if not video_id or not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError(f"Could not extract a valid video ID from {video_url!r}")

    return video_id


def fetch_transcript(
    video_url: str,
    *,
    languages: Iterable[str] = DEFAULT_LANGUAGES,
) -> VideoTranscript | None:
    video_id = extract_video_id(video_url)
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    except CouldNotRetrieveTranscript:
        return None

    segments = tuple(
        TranscriptSegment(
            text=snippet.text,
            start=snippet.start,
            duration=snippet.duration,
        )
        for snippet in fetched.snippets
    )
    return VideoTranscript(
        video_id=video_id,
        text=" ".join(
            segment.text.strip()
            for segment in segments
            if segment.text.strip()
        ),
        language=fetched.language,
        language_code=fetched.language_code,
        is_generated=fetched.is_generated,
        segments=segments,
    )


def get_video_content(
    video_url: str,
    *,
    description: str = "",
    languages: Iterable[str] = DEFAULT_LANGUAGES,
) -> VideoContent:
    transcript = fetch_transcript(video_url, languages=languages)
    if transcript and transcript.text:
        return VideoContent(
            text=transcript.text,
            source="transcript",
            transcript=transcript,
        )
    if description.strip():
        return VideoContent(text=description.strip(), source="description")
    return VideoContent(text="", source="unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a YouTube transcript, falling back to an RSS description."
    )
    parser.add_argument("video_url", help="YouTube video URL or 11-character video ID.")
    parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        help="Preferred transcript language; can be repeated (default: en).",
    )
    parser.add_argument(
        "--description",
        default="",
        help="RSS description to use if no transcript is available.",
    )
    args = parser.parse_args()

    content = get_video_content(
        args.video_url,
        description=args.description,
        languages=args.languages or DEFAULT_LANGUAGES,
    )
    if content.source == "unavailable":
        parser.exit(
            1,
            "No transcript is available. Pass --description to use the RSS description as fallback.\n",
        )

    print(f"Source: {content.source}")
    if content.transcript:
        print(
            f"Language: {content.transcript.language} "
            f"({content.transcript.language_code})"
        )
        print(f"Generated captions: {content.transcript.is_generated}")
    print(content.text)


if __name__ == "__main__":
    main()

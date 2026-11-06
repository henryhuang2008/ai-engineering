import unittest
from datetime import UTC, datetime

from app.database.models import Article, Source
from app.digest.input import (
    MAX_ARTICLE_CONTENT_CHARS,
    MAX_DIGEST_INPUT_CHARS,
    TRUNCATION_MARKER,
    build_digest_input,
)


def make_article(
    *,
    title: str = "Example video",
    transcript: str | None = None,
    description: str = "RSS description",
    url: str = "https://youtu.be/abcdefghijk",
    source_name: str = "Example channel",
) -> Article:
    return Article(
        title=title,
        transcript=transcript,
        description=description,
        url=url,
        published_at=datetime(2026, 11, 6, 9, tzinfo=UTC),
        source=Source(name=source_name),
    )


class BuildDigestInputTests(unittest.TestCase):
    def test_prefers_transcript_and_falls_back_to_description(self) -> None:
        with_transcript = make_article(
            transcript=" Saved transcript ",
            description="RSS description should not be used",
        )
        without_transcript = make_article(
            title="Description fallback",
            transcript="  ",
            description=" Description text ",
        )

        digest_input = build_digest_input([with_transcript, without_transcript])

        self.assertIn("Content source: transcript", digest_input)
        self.assertIn("Content source: description", digest_input)
        self.assertIn("Content:\nSaved transcript", digest_input)
        self.assertIn("Content:\nDescription text", digest_input)
        self.assertIn("Channel: Example channel", digest_input)
        self.assertIn("URL: https://youtu.be/abcdefghijk", digest_input)
        self.assertNotIn("RSS description should not be used", digest_input)

    def test_truncates_long_content_at_per_article_limit(self) -> None:
        article = make_article(
            transcript="x" * (MAX_ARTICLE_CONTENT_CHARS + 100),
        )
        next_article = make_article(title="Next video")

        digest_input = build_digest_input([article, next_article])

        self.assertIn("x" * MAX_ARTICLE_CONTENT_CHARS, digest_input)
        self.assertIn(TRUNCATION_MARKER, digest_input)
        self.assertIn("## Video: Next video", digest_input)
        self.assertLessEqual(len(digest_input), MAX_DIGEST_INPUT_CHARS)

    def test_caps_combined_input_length(self) -> None:
        articles = [
            make_article(
                title=f"Video {index}",
                description=f"{index}" * MAX_ARTICLE_CONTENT_CHARS,
            )
            for index in range(5)
        ]

        digest_input = build_digest_input(articles)

        self.assertLessEqual(len(digest_input), MAX_DIGEST_INPUT_CHARS)
        self.assertIn(TRUNCATION_MARKER, digest_input)
        self.assertIn("Content source: description", digest_input)


if __name__ == "__main__":
    unittest.main()

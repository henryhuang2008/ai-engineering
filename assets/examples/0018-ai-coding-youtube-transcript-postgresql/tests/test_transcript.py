import unittest
from types import SimpleNamespace
from unittest.mock import patch

from youtube_transcript_api import TranscriptsDisabled

from app.ingest.transcript import (
    extract_video_id,
    get_video_content,
)

VIDEO_ID = "abcdefghijk"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


class ExtractVideoIdTests(unittest.TestCase):
    def test_extracts_id_from_common_youtube_urls(self) -> None:
        urls = (
            VIDEO_URL,
            f"https://youtu.be/{VIDEO_ID}?t=30",
            f"https://www.youtube.com/shorts/{VIDEO_ID}",
            f"https://youtube.com/live/{VIDEO_ID}",
            VIDEO_ID,
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), VIDEO_ID)

    def test_rejects_non_youtube_urls_and_invalid_ids(self) -> None:
        for url in ("https://example.com/watch?v=abcdefghijk", "bad-id"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                extract_video_id(url)


class GetVideoContentTests(unittest.TestCase):
    @patch("app.ingest.transcript.YouTubeTranscriptApi")
    def test_returns_joined_transcript_and_metadata(self, api_class) -> None:
        api_class.return_value.fetch.return_value = SimpleNamespace(
            snippets=[
                SimpleNamespace(text="Hello", start=0.0, duration=1.0),
                SimpleNamespace(text="world.", start=1.0, duration=1.5),
            ],
            language="English",
            language_code="en",
            is_generated=True,
        )

        content = get_video_content(VIDEO_URL, languages=("en", "ja"))

        self.assertEqual(content.source, "transcript")
        self.assertEqual(content.text, "Hello world.")
        self.assertEqual(content.transcript.video_id, VIDEO_ID)
        self.assertEqual(content.transcript.language_code, "en")
        self.assertTrue(content.transcript.is_generated)
        api_class.return_value.fetch.assert_called_once_with(
            VIDEO_ID, languages=("en", "ja")
        )

    @patch("app.ingest.transcript.YouTubeTranscriptApi")
    def test_uses_description_when_transcript_is_unavailable(self, api_class) -> None:
        api_class.return_value.fetch.side_effect = TranscriptsDisabled(VIDEO_ID)

        content = get_video_content(VIDEO_URL, description=" RSS summary ")

        self.assertEqual(content.source, "description")
        self.assertEqual(content.text, "RSS summary")
        self.assertIsNone(content.transcript)

    @patch("app.ingest.transcript.YouTubeTranscriptApi")
    def test_reports_unavailable_without_transcript_or_description(
        self, api_class
    ) -> None:
        api_class.return_value.fetch.side_effect = TranscriptsDisabled(VIDEO_ID)

        content = get_video_content(VIDEO_URL)

        self.assertEqual(content.source, "unavailable")
        self.assertEqual(content.text, "")


if __name__ == "__main__":
    unittest.main()

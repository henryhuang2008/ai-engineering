import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.service import generate_digest_content, parse_digest_response
from app.config import Settings

ARTICLE_URLS = ("https://youtu.be/abcdefghijk", "https://youtu.be/lmnopqrstuv")


class ParseDigestResponseTests(unittest.TestCase):
    def test_parses_entries_for_all_allowed_urls(self) -> None:
        response = (
            '{"subject":"Daily digest","entries":['
            '{"title":"First","summary":"Summary one","url":"'
            + ARTICLE_URLS[0]
            + '"},{"title":"Second","summary":"Summary two","url":"'
            + ARTICLE_URLS[1]
            + '"}]}'
        )

        digest = parse_digest_response(response, allowed_urls=ARTICLE_URLS)

        self.assertEqual(digest.subject, "Daily digest")
        self.assertEqual(
            tuple(entry.url for entry in digest.entries),
            ARTICLE_URLS,
        )

    def test_rejects_malformed_response_and_unknown_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            parse_digest_response("not json", allowed_urls=ARTICLE_URLS)

        response = (
            '{"subject":"Daily digest","entries":[{"title":"Video",'
            '"summary":"Summary","url":"https://example.com/"}]}'
        )
        with self.assertRaisesRegex(ValueError, "unrecognized article URL"):
            parse_digest_response(response, allowed_urls=(ARTICLE_URLS[0],))

    def test_rejects_non_youtube_or_insecure_allowlisted_urls(self) -> None:
        response = (
            '{"subject":"Daily digest","entries":[{"title":"Video",'
            '"summary":"Summary","url":"javascript:alert(1)"}]}'
        )
        with self.assertRaisesRegex(ValueError, "non-HTTPS YouTube URL"):
            parse_digest_response(
                response,
                allowed_urls=("javascript:alert(1)",),
            )

    def test_rejects_missing_or_duplicate_article_entries(self) -> None:
        response = (
            '{"subject":"Daily digest","entries":[{"title":"First",'
            '"summary":"Summary","url":"'
            + ARTICLE_URLS[0]
            + '"}]}'
        )
        with self.assertRaisesRegex(ValueError, "each selected article"):
            parse_digest_response(response, allowed_urls=ARTICLE_URLS)

    @patch("app.agent.service.OpenAI")
    def test_calls_configured_openai_compatible_service(self, openai_class) -> None:
        response_text = (
            '{"subject":"Daily digest","entries":[{"title":"Video",'
            '"summary":"Summary","url":"'
            + ARTICLE_URLS[0]
            + '"}]}'
        )
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=response_text),
                    )
                ]
            )
        )
        settings = Settings(
            database_url="sqlite://",
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.example.com",
            deepseek_model="test-model",
            smtp_host=None,
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            email_sender=None,
            email_recipient=None,
        )

        digest = generate_digest_content(
            "Video content",
            allowed_urls=(ARTICLE_URLS[0],),
            settings=settings,
        )

        openai_class.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.example.com",
        )
        self.assertEqual(
            openai_class.return_value.chat.completions.create.call_args.kwargs[
                "model"
            ],
            "test-model",
        )
        self.assertEqual(digest.entries[0].url, ARTICLE_URLS[0])


if __name__ == "__main__":
    unittest.main()

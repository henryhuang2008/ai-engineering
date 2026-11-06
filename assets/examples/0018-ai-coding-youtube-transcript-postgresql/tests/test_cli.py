import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app.cli import main
from app.digest.preview import DigestPreview


class DigestCliTests(unittest.TestCase):
    @patch("app.cli.run_daily_digest")
    @patch("app.cli.preview_daily_digest")
    @patch("app.cli.saved_articles_json")
    @patch("app.cli.SessionLocal")
    @patch("app.cli.get_settings")
    def test_run_defaults_to_printing_preview_without_sending(
        self,
        get_settings,
        session_local,
        saved_articles_json,
        preview_daily_digest,
        run_daily_digest,
    ) -> None:
        get_settings.return_value = object()
        session_local.return_value = nullcontext(object())
        preview_daily_digest.return_value = DigestPreview(
            status="preview",
            article_count=1,
            subject="Printed digest",
            text_body="Printed digest\n\nPreview body",
        )

        with patch("builtins.print") as print_mock:
            result = main(["run"])

        self.assertEqual(result, 0)
        preview_daily_digest.assert_called_once()
        saved_articles_json.assert_not_called()
        run_daily_digest.assert_not_called()
        print_mock.assert_any_call("Printed digest\n\nPreview body")

    @patch("app.cli.run_daily_digest")
    @patch("app.cli.preview_daily_digest")
    @patch("app.cli.saved_articles_json")
    @patch("app.cli.SessionLocal")
    @patch("app.cli.get_settings")
    def test_raw_option_prints_saved_records_without_deepseek_or_email(
        self,
        get_settings,
        session_local,
        saved_articles_json,
        preview_daily_digest,
        run_daily_digest,
    ) -> None:
        get_settings.return_value = object()
        session_local.return_value = nullcontext(object())
        saved_articles_json.return_value = '[{"title":"Stored title"}]'

        with patch("builtins.print") as print_mock:
            result = main(["run", "--raw"])

        self.assertEqual(result, 0)
        saved_articles_json.assert_called_once()
        preview_daily_digest.assert_not_called()
        run_daily_digest.assert_not_called()
        print_mock.assert_called_once_with('[{"title":"Stored title"}]')

    def test_force_requires_explicit_send_email_opt_in(self) -> None:
        with self.assertRaises(SystemExit) as error:
            main(["run", "--force"])

        self.assertEqual(error.exception.code, 2)

    def test_raw_mode_cannot_be_combined_with_email(self) -> None:
        with self.assertRaises(SystemExit) as error:
            main(["run", "--raw", "--send-email"])

        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

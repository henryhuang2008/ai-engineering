import unittest
from contextlib import nullcontext
from unittest.mock import patch

from app.cli import main
from app.digest.preview import DigestPreview


class DigestCliTests(unittest.TestCase):
    @patch("app.cli.run_daily_digest")
    @patch("app.cli.preview_daily_digest")
    @patch("app.cli.SessionLocal")
    @patch("app.cli.get_settings")
    def test_run_defaults_to_printing_preview_without_sending(
        self,
        get_settings,
        session_local,
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
        run_daily_digest.assert_not_called()
        print_mock.assert_any_call("Printed digest\n\nPreview body")

    def test_force_requires_explicit_send_email_opt_in(self) -> None:
        with self.assertRaises(SystemExit) as error:
            main(["run", "--force"])

        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

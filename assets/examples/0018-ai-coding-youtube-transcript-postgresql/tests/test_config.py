import os
import unittest
from unittest.mock import patch

from app.config import get_settings


class SettingsTests(unittest.TestCase):
    def test_reads_digest_and_smtp_environment_settings(self) -> None:
        values = {
            "DATABASE_URL": "sqlite://",
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_BASE_URL": "https://api.example.com",
            "DEEPSEEK_MODEL": "test-model",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "2525",
            "SMTP_USERNAME": "user",
            "SMTP_PASSWORD": "password",
            "EMAIL_SENDER": "digest@example.com",
            "EMAIL_RECIPIENT": "reader@example.com",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = get_settings()

        self.assertEqual(settings.database_url, "sqlite://")
        self.assertEqual(settings.require_deepseek(), (
            "test-key",
            "https://api.example.com",
            "test-model",
        ))
        self.assertEqual(settings.require_smtp(), (
            "smtp.example.com",
            2525,
            "user",
            "password",
            "digest@example.com",
            "reader@example.com",
        ))

    def test_reports_missing_service_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()

        with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
            settings.require_deepseek()
        with self.assertRaisesRegex(ValueError, "SMTP_HOST"):
            settings.require_smtp()

    def test_rejects_non_numeric_smtp_port(self) -> None:
        with patch.dict(os.environ, {"SMTP_PORT": "invalid"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SMTP_PORT must be an integer"):
                get_settings()


if __name__ == "__main__":
    unittest.main()

import unittest
import smtplib
from unittest.mock import MagicMock, patch

from app.agent.service import DigestEntry, GeneratedDigest
from app.config import Settings
from app.emailer.smtp import (
    create_message,
    render_digest_email,
    send_digest_email,
)


def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="password",
        email_sender="digest@example.com",
        email_recipient="reader@example.com",
    )


class DigestEmailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.digest = GeneratedDigest(
            subject="Daily <digest>",
            entries=(
                DigestEntry(
                    title="<script>alert(1)</script>",
                    summary="Tom & Jerry",
                    url="https://youtu.be/abcdefghijk?a=1&b=2",
                ),
            ),
        )

    def test_escapes_html_and_keeps_plain_text(self) -> None:
        rendered = render_digest_email(self.digest)

        self.assertIn("<script>alert(1)</script>", rendered.text_body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered.html_body)
        self.assertIn("Tom &amp; Jerry", rendered.html_body)
        self.assertIn("a=1&amp;b=2", rendered.html_body)

    def test_creates_multipart_message(self) -> None:
        rendered = render_digest_email(self.digest)
        message = create_message(
            self.digest.subject,
            rendered,
            settings=settings(),
        )

        self.assertEqual(message["To"], "reader@example.com")
        self.assertTrue(message.is_multipart())
        self.assertEqual(
            {part.get_content_type() for part in message.iter_parts()},
            {"text/plain", "text/html"},
        )

    @patch("app.emailer.smtp.smtplib.SMTP")
    def test_sends_using_starttls_and_authentication(self, smtp_class) -> None:
        smtp = MagicMock()
        smtp_class.return_value.__enter__.return_value = smtp

        send_digest_email(
            self.digest.subject,
            render_digest_email(self.digest),
            settings=settings(),
        )

        smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user", "password")
        smtp.send_message.assert_called_once()

    @patch("app.emailer.smtp.smtplib.SMTP")
    def test_explains_smtp_disconnect_during_authentication(self, smtp_class) -> None:
        smtp = MagicMock()
        smtp_class.return_value.__enter__.return_value = smtp
        smtp.login.side_effect = smtplib.SMTPServerDisconnected(
            "Connection unexpectedly closed"
        )

        with self.assertRaisesRegex(ConnectionError, "16-character Google app password"):
            send_digest_email(
                self.digest.subject,
                render_digest_email(self.digest),
                settings=settings(),
            )
        smtp.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    email_sender: str | None
    email_recipient: str | None

    def require_deepseek(self) -> tuple[str, str, str]:
        if not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required to generate a digest")
        return (
            self.deepseek_api_key,
            self.deepseek_base_url,
            self.deepseek_model,
        )

    def require_smtp(self) -> tuple[str, int, str, str, str, str]:
        host = self.smtp_host
        username = self.smtp_username
        password = self.smtp_password
        sender = self.email_sender
        recipient = self.email_recipient
        if not host or not username or not password or not sender or not recipient:
            raise ValueError(
                "SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, "
                "EMAIL_SENDER, and EMAIL_RECIPIENT are required to send a digest"
            )
        return (
            host,
            self.smtp_port,
            username,
            password,
            sender,
            recipient,
        )


def get_settings() -> Settings:
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise ValueError("SMTP_PORT must be an integer") from error
    if not 1 <= smtp_port <= 65535:
        raise ValueError("SMTP_PORT must be between 1 and 65535")

    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://youtube_digest:local_dev_password"
            "@localhost:5432/youtube_digest",
        ),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=smtp_port,
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        email_sender=os.getenv("EMAIL_SENDER") or None,
        email_recipient=os.getenv("EMAIL_RECIPIENT") or None,
    )

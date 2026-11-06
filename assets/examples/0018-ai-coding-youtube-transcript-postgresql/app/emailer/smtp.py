from __future__ import annotations

import html
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.agent.service import GeneratedDigest
from app.config import Settings, get_settings


@dataclass(frozen=True)
class RenderedEmail:
    text_body: str
    html_body: str


def render_digest_email(digest: GeneratedDigest) -> RenderedEmail:
    text_parts = [digest.subject, ""]
    html_parts = [
        "<!doctype html>",
        '<html lang="en"><body>',
        f"<h1>{html.escape(digest.subject)}</h1>",
    ]
    for entry in digest.entries:
        text_parts.extend((entry.title, entry.summary, entry.url, ""))
        html_parts.append("<article>")
        html_parts.append(
            f'<h2><a href="{html.escape(entry.url, quote=True)}">'
            f"{html.escape(entry.title)}</a></h2>"
        )
        html_parts.append(f"<p>{html.escape(entry.summary)}</p>")
        html_parts.append("</article>")
    html_parts.append("View the videos using the links above.")
    html_parts.append("")
    html_parts.extend(("</body></html>",))
    return RenderedEmail(
        text_body="\n".join(text_parts),
        html_body="\n".join(html_parts),
    )


def create_message(
    subject: str,
    rendered: RenderedEmail,
    *,
    settings: Settings,
) -> EmailMessage:
    _, _, _, _, sender, recipient = settings.require_smtp()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(rendered.text_body)
    message.add_alternative(rendered.html_body, subtype="html")
    return message


def send_digest_email(
    subject: str,
    rendered: RenderedEmail,
    *,
    settings: Settings | None = None,
) -> None:
    active_settings = settings or get_settings()
    host, port, username, password, _, _ = active_settings.require_smtp()
    message = create_message(subject, rendered, settings=active_settings)
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        try:
            client.login(username, password)
        except smtplib.SMTPServerDisconnected as error:
            raise ConnectionError(
                "SMTP server disconnected during authentication. For Gmail, "
                "use your full Gmail address and a 16-character Google app "
                "password (remove any display spaces); do not use your regular "
                "account password."
            ) from error
        client.send_message(message)

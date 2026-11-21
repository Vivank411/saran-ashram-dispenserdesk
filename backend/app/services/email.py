"""Outgoing email for sign-in codes: Gmail via Apps Script (free), Brevo HTTP API, plain SMTP, or console (development)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from ..config import Settings
from ..util import AppError

log = logging.getLogger("dispensary.email")


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"


def send_email(settings: Settings, to: str, subject: str, text: str) -> None:
    try:
        if settings.email_provider == "gmail_script":
            # Apps Script answers the POST with a redirect to the result; the email is already sent by then.
            r = httpx.post(settings.gmail_script_url, timeout=30, follow_redirects=True,
                           json={"token": settings.gmail_script_token, "to": to, "subject": subject, "text": text,
                                 "name": settings.email_from_name})
            r.raise_for_status()
            try:
                ok = r.json().get("ok") is True
            except ValueError:
                ok = False
            if not ok:
                raise httpx.HTTPError(f"Apps Script refused: {r.text[:200]}")
        elif settings.email_provider == "brevo":
            r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=15,
                           headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
                           json={"sender": {"email": settings.email_from, "name": settings.email_from_name},
                                 "to": [{"email": to}], "subject": subject, "textContent": text})
            r.raise_for_status()
        elif settings.email_provider == "smtp":
            msg = EmailMessage()
            msg["From"] = f"{settings.email_from_name} <{settings.email_from}>"
            msg["To"], msg["Subject"] = to, subject
            msg.set_content(text)
            ctx = ssl.create_default_context()
            if settings.smtp_ssl:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx, timeout=15) as s:
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                    s.starttls(context=ctx)
                    s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
        else:
            # Development only (refused in production by config validation).
            log.warning("EMAIL to %s · %s · %s", mask_email(to), subject, text)
    except (httpx.HTTPError, smtplib.SMTPException, OSError) as exc:
        log.error("Email to %s failed: %s", mask_email(to), exc)
        raise AppError("EMAIL_FAILED", "The sign-in code could not be emailed. Please try again shortly.", 502) from exc

"""Email saliente por SMTP (biblioteca estándar). Requiere permiso email.send y configuración SMTP_*."""
from __future__ import annotations

import os
import smtplib
import sqlite3
from email.message import EmailMessage

from .. import permissions
from ..actors import Actor
from . import IntegrationError, IntegrationInfo, IntegrationNotConfigured


def info() -> IntegrationInfo:
    ok = all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"))
    return IntegrationInfo("email_smtp", ok, "email.send (aprobación humana por defecto)",
                           "Configura SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD y SMTP_FROM.")


def send(conn: sqlite3.Connection, actor: Actor, to: str, subject: str, body: str) -> None:
    if not info().configured:
        raise IntegrationNotConfigured(info().setup)
    permissions.authorize(conn, actor, "email", "send", to)
    msg = EmailMessage()
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise IntegrationError(f"fallo SMTP: {type(e).__name__}") from e

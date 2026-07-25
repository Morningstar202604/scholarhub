"""Email sending abstraction.

The app never talks to an SMTP server or a transactional API directly —
it goes through ``EmailSender``. The default ``ConsoleEmailSender`` logs
the message to stdout, which is fine for dev and tests. To go live, set
``SCHOLARHUB_EMAIL_BACKEND=smtp`` and configure SMTP credentials (see
``Settings.email_*`` in ``app/core/config.py``).

Mailgun / SendGrid / SES / Postmark all expose an SMTP relay, so the
SMTP backend covers every mainstream provider without per-vendor code.
A custom backend (e.g. direct Mailgun API) only needs to implement the
``EmailSender`` Protocol and be wired in ``get_email_sender``.

Why a Protocol instead of an ABC: ``Protocol`` is structural typing —
tests substitute a fake without inheriting. The runtime lookup in
``get_email_sender`` stays tiny.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("scholarhub.email")


@runtime_checkable
class EmailSender(Protocol):
    """Send a transactional email to one recipient."""

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> None: ...


class ConsoleEmailSender:
    """Dev / test sender — writes the message to the log stream.

    No network, no credentials, no flakiness. Tests can introspect sent
    mail by capturing the ``caplog`` fixture or by replacing
    ``get_email_sender()`` with a fake.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> None:
        logger.info(
            "email_sent_console",
            to=to,
            subject=subject,
            body_preview=body[:200],
        )


class SMTPEmailSender:
    """SMTP relay sender. Covers Mailgun / SendGrid / SES / Postmark / SMTP.

    Each call opens a fresh SMTP connection (no pooling). Transactional
    volume on this app is low (account verification, password reset),
    so pooling would be premature. If volume grows, add a connection
    pool here without touching the caller.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_addr: str,
        use_tls: bool = True,
        starttls: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._use_tls = use_tls
        self._starttls = starttls

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> None:
        msg = EmailMessage()
        msg["From"] = self._from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if html is not None:
            msg.add_alternative(html, subtype="html")

        # smtplib is sync; offload to a thread via asyncio.to_thread in
        # the caller would be cleaner, but volume is tiny so blocking
        # the event loop for one SMTP round-trip is acceptable. If a
        # caller needs strict non-blocking, await asyncio.to_thread(...)
        # around send_message.
        with smtplib.SMTP(self._host, self._port) as client:
            if self._starttls:
                client.starttls()
            if self._username and self._password:
                client.login(self._username, self._password)
            client.send_message(msg)
        logger.info("email_sent_smtp", to=to, subject=subject)


_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    """Return the configured sender. Constructed lazily on first call so
    that test overrides via ``app.core.email._sender = ...`` work."""
    global _sender
    if _sender is not None:
        return _sender

    if settings.email_backend == "console" or settings.environment == "test":
        _sender = ConsoleEmailSender()
        return _sender

    if settings.email_backend == "smtp":
        if not settings.email_smtp_host or not settings.email_from_address:
            # Misconfiguration — fall back to console so the request still
            # succeeds. The operator should see the warning.
            logger.warning(
                "email_smtp_misconfigured_fallback_to_console",
                reason="missing host or from_address",
            )
            _sender = ConsoleEmailSender()
            return _sender

        _sender = SMTPEmailSender(
            host=settings.email_smtp_host,
            port=settings.email_smtp_port,
            username=settings.email_smtp_username,
            password=settings.email_smtp_password,
            from_addr=settings.email_from_address,
            use_tls=settings.email_smtp_use_tls,
            starttls=settings.email_smtp_starttls,
        )
        return _sender

    # Unknown backend — fall back to console.
    logger.warning("email_unknown_backend_fallback_to_console", backend=settings.email_backend)
    _sender = ConsoleEmailSender()
    return _sender


def reset_email_sender() -> None:
    """Test helper: clear the cached sender so the next ``get_email_sender()``
    call re-reads settings. Tests should call this in teardown if they
    swapped the sender."""
    global _sender
    _sender = None

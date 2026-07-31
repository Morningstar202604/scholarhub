"""CAPTCHA verification hook.

Goal: a pluggable point where any provider (Cloudflare Turnstile,
hCaptcha, reCAPTCHA) can verify a token. We do **not** bundle a
specific provider's SDK by default — operators wire up their own
verifier via the ``captcha_verifier`` setting (a dotted path to a
``async def verify(token: str, *, remote_ip: str | None) -> bool``
callable). When unset the hook is a no-op so the registration flow
keeps working in dev / CI without external dependencies.

The hook is invoked by ``require_captcha_for_registration`` below,
which is consumed by the registration endpoint when
``settings.captcha_required_for_registration`` is True.
"""

from __future__ import annotations

import importlib
from typing import Protocol, runtime_checkable

from fastapi import HTTPException, Request, status

from app.core.config import settings


@runtime_checkable
class CaptchaVerifier(Protocol):
    """The contract operators must satisfy when wiring up a provider."""

    async def verify(self, token: str, *, remote_ip: str | None) -> bool: ...


class _AlwaysPassVerifier:
    """Default dev/CI verifier. Logs a warning at first call."""

    _warned: bool = False

    async def verify(self, token: str, *, remote_ip: str | None) -> bool:
        if not _AlwaysPassVerifier._warned:
            _AlwaysPassVerifier._warned = True
            # Lazy import — logging module is heavy and we want this
            # to import cleanly even before configure_logging() runs.
            from app.core.logging import get_logger

            get_logger("scholarhub.captcha").warning(
                "captcha_disabled_using_passthrough",
                provider="dev-passthrough",
            )
        return True


def _load_verifier() -> CaptchaVerifier:
    """Resolve the configured verifier or return the passthrough default."""
    dotted = settings.captcha_verifier
    if not dotted:
        return _AlwaysPassVerifier()
    module_name, _, attr = dotted.rpartition(".")
    if not module_name:
        raise RuntimeError(f"Invalid captcha_verifier path: {dotted!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(f"captcha_verifier {dotted!r} could not be imported: {exc}") from exc
    obj = getattr(module, attr, None)
    if obj is None:
        raise RuntimeError(f"captcha_verifier {dotted!r} does not resolve to an attribute")
    if not callable(obj):
        raise RuntimeError(
            f"captcha_verifier {dotted!r} is not callable; expected a "
            "verifier instance or factory returning one"
        )
    # Allow either an instance (callable with __call__) or a factory.
    if isinstance(obj, type):
        return obj()  # type: ignore[no-any-return]
    if callable(obj):
        result = obj()
        if isinstance(result, CaptchaVerifier):
            return result
    raise RuntimeError(f"captcha_verifier {dotted!r} must return a CaptchaVerifier")


async def verify_captcha_token(request: Request, token: str | None) -> None:
    """Validate the CAPTCHA token against the configured verifier.

    Call directly from the endpoint body (NOT a Depends), so the
    request body has already been parsed and we don't double-deserialize.

    Raises ``HTTPException(400)`` when the token is missing or fails
    verification. Returns ``None`` when verification succeeds or
    when the policy is off.
    """
    if not settings.captcha_required_for_registration:
        return
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA token required",
        )
    verifier = _load_verifier()
    remote_ip = request.client.host if request.client else None
    ok = await verifier.verify(token, remote_ip=remote_ip)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed",
        )


# Backwards-compatible alias kept so existing call sites / tests do
# not have to change. Resolves a real dependency by declaring no
# FastAPI-injected parameters (so the framework won't try to
# deserialize anything else from the request).
async def require_captcha_for_registration() -> None:
    """No-op dependency. The real check happens via verify_captcha_token."""
    return None

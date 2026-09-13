"""Turnstile captcha verifier: fail-closed semantics + success path."""

from __future__ import annotations

from app.core.captcha import TurnstileCaptchaVerifier


def test_verifier_requires_secret_key():
    try:
        TurnstileCaptchaVerifier("")
    except ValueError:
        return
    raise AssertionError("empty secret key must be rejected")


async def test_verifier_rejects_empty_token_without_network():
    verifier = TurnstileCaptchaVerifier("test-secret")
    assert await verifier.verify("", remote_ip="1.2.3.4") is False

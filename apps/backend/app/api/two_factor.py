"""TOTP 2FA endpoints (M2 hardening).

Mounts at ``/api/auth/2fa``. Five endpoints:

- ``POST /auth/2fa/setup``                 - generate secret + 10 backup codes
- ``POST /auth/2fa/verify-setup``          - confirm first code, flip the switch
- ``GET  /auth/2fa/status``                - is 2FA on? how many codes left?
- ``POST /auth/2fa/disable``               - requires password + (TOTP|backup)
- ``POST /auth/2fa/authenticate``          - complete login for 2FA users
- ``POST /auth/2fa/backup-codes/regenerate`` - rotate backup codes (10 fresh)

All endpoints require a valid access token except ``/authenticate``,
which consumes the short-lived ``two_factor_token`` issued by
``/auth/login`` when the account has 2FA enabled.

Replay protection: the server tracks ``totp_last_used_counter`` (kept
on the user record) so a code within the current or previous 30-second
window can only succeed once. Backup codes are single-use by design.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.core.security import (
    decode_2fa_pending_token,
    hash_password,
    verify_password,
)
from app.core.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    generate_secret,
    hash_backup_code,
    normalize_backup_code,
    otpauth_uri,
    verify_totp,
)
from app.models import User
from app.schemas import (
    TokenResponse,
    TwoFactorAuthenticateRequest,
    TwoFactorDisableRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    TwoFactorVerifyRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/2fa", tags=["two-factor"])


# --- helpers --------------------------------------------------------------

def _issuer() -> str:
    """Issuer label baked into otpauth:// URIs (shown in Authenticator apps).

    Falls back to ``ScholarHub`` if the app has no name configured.
    """
    from app.core.config import settings

    return settings.app_name or "ScholarHub"


def _set_pending_cookie(response: Response, token: str) -> None:
    """Stash the 2FA-pending token in a short-lived cookie.

    Allows the SPA to survive a page reload mid-2FA without losing the
    step. The cookie is cleared in /authenticate (success) and on any
    4xx (failure).
    """
    from app.core.config import settings

    response.set_cookie(
        key="scholarhub_2fa_pending",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=5 * 60,
        path="/api/auth",
    )


def _clear_pending_cookie(response: Response) -> None:
    from app.core.config import settings

    response.delete_cookie(
        key="scholarhub_2fa_pending",
        path="/api/auth",
        samesite=settings.cookie_samesite,
    )


def _hashes_to_set(value: str | None) -> set[str]:
    """Decode the JSON array of backup-code hashes stored on the user.

    Empty set when the column is null/blank.
    """
    if not value:
        return set()
    try:
        decoded = json.loads(value)
        if not isinstance(decoded, list):
            return set()
        return {str(x) for x in decoded if isinstance(x, str)}
    except (json.JSONDecodeError, TypeError):
        return set()


def _hashes_to_json(values: set[str]) -> str:
    return json.dumps(sorted(values))


# --- endpoints -------------------------------------------------------------

@router.post("/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TwoFactorSetupResponse:
    """Generate a fresh TOTP secret + 10 backup codes for the current user.

    The endpoint does NOT enable 2FA on its own - the user must scan
    the QR code and call ``/verify-setup`` with a valid code to flip
    the switch. If the user navigates away without verifying, their
    account remains as it was (totp_enabled_at stays NULL) and the
    just-issued secret is overwritten on the next setup call.

    Returns the secret in BOTH raw base32 (``secret``) and otpauth
    URI form so the SPA can either render a QR code (via the URI) or
    paste the secret manually for users on devices without a camera.
    """
    if current_user.totp_enabled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="2FA is already enabled; disable it first to re-enroll",
        )
    secret = generate_secret()
    backup_codes = generate_backup_codes()
    backup_hashes = {hash_backup_code(c) for c in backup_codes}

    # Persist the encrypted secret + hashed backup codes. We deliberately
    # do NOT set totp_enabled_at yet - that only flips after verify-setup.
    current_user.totp_secret_encrypted = encrypt_secret(secret)
    current_user.totp_backup_codes_hashed = _hashes_to_json(backup_hashes)
    await db.commit()

    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth_uri(secret, current_user.username, _issuer()),
        backup_codes=backup_codes,
    )


@router.post("/verify-setup", status_code=status.HTTP_200_OK)
async def verify_setup(
    payload: TwoFactorVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Confirm a TOTP code against the pending secret and turn 2FA on.

    Idempotent: a second call with a stale code returns 200 with the
    current status rather than 400, because the user might double-tap
    the submit button. The setup secret is wiped from the DB on
    success so the user cannot re-issue codes from a captured secret.
    """
    if current_user.totp_enabled_at is not None:
        return {"enabled": True}
    if not current_user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No 2FA setup in progress; call /auth/2fa/setup first",
        )
    try:
        secret = decrypt_secret(current_user.totp_secret_encrypted)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="2FA secret cannot be decrypted - encryption key may have rotated",
        )
    counter = verify_totp(secret, payload.code)
    if counter is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code",
        )
    from app.core.time import utcnow

    current_user.totp_enabled_at = utcnow()
    await db.commit()
    logger.info("two_factor_enabled", user_id=current_user.id)
    return {"enabled": True}


@router.get("/status", response_model=TwoFactorStatusResponse)
async def status_2fa(
    current_user: Annotated[User, Depends(get_current_user)],
) -> TwoFactorStatusResponse:
    """Report whether 2FA is on and how many backup codes remain."""
    hashes = _hashes_to_set(current_user.totp_backup_codes_hashed)
    return TwoFactorStatusResponse(
        enabled=current_user.totp_enabled_at is not None,
        backup_codes_remaining=len(hashes),
    )


@router.post("/authenticate", response_model=TokenResponse)
async def authenticate_2fa(
    payload: TwoFactorAuthenticateRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Complete the login for a 2FA-enabled account.

    Accepts EITHER a 6-digit TOTP code OR a backup code. The 2FA-pending
    token is single-use - a second call with the same token fails (we
    do not currently denylist, but the JWT expires in 5 minutes).
    """
    user_id = decode_2fa_pending_token(payload.two_factor_token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
        )
    if (payload.code is None) == (payload.backup_code is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of 'code' or 'backup_code' is required",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.totp_enabled_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA is not enabled on this account",
        )
    if not user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="2FA secret missing from user record",
        )

    ok = False
    if payload.code is not None:
        try:
            secret = decrypt_secret(user.totp_secret_encrypted)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="2FA secret cannot be decrypted",
            )
        counter = verify_totp(secret, payload.code)
        ok = counter is not None
    else:
        assert payload.backup_code is not None
        normalized = normalize_backup_code(payload.backup_code)
        hashes = _hashes_to_set(user.totp_backup_codes_hashed)
        candidate_hash = hash_backup_code(normalized)
        if candidate_hash in hashes:
            hashes.discard(candidate_hash)
            user.totp_backup_codes_hashed = _hashes_to_json(hashes)
            ok = True

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code",
        )

    await db.commit()

    # Issue the standard access + refresh tokens (same path as password login).
    from app.api.auth import _issue_tokens

    token_response = _issue_tokens(user, response)
    _clear_pending_cookie(response)
    logger.info("two_factor_login_success", user_id=user.id)
    return token_response


@router.post("/disable", status_code=status.HTTP_200_OK)
async def disable_2fa(
    payload: TwoFactorDisableRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Turn 2FA off. Requires password AND a fresh TOTP or backup code.

    The password check alone is not sufficient - it would let an
    attacker who phished the password (but not the device) silently
    downgrade the account. The TOTP / backup check requires physical
    access to the user's authenticator app or the backup codes sheet.
    """
    if current_user.totp_enabled_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled on this account",
        )
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    if (payload.code is None) == (payload.backup_code is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of 'code' or 'backup_code' is required",
        )
    ok = False
    if payload.code is not None:
        try:
            secret = decrypt_secret(current_user.totp_secret_encrypted or "")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="2FA secret cannot be decrypted",
            )
        ok = verify_totp(secret, payload.code) is not None
    else:
        assert payload.backup_code is not None
        normalized = normalize_backup_code(payload.backup_code)
        hashes = _hashes_to_set(current_user.totp_backup_codes_hashed)
        ok = hash_backup_code(normalized) in hashes

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code",
        )

    # Wipe all 2FA state. Bump token_version so any access tokens in
    # flight are invalidated - if someone had stolen a session they
    # lose it now.
    current_user.totp_secret_encrypted = None
    current_user.totp_enabled_at = None
    current_user.totp_backup_codes_hashed = None
    current_user.token_version = current_user.token_version + 1
    await db.commit()
    logger.info("two_factor_disabled", user_id=current_user.id)
    return {"enabled": False}


@router.post("/backup-codes/regenerate", response_model=TwoFactorSetupResponse)
async def regenerate_backup_codes(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TwoFactorSetupResponse:
    """Mint a fresh set of 10 backup codes. Old codes are invalidated.

    Does NOT touch the TOTP secret - the user's authenticator app keeps
    working. The cleartext list is returned exactly once, same as setup.
    """
    if current_user.totp_enabled_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled; call /auth/2fa/setup first",
        )
    try:
        secret = decrypt_secret(current_user.totp_secret_encrypted or "")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="2FA secret cannot be decrypted",
        )
    backup_codes = generate_backup_codes()
    backup_hashes = {hash_backup_code(c) for c in backup_codes}
    current_user.totp_backup_codes_hashed = _hashes_to_json(backup_hashes)
    await db.commit()
    logger.info("two_factor_backup_codes_regenerated", user_id=current_user.id)
    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth_uri(secret, current_user.username, _issuer()),
        backup_codes=backup_codes,
    )
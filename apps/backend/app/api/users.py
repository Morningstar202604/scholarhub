"""User self-management endpoints.

Admin user management (list/create/delete) lives in ``app.api.admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.core.twofactor import (
    build_otpauth_uri,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_totp_code,
)
from app.models import User
from app.schemas import (
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorEnableResponse,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

logger = get_logger("scholarhub.users")


class ChangePasswordRequest(BaseModel):
    # Body, not query string: passwords must never appear in URLs
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Allow a user to update their own email / username / active flag.

    Email change resets ``is_email_verified`` to False and triggers a new
    verification email (best effort) so the user can re-verify.

    Disabling your own account is permitted — it's the closest thing to
    "delete me" we offer without data-loss risk; an admin can re-enable.
    """
    email_changed = payload.email is not None and payload.email != current_user.email
    if payload.email is not None:
        current_user.email = payload.email
    if email_changed:
        current_user.is_email_verified = False
    if payload.username is not None:
        current_user.username = payload.username
    if payload.is_active is not None:
        current_user.is_active = payload.is_active
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already taken in this tenant",
        ) from exc
    await db.refresh(current_user)

    if email_changed:
        try:
            from app.api.auth import _send_verification_email

            await _send_verification_email(current_user)
        except Exception:
            logger.warning(
                "post_email_change_verification_send_failed",
                user_id=current_user.id,
                exc_info=True,
            )

    return UserResponse.model_validate(current_user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change the current user's password; bumps token_version + rtv.

    Both counters are bumped so outstanding access AND refresh tokens
    are invalidated — the user must re-authenticate on every device.
    """
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect"
        )
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.token_version += 1
    current_user.refresh_token_version += 1
    await db.commit()


# --- Two-factor auth (TOTP) self-management ---
#
# Flow: POST /me/2fa/setup → scan QR → POST /me/2fa/enable {code}
#       → store recovery codes shown once in the response.
# Disable requires the account password, not just a live session.


@router.get("/me/2fa", response_model=TwoFactorStatusResponse)
async def two_factor_status(
    current_user: User = Depends(get_current_user),
) -> TwoFactorStatusResponse:
    return TwoFactorStatusResponse(
        enabled=current_user.two_factor_enabled,
        backup_codes_remaining=len(current_user.two_factor_recovery_codes or []),
    )


@router.post("/me/2fa/setup", response_model=TwoFactorSetupResponse)
async def two_factor_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorSetupResponse:
    """Generate (or regenerate) a TOTP secret. 2FA stays OFF until the
    user proves possession of the authenticator via /me/2fa/enable.

    Re-calling before enable simply rotates the pending secret — safe,
    because nothing depends on it yet.
    """
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled",
        )
    secret = generate_totp_secret()
    current_user.two_factor_secret = secret
    await db.commit()
    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=build_otpauth_uri(secret, current_user.email),
    )


@router.post("/me/2fa/enable", response_model=TwoFactorEnableResponse)
async def two_factor_enable(
    payload: TwoFactorEnableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorEnableResponse:
    """Confirm setup with a valid TOTP code; activates 2FA and returns
    single-use recovery codes (shown exactly once — only hashes stored)."""
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled",
        )
    if current_user.two_factor_secret is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run two-factor setup first",
        )
    if not verify_totp_code(current_user.two_factor_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid two-factor code",
        )
    codes = generate_recovery_codes()
    current_user.two_factor_enabled = True
    current_user.two_factor_recovery_codes = [hash_recovery_code(c) for c in codes]
    await db.commit()
    logger.info("two_factor_enabled", user_id=current_user.id)
    return TwoFactorEnableResponse(recovery_codes=codes)


@router.post("/me/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(
    payload: TwoFactorDisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disable 2FA. Requires the account password so a hijacked browser
    session alone cannot strip the second factor."""
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled",
        )
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        )
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.two_factor_recovery_codes = None
    # Deliberately NOT bumping token_version: outstanding pending tokens
    # are already dead (login/2fa rejects users with 2FA off), so a bump
    # would only log the user out of their own current session for nothing.
    await db.commit()
    logger.info("two_factor_disabled", user_id=current_user.id)

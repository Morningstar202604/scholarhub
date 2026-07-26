"""Authentication endpoints: register, login, refresh, logout, me,
email verification, password reset.

JWT-based: access token (short-lived) + refresh token (long-lived in
httpOnly cookie). ``token_version`` on the User row invalidates all
outstanding access tokens on logout/password change. ``refresh_token_version``
independently rotates refresh tokens: each ``/auth/refresh`` call bumps
it, so the consumed refresh token (and any older ones) become invalid
without affecting access tokens or other devices.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, get_current_user, require_tenant_id
from app.core.captcha import verify_captcha_token
from app.core.config import settings
from app.core.db import get_db
from app.core.email import get_email_sender
from app.core.logging import get_logger
from app.core.schemas import MessageResponse
from app.core.security import (
    create_2fa_pending_token,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    refresh_token_version_matches,
    token_version_matches,
    verify_password,
)
from app.core.tokens import (
    RESET_PASSWORD_TOKEN_TYPE,
    VERIFY_EMAIL_TOKEN_TYPE,
    create_email_verification_token,
    create_password_reset_token,
    decode_token,
)
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    ORCIDUpdateRequest,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    VerifyEmailRequest,
)

# Anti-enumeration: same body returned whether registration succeeded
# or hit a duplicate-email/username collision.
_REGISTER_DUPLICATE_MESSAGE = (
    "If the email is not yet registered, a verification email has been sent."
)

router = APIRouter(prefix="/auth", tags=["auth"])

logger = get_logger("scholarhub.auth")

_REFRESH_COOKIE_KEY = settings.refresh_token_cookie_name


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the refresh token as an HttpOnly cookie scoped to /api/auth."""
    response.set_cookie(
        key=_REFRESH_COOKIE_KEY,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE_KEY,
        path="/api/auth",
        samesite=settings.cookie_samesite,
    )


def _extract_refresh_token(request: Request, body_token: str | None) -> str | None:
    """Read refresh token from cookie first (HttpOnly, XSS-safe), then body."""
    return request.cookies.get(_REFRESH_COOKIE_KEY) or body_token


@router.post(
    "/register",
    response_model=TokenResponse | MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    response: Response,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse | MessageResponse:
    """Register a new user under the current tenant.

    Anti-enumeration: a duplicate email/username collapses to the same 201
    response as a successful registration, but WITHOUT issuing tokens. The
    owner of an existing matching email is notified of the attempt (best
    effort when SMTP is configured) so they can act on it; the caller
    cannot tell whether the registration succeeded.
    """
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context not resolved",
        )
    # Verify CAPTCHA token when the deployment has the policy on.
    # When off this is a cheap no-op (settings check inside).
    await verify_captcha_token(request, payload.captcha_token)
    user = User(
        tenant_id=tenant_id,
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_admin=False,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Duplicate email or username — collapse to the same 201 response as
        # a successful registration so the caller cannot enumerate accounts.
        # No token is issued (anti-takeover) and no second user is created.
        await db.rollback()
        await _notify_duplicate_registration(db, payload.email, payload.username)
        return MessageResponse(message=_REGISTER_DUPLICATE_MESSAGE)
    await db.refresh(user)

    # Fire-and-forget verification email. Failure is logged but does not
    # fail registration — the user can request a resend via /resend-verification.
    try:
        await _send_verification_email(user)
    except Exception:
        logger.warning("verification_email_send_failed", user_id=user.id, exc_info=True)

    return _issue_tokens(user, response)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate and issue tokens."""
    # User.username uniqueness is (tenant_id, username) — a query without
    # the tenant filter could match a user from another tenant.
    tenant_id = require_tenant_id()
    result = await db.execute(
        select(User).where(
            User.username == payload.username,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )

    # M2 2FA: if the account has TOTP enabled, the password step alone is
    # NOT enough to issue tokens. Return a short-lived 2FA-pending token
    # that the client redeems via POST /auth/2fa/authenticate. Tokens are
    # empty strings in this branch so a careless client that ignores the
    # requires_2fa flag still cannot use them as a bearer.
    if user.totp_enabled_at is not None:
        pending = create_2fa_pending_token(user.id)
        return TokenResponse(
            access_token="",
            refresh_token="",
            user_id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            requires_2fa=True,
            two_factor_token=pending,
        )

    return _issue_tokens(user, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a refresh token for a fresh access + refresh token pair.

    Refresh token rotation: the consumed refresh token's ``rtv`` is
    checked against ``User.refresh_token_version``; if it matches, the
    counter is bumped before the new token pair is issued, so the same
    refresh token cannot be replayed (and any older refresh tokens
    for this user are also invalidated). Access tokens are unaffected.
    """
    body_token = payload.refresh_token if payload else None
    raw_token = _extract_refresh_token(request, body_token)
    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    decoded = decode_refresh_token(raw_token)
    if decoded is None or "sub" not in decoded:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    try:
        user_id = int(decoded["sub"])
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    result = await db.execute(
        select(User)
        .where(
            User.id == user_id,
            # Reject refresh tokens whose owner lives in another tenant —
            # without this, a token minted in tenant A would still refresh
            # against tenant B's deployment.
            User.tenant_id == require_tenant_id(),
        )
        # Row lock serializes concurrent refresh attempts: the first commit
        # bumps refresh_token_version, the second reader sees the new value
        # and fails the rtv check.
        .with_for_update()
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    # token_version check catches logout / password change.
    if not token_version_matches(decoded, user.token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    # rtv check enforces rotation — a replayed refresh token is refused.
    if not refresh_token_version_matches(decoded, user.refresh_token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been rotated"
        )

    # Bump refresh_token_version BEFORE issuing the new pair so the old
    # refresh token (and any other outstanding ones) cannot be replayed.
    user.refresh_token_version += 1
    await db.commit()
    await db.refresh(user)

    return _issue_tokens(user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Bump token_version + refresh_token_version to invalidate all
    outstanding access AND refresh tokens, then clear the cookie."""
    current_user.token_version += 1
    current_user.refresh_token_version += 1
    await db.commit()
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me/orcid", response_model=UserResponse)
async def update_my_orcid(
    payload: ORCIDUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Set or clear the authenticated user's ORCID iD.

    Body: ``{"orcid": "0000-0002-1825-0097"}`` to set, ``{"orcid": ""}``
    to clear, or omit the field (``{}``) to leave unchanged.
    The Pydantic validator canonicalises the input; we only persist
    what the schema accepted.
    """
    current_user.orcid = payload.orcid  # may be None
    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke every outstanding token for the caller.

    Bumps both ``token_version`` (kills access tokens) and
    ``refresh_token_version`` (kills refresh tokens) so even a stolen
    refresh token already in flight cannot be used.

    After this endpoint returns, the user must log in again — but
    doing so on this device still works, because login issues a
    fresh token pair.
    """
    current_user.token_version += 1
    current_user.refresh_token_version += 1
    await db.commit()
    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _issue_tokens(user: User, response: Response) -> TokenResponse:
    """Helper: build access+refresh tokens and set the refresh cookie.

    Access token carries ``token_version`` (invalidated on logout /
    password change). Refresh token additionally carries ``rtv``
    (refresh_token_version) — a separate counter bumped on each refresh
    so refresh rotation does not log out other devices.
    """
    base_claims = {"sub": str(user.id), "token_version": user.token_version}
    access_token = create_access_token(base_claims)
    # Refresh token gets its own version claim so it can be rotated
    # independently of the access token.
    refresh_claims = {**base_claims, "rtv": user.refresh_token_version}
    refresh_token = create_refresh_token(refresh_claims)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
    )


# --- Email verification + password reset ---


def _verify_link(token: str) -> str:
    """Build the verify-email deep link for the SPA to consume."""
    base = settings.frontend_base_url.rstrip("/") if settings.frontend_base_url else ""
    return f"{base}/verify-email?token={token}"


def _reset_link(token: str) -> str:
    """Build the password-reset deep link for the SPA to consume."""
    base = settings.frontend_base_url.rstrip("/") if settings.frontend_base_url else ""
    return f"{base}/reset-password?token={token}"


async def _send_verification_email(user: User) -> None:
    """Send the verify-email message via the configured sender."""
    token = create_email_verification_token(user.id, user.token_version)
    link = _verify_link(token)
    body = (
        f"Welcome to ScholarHUB, {user.username}.\n\n"
        f"Verify your email by visiting:\n  {link}\n\n"
        f"This link expires in {settings.email_verification_expire_hours} hours.\n"
        f"If you did not create an account, ignore this email.\n"
    )
    await get_email_sender().send(
        to=user.email,
        subject="Verify your ScholarHUB email",
        body=body,
    )


async def _send_password_reset_email(user: User) -> None:
    """Send the password-reset message via the configured sender."""
    token = create_password_reset_token(user.id, user.token_version)
    link = _reset_link(token)
    body = (
        f"Reset your ScholarHUB password by visiting:\n  {link}\n\n"
        f"This link expires in {settings.password_reset_expire_minutes} minutes.\n"
        f"If you did not request a reset, ignore this email.\n"
    )
    await get_email_sender().send(
        to=user.email,
        subject="Reset your ScholarHUB password",
        body=body,
    )


async def _notify_duplicate_registration(
    db: AsyncSession, attempted_email: str, attempted_username: str
) -> None:
    """Best-effort: warn the owner of an existing matching account that
    someone tried to register with their email/username.

    Failures are logged but never surface to the caller — the caller always
    sees the same 201 to preserve the anti-enumeration contract.
    """
    # Scope to the current tenant so a duplicate attempt in tenant A does
    # not surface the email of a user in tenant B.
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return
    result = await db.execute(
        select(User).where(
            (User.email == attempted_email) | (User.username == attempted_username),
            User.tenant_id == tenant_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return
    body = (
        "Someone attempted to register a ScholarHUB account using your"
        " email address.\n\n"
        "If this was you, you can ignore this email; your existing account"
        " is unaffected.\n"
        "If you did not initiate this registration, please contact your"
        " administrator.\n"
    )
    try:
        await get_email_sender().send(
            to=existing.email,
            subject="ScholarHUB registration attempt",
            body=body,
        )
    except Exception:
        logger.warning("duplicate_registration_email_send_failed", exc_info=True)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Exchange a verification token for ``is_email_verified=True``."""
    decoded = decode_token(payload.token, expected_type=VERIFY_EMAIL_TOKEN_TYPE)
    if decoded is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    try:
        user_id = int(decoded["sub"])
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        ) from exc

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == require_tenant_id(),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )
    # token_version check ties the token to the account state at issue
    # time — bumping it (logout, password change, admin disable) invalidates
    # outstanding verification tokens too.
    if not token_version_matches(decoded, user.token_version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is no longer valid",
        )
    if user.is_email_verified:
        return MessageResponse(message="Email already verified")
    user.is_email_verified = True
    await db.commit()
    return MessageResponse(message="Email verified")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def resend_verification(
    payload: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Re-send the verification email. Always returns 200 (don't leak
    whether an account exists for the address)."""
    tenant_id = get_current_tenant_id()
    stmt = select(User).where(User.email == payload.email)
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or user.is_email_verified:
        # Pretend success to avoid account enumeration.
        return MessageResponse(message="If the account exists, a verification email was sent")
    try:
        await _send_verification_email(user)
    except Exception:
        logger.warning("resend_verification_failed", user_id=user.id, exc_info=True)
    return MessageResponse(message="If the account exists, a verification email was sent")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Trigger a password-reset email. Always returns 200 (don't leak
    whether an account exists for the address)."""
    tenant_id = get_current_tenant_id()
    stmt = select(User).where(User.email == payload.email)
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return MessageResponse(message="If the account exists, a reset email was sent")
    try:
        await _send_password_reset_email(user)
    except Exception:
        logger.warning("password_reset_email_failed", user_id=user.id, exc_info=True)
    return MessageResponse(message="If the account exists, a reset email was sent")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Exchange a reset token for a new password. Bumps ``token_version``
    so all previously-issued access + refresh tokens are invalidated."""
    decoded = decode_token(payload.token, expected_type=RESET_PASSWORD_TOKEN_TYPE)
    if decoded is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    try:
        user_id = int(decoded["sub"])
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token",
        ) from exc

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == require_tenant_id(),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token",
        )
    if not token_version_matches(decoded, user.token_version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is no longer valid",
        )
    user.hashed_password = hash_password(payload.new_password)
    # Bumping token_version invalidates outstanding access tokens AND any
    # other outstanding reset tokens for this user; bumping refresh_token_version
    # also invalidates outstanding refresh tokens so the user must log in again.
    user.token_version += 1
    user.refresh_token_version += 1
    await db.commit()
    return MessageResponse(message="Password reset successful")

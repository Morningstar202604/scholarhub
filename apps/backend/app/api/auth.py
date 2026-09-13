"""Authentication endpoints: register, login, refresh, logout, me,
email verification, password reset.

JWT-based: access token (short-lived) + refresh token (long-lived in
httpOnly cookie). ``token_version`` on the User row invalidates all
outstanding access tokens on logout/password change.

Refresh tokens use a JTI-based denylist for fine-grained per-token
revocation: each ``/auth/refresh`` adds the consumed token's ``jti``
to the denylist, so the same refresh token cannot be replayed without
affecting other devices. ``refresh_token_version`` is reserved for
bulk revocation (revoke-all, password change).
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
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    refresh_token_version_matches,
    token_version_matches,
    verify_password,
)
from app.core.token_denylist import get_denylist
from app.core.tokens import (
    RESET_PASSWORD_TOKEN_TYPE,
    VERIFY_EMAIL_TOKEN_TYPE,
    create_email_verification_token,
    create_password_reset_token,
    decode_token,
    random_jti,
)
from app.core.twofactor import (
    consume_recovery_code,
    create_two_factor_pending_token,
    decode_two_factor_pending_token,
    verify_totp_code,
)
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    ORCIDUpdateRequest,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    TwoFactorLoginRequest,
    TwoFactorRequiredResponse,
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
    # CAPTCHA check if the policy is enabled.
    await verify_captcha_token(request, payload.captcha_token)

    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context not resolved",
        )
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


@router.post(
    "/login",
    response_model=TokenResponse | TwoFactorRequiredResponse,
    responses={
        200: {
            "description": (
                "Tokens on success; or `{two_factor_required: true, "
                "pending_token}` when the account has 2FA enabled."
            )
        }
    },
)
async def login(
    request: Request,
    response: Response,
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse | TwoFactorRequiredResponse:
    """Authenticate and issue tokens.

    When the account has TOTP 2FA enabled, no tokens are issued here —
    the response carries a short-lived ``pending_token`` that must be
    exchanged with a valid code at ``/auth/login/2fa``.
    """
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

    if user.two_factor_enabled:
        # Password OK, but the second factor is outstanding. Issue a
        # 5-minute pending token instead of real credentials.
        return TwoFactorRequiredResponse(
            pending_token=create_two_factor_pending_token(user.id, user.token_version)
        )

    return _issue_tokens(user, response)


@router.post("/login/2fa", response_model=TokenResponse)
async def login_two_factor(
    response: Response,
    payload: TwoFactorLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Second step of 2FA login: pending token + TOTP/recovery code → tokens.

    Accepts either a 6-digit TOTP code or an unused xxxx-xxxx-xxxx
    recovery code (which is consumed on success).
    """
    claims = decode_two_factor_pending_token(payload.pending_token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired two-factor session; log in again",
        )

    tenant_id = require_tenant_id()
    result = await db.execute(
        select(User).where(
            User.id == int(claims["sub"]),
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    # token_version check: a password change / logout-everywhere after
    # the pending token was issued must invalidate it too.
    if (
        user is None
        or not user.is_active
        or not user.two_factor_enabled
        or user.two_factor_secret is None
        or claims.get("token_version") != user.token_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired two-factor session; log in again",
        )

    if verify_totp_code(user.two_factor_secret, payload.code):
        return _issue_tokens(user, response)

    # Fall back to recovery codes (single use).
    remaining = consume_recovery_code(user.two_factor_recovery_codes or [], payload.code)
    if remaining is not None:
        user.two_factor_recovery_codes = remaining
        await db.commit()
        logger.info("two_factor_recovery_code_used", user_id=user.id, remaining=len(remaining))
        return _issue_tokens(user, response)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid two-factor code",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a refresh token for a fresh access + refresh token pair.

    Per-token revocation via JTI denylist: the consumed refresh token's
    ``jti`` is added to the denylist so it cannot be replayed. The
    ``rtv`` (refresh_token_version) is NOT bumped here — other devices'
    refresh tokens remain valid (fine-grained). Bulk revocation
    (password change, revoke-all) still bumps ``rtv``.
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

    # Per-token denylist check — a previously-consumed refresh token
    # (e.g. rotated or logged out) must be rejected.
    denylist = await get_denylist()
    token_jti = decoded.get("jti")
    if token_jti and await denylist.is_denied(str(token_jti)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
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
        # Row lock serializes concurrent refresh attempts: the first caller
        # adds the JTI to the denylist and commits, the second caller sees
        # the denylist entry and fails.
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
    # rtv check enforces bulk revocation (revoke-all, password change).
    if not refresh_token_version_matches(decoded, user.refresh_token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been rotated"
        )

    # Per-token revocation: add the consumed token's JTI to the denylist
    # so it cannot be replayed. The new token pair gets a fresh JTI.
    if token_jti and "exp" in decoded:
        await denylist.add(str(token_jti), float(decoded["exp"]))

    # Commit releases the row lock. We do NOT bump refresh_token_version
    # here — the denylist handles per-token rotation so other devices'
    # refresh tokens are unaffected.
    await db.commit()
    await db.refresh(user)

    return _issue_tokens(user, response)


@router.post("/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Bump token_version + refresh_token_version to invalidate all
    outstanding access AND refresh tokens."""
    current_user.token_version += 1
    current_user.refresh_token_version += 1
    await db.commit()
    _clear_refresh_cookie(response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Log out the current session only (fine-grained).

    Adds the current refresh token's ``jti`` to the denylist so it
    cannot be replayed, and bumps ``token_version`` to invalidate the
    current access token. Other sessions' refresh tokens are unaffected
    — this is a per-session logout, not a logout-everywhere.

    For bulk revocation (all sessions), use ``/auth/revoke-all``.
    """
    # Denylist the current refresh token (per-session revocation).
    raw_token = _extract_refresh_token(request, None)
    if raw_token:
        decoded = decode_refresh_token(raw_token)
        if decoded and "jti" in decoded and "exp" in decoded:
            denylist = await get_denylist()
            await denylist.add(str(decoded["jti"]), float(decoded["exp"]))

    # Bump token_version to invalidate the current access token.
    # We do NOT bump refresh_token_version — the JTI denylist above
    # handles per-token refresh revocation, so other sessions survive.
    current_user.token_version += 1
    await db.commit()
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me/orcid", response_model=UserResponse)
async def patch_orcid(
    payload: ORCIDUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the current user's ORCID iD.

    Accepts ``{"orcid": "0000-0002-1825-0097"}`` (set),
    ``{"orcid": ""}`` (clear), or ``{}`` (no-op). The canonical
    ORCID iD (19-char hyphenated form) is stored on the User row.
    """
    # Check if the orcid field was explicitly provided in the request body.
    # payload.orcid is None both when the field is omitted (no-op) and when
    # empty string is sent (validator converts "" to None). Use
    # exclude_unset to distinguish the two cases.
    if "orcid" in payload.model_dump(exclude_unset=True):
        current_user.orcid = payload.orcid
        await db.commit()
        await db.refresh(current_user)
    return UserResponse.model_validate(current_user)


def _issue_tokens(user: User, response: Response) -> TokenResponse:
    """Helper: build access+refresh tokens and set the refresh cookie.

    Access token carries ``token_version`` (invalidated on logout /
    password change). Refresh token additionally carries ``rtv``
    (refresh_token_version) — a separate counter bumped on revoke-all
    so bulk revocation does not depend on the JTI denylist — and a
    unique ``jti`` (JWT ID) for per-token revocation via the denylist.
    """
    base_claims = {"sub": str(user.id), "token_version": user.token_version}
    access_token = create_access_token(base_claims)
    # Refresh token gets its own version claim so it can be rotated
    # independently of the access token, and a unique jti for the denylist.
    refresh_claims = {
        **base_claims,
        "rtv": user.refresh_token_version,
        "jti": random_jti(),
    }
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

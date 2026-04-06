# api/routers/auth/queries/auth.py
#
# Full authentication API:
#   POST /api/v1/auth/register
#   POST /api/v1/auth/token
#   POST /api/v1/auth/token/refresh
#   POST /api/v1/auth/logout
#   GET  /api/v1/auth/me
#   POST /api/v1/auth/password/reset
#   POST /api/v1/auth/password/reset/confirm
#   POST /api/v1/auth/password/change

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.utils import timezone as django_tz
from asgiref.sync import sync_to_async

from users.auth import get_current_user
from users.models import PasswordResetToken
from api.dependencies import get_request_context
from tenants.context import RequestContext

logger = logging.getLogger(__name__)

User = get_user_model()

router = APIRouter(prefix="/auth")

# ── Token configuration ───────────────────────────────────────
ACCESS_LIFETIME_MINUTES  = int(getattr(settings, 'ACCESS_TOKEN_LIFETIME_MINUTES', 60))
REFRESH_LIFETIME_DAYS    = int(getattr(settings, 'REFRESH_TOKEN_LIFETIME_DAYS', 7))

# ── Pydantic schemas ──────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh: str


class LogoutRequest(BaseModel):
    refresh: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class UserProfileResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    is_active: bool
    is_staff: bool
    date_joined: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str


class TenantInfo(BaseModel):
    id: str
    name: str
    slug: str
    domain: str
    location: str
    timezone: str


class ApiKeyInfo(BaseModel):
    name: str
    key_prefix: str
    permissions: str
    expires_at: Optional[datetime]


class SessionResponse(BaseModel):
    auth_method: str
    role: str
    user: Optional[UserProfileResponse]
    tenant: TenantInfo
    api_key: Optional[ApiKeyInfo]


# ── JWT helpers ───────────────────────────────────────────────

def _make_tokens(user) -> tuple[str, str]:
    """Return (access_token, refresh_token) for a user."""
    now = datetime.now(tz=timezone.utc)

    access_payload = {
        "user_id":    user.id,
        "email":      user.email,
        "token_type": "access",
        "iat":        now,
        "exp":        now + timedelta(minutes=ACCESS_LIFETIME_MINUTES),
    }
    access = jwt.encode(access_payload, settings.SECRET_KEY, algorithm="HS256")

    refresh_payload = {
        "user_id":    user.id,
        "token_type": "refresh",
        "jti":        str(uuid.uuid4()),
        "iat":        now,
        "exp":        now + timedelta(days=REFRESH_LIFETIME_DAYS),
    }
    refresh = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm="HS256")

    return access, refresh


def _decode_refresh(token: str, verify_exp: bool = True) -> dict:
    """Decode a refresh token; raise 401 on any failure."""
    try:
        options = {} if verify_exp else {"verify_exp": False}
        payload = jwt.decode(
            token, settings.SECRET_KEY,
            algorithms=["HS256"],
            options=options,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    if payload.get("token_type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token.")

    return payload


def _jti_cache_key(jti: str) -> str:
    return f"revoked_jti:{jti}"


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Create a new user account."""

    exists = await sync_to_async(
        User.objects.filter(email=request.email).exists
    )()
    if exists:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Validate password strength with Django's validators
    try:
        await sync_to_async(validate_password)(request.password)
    except DjangoValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="; ".join(exc.messages),
        )

    user = await sync_to_async(User.objects.create_user)(
        email=request.email,
        password=request.password,
        username=request.email,           # required by AbstractUser unique constraint
        name=request.name or "",
    )

    return UserProfileResponse.model_validate(user)


@router.post("/token", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Authenticate and return access + refresh tokens."""

    try:
        user = await sync_to_async(User.objects.get)(email=request.email, is_active=True)
    except User.DoesNotExist:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    password_ok = await sync_to_async(user.check_password)(request.password)
    if not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access, refresh = _make_tokens(user)
    return TokenResponse(access=access, refresh=refresh)


@router.post("/token/refresh", response_model=AccessTokenResponse)
async def token_refresh(request: RefreshRequest):
    """Issue a new access token from a valid refresh token."""

    payload = _decode_refresh(request.refresh)

    # Check revocation blocklist
    if await sync_to_async(cache.get)(_jti_cache_key(payload["jti"])):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked.")

    try:
        user = await sync_to_async(User.objects.get)(id=payload["user_id"], is_active=True)
    except User.DoesNotExist:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    now = datetime.now(tz=timezone.utc)
    access_payload = {
        "user_id":    user.id,
        "email":      user.email,
        "token_type": "access",
        "iat":        now,
        "exp":        now + timedelta(minutes=ACCESS_LIFETIME_MINUTES),
    }
    access = jwt.encode(access_payload, settings.SECRET_KEY, algorithm="HS256")
    return AccessTokenResponse(access=access)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: LogoutRequest,
    _user=Depends(get_current_user),
):
    """Revoke the provided refresh token."""

    payload = _decode_refresh(request.refresh, verify_exp=False)
    jti = payload.get("jti", "")

    if jti:
        # Calculate remaining TTL so the cache entry auto-expires
        exp = payload.get("exp", 0)
        remaining = max(int(exp - datetime.now(tz=timezone.utc).timestamp()), 0)
        timeout = remaining + 60  # small buffer
        await sync_to_async(cache.set)(_jti_cache_key(jti), True, timeout=timeout)

    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=UserProfileResponse)
async def me(user=Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return UserProfileResponse.model_validate(user)


@router.get("/session", response_model=SessionResponse)
async def get_session(ctx: RequestContext = Depends(get_request_context)):
    """Return current session info. Works with both JWT and API key auth."""
    tenant = ctx.tenant
    tenant_info = TenantInfo(
        id=str(tenant.tenant_id),
        name=tenant.name,
        slug=tenant.slug,
        domain=tenant.domain or "",
        location=tenant.location or "",
        timezone=tenant.timezone or "UTC",
    )

    user_info = None
    if ctx.user:
        user_info = UserProfileResponse.model_validate(ctx.user)

    api_key_info = None
    if ctx.api_key:
        api_key_info = ApiKeyInfo(
            name=ctx.api_key.name,
            key_prefix=ctx.api_key.key_prefix,
            permissions=ctx.api_key.permissions,
            expires_at=ctx.api_key.expires_at,
        )

    return SessionResponse(
        auth_method=ctx.auth_method,
        role=ctx.role,
        user=user_info,
        tenant=tenant_info,
        api_key=api_key_info,
    )


@router.post("/password/reset", response_model=MessageResponse)
async def password_reset_request(request: PasswordResetRequest):
    """
    Request a password reset link.
    Always returns 200 to prevent user enumeration.
    """
    generic = MessageResponse(
        message="If that email is registered you will receive a reset link shortly."
    )

    try:
        user = await sync_to_async(User.objects.get)(email=request.email, is_active=True)
    except User.DoesNotExist:
        return generic

    reset_token = await sync_to_async(PasswordResetToken.create_for_user)(user)

    # In production replace this log with a real email via Django's send_mail
    reset_url = f"/password/reset/confirm?token={reset_token.token}"
    logger.info(
        "Password reset requested for %s — reset URL: %s",
        user.email,
        reset_url,
    )

    return generic


@router.post("/password/reset/confirm", response_model=MessageResponse)
async def password_reset_confirm(request: PasswordResetConfirmRequest):
    """Consume a reset token and update the user's password."""

    try:
        reset_token = await sync_to_async(
            PasswordResetToken.objects
            .select_related('user')
            .get
        )(token=request.token)
    except PasswordResetToken.DoesNotExist:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")

    if not reset_token.is_valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This reset token has expired or was already used.")

    user = reset_token.user

    try:
        await sync_to_async(validate_password)(request.new_password, user)
    except DjangoValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="; ".join(exc.messages))

    await sync_to_async(user.set_password)(request.new_password)
    await sync_to_async(user.save)()

    reset_token.is_used = True
    await sync_to_async(reset_token.save)()

    return MessageResponse(message="Password updated successfully.")


@router.post("/password/change", response_model=MessageResponse)
async def password_change(
    request: ChangePasswordRequest,
    user=Depends(get_current_user),
):
    """Change password for the currently authenticated user."""

    current_ok = await sync_to_async(user.check_password)(request.current_password)
    if not current_ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    try:
        await sync_to_async(validate_password)(request.new_password, user)
    except DjangoValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="; ".join(exc.messages))

    await sync_to_async(user.set_password)(request.new_password)
    await sync_to_async(user.save)()

    return MessageResponse(message="Password changed successfully.")

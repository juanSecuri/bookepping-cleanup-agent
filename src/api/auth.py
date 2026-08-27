"""
Supabase JWT auth + workspace membership checks for the FastAPI API.

AUTH_ENABLED=false (default / local demos)
  - JWT not required; get_current_user returns a bypass identity.
  - require_workspace_access is a no-op.
  - Document this clearly: never leave AUTH_ENABLED=false on public Render.

AUTH_ENABLED=true (production)
  - Authorization: Bearer <supabase_access_token> required.
  - Verify with SUPABASE_JWT_SECRET (HS256) or JWKS at SUPABASE_URL
    (/auth/v1/.well-known/jwks.json) for asymmetric keys.
  - workspace_members row required for tenant-scoped mutations.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from src.config import get_settings
from src.infrastructure.repositories.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Stable UUID for local bypass so logs/audits stay consistent.
DEV_BYPASS_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

_JWKS_CACHE: dict[str, Any] = {"client": None, "url": None, "fetched_at": 0.0}
_JWKS_TTL_SEC = 3600.0


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: uuid.UUID
    email: str | None = None
    role: str | None = None
    bypass: bool = False
    raw_claims: dict[str, Any] | None = None


def auth_enabled() -> bool:
    return bool(get_settings().auth_enabled)


def _jwks_url(supabase_url: str) -> str:
    base = supabase_url.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _get_jwks_client(supabase_url: str) -> PyJWKClient:
    url = _jwks_url(supabase_url)
    now = time.monotonic()
    cached = _JWKS_CACHE.get("client")
    if (
        cached is not None
        and _JWKS_CACHE.get("url") == url
        and now - float(_JWKS_CACHE.get("fetched_at") or 0) < _JWKS_TTL_SEC
    ):
        return cached  # type: ignore[return-value]
    client = PyJWKClient(url, cache_keys=True, lifespan=_JWKS_TTL_SEC)
    _JWKS_CACHE["client"] = client
    _JWKS_CACHE["url"] = url
    _JWKS_CACHE["fetched_at"] = now
    return client


def _decode_with_secret(token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]},
    )


def _decode_with_jwks(token: str, supabase_url: str) -> dict[str, Any]:
    jwks = _get_jwks_client(supabase_url)
    signing_key = jwks.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256", "HS256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]},
    )


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify a Supabase access token; raises HTTPException on failure."""
    settings = get_settings()
    secret = (settings.supabase_jwt_secret or "").strip()
    errors: list[str] = []

    if secret:
        try:
            return _decode_with_secret(token, secret)
        except jwt.PyJWTError as exc:
            errors.append(f"HS256: {exc}")

    try:
        return _decode_with_jwks(token, settings.supabase_url)
    except Exception as exc:  # noqa: BLE001 — surface as 401 below
        errors.append(f"JWKS: {exc}")

    logger.warning("JWT verification failed: %s", "; ".join(errors) or "no verifier configured")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def claims_to_user(claims: dict[str, Any]) -> AuthUser:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub")
    try:
        uid = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid subject") from exc
    return AuthUser(
        id=uid,
        email=claims.get("email"),
        role=claims.get("role"),
        bypass=False,
        raw_claims=claims,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    """
    Optional-but-enforced when AUTH_ENABLED=true.
    When AUTH_ENABLED=false, returns a documented local bypass user.
    """
    if not auth_enabled():
        return AuthUser(
            id=DEV_BYPASS_USER_ID,
            email="dev-bypass@local",
            role="bypass",
            bypass=True,
        )

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = verify_supabase_jwt(credentials.credentials)
    return claims_to_user(claims)


def require_workspace_access(user_id: uuid.UUID, workspace_id: uuid.UUID | str) -> None:
    """
    Ensure user_id has a row in workspace_members for workspace_id.
    No-op when AUTH_ENABLED=false (local demos).
    If the workspace has zero members, bootstrap the caller as owner
    (AUTH_BOOTSTRAP_FIRST_OWNER, default true) so first login works.
    """
    if not auth_enabled():
        return

    wid = str(workspace_id)
    try:
        client = get_supabase_client()
        result = (
            client.table("workspace_members")
            .select("user_id,workspace_id,role")
            .eq("user_id", str(user_id))
            .eq("workspace_id", wid)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("workspace_members lookup failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Membership check unavailable",
        ) from exc

    if result.data:
        return

    settings = get_settings()
    bootstrap = bool(getattr(settings, "auth_bootstrap_first_owner", True))
    if bootstrap:
        try:
            existing = (
                client.table("workspace_members")
                .select("user_id")
                .eq("workspace_id", wid)
                .limit(1)
                .execute()
            )
            if not existing.data:
                client.table("workspace_members").upsert(
                    {
                        "user_id": str(user_id),
                        "workspace_id": wid,
                        "role": "owner",
                    },
                    on_conflict="user_id,workspace_id",
                ).execute()
                logger.info("Bootstrapped owner %s on workspace %s", user_id, wid)
                return
        except Exception:  # noqa: BLE001
            logger.exception("workspace_members bootstrap failed")

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "No access to this workspace",
    )


def assert_workspace_access(user: AuthUser, workspace_id: uuid.UUID | str) -> None:
    require_workspace_access(user.id, workspace_id)

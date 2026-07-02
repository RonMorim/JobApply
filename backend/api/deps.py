"""
FastAPI authentication dependencies.

Supabase can sign JWTs with either HS256 (older / self-hosted projects) or
RS256 (newer hosted projects with asymmetric key pairs).  This module handles
both, preferring RS256/JWKS when SUPABASE_URL is present in the environment.

RS256 flow (preferred — Supabase-hosted projects)
──────────────────────────────────────────────────
  • Public keys are fetched from
      {SUPABASE_URL}/auth/v1/.well-known/jwks.json
  • The response is cached in-process with a 1-hour TTL so the network call
    happens at most once per hour, not on every request.
  • On cache miss for a specific `kid` the cache is force-refreshed once
    (handles key rotation without a server restart).

HS256 fallback (legacy / local Supabase CLI)
────────────────────────────────────────────
  • Used when SUPABASE_URL is absent (i.e. local dev without a hosted project).
  • Verifies the token against SUPABASE_JWT_SECRET using HMAC-SHA256.
  • The startup check rejects the anon/service-role key (starts with 'eyJ').

Setup
─────
  backend/.env should contain at least one of:
    SUPABASE_URL=https://<ref>.supabase.co   ← enables RS256/JWKS
    SUPABASE_JWT_SECRET=<raw-secret>         ← HS256 fallback only
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
_JWT_SECRET   = os.getenv("SUPABASE_JWT_SECRET", "")

# RS256/JWKS endpoint derived from the Supabase project URL
_JWKS_URL = f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json" if _SUPABASE_URL else ""

# ── Startup diagnostics ───────────────────────────────────────────────────────

if _SUPABASE_URL:
    logger.info(
        "[auth] JWKS mode (RS256/ES256) — public keys will be fetched from %s", _JWKS_URL
    )
elif _JWT_SECRET:
    if _JWT_SECRET.startswith("eyJ"):
        logger.error(
            "[auth] SUPABASE_JWT_SECRET looks like a JWT token (starts with 'eyJ'). "
            "It must be the raw signing secret, not the anon/service-role key. "
            "Go to Supabase Dashboard → Project Settings → API → JWT Settings → JWT Secret."
        )
    else:
        logger.info("[auth] HS256 fallback mode — using SUPABASE_JWT_SECRET.")
else:
    logger.error(
        "[auth] Neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set. "
        "All protected endpoints will return HTTP 503. "
        "Add SUPABASE_URL=https://<ref>.supabase.co to backend/.env."
    )

# ── JWKS cache ────────────────────────────────────────────────────────────────
#
# Structure: (fetched_at_monotonic, list_of_jwk_dicts)
# A list is used so python-jose can match by `kid` if multiple keys are present.

_CACHE_TTL_SECONDS: float = 3600.0   # refetch at most once per hour

_jwks_fetched_at: float      = 0.0
_jwks_keys:       list[dict] = []


async def _fetch_jwks(*, force: bool = False) -> list[dict]:
    """
    Return the cached JWKS key list, refreshing when stale or forced.

    *force=True* is used on a `kid` cache-miss to handle key rotation without
    requiring a server restart.

    Thread-safety note: this is an async function called from a single-process
    ASGI server.  Concurrent refreshes may occur under high load, but the result
    is idempotent (last writer wins) and the cost of an extra JWKS fetch is low.
    """
    global _jwks_fetched_at, _jwks_keys

    now = time.monotonic()
    if not force and _jwks_keys and now - _jwks_fetched_at < _CACHE_TTL_SECONDS:
        return _jwks_keys

    if not _JWKS_URL:
        return []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(_JWKS_URL)
            r.raise_for_status()
            keys: list[dict] = r.json().get("keys", [])
        _jwks_keys      = keys
        _jwks_fetched_at = now
        logger.info("[auth] JWKS refreshed — %d key(s) cached", len(keys))
        return keys
    except Exception as exc:
        logger.error("[auth] JWKS fetch failed (%s) — using stale cache (%d key(s))", exc, len(_jwks_keys))
        return _jwks_keys   # stale is better than nothing


def _pick_key(keys: list[dict], kid: Optional[str]) -> Optional[dict]:
    """
    Return the JWK entry whose `kid` matches the JWT header.

    If the JWT has no `kid` claim (uncommon) fall back to the first key so
    single-key setups still work without requiring strict `kid` usage.
    """
    if not keys:
        return None
    if not kid:
        return keys[0]
    return next((k for k in keys if k.get("kid") == kid), None)


# ── FastAPI plumbing ──────────────────────────────────────────────────────────

# auto_error=False lets us return a descriptive 401 body ourselves
_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id:  str
    email:    str  = field(default="")
    is_admin: bool = field(default=False)


def _load_is_admin(user_id: str) -> bool:
    """Cheap master_profiles lookup; absent row (or any DB error) → False."""
    try:
        from sqlalchemy import text as _text
        from backend.services.db import ENGINE
        with ENGINE.connect() as conn:
            row = conn.execute(
                _text("SELECT is_admin FROM master_profiles WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
        return bool(row[0]) if row else False
    except Exception:
        return False


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency: verifies a Supabase Bearer JWT and returns the caller's
    identity.

    Raises HTTP 503 when neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set.
    Raises HTTP 401 for a missing/expired/invalid token or absent `sub` claim.

    Inject with:
        user: CurrentUser = Depends(get_current_user)
    """
    # ── Server misconfiguration check ─────────────────────────────────────────
    if not _SUPABASE_URL and not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured on this server. "
                "Add SUPABASE_URL=https://<ref>.supabase.co to backend/.env."
            ),
        )

    # ── Token presence check ──────────────────────────────────────────────────
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from jose import JWTError, jwt

    token = credentials.credentials

    # ── RS256/JWKS path ───────────────────────────────────────────────────────
    if _SUPABASE_URL:
        user = await _verify_rs256(token, jwt, JWTError)
    else:
        # ── HS256 fallback ────────────────────────────────────────────────────
        user = _verify_hs256(token, jwt, JWTError)

    user.is_admin = _load_is_admin(user.user_id)
    return user


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    FastAPI dependency for admin-only routes (Phase 2 foundation — defined
    and exported, not yet mounted on any route).

        user: CurrentUser = Depends(require_admin)
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


async def _verify_rs256(token: str, jwt, JWTError) -> CurrentUser:
    """Verify an RS256 token against Supabase's JWKS public keys."""
    try:
        # Peek at the header to find the signing key
        header = jwt.get_unverified_header(token)
        kid    = header.get("kid")
        # Use whatever algorithm the token header declares (RS256, ES256, etc.)
        # rather than hardcoding a single algorithm — Supabase may rotate alg types.
        alg    = header.get("alg")
        if not alg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header is missing the 'alg' field.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        keys = await _fetch_jwks()
        key  = _pick_key(keys, kid)

        if key is None and kid is not None:
            # kid not in cache — rotate and try once more
            logger.info("[auth] kid=%r not in cache — force-refreshing JWKS", kid)
            keys = await _fetch_jwks(force=True)
            key  = _pick_key(keys, kid)

        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key not found in JWKS.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],        # honour whatever alg the key advertises
            options={"verify_aud": False},
        )
        return _extract_user(payload)

    except HTTPException:
        raise
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _verify_hs256(token: str, jwt, JWTError) -> CurrentUser:
    """Verify an HS256 token against the raw SUPABASE_JWT_SECRET."""
    try:
        payload = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return _extract_user(payload)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _extract_user(payload: dict) -> CurrentUser:
    """Pull user_id and email from a verified JWT payload."""
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the 'sub' claim.",
        )
    return CurrentUser(
        user_id=user_id,
        email=payload.get("email", ""),
    )

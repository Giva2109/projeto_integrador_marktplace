from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from loguru import logger


_bearer = HTTPBearer(auto_error=False)
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_until: float = 0.0


def _get_supabase_project_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL não definido.")
    return url.rstrip("/")


async def _get_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_until

    now = time.time()
    if _jwks_cache and now < _jwks_cache_until:
        return _jwks_cache

    jwks_url = f"{_get_supabase_project_url()}/auth/v1/.well-known/jwks.json"
    logger.info("Auth JWKS fetch: {}", jwks_url)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url, headers={"Accept": "application/json"})
        logger.info("Auth JWKS response: status={}", resp.status_code)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_until = now + 60 * 10  # 10 min cache
        return _jwks_cache


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Authorization Bearer token ausente.")

    token = creds.credentials
    jwks = await _get_jwks()

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="JWT sem kid.")

        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key:
            raise HTTPException(status_code=401, detail="Chave pública (kid) não encontrada.")

        claims = jwt.decode(
            token,
            key,
            algorithms=[header.get("alg", "RS256")],
            audience=os.getenv("SUPABASE_JWT_AUD", "authenticated"),
            options={"verify_aud": True},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("JWT validation failed: {}", str(e))
        raise HTTPException(status_code=401, detail="JWT inválido ou expirado.")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="JWT sem subject (sub).")
    return str(user_id)


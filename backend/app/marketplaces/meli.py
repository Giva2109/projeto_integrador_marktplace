from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loguru import logger

from app.core.settings import settings
from app.db.supabase_client import get_service_client
from app.marketplaces.base import MarketplaceProvider, PublishResult
from app.marketplaces.meli_errors import MeliApiError, log_meli_api_error
from app.services.token_crypto import TokenCrypto


class MercadoLivreProvider(MarketplaceProvider):
    platform = "meli"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=45)
        self._sb = get_service_client()
        self._crypto = TokenCrypto(settings.token_crypto_secret)

    async def get_oauth_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.meli_client_id,
            "redirect_uri": settings.meli_redirect_uri,
            "state": state,
        }
        req = httpx.Request("GET", "https://auth.mercadolivre.com.br/authorization", params=params)
        return str(req.url)

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        url = "https://api.mercadolibre.com/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.meli_client_id,
            "client_secret": settings.meli_client_secret,
            "code": code,
            "redirect_uri": settings.meli_redirect_uri,
        }

        logger.info("Meli OAuth | troca de code | iniciando")
        resp = await self._http.post(url, data=data, headers={"Accept": "application/json"})
        logger.info("Meli OAuth | troca de code | http_status={}", resp.status_code)
        if resp.status_code >= 400:
            parsed = log_meli_api_error("oauth_exchange", resp)
            raise MeliApiError(
                "Falha na troca do code OAuth do Mercado Livre.",
                status_code=resp.status_code,
                body_text=resp.text,
                parsed=parsed,
            )
        payload = resp.json()

        expires_in = int(payload.get("expires_in") or 0)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 0))
        payload["expires_at"] = expires_at.isoformat()
        return payload

    async def refresh_token_if_needed(self, owner_id: str) -> None:
        token_row = (
            self._sb.table("marketplace_tokens")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("platform", self.platform)
            .maybe_single()
            .execute()
        )
        if not token_row.data:
            raise RuntimeError("Token do Mercado Livre não encontrado para este usuário.")

        expires_at = token_row.data.get("expires_at")
        if not expires_at:
            logger.warning("Meli token | expires_at ausente; não fazendo refresh preventivo.")
            return

        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if exp - datetime.now(timezone.utc) > timedelta(minutes=3):
            return

        await self._refresh_tokens(owner_id)

    async def force_refresh_access_token(self, owner_id: str) -> None:
        """Sempre renova via refresh_token (ex.: após 401 invalid_token)."""
        await self._refresh_tokens(owner_id)

    async def _refresh_tokens(self, owner_id: str) -> None:
        token_row = (
            self._sb.table("marketplace_tokens")
            .select("*")
            .eq("owner_id", owner_id)
            .eq("platform", self.platform)
            .maybe_single()
            .execute()
        )
        if not token_row.data:
            raise RuntimeError("Token do Mercado Livre não encontrado para este usuário.")

        refresh_token_enc = token_row.data.get("refresh_token_enc")
        if not refresh_token_enc:
            raise RuntimeError("Refresh token ausente; reautorização necessária.")

        refresh_token = self._crypto.decrypt_from_b64(refresh_token_enc)
        url = "https://api.mercadolibre.com/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.meli_client_id,
            "client_secret": settings.meli_client_secret,
            "refresh_token": refresh_token,
        }

        logger.info("Meli OAuth | refresh | owner_id={}", owner_id)
        resp = await self._http.post(url, data=data, headers={"Accept": "application/json"})
        logger.info("Meli OAuth | refresh | http_status={}", resp.status_code)
        if resp.status_code >= 400:
            parsed = log_meli_api_error("oauth_refresh", resp)
            raise MeliApiError(
                "Falha ao renovar token do Mercado Livre (expirado ou revogado).",
                status_code=resp.status_code,
                body_text=resp.text,
                parsed=parsed,
            )
        payload = resp.json()

        expires_in = int(payload.get("expires_in") or 0)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 0))

        access_token_b64 = self._crypto.encrypt_to_b64(payload["access_token"])
        refresh_token_b64 = self._crypto.encrypt_to_b64(payload.get("refresh_token") or refresh_token)

        self._sb.table("marketplace_tokens").update(
            {
                "access_token_enc": access_token_b64,
                "refresh_token_enc": refresh_token_b64,
                "token_type": payload.get("token_type"),
                "scope": payload.get("scope"),
                "expires_at": expires_at.isoformat(),
            }
        ).eq("owner_id", owner_id).eq("platform", self.platform).execute()

    async def publish_product(self, owner_id: str, product: dict[str, Any]) -> PublishResult:
        await self.refresh_token_if_needed(owner_id)
        url = "https://api.mercadolibre.com/items"
        plain_description = str(product.pop("_plain_description", "") or "")

        resp = await self._request_with_token_retry(
            owner_id,
            "POST",
            url,
            json_body=product,
            operation="publish_item",
        )
        payload = resp.json()
        item_id = str(payload.get("id") or "")
        if not item_id:
            logger.error("Meli publish | resposta sem id | body={}", resp.text[:4000])
            raise MeliApiError(
                "Resposta do Mercado Livre sem ID do anúncio.",
                status_code=resp.status_code,
                body_text=resp.text,
                parsed=payload if isinstance(payload, dict) else None,
            )

        if plain_description:
            desc_url = f"https://api.mercadolibre.com/items/{item_id}/description"
            await self._request_with_token_retry(
                owner_id,
                "PUT",
                desc_url,
                json_body={"plain_text": plain_description},
                operation="publish_description",
            )

        return PublishResult(external_listing_id=item_id, raw_response=payload)

    async def sync_listing_status(self, owner_id: str, external_listing_id: str) -> dict[str, Any]:
        await self.refresh_token_if_needed(owner_id)
        url = f"https://api.mercadolibre.com/items/{external_listing_id}"
        resp = await self._request_with_token_retry(owner_id, "GET", url, operation="sync_item")
        return resp.json()

    async def update_listing(self, owner_id: str, external_listing_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        await self.refresh_token_if_needed(owner_id)
        url = f"https://api.mercadolibre.com/items/{external_listing_id}"
        resp = await self._request_with_token_retry(
            owner_id,
            "PUT",
            url,
            json_body=patch,
            operation="update_item",
        )
        return resp.json()

    async def _request_with_token_retry(
        self,
        owner_id: str,
        method: str,
        url: str,
        *,
        operation: str,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_resp: httpx.Response | None = None
        for attempt in range(2):
            token = self._decrypt_access_token(owner_id)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            logger.info(
                "Meli HTTP | {} | {} | attempt={} | owner_id={}",
                operation,
                url,
                attempt + 1,
                owner_id,
            )
            if method.upper() == "GET":
                resp = await self._http.get(url, headers=headers)
            elif method.upper() == "POST":
                resp = await self._http.post(url, json=json_body, headers=headers)
            elif method.upper() == "PUT":
                resp = await self._http.put(url, json=json_body, headers=headers)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")

            last_resp = resp
            logger.info("Meli HTTP | {} | http_status={}", operation, resp.status_code)

            if resp.status_code == 401 and attempt == 0:
                logger.warning(
                    "Meli HTTP | 401 em {} | tentando force_refresh e repetir | owner_id={}",
                    operation,
                    owner_id,
                )
                try:
                    await self.force_refresh_access_token(owner_id)
                except Exception as e:
                    logger.error("Meli HTTP | refresh após 401 falhou | err={}", str(e))
                    parsed = log_meli_api_error(operation, resp)
                    raise MeliApiError(
                        "Token do Mercado Livre inválido ou expirado.",
                        status_code=401,
                        body_text=resp.text,
                        parsed=parsed,
                    ) from e
                continue

            if resp.status_code >= 400:
                parsed = log_meli_api_error(operation, resp)
                raise MeliApiError(
                    f"Erro na API do Mercado Livre ({operation}).",
                    status_code=resp.status_code,
                    body_text=resp.text,
                    parsed=parsed,
                )

            return resp

        assert last_resp is not None
        parsed = log_meli_api_error(operation, last_resp)
        raise MeliApiError(
            f"Erro na API do Mercado Livre ({operation}).",
            status_code=last_resp.status_code,
            body_text=last_resp.text,
            parsed=parsed,
        )

    def store_tokens_for_owner(self, owner_id: str, token_payload: dict[str, Any]) -> None:
        access_token_b64 = self._crypto.encrypt_to_b64(token_payload["access_token"])
        refresh_token = token_payload.get("refresh_token")
        refresh_token_b64 = self._crypto.encrypt_to_b64(refresh_token) if refresh_token else None

        expires_at = token_payload.get("expires_at")

        row = {
            "owner_id": owner_id,
            "platform": self.platform,
            "access_token_enc": access_token_b64,
            "refresh_token_enc": refresh_token_b64,
            "token_type": token_payload.get("token_type"),
            "scope": token_payload.get("scope"),
            "expires_at": expires_at,
        }

        logger.info("Meli tokens | persistindo | owner_id={}", owner_id)
        self._sb.table("marketplace_tokens").upsert(row, on_conflict="owner_id,platform").execute()

    def _decrypt_access_token(self, owner_id: str) -> str:
        token_row = (
            self._sb.table("marketplace_tokens")
            .select("access_token_enc,expires_at")
            .eq("owner_id", owner_id)
            .eq("platform", self.platform)
            .maybe_single()
            .execute()
        )
        if not token_row.data:
            raise RuntimeError("Token do Mercado Livre não encontrado para este usuário.")

        access_token_enc = token_row.data["access_token_enc"]
        return self._crypto.decrypt_from_b64(access_token_enc)

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.core.auth import get_current_user_id
from app.core.settings import settings
from app.marketplaces.meli import MercadoLivreProvider
from app.marketplaces.meli_errors import MeliApiError
from app.models.oauth_meli import MeliAuthorizeResponse, MeliCallbackBody, MeliCallbackResponse
from app.services.meli_oauth_state import create_meli_oauth_state, parse_meli_oauth_state

router = APIRouter(prefix="/oauth/meli", tags=["oauth-meli"])


def _meli() -> MercadoLivreProvider:
    return MercadoLivreProvider()


@router.get("/authorize", response_model=MeliAuthorizeResponse)
async def meli_authorize(
    user_id: str = Depends(get_current_user_id),
    provider: MercadoLivreProvider = Depends(_meli),
) -> MeliAuthorizeResponse:
    """
    Retorna a URL do Mercado Livre para o usuário autorizar o app.
    O `state` deve ser enviado de volta no callback (ML devolve junto com `code`).
    """
    ttl = 15
    state = create_meli_oauth_state(user_id, settings.token_crypto_secret, ttl_minutes=ttl)
    authorize_url = await provider.get_oauth_authorize_url(state)
    logger.info("OAuth Meli | authorize URL gerada | owner_id={}", user_id)
    return MeliAuthorizeResponse(authorize_url=authorize_url, state=state, state_ttl_minutes=ttl)


async def _execute_meli_callback(body: MeliCallbackBody, provider: MercadoLivreProvider) -> MeliCallbackResponse:
    try:
        owner_id = parse_meli_oauth_state(body.state, settings.token_crypto_secret)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    logger.info("OAuth Meli | callback | troca de code | owner_id={}", owner_id)
    try:
        token_payload = await provider.exchange_code_for_token(body.code)
    except MeliApiError as e:
        logger.error("OAuth Meli | callback | troca falhou | {}", str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(e),
                "meli_status": e.status_code,
                "meli_body": e.parsed,
            },
        ) from e

    provider.store_tokens_for_owner(owner_id, token_payload)
    return MeliCallbackResponse(user_id=owner_id)


@router.post("/callback", response_model=MeliCallbackResponse)
async def meli_callback_post(
    body: MeliCallbackBody,
    provider: MercadoLivreProvider = Depends(_meli),
) -> MeliCallbackResponse:
    """
    Troca `code` por tokens e persiste em `marketplace_tokens` (criptografado).
    Uso típico: Postman ou frontend após capturar `code` e `state` do redirect.
    """
    return await _execute_meli_callback(body, provider)


@router.get("/callback", response_model=MeliCallbackResponse)
async def meli_callback_get(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    provider: MercadoLivreProvider = Depends(_meli),
) -> MeliCallbackResponse:
    """
    Mesmo fluxo do POST, para quando o Redirect URI do app no Meli aponta para esta URL
    (ex.: `https://api.seudominio.com/oauth/meli/callback`).
    """
    return await _execute_meli_callback(MeliCallbackBody(code=code, state=state), provider)

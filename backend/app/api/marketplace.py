from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.core.auth import get_current_user_id
from app.db.supabase_client import get_service_client
from app.marketplaces.meli import MercadoLivreProvider
from app.marketplaces.meli_errors import MeliApiError
from app.models.marketplace_meli import (
    PublishRequest,
    PublishResponse,
    SyncResponse,
    UpdateRequest,
    UpdateResponse,
)
from app.services.meli_item_builder import (
    build_meli_item_payload,
    build_meli_update_payload_from_product,
    meli_listing_status_from_item,
)

router = APIRouter(tags=["marketplace"])


def _meli_provider() -> MercadoLivreProvider:
    return MercadoLivreProvider()


def _http_status_from_meli(code: int) -> int:
    if code == 401:
        return status.HTTP_401_UNAUTHORIZED
    if code >= 500:
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_400_BAD_REQUEST


def _listing_row_for_product(sb: Any, owner_id: str, product_id: str) -> dict[str, Any] | None:
    res = (
        sb.table("platform_listings")
        .select("*")
        .eq("owner_id", owner_id)
        .eq("platform", "meli")
        .eq("product_id", product_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


@router.post("/publish", response_model=PublishResponse)
async def publish_listing(
    body: PublishRequest,
    user_id: str = Depends(get_current_user_id),
    meli: MercadoLivreProvider = Depends(_meli_provider),
) -> PublishResponse:
    sb = get_service_client()
    pid = str(body.product_id)

    pres = sb.table("products").select("*").eq("id", pid).eq("owner_id", user_id).limit(1).execute()
    rows = pres.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Produto não encontrado ou sem permissão.")
    product_row = rows[0]

    try:
        item_payload = build_meli_item_payload(product_row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    item_payload["_plain_description"] = str(product_row.get("description") or "")

    logger.info("POST /publish | meli | product_id={} owner_id={}", pid, user_id)
    try:
        result = await meli.publish_product(user_id, item_payload)
    except MeliApiError as e:
        logger.error("POST /publish | MeliApiError | {}", str(e))
        raise HTTPException(
            status_code=_http_status_from_meli(e.status_code),
            detail={
                "message": str(e),
                "meli_status": e.status_code,
                "meli_body": e.parsed,
            },
        ) from e

    ext_id = result.external_listing_id
    raw = result.raw_response
    listing_status = meli_listing_status_from_item(raw)
    now = datetime.now(timezone.utc).isoformat()

    sb.table("platform_listings").upsert(
        {
            "owner_id": user_id,
            "product_id": pid,
            "platform": "meli",
            "external_listing_id": ext_id,
            "status": listing_status,
            "last_sync_at": now,
            "last_error": None,
        },
        on_conflict="owner_id,product_id,platform",
    ).execute()

    return PublishResponse(product_id=pid, external_listing_id=ext_id, meli=raw)


@router.get("/sync", response_model=SyncResponse)
async def sync_listing(
    user_id: str = Depends(get_current_user_id),
    meli: MercadoLivreProvider = Depends(_meli_provider),
    external_listing_id: str | None = Query(None),
    product_id: UUID | None = Query(None),
) -> SyncResponse:
    if bool(external_listing_id) == bool(product_id):
        raise HTTPException(
            status_code=400,
            detail="Informe exatamente um filtro: external_listing_id ou product_id.",
        )

    sb = get_service_client()
    ext_id: str

    if product_id:
        row = _listing_row_for_product(sb, user_id, str(product_id))
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Não há anúncio do Mercado Livre vinculado a este produto.",
            )
        ext_id = str(row["external_listing_id"])
    else:
        ext_id = external_listing_id or ""
        chk = (
            sb.table("platform_listings")
            .select("id")
            .eq("owner_id", user_id)
            .eq("platform", "meli")
            .eq("external_listing_id", ext_id)
            .limit(1)
            .execute()
        )
        if not (chk.data or []):
            raise HTTPException(status_code=404, detail="Anúncio não encontrado para este usuário.")

    logger.info("GET /sync | meli | external_listing_id={} owner_id={}", ext_id, user_id)
    try:
        raw = await meli.sync_listing_status(user_id, ext_id)
    except MeliApiError as e:
        logger.error("GET /sync | MeliApiError | {}", str(e))
        sb.table("platform_listings").update({"last_error": e.body_text[:2000]}).eq("owner_id", user_id).eq(
            "platform", "meli"
        ).eq("external_listing_id", ext_id).execute()
        raise HTTPException(
            status_code=_http_status_from_meli(e.status_code),
            detail={
                "message": str(e),
                "meli_status": e.status_code,
                "meli_body": e.parsed,
            },
        ) from e

    listing_status = meli_listing_status_from_item(raw)
    now = datetime.now(timezone.utc).isoformat()

    sb.table("platform_listings").update(
        {
            "status": listing_status,
            "last_sync_at": now,
            "last_error": None,
        }
    ).eq("owner_id", user_id).eq("platform", "meli").eq("external_listing_id", ext_id).execute()

    return SyncResponse(external_listing_id=ext_id, listing_status=listing_status, meli=raw)


@router.patch("/update", response_model=UpdateResponse)
async def update_listing(
    body: UpdateRequest,
    user_id: str = Depends(get_current_user_id),
    meli: MercadoLivreProvider = Depends(_meli_provider),
) -> UpdateResponse:
    sb = get_service_client()
    ext_id = body.external_listing_id

    chk = (
        sb.table("platform_listings")
        .select("product_id")
        .eq("owner_id", user_id)
        .eq("platform", "meli")
        .eq("external_listing_id", ext_id)
        .limit(1)
        .execute()
    )
    chk_rows = chk.data or []
    if not chk_rows:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado para este usuário.")

    merged: dict[str, Any] = dict(body.patch or {})
    if body.product_id is not None:
        pid = str(body.product_id)
        if str(chk_rows[0].get("product_id")) != pid:
            raise HTTPException(
                status_code=400,
                detail="product_id não corresponde ao vínculo deste external_listing_id.",
            )
        pres = sb.table("products").select("*").eq("id", pid).eq("owner_id", user_id).limit(1).execute()
        prs = pres.data or []
        if not prs:
            raise HTTPException(status_code=404, detail="Produto não encontrado ou sem permissão.")
        ssot_patch = build_meli_update_payload_from_product(prs[0])
        merged = {**ssot_patch, **merged}

    if not merged:
        raise HTTPException(status_code=400, detail="Nada para atualizar.")

    logger.info("PATCH /update | meli | external_listing_id={} owner_id={}", ext_id, user_id)
    try:
        raw = await meli.update_listing(user_id, ext_id, merged)
    except MeliApiError as e:
        logger.error("PATCH /update | MeliApiError | {}", str(e))
        sb.table("platform_listings").update({"last_error": e.body_text[:2000]}).eq("owner_id", user_id).eq(
            "platform", "meli"
        ).eq("external_listing_id", ext_id).execute()
        raise HTTPException(
            status_code=_http_status_from_meli(e.status_code),
            detail={
                "message": str(e),
                "meli_status": e.status_code,
                "meli_body": e.parsed,
            },
        ) from e

    listing_status = meli_listing_status_from_item(raw)
    now = datetime.now(timezone.utc).isoformat()
    sb.table("platform_listings").update(
        {
            "status": listing_status,
            "last_sync_at": now,
            "last_error": None,
        }
    ).eq("owner_id", user_id).eq("platform", "meli").eq("external_listing_id", ext_id).execute()

    return UpdateResponse(external_listing_id=ext_id, meli=raw)

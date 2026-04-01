from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.core.auth import get_current_user_id
from app.db.supabase_client import get_service_client
from app.models.product import ProductCreate, ProductOut


router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, user_id: str = Depends(get_current_user_id)) -> ProductOut:
    sb = get_service_client()

    row = {
        "owner_id": user_id,
        "title": payload.title,
        "description": payload.description,
        "price": str(payload.price),
        "stock": payload.stock,
        "category_id": payload.category_id,
        "images": [str(u) for u in payload.images],
        "status": payload.status.value,
    }

    logger.info("Create product owner_id={} title={}", user_id, payload.title)
    res = sb.table("products").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Falha ao criar produto.")
    created = res.data[0]
    return ProductOut(**created)


@router.get("", response_model=list[ProductOut])
def list_products(user_id: str = Depends(get_current_user_id)) -> list[ProductOut]:
    sb = get_service_client()
    logger.info("List products owner_id={}", user_id)

    res = sb.table("products").select("*").eq("owner_id", user_id).order("created_at", desc=True).execute()
    data = res.data or []
    return [ProductOut(**row) for row in data]


from __future__ import annotations

from typing import Any


def build_meli_item_payload(product_row: dict[str, Any]) -> dict[str, Any]:
    """
    Monta o corpo inicial do POST /items (MLB).
    Requer category_id do ML no produto SSOT e ao menos uma imagem pública (URL).
    """
    category_id = product_row.get("category_id")
    if not category_id:
        raise ValueError("category_id é obrigatório para publicar no Mercado Livre (ID da categoria ML).")

    images = product_row.get("images") or []
    if not images:
        raise ValueError("Informe ao menos uma URL em images para publicar no Mercado Livre.")

    pictures = [{"source": url} for url in images if url]

    return {
        "title": product_row["title"],
        "category_id": category_id,
        "price": float(product_row["price"]),
        "currency_id": "BRL",
        "available_quantity": int(product_row.get("stock") or 0),
        "buying_mode": "buy_it_now",
        "listing_type_id": "gold_special",
        "condition": "new",
        "pictures": pictures,
    }


def meli_listing_status_from_item(item: dict[str, Any]) -> str:
    """Mapeia status do item ML para listing_status do Supabase."""
    s = str(item.get("status") or "").lower()
    if s == "active":
        return "published"
    if s == "paused":
        return "paused"
    if s in ("closed", "deleted"):
        return "closed"
    if s == "under_review":
        return "queued"
    return "unknown"


def build_meli_update_payload_from_product(product_row: dict[str, Any]) -> dict[str, Any]:
    """Campos comuns para PUT /items/{id} a partir do SSOT."""
    payload: dict[str, Any] = {
        "title": product_row["title"],
        "price": float(product_row["price"]),
        "available_quantity": int(product_row.get("stock") or 0),
    }
    images = product_row.get("images") or []
    if images:
        payload["pictures"] = [{"source": url} for url in images if url]
    return payload

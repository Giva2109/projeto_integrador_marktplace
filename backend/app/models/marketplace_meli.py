from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PublishRequest(BaseModel):
    product_id: UUID


class UpdateRequest(BaseModel):
    external_listing_id: str = Field(min_length=1)
    """Se informado, mescla dados do SSOT (título, preço, estoque, imagens) antes do patch."""
    product_id: UUID | None = None
    """Campos extras no formato da API do Mercado Livre (PUT /items/{id})."""
    patch: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_patch_or_product(self) -> UpdateRequest:
        if self.product_id is not None:
            return self
        if self.patch and len(self.patch) > 0:
            return self
        raise ValueError("Informe product_id (SSOT) ou patch com ao menos um campo da API Meli.")


class PublishResponse(BaseModel):
    product_id: str
    external_listing_id: str
    meli: dict[str, Any]


class SyncResponse(BaseModel):
    external_listing_id: str
    listing_status: str
    meli: dict[str, Any]


class UpdateResponse(BaseModel):
    external_listing_id: str
    meli: dict[str, Any]

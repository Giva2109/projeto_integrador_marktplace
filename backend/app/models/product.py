from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, condecimal, conint


class ProductStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    published = "published"
    paused = "paused"
    error = "error"
    archived = "archived"


class ProductCreate(BaseModel):
    # Reflete exatamente os campos de negócio da tabela `products`
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    price: condecimal(ge=0, max_digits=12, decimal_places=2)
    stock: conint(ge=0) = 0
    category_id: str | None = None
    images: list[HttpUrl] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.draft


class ProductOut(ProductCreate):
    id: str
    owner_id: str


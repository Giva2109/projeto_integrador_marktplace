from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, condecimal, conint


class ProductStatus(str, Enum):
    draft = "draft"
    ready = "ready"
    published = "published"
    paused = "paused"
    error = "error"
    archived = "archived"


class ProductBase(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10)
    price: condecimal(ge=0, max_digits=12, decimal_places=2)
    stock: conint(ge=0) = 0
    category_id: str | None = Field(default=None, max_length=128)
    images: list[HttpUrl] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.draft


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=10)
    price: condecimal(ge=0, max_digits=12, decimal_places=2) | None = None
    stock: conint(ge=0) | None = None
    category_id: str | None = Field(default=None, max_length=128)
    images: list[HttpUrl] | None = None
    status: ProductStatus | None = None


class ProductOut(ProductBase):
    id: UUID
    owner_id: UUID


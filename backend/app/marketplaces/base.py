from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PublishResult:
    external_listing_id: str
    raw_response: dict[str, Any]


class MarketplaceProvider(ABC):
    platform: str

    @abstractmethod
    async def get_oauth_authorize_url(self, state: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def refresh_token_if_needed(self, owner_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def publish_product(self, owner_id: str, product: dict[str, Any]) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    async def sync_listing_status(self, owner_id: str, external_listing_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def update_listing(self, owner_id: str, external_listing_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


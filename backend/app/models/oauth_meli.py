from __future__ import annotations

from pydantic import BaseModel, Field


class MeliAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str = Field(description="Repasse no callback (query ou body) junto com o code.")
    state_ttl_minutes: int = 15


class MeliCallbackBody(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)


class MeliCallbackResponse(BaseModel):
    ok: bool = True
    platform: str = "meli"
    user_id: str
    message: str = "Tokens do Mercado Livre salvos com sucesso."

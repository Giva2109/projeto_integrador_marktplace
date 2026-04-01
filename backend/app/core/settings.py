from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

# Garante .env carregado ao importar settings (uvicorn cwd = pasta backend).
load_dotenv()


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app_env: str = "dev"
    app_name: str = "Projeto Integrador Mercado Livre"

    supabase_url: str
    supabase_anon_key: str | None = None
    supabase_service_role_key: str

    token_crypto_secret: str

    meli_client_id: str
    meli_client_secret: str
    meli_redirect_uri: str

    shopee_partner_id: str | None = None
    shopee_partner_key: str | None = None
    shopee_redirect_uri: str | None = None


def _req(key: str) -> str:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        raise RuntimeError(f"Variável de ambiente obrigatória ausente ou vazia: {key}")
    return v


def load_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        app_name=os.getenv("APP_NAME", "Projeto Integrador Mercado Livre"),
        supabase_url=_req("SUPABASE_URL"),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or None,
        supabase_service_role_key=_req("SUPABASE_SERVICE_ROLE_KEY"),
        token_crypto_secret=_req("TOKEN_CRYPTO_SECRET"),
        meli_client_id=_req("MELI_CLIENT_ID"),
        meli_client_secret=_req("MELI_CLIENT_SECRET"),
        meli_redirect_uri=_req("MELI_REDIRECT_URI"),
        shopee_partner_id=os.getenv("SHOPEE_PARTNER_ID") or None,
        shopee_partner_key=os.getenv("SHOPEE_PARTNER_KEY") or None,
        shopee_redirect_uri=os.getenv("SHOPEE_REDIRECT_URI") or None,
    )


settings = load_settings()

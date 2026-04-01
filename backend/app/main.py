from __future__ import annotations

import os

from dotenv import load_dotenv

# Carregar .env antes de importar rotas que puxam `settings`.
load_dotenv()

from fastapi import FastAPI

from app.api.marketplace import router as marketplace_router
from app.api.oauth_meli import router as oauth_meli_router
from app.api.products import router as products_router

_DEFAULT_TITLE = "Projeto Integrador Mercado Livre"

app = FastAPI(
    title=os.getenv("APP_NAME", _DEFAULT_TITLE),
    description="API do integrador com Mercado Livre (hub de produtos e OAuth).",
)

app.include_router(products_router)
app.include_router(marketplace_router)
app.include_router(oauth_meli_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def log_meli_api_error(operation: str, resp: httpx.Response) -> dict[str, Any] | None:
    """
    Logs detalhados para depuração (token expirado, categoria inválida, validação).
    Retorna o JSON parseado quando existir.
    """
    status = resp.status_code
    body_text = resp.text
    parsed = _safe_json(body_text)

    logger.error(
        "Meli API falhou | operation={} | http_status={} | response_body={}",
        operation,
        status,
        body_text[:8000] if body_text else "",
    )

    if parsed is not None:
        err = parsed.get("error") or parsed.get("message")
        cause = parsed.get("cause")
        error_fields = []

        if isinstance(cause, list):
            for c in cause:
                if isinstance(c, dict):
                    error_fields.append(
                        {
                            "code": c.get("code"),
                            "message": c.get("message"),
                            "department": c.get("department"),
                        }
                    )
                else:
                    error_fields.append({"raw": str(c)})
        elif cause is not None:
            error_fields.append({"raw": str(cause)})

        # Token expirado / inválido
        if status == 401 or (isinstance(err, str) and err in ("invalid_token", "expired_token", "forbidden")):
            logger.error(
                "Meli auth | provável token expirado ou inválido | error={} | cause_summary={}",
                err,
                error_fields,
            )

        # Categoria e validação de domínio
        blob = json.dumps(parsed, ensure_ascii=False).lower()
        if "category" in blob or "categor" in blob:
            logger.error(
                "Meli categoria | verifique category_id e regras da categoria | error={} | cause={}",
                err,
                error_fields,
            )

        if error_fields:
            logger.error("Meli validação | campos/causas: {}", error_fields)

    return parsed


class MeliApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body_text: str,
        parsed: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body_text = body_text
        self.parsed = parsed

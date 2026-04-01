from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt


def create_meli_oauth_state(user_id: str, secret: str, *, ttl_minutes: int = 15) -> str:
    exp_dt = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {
        "sub": user_id,
        "typ": "meli_oauth",
        "exp": int(exp_dt.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def parse_meli_oauth_state(state_token: str, secret: str) -> str:
    try:
        claims = jwt.decode(state_token, secret, algorithms=["HS256"])
    except JWTError as e:
        raise ValueError("state inválido ou expirado.") from e
    if claims.get("typ") != "meli_oauth":
        raise ValueError("state não é do fluxo Meli.")
    sub = claims.get("sub")
    if not sub:
        raise ValueError("state sem usuário.")
    return str(sub)

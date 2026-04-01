from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenCrypto:
    """
    Minimal symmetric encryption for tokens before storing in DB.
    Uses AES-256-GCM with a key derived from a server secret.
    """

    _NONCE_BYTES: Final[int] = 12

    def __init__(self, secret: str):
        if not secret or len(secret) < 16:
            raise ValueError("token_crypto_secret must be set (>=16 chars).")
        self._key = hashlib.sha256(secret.encode("utf-8")).digest()

    def encrypt_to_b64(self, plaintext: str) -> str:
        nonce = os.urandom(self._NONCE_BYTES)
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
        blob = nonce + ct
        return base64.b64encode(blob).decode("ascii")

    def decrypt_from_b64(self, b64: str) -> str:
        blob = base64.b64decode(b64.encode("ascii"))
        nonce, ct = blob[: self._NONCE_BYTES], blob[self._NONCE_BYTES :]
        aesgcm = AESGCM(self._key)
        pt = aesgcm.decrypt(nonce, ct, associated_data=None)
        return pt.decode("utf-8")


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


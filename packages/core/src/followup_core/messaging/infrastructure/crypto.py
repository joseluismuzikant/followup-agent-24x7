"""Access tokens at rest: AES-256-GCM, with a key id prefix so keys can be rotated later
(new tokens use the current key; old ones still decrypt with theirs)."""

import base64
import binascii
import os
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12


class TokenCipherError(ValueError):
    pass


def parse_key(encoded: str) -> bytes:
    """A base64 key of exactly 32 bytes (TOKEN_ENCRYPTION_KEY)."""
    try:
        key = base64.b64decode(encoded.strip(), validate=True)
    except (binascii.Error, ValueError) as error:
        raise TokenCipherError("The encryption key is not valid base64.") from error
    if len(key) != 32:
        raise TokenCipherError("The encryption key must be 32 bytes.")
    return key


class TokenCipher:
    def __init__(self, keys: Mapping[str, bytes], current: str) -> None:
        if current not in keys:
            raise TokenCipherError(f"Unknown current key id '{current}'.")
        self._keys = {key_id: AESGCM(key) for key_id, key in keys.items()}
        self._current = current

    @classmethod
    def from_setting(cls, encoded: str, key_id: str = "k1") -> "TokenCipher":
        return cls({key_id: parse_key(encoded)}, key_id)

    def encrypt(self, token: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._keys[self._current].encrypt(nonce, token.encode(), self._current.encode())
        return f"{self._current}:{base64.b64encode(nonce + sealed).decode()}"

    def decrypt(self, stored: str) -> str:
        key_id, _, encoded = stored.partition(":")
        cipher = self._keys.get(key_id)
        if cipher is None or not encoded:
            raise TokenCipherError("Token encrypted with an unknown key.")
        try:
            raw = base64.b64decode(encoded, validate=True)
            return cipher.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], key_id.encode()).decode()
        except (InvalidTag, binascii.Error, ValueError) as error:
            raise TokenCipherError("The token could not be decrypted.") from error

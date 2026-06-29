"""
persistence/crypto.py
────────────────────────────────────────────────────────────────────────────
AES-256-GCM encrypted serializer for LangGraph checkpoints.

Extracted from checkpointer.py so it is importable and testable in isolation
without requiring langgraph-checkpoint-postgres or psycopg to be installed.
Only depends on pycryptodome and langgraph-checkpoint (core, lightweight).

Wire format per encrypted blob: nonce (16 B) | tag (16 B) | ciphertext
"""

from __future__ import annotations

from typing import Any

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


class EncryptedSerializer:
    """
    Wraps JsonPlusSerializer with AES-256-GCM authenticated encryption.

    Each value is encrypted with a fresh random 16-byte nonce, so every
    checkpoint row in Postgres is opaque ciphertext. The GCM tag provides
    integrity protection — tampered bytes raise an exception on decryption
    rather than silently producing garbage.
    """

    _MIN_ENCRYPTED_LEN = 32  # nonce + tag minimum, before any ciphertext

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError(f"AES-256 key must be exactly 32 bytes; got {len(key)}")
        self._key = key
        self._base = JsonPlusSerializer()

    @classmethod
    def from_pycryptodome_aes(cls, key: bytes) -> "EncryptedSerializer":
        return cls(key)

    def _encrypt(self, plaintext: bytes) -> bytes:
        nonce = get_random_bytes(16)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return nonce + tag + ciphertext

    def _decrypt(self, data: bytes) -> bytes:
        if len(data) < self._MIN_ENCRYPTED_LEN:
            raise ValueError(
                f"Encrypted blob is too short ({len(data)} B); "
                "expected at least 32 B (nonce + tag). "
                "The data may be corrupted or was not encrypted with this serializer."
            )
        nonce, tag, ciphertext = data[:16], data[16:32], data[32:]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        type_str, raw = self._base.dumps_typed(obj)
        return type_str, self._encrypt(raw)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        type_str, raw = data
        return self._base.loads_typed((type_str, self._decrypt(raw)))

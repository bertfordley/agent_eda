"""
persistence/checkpointer.py
────────────────────────────────────────────────────────────────────────────
LangGraph AsyncPostgresSaver lifecycle.

Public surface:
  open_checkpointer()  — async context manager used in FastAPI lifespan.
                         Opens the pool, sets the module-level holder,
                         closes on exit.
  get_checkpointer()   — returns the live saver (None when persistence is
                         disabled) for use in build_agent().

Design invariants (MUST NOT be violated):
  • Do NOT call checkpointer.setup() here. Schema creation belongs in the
    standalone migration script (poetry run init-checkpoints). Runtime code
    assumes tables exist.
  • DataFrames must never enter the checkpoint. Graph state is text-only;
    the DF cache is ephemeral and lives outside LangGraph state. Adding a
    DataFrame to graph state would cause the encrypted bytes for the entire
    frame to be rewritten to Postgres on every graph step — a documented
    bloat anti-pattern.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from typing import Any

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from config.settings import settings


# ── AES-256-GCM encrypted serializer ─────────────────────────────────────────

class EncryptedSerializer:
    """
    Wraps JsonPlusSerializer with AES-256-GCM authenticated encryption.

    Each value is encrypted with a fresh random 16-byte nonce, so every
    checkpoint row in Postgres is opaque ciphertext. The GCM tag provides
    integrity protection — tampered bytes raise ValueError on decryption
    rather than silently producing garbage.

    Wire format per encrypted blob: nonce (16 B) | tag (16 B) | ciphertext
    """

    _MIN_ENCRYPTED_LEN = 32  # nonce + tag, before ciphertext

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


# ── Module-level holder ───────────────────────────────────────────────────────

_checkpointer: AsyncPostgresSaver | None = None


def get_checkpointer() -> AsyncPostgresSaver | None:
    """
    Return the live AsyncPostgresSaver, or None when persistence is disabled.

    None is the valid no-op value — callers (build_agent, /health) must
    handle it without raising.
    """
    return _checkpointer


# ── Lifecycle context manager ─────────────────────────────────────────────────

@asynccontextmanager
async def open_checkpointer():
    """
    Async context manager for the checkpointer lifecycle. Intended for use
    in FastAPI's lifespan handler — call once at app startup, not per-request.

    On enter:
      1. Decode the AES-256 key from settings.
      2. Build an EncryptedSerializer.
      3. Open a psycopg AsyncConnectionPool (autocommit + dict_row required
         by AsyncPostgresSaver — omitting either raises at runtime).
      4. Instantiate AsyncPostgresSaver and set the module-level holder.

    On exit: clear the holder, then close the pool (psycopg drains in-flight
    queries before closing).

    Only call this when settings.checkpoint_enabled is True. Calling it when
    disabled is a programming error, not a configuration error.
    """
    global _checkpointer

    key = base64.b64decode(settings.checkpoint_encryption_key)
    serde = EncryptedSerializer.from_pycryptodome_aes(key)

    async with AsyncConnectionPool(
        conninfo=settings.checkpoint_db_uri,
        min_size=settings.checkpoint_pool_min,
        max_size=settings.checkpoint_pool_max,
        kwargs={"autocommit": True, "row_factory": dict_row},
    ) as pool:
        _checkpointer = AsyncPostgresSaver(pool, serde=serde)
        try:
            yield _checkpointer
        finally:
            _checkpointer = None

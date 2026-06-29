"""
Unit tests for persistence/checkpointer.py — EncryptedSerializer.

These tests verify AES-256-GCM encrypt/decrypt round-trips and tamper detection
without any database connection. pycryptodome is a direct project dependency.
"""

from __future__ import annotations

import os

import pytest

from persistence.crypto import EncryptedSerializer


def _make_serializer(key_len: int = 32) -> EncryptedSerializer:
    return EncryptedSerializer(os.urandom(key_len))


# ── Key validation ────────────────────────────────────────────────────────────


def test_key_too_short_raises():
    with pytest.raises(ValueError, match="32 bytes"):
        EncryptedSerializer(os.urandom(16))


def test_key_too_long_raises():
    with pytest.raises(ValueError, match="32 bytes"):
        EncryptedSerializer(os.urandom(64))


def test_key_zero_bytes_raises():
    with pytest.raises(ValueError, match="32 bytes"):
        EncryptedSerializer(b"")


def test_exactly_32_bytes_succeeds():
    EncryptedSerializer(os.urandom(32))


# ── Encrypt / decrypt round-trip ──────────────────────────────────────────────


def test_encrypt_decrypt_roundtrip():
    serde = _make_serializer()
    plaintext = b"Hello, AES-256-GCM!"

    ciphertext = serde._encrypt(plaintext)
    result = serde._decrypt(ciphertext)

    assert result == plaintext


def test_encrypt_produces_different_ciphertext_each_time():
    serde = _make_serializer()
    plaintext = b"same plaintext"

    ct1 = serde._encrypt(plaintext)
    ct2 = serde._encrypt(plaintext)

    # Fresh nonce each call → different ciphertext
    assert ct1 != ct2


def test_encrypted_blob_length():
    serde = _make_serializer()
    plaintext = b"x" * 100

    ciphertext = serde._encrypt(plaintext)

    # Wire format: 16 (nonce) + 16 (tag) + len(plaintext)
    assert len(ciphertext) == 16 + 16 + len(plaintext)


def test_decrypt_too_short_raises():
    serde = _make_serializer()
    with pytest.raises(ValueError, match="too short"):
        serde._decrypt(b"\x00" * 31)  # one byte short of nonce+tag minimum


def test_decrypt_empty_plaintext_blob():
    # An empty plaintext is valid; blob is exactly 32 bytes (nonce + tag)
    serde = _make_serializer()
    ciphertext = serde._encrypt(b"")
    assert serde._decrypt(ciphertext) == b""


# ── Tamper detection (GCM tag verification) ───────────────────────────────────


def _flip_byte(data: bytes, index: int) -> bytes:
    """Return data with the byte at index XOR'd with 0xFF."""
    arr = bytearray(data)
    arr[index] ^= 0xFF
    return bytes(arr)


def test_tamper_nonce_raises():
    serde = _make_serializer()
    ct = serde._encrypt(b"secret")
    tampered = _flip_byte(ct, 0)  # flip first nonce byte
    with pytest.raises(Exception):
        serde._decrypt(tampered)


def test_tamper_tag_raises():
    serde = _make_serializer()
    ct = serde._encrypt(b"secret")
    tampered = _flip_byte(ct, 16)  # flip first tag byte
    with pytest.raises(Exception):
        serde._decrypt(tampered)


def test_tamper_ciphertext_raises():
    serde = _make_serializer()
    ct = serde._encrypt(b"secret data that is long enough here")
    tampered = _flip_byte(ct, 32)  # flip first ciphertext byte
    with pytest.raises(Exception):
        serde._decrypt(tampered)


# ── dumps_typed / loads_typed round-trip ──────────────────────────────────────


def test_dumps_loads_typed_roundtrip_string():
    serde = _make_serializer()

    type_str, encrypted = serde.dumps_typed("hello world")
    result = serde.loads_typed((type_str, encrypted))

    assert result == "hello world"


def test_dumps_loads_typed_roundtrip_dict():
    serde = _make_serializer()
    data = {"messages": [{"role": "user", "content": "hi"}], "count": 42}

    type_str, encrypted = serde.dumps_typed(data)
    result = serde.loads_typed((type_str, encrypted))

    assert result == data


def test_dumps_loads_typed_roundtrip_none():
    serde = _make_serializer()

    type_str, encrypted = serde.dumps_typed(None)
    result = serde.loads_typed((type_str, encrypted))

    assert result is None


def test_loads_typed_with_tampered_bytes_raises():
    serde = _make_serializer()
    type_str, encrypted = serde.dumps_typed({"key": "value"})
    tampered = _flip_byte(encrypted, 32)  # flip a ciphertext byte
    with pytest.raises(Exception):
        serde.loads_typed((type_str, tampered))


def test_wrong_key_raises():
    key1 = os.urandom(32)
    key2 = os.urandom(32)
    serde1 = EncryptedSerializer(key1)
    serde2 = EncryptedSerializer(key2)

    type_str, encrypted = serde1.dumps_typed("secret")
    with pytest.raises(Exception):
        serde2.loads_typed((type_str, encrypted))

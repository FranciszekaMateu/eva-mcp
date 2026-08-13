"""Tests del módulo de credenciales (keyring mockeado + cifrado Fernet)."""

from __future__ import annotations

import pytest

from eva_cli import credentials


@pytest.fixture
def fake_keyring(monkeypatch):
    """Reemplaza keyring por un dict en memoria (no toca el llavero real)."""
    store: dict[str, str] = {}

    def get_password(service: str, key: str) -> str | None:
        assert service == credentials.SERVICE
        return store.get(key)

    def set_password(service: str, key: str, value: str) -> None:
        assert service == credentials.SERVICE
        store[key] = value

    def delete_password(service: str, key: str) -> None:
        assert service == credentials.SERVICE
        store.pop(key, None)

    monkeypatch.setattr(credentials.keyring, "get_password", get_password)
    monkeypatch.setattr(credentials.keyring, "set_password", set_password)
    monkeypatch.setattr(credentials.keyring, "delete_password", delete_password)
    return store


def test_store_and_get_credentials(fake_keyring):
    credentials.store_credentials("53087475", "secreta")
    assert credentials.get_credential(credentials.USER_KEY) == "53087475"
    assert credentials.get_credential(credentials.PASS_KEY) == "secreta"


def test_clear_credentials(fake_keyring):
    credentials.store_credentials("u", "p")
    credentials.encrypt_bytes(b"x")  # genera la clave de cookie en el store
    credentials.clear_credentials()
    assert fake_keyring == {}


def test_encrypt_decrypt_roundtrip(fake_keyring):
    token = credentials.encrypt_bytes(b"sesion secreta")
    assert token != b"sesion secreta"
    assert credentials.decrypt_bytes(token) == b"sesion secreta"


def test_decrypt_invalid_token_returns_none(fake_keyring):
    assert credentials.decrypt_bytes(b"no-es-un-token-fernet") is None

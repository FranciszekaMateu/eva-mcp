"""Gestión segura de secretos: keyring del SO + cifrado de la cookie de sesión.

La contraseña del EVA se guarda en el llavero del sistema operativo (Windows
Credential Manager vía DPAPI, macOS Keychain, Linux Secret Service) en vez de
texto plano. La cookie de sesión se cifra con Fernet usando una clave maestra
que también vive en el llavero, de modo que ni contraseña ni sesión quedan
legibles en disco.
"""

from __future__ import annotations

import contextlib

import keyring
from cryptography.fernet import Fernet, InvalidToken

SERVICE = "eva-mcp"
USER_KEY = "EVA_USER"
PASS_KEY = "EVA_PASS"
COOKIE_KEY = "cookie_key"


# --------------------------------------------------------------------------- #
# Credenciales (keyring)
# --------------------------------------------------------------------------- #
def store_credentials(user: str, password: str) -> None:
    """Guarda las credenciales en el llavero del sistema."""
    keyring.set_password(SERVICE, USER_KEY, user)
    keyring.set_password(SERVICE, PASS_KEY, password)


def get_credential(key: str) -> str | None:
    """Lee una credencial del llavero (``None`` si no existe)."""
    return keyring.get_password(SERVICE, key)


def clear_credentials() -> None:
    """Borra credenciales y clave de cookie del llavero (no falla si no existen)."""
    for key in (USER_KEY, PASS_KEY, COOKIE_KEY):
        with contextlib.suppress(keyring.errors.KeyringError):
            keyring.delete_password(SERVICE, key)


# --------------------------------------------------------------------------- #
# Cookie de sesión (Fernet con clave maestra en keyring)
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    key = get_credential(COOKIE_KEY)
    if key is None:
        key = Fernet.generate_key().decode()
        keyring.set_password(SERVICE, COOKIE_KEY, key)
    return Fernet(key.encode())


def encrypt_bytes(data: bytes) -> bytes:
    """Cifra ``data`` (devuelve un token Fernet)."""
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes | None:
    """Descifra ``token``; ``None`` si la clave cambió o el token es inválido."""
    try:
        return _fernet().decrypt(token)
    except (InvalidToken, ValueError):
        return None

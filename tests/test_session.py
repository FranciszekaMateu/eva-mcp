"""Tests de session.py: resolución de credenciales y cookie cifrada."""

from __future__ import annotations

import httpx
import pytest

from eva_cli import credentials, session
from eva_cli.session import load_credentials


def _sin_env(monkeypatch) -> None:
    monkeypatch.delenv("EVA_USER", raising=False)
    monkeypatch.delenv("EVA_PASS", raising=False)


def _fake_load_dotenv(monkeypatch):
    """Hace que load_dotenv() sin path sea no-op (no carga el .env del cwd real)."""
    import dotenv

    def fake(path=None, **kwargs):
        if path is not None:
            dotenv.load_dotenv(path, **kwargs)

    monkeypatch.setattr(session, "load_dotenv", fake)


def test_env_vars_tienen_prioridad(monkeypatch):
    monkeypatch.setenv("EVA_USER", "env_user")
    monkeypatch.setenv("EVA_PASS", "env_pass")
    monkeypatch.setattr(credentials, "get_credential", lambda k: "keyring_val")
    assert load_credentials() == ("env_user", "env_pass")


def test_keyring_como_segunda_opcion(monkeypatch):
    _sin_env(monkeypatch)
    _fake_load_dotenv(monkeypatch)
    monkeypatch.setattr(session, "_env_candidates", lambda: [])
    monkeypatch.setattr(
        credentials, "get_credential", lambda k: {"EVA_USER": "ku", "EVA_PASS": "kp"}.get(k)
    )
    assert load_credentials() == ("ku", "kp")


def test_dotenv_como_fallback(monkeypatch, tmp_path):
    _sin_env(monkeypatch)
    _fake_load_dotenv(monkeypatch)
    monkeypatch.setattr(credentials, "get_credential", lambda k: None)
    env_file = tmp_path / ".env"
    env_file.write_text("EVA_USER=dotenv_user\nEVA_PASS=dotenv_pass\n")
    monkeypatch.setattr(session, "_env_candidates", lambda: [env_file])
    assert load_credentials() == ("dotenv_user", "dotenv_pass")


def test_sin_credenciales_lanza_error(monkeypatch):
    _sin_env(monkeypatch)
    _fake_load_dotenv(monkeypatch)
    monkeypatch.setattr(session, "_env_candidates", lambda: [])
    monkeypatch.setattr(credentials, "get_credential", lambda k: None)
    with pytest.raises(RuntimeError, match="credenciales"):
        load_credentials()


def test_cookie_save_load_roundtrip_cifrado(monkeypatch, tmp_path):
    # keyring en memoria para la clave Fernet
    store: dict[str, str] = {}
    monkeypatch.setattr(credentials.keyring, "get_password", lambda s, k: store.get(k))
    monkeypatch.setattr(
        credentials.keyring, "set_password", lambda s, k, v: store.__setitem__(k, v)
    )
    monkeypatch.setattr(session, "SESSION_FILE", tmp_path / "cookies.enc")

    client = httpx.Client()
    client.cookies.set("MoodleSessionfing", "abc123", domain="eva.fing.edu.uy")
    session._save_cookie(client)

    # El archivo es binario cifrado: no contiene la cookie en claro
    raw = (tmp_path / "cookies.enc").read_bytes()
    assert b"abc123" not in raw

    client2 = httpx.Client()
    assert session._load_cookie(client2) is True
    assert "MoodleSessionfing" in {c.name for c in client2.cookies.jar}


def test_load_cookie_sin_archivo_devuelve_false(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "SESSION_FILE", tmp_path / "no-existe.enc")
    assert session._load_cookie(httpx.Client()) is False

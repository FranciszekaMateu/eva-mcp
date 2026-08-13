"""Gestión de credenciales y sesión, compartida entre el CLI y el MCP.

Centraliza la lectura de credenciales (entorno o ``.env``), el cacheo de la
sesión autenticada en disco y la creación de un :class:`EvaClient` listo para
usar. Tanto ``eva`` (CLI) como ``eva-mcp`` (servidor MCP) consumen de acá para
no duplicar lógica.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from eva_cli.auth import EVA_BASE, USER_AGENT, EvaSession
from eva_cli.client import EvaClient

# Directorio de datos de la app (override con EVA_CLI_DIR).
APP_DIR = Path(os.environ.get("EVA_CLI_DIR", Path.home() / ".eva-cli"))
SESSION_FILE = APP_DIR / "cookies.txt"


def _project_root() -> Path:
    """Raíz del proyecto (src/eva_cli/ → dos niveles arriba)."""
    return Path(__file__).resolve().parent.parent.parent


def _env_candidates() -> list[Path]:
    """Rutas candidatas para el archivo ``.env`` (de más a menos específica)."""
    return [
        Path.cwd() / ".env",
        APP_DIR / ".env",
        _project_root() / ".env",
    ]


def load_credentials() -> tuple[str, str]:
    """Lee ``EVA_USER`` / ``EVA_PASS`` del entorno o de un ``.env``.

    Levanta :class:`RuntimeError` si faltan, para que cada interfaz (CLI/MCP)
    lo traduzca a su propio formato de error.
    """
    load_dotenv()  # .env del cwd (comportamiento estándar)
    for path in _env_candidates():
        load_dotenv(path, override=False)  # no pisa variables de entorno ya seteadas
    user = os.environ.get("EVA_USER", "")
    password = os.environ.get("EVA_PASS", "")
    if not user or not password:
        raise RuntimeError(
            "Faltan credenciales. Configurá EVA_USER y EVA_PASS en un archivo .env "
            "o como variables de entorno."
        )
    return user, password


def _client_from_cached_session() -> EvaClient | None:
    """Reutiliza la sesión cacheada en disco; ``None`` si no sirve."""
    if not SESSION_FILE.exists():
        return None
    try:
        client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            client.cookies.jar.load(str(SESSION_FILE), ignore_discard=True, ignore_expires=True)
        except Exception:
            client.close()
            return None
        resp = client.get(f"{EVA_BASE}/my/")
        if resp.status_code == 200 and "login" not in resp.url.host:
            return EvaClient(session=EvaSession(client=client))
        client.close()
    except Exception:
        pass
    return None


def get_client(*, reutilizar: bool = True) -> EvaClient:
    """Devuelve un cliente autenticado, reutilizando la sesión cacheada si vive.

    Si no hay sesión cacheada (o expiró), hace el login SAML fresco y guarda
    las cookies para la próxima vez.
    """
    user, password = load_credentials()
    if reutilizar:
        cached = _client_from_cached_session()
        if cached is not None:
            return cached
    session = EvaSession.login(user, password)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # El guardado de cookies es best-effort: no debe romper una sesión ya válida.
    with contextlib.suppress(Exception):
        session.client.cookies.jar.save(str(SESSION_FILE), ignore_discard=True, ignore_expires=True)
    return EvaClient(session=session)

"""Gestión de credenciales y sesión, compartida entre el CLI y el MCP.

Resolución de credenciales (de mayor a menor prioridad):
  1. Variables de entorno ``EVA_USER`` / ``EVA_PASS`` (CI/containers).
  2. Llavero del sistema operativo (ver :mod:`eva_cli.credentials`).
  3. Archivo ``.env`` (fallback legacy, texto plano).

La cookie de sesión se guarda cifrada en ``~/.eva-cli/cookies.enc`` (Fernet con
clave maestra en el llavero), de modo que no queda texto plano en disco.
"""

from __future__ import annotations

import contextlib
import http.cookiejar
import os
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

from eva_cli import credentials
from eva_cli.auth import EVA_BASE, USER_AGENT, EvaSession
from eva_cli.client import EvaClient

# Directorio de datos de la app (override con EVA_CLI_DIR).
APP_DIR = Path(os.environ.get("EVA_CLI_DIR", Path.home() / ".eva-cli"))
SESSION_FILE = APP_DIR / "cookies.enc"  # cifrado (Fernet)
LEGACY_SESSION_FILE = APP_DIR / "cookies.txt"  # formato viejo (texto plano)


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
    """Resuelve ``EVA_USER`` / ``EVA_PASS`` en orden: entorno → keyring → .env.

    Levanta :class:`RuntimeError` si faltan, para que cada interfaz (CLI/MCP)
    lo traduzca a su propio formato de error.
    """
    # 1. Variables de entorno reales (antes de tocar .env)
    user = os.environ.get("EVA_USER", "")
    password = os.environ.get("EVA_PASS", "")
    # 2. Llavero del sistema (seguro)
    if not user:
        user = credentials.get_credential(credentials.USER_KEY) or ""
    if not password:
        password = credentials.get_credential(credentials.PASS_KEY) or ""
    # 3. .env (fallback legacy)
    if not user or not password:
        load_dotenv()
        for path in _env_candidates():
            load_dotenv(path, override=False)
        user = user or os.environ.get("EVA_USER", "")
        password = password or os.environ.get("EVA_PASS", "")
    if not user or not password:
        raise RuntimeError(
            "Faltan credenciales. Ejecutá `eva login` (las guarda en el llavero del "
            "sistema) o configurá EVA_USER/EVA_PASS en un archivo .env o variables "
            "de entorno."
        )
    return user, password


# --------------------------------------------------------------------------- #
# Cookie de sesión cifrada
# --------------------------------------------------------------------------- #
def _save_cookie(client: httpx.Client) -> None:
    """Serializa las cookies (formato Netscape) a un temporal, cifra y persiste."""
    jar = http.cookiejar.MozillaCookieJar()
    for cookie in client.cookies.jar:
        jar.set_cookie(cookie)
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        jar.save(tmp, ignore_discard=True, ignore_expires=True)
        SESSION_FILE.write_bytes(credentials.encrypt_bytes(Path(tmp).read_bytes()))
    finally:
        Path(tmp).unlink(missing_ok=True)


def _load_cookie(client: httpx.Client) -> bool:
    """Carga las cookies descifrando ``cookies.enc``; ``False`` si no se puede."""
    if not SESSION_FILE.exists():
        return False
    data = credentials.decrypt_bytes(SESSION_FILE.read_bytes())
    if data is None:
        return False
    jar = http.cookiejar.MozillaCookieJar()
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        Path(tmp).write_bytes(data)
        jar.load(tmp, ignore_discard=True, ignore_expires=True)
        for cookie in jar:
            client.cookies.jar.set_cookie(cookie)
        return True
    finally:
        Path(tmp).unlink(missing_ok=True)


def _client_from_cached_session() -> EvaClient | None:
    """Reutiliza la sesión cacheada (cifrada); ``None`` si no sirve o no existe."""
    # Migración one-shot del formato viejo (texto plano) si aún existe.
    if not SESSION_FILE.exists() and LEGACY_SESSION_FILE.exists():
        _migrate_legacy_cookie()

    if not SESSION_FILE.exists():
        return None
    try:
        client = httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
        )
        if not _load_cookie(client):
            client.close()
            return None
        resp = client.get(f"{EVA_BASE}/my/")
        if resp.status_code == 200 and "login" not in resp.url.host:
            return EvaClient(session=EvaSession(client=client))
        client.close()
    except Exception:
        pass
    return None


def _migrate_legacy_cookie() -> None:
    """Convierte ``cookies.txt`` (texto plano) a ``cookies.enc`` (cifrado)."""
    if not LEGACY_SESSION_FILE.exists():
        return
    client = httpx.Client(follow_redirects=True, timeout=30.0, headers={"User-Agent": USER_AGENT})
    try:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(str(LEGACY_SESSION_FILE), ignore_discard=True, ignore_expires=True)
        for cookie in jar:
            client.cookies.jar.set_cookie(cookie)
        resp = client.get(f"{EVA_BASE}/my/")
        if resp.status_code == 200 and "login" not in resp.url.host:
            _save_cookie(client)
            LEGACY_SESSION_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Cliente autenticado
# --------------------------------------------------------------------------- #
def get_client(*, reutilizar: bool = True) -> EvaClient:
    """Devuelve un cliente autenticado, reutilizando la sesión cacheada si vive.

    Si no hay sesión cacheada (o expiró), hace el login SAML fresco y guarda las
    cookies cifradas para la próxima vez.
    """
    user, password = load_credentials()
    if reutilizar:
        cached = _client_from_cached_session()
        if cached is not None:
            return cached
    session = EvaSession.login(user, password)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # El guardado de la cookie es best-effort: no debe romper una sesión ya válida.
    with contextlib.suppress(Exception):
        _save_cookie(session.client)
    return EvaClient(session=session)


def clear_session() -> None:
    """Borra la cookie de sesión cifrada y cualquier archivo legacy."""
    SESSION_FILE.unlink(missing_ok=True)
    LEGACY_SESSION_FILE.unlink(missing_ok=True)

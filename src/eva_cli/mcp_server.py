"""Servidor MCP del EVA FING — tools ``mcp__eva__*`` para Hermes.

Expone :class:`EvaClient` como tools MCP (protocolo stdio) consumibles por
Hermes o cualquier cliente MCP. Cada tool devuelve estructuras JSON simples
(dicts/listas) para que el agente las interprete sin lógica adicional.

Las credenciales se resuelven igual que en el CLI (entorno o ``.env``), y la
sesión se cachea en un singleton protegido por un lock.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import asdict
from typing import Any

# Blindaje contra PYTHONPATH contaminado: cuando Hermes lanza este server, el
# entorno puede traer el site-packages del agente (que incluye un ``mcp``
# distinto). Quitamos esas rutas para que ``import fastmcp``/``mcp`` resuelvan
# SIEMPRE desde el venv de este proyecto.
sys.path[:] = [p for p in sys.path if "hermes-agent" not in p]

from fastmcp import FastMCP  # noqa: E402

from eva_cli.client import EvaClient  # noqa: E402
from eva_cli.paths import normalize_path  # noqa: E402
from eva_cli.session import get_client  # noqa: E402

mcp = FastMCP(
    "eva",
    instructions=(
        "Acceso al EVA FING (Moodle de la Facultad de Ingeniería, UdelaR): "
        "cursos, avisos de foros, actividades, calendario y material de estudio. "
        "Las respuestas son JSON. Usá eva_cursos para obtener los ids/nombres y "
        "luego consultá el resto por nombre o id."
    ),
)

_client: EvaClient | None = None
_lock = threading.Lock()


def _eva() -> EvaClient:
    """Cliente autenticado cacheado (login fresco la primera vez)."""
    global _client
    with _lock:
        if _client is None:
            _client = get_client()
        return _client


@mcp.tool
def eva_cursos() -> list[dict[str, Any]]:
    """Lista los cursos matriculados en el EVA (id, nombre, código)."""
    return [asdict(c) for c in _eva().cursos()]


@mcp.tool
def eva_avisos(curso: str, limite: int = 10) -> list[dict[str, Any]]:
    """Últimos avisos del foro de un curso (nombre, código o id)."""
    return [asdict(a) for a in _eva().avisos(curso, limite=limite)]


@mcp.tool
def eva_aviso(discusion_id: int) -> str:
    """Texto completo de un aviso (id de la discusión)."""
    return _eva().aviso_detalle(discusion_id)


@mcp.tool
def eva_actividades(curso: str, seccion: str | None = None) -> list[dict[str, Any]]:
    """Actividades de un curso, opcionalmente filtradas por sección."""
    return [asdict(a) for a in _eva().actividades(curso, seccion=seccion)]


@mcp.tool
def eva_calendario(mes: int | None = None, anio: int | None = None) -> list[dict[str, Any]]:
    """Eventos del calendario (por defecto el mes actual)."""
    return [asdict(e) for e in _eva().calendario(mes=mes, anio=anio)]


@mcp.tool
def eva_material(curso: str) -> list[dict[str, Any]]:
    """Materiales (archivos y páginas) de un curso, sin descargar."""
    return [asdict(a) for a in _eva().material(curso)]


@mcp.tool
def eva_descargar_material(curso: str, destino: str) -> list[dict[str, Any]]:
    """Descarga los materiales de un curso a `destino` y devuelve las rutas.

    `destino` acepta rutas Windows nativas, ``~/...`` y rutas MSYS (``/tmp/...``,
    ``/c/Users/...``); se normalizan automáticamente.
    """
    return [asdict(a) for a in _eva().material(curso, destino=normalize_path(destino))]


@mcp.tool
def eva_login() -> str:
    """Fuerza un login fresco, descartando la sesión cacheada."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
        _client = get_client(reutilizar=False)
    return "Login OK"


def main() -> None:
    """Entry point del servidor MCP (stdio)."""
    mcp.run()


if __name__ == "__main__":
    main()

"""Tests del servidor MCP: registro de tools y firma de cada una."""

from __future__ import annotations

import asyncio

import eva_cli.mcp_server as server


def _nombres_tools() -> set[str]:
    async def go():
        return {t.name for t in await server.mcp.list_tools()}

    return asyncio.run(go())


def test_tools_registradas():
    esperadas = {
        "eva_cursos",
        "eva_avisos",
        "eva_aviso",
        "eva_actividades",
        "eva_calendario",
        "eva_material",
        "eva_descargar_material",
        "eva_login",
    }
    assert esperadas <= _nombres_tools()

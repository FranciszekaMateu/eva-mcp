"""Smoke tests de la interfaz CLI (typer)."""

from __future__ import annotations

from typer.testing import CliRunner

import eva_cli.cli as cli
from eva_cli.cli import app

runner = CliRunner()


def test_help_lista_comandos():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in [
        "login",
        "logout",
        "cursos",
        "avisos",
        "aviso",
        "actividades",
        "cal",
        "material",
    ]:
        assert cmd in result.stdout


def test_sin_credenciales_muestra_error(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("Faltan credenciales. Ejecutá `eva login`.")

    monkeypatch.setattr(cli, "get_client", _boom)
    result = runner.invoke(app, ["cursos"])
    assert result.exit_code != 0
    assert "credenciales" in result.stdout.lower()

"""Smoke tests de la interfaz CLI (typer)."""

from __future__ import annotations

from typer.testing import CliRunner

from eva_cli.cli import app

runner = CliRunner()


def test_help_lista_comandos():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["login", "cursos", "avisos", "aviso", "actividades", "cal", "material"]:
        assert cmd in result.stdout


def test_sin_credenciales_muestra_error():
    result = runner.invoke(app, ["cursos"], env={"EVA_USER": "", "EVA_PASS": ""})
    assert result.exit_code != 0
    assert (
        "credenciales" in result.stdout.lower() or "credenciales" in str(result.exception).lower()
    )

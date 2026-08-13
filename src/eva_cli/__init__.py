"""eva-cli: acceso headless al EVA FING para humanos y agentes."""

from eva_cli.auth import EvaAuthError, EvaSession
from eva_cli.client import Actividad, Aviso, Curso, EvaClient, EventoCalendario
from eva_cli.paths import normalize_path
from eva_cli.session import get_client, load_credentials

__all__ = [
    "Actividad",
    "Aviso",
    "Curso",
    "EvaAuthError",
    "EvaClient",
    "EvaSession",
    "EventoCalendario",
    "get_client",
    "load_credentials",
    "normalize_path",
]

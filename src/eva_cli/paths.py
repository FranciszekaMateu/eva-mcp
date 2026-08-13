"""Normalización de rutas MSYS/POSIX → Windows nativo.

En git-bash/MSYS, rutas estilo ``/c/Users/...`` o ``/tmp/...`` llegan a Python
(un proceso nativo de Windows) como texto POSIX que Windows no resuelve igual:
``/tmp/x`` se convierte en ``C:\\tmp\\x`` (raíz del drive actual) en vez del
directorio temporal real. Estas funciones las convierten a rutas Windows
válidas para que ``eva material -d /tmp/x`` y ``-d /c/Users/...`` se comporten
igual que sus equivalentes nativos.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# /c/Users/...  ó  /d/  →  C:\Users\...  ó  D:\
_DRIVE_RE = re.compile(r"^/([a-zA-Z])(?:/|$)")
# /tmp/... → directorio temporal de Windows
_TMP_RE = re.compile(r"^/tmp(?:/|$)")


def normalize_path(value: str | os.PathLike[str] | Path) -> Path:
    """Convierte una ruta escrita por el usuario a un ``Path`` nativo.

    Reglas (solo cuando corre sobre Windows):
      - ``~/...``           → directorio home del usuario (``Path.expanduser``).
      - ``/c/Users/...``    → ``C:\\Users\\...`` (conversión MSYS→Windows).
      - ``/tmp/...``        → ``%TEMP%\\...`` (o ``%TMP%``).
      - ``C:\\Users\\...``   → se deja tal cual (ya es nativa).
      - resto              → ``Path(value)`` tal cual.

    Fuera de Windows devuelve ``Path(value).expanduser()`` sin tocar nada.
    """
    path = Path(value).expanduser()
    if sys.platform != "win32":
        return path

    s = os.fspath(value)
    # Sólo se normalizan rutas POSIX absolutas; las nativas (C:\...) no.
    if not (s.startswith("/") and not s.startswith("//")):
        return path

    m = _DRIVE_RE.match(s)
    if m:
        drive = m.group(1).upper()
        rest = s[len(m.group(0)) :].lstrip("/")
        return Path(f"{drive}:\\") / rest if rest else Path(f"{drive}:\\")

    if _TMP_RE.match(s):
        base = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Windows\Temp"
        rest = s[len("/tmp") :].lstrip("/")
        return Path(base) / rest if rest else Path(base)

    return path

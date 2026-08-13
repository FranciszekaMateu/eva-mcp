"""Tests de normalización de rutas MSYS → Windows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from eva_cli.paths import normalize_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="normalización MSYS→Windows solo aplica en Windows"
)


def test_home_expansion():
    p = normalize_path("~/Documents/eva")
    assert p == Path.home() / "Documents" / "eva"


def test_msys_drive_path():
    p = normalize_path("/c/Users/Francisco/Documents")
    assert str(p).lower().replace("\\", "/") == "c:/users/francisco/documents"


def test_msys_drive_root():
    p = normalize_path("/d")
    assert str(p).lower().replace("\\", "/") == "d:/"


def test_msys_tmp_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.delenv("TMP", raising=False)
    p = normalize_path("/tmp/eva/material")
    assert p == tmp_path / "eva" / "material"


def test_msys_tmp_root(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.delenv("TMP", raising=False)
    p = normalize_path("/tmp")
    assert p == tmp_path


def test_native_windows_path_untouched():
    p = normalize_path(r"C:\Users\Fran\doc")
    assert p == Path(r"C:\Users\Fran\doc")

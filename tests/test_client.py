"""Tests del scraping de Moodle (cursos, avisos, actividades, calendario)."""

from __future__ import annotations

import httpx
import pytest

from eva_cli.auth import EvaSession
from eva_cli.client import EvaClient

CURSO_HTML = """
<html><body>
  <a href="/mod/forum/view.php?id=100">Foro de avisos</a>
  <a href="/mod/forum/view.php?id=101">Foro general</a>
  <a href="/course/view.php?id=62&section=1">Semana 1</a>
  <a href="/mod/resource/view.php?id=500">Práctico 1 - Enunciado Archivo</a>
  <a href="/mod/page/view.php?id=501">Notas de teórico Página</a>
</body></html>
"""

MY_HTML = """
<html><body>
  <a href="/course/view.php?id=62">Métodos Numéricos</a>
  <a href="/course/view.php?id=947">BD NoSQL</a>
  <a href="/course/view.php?id=62">Métodos Numéricos (dup)</a>
  <a href="/">Inicio</a>
</body></html>
"""

AMBIGUO_HTML = """
<html><body>
  <a href="/course/view.php?id=62">Métodos Numéricos</a>
  <a href="/course/view.php?id=63">Métodos Numéricos Avanzados</a>
</body></html>
"""

FORO_HTML = """
<html><body><table>
  <tr class="discussion">
    <td><a href="/mod/forum/discuss.php?d=11740">Aviso importante</a></td>
    <td><div class="author-info"><span class="text-truncate">Prof. X</span></div></td>
    <td><time data-timestamp="1234567">12 agosto 2026</time></td>
    <td>3 respuestas</td>
  </tr>
</table></body></html>
"""

CAL_HTML = """
<html><body>
  <td data-day="16">
    <li data-region="event-item">
      <a data-action="view-event" data-event-id="7" href="/calendar/view.php?view=day" title="Entrega semana 0"></a>
    </li>
  </td>
</body></html>
"""


def _cliente(handler) -> EvaClient:
    session = EvaSession(client=httpx.Client(transport=httpx.MockTransport(handler)))
    return EvaClient(session=session)


def _static(html: str):
    return _cliente(lambda request: httpx.Response(200, text=html))


def test_cursos_ordenados_y_sin_duplicados():
    cursos = _static(MY_HTML).cursos()
    # Orden alfabético: "BD NoSQL" (947) antes que "Métodos Numéricos" (62)
    assert [(c.id, c.nombre) for c in cursos] == [
        (947, "BD NoSQL"),
        (62, "Métodos Numéricos"),
    ]


def test_avisos_extrae_autor_fecha_respuestas():
    def handler(request: httpx.Request) -> httpx.Response:
        if "forum/view" in request.url.path:
            return httpx.Response(200, text=FORO_HTML)
        return httpx.Response(200, text=CURSO_HTML)

    avisos = _cliente(handler).avisos(62)
    assert len(avisos) == 1
    a = avisos[0]
    assert a.id == 11740
    assert a.titulo == "Aviso importante"
    assert a.autor == "Prof. X"
    assert a.fecha == "12 agosto 2026"
    assert a.respuestas == 3


def test_actividades_limpia_sufijo_y_sin_duplicados():
    act = _static(CURSO_HTML).actividades(62)
    nombres = {a.nombre for a in act}
    tipos = {a.tipo for a in act}
    assert {"resource", "page", "forum"} <= tipos
    assert "Práctico 1 - Enunciado" in nombres
    assert "Notas de teórico" in nombres
    # Cada actividad (tipo, id) aparece una sola vez aunque el HTML se repita
    claves = [(a.tipo, a.id) for a in act]
    assert len(claves) == len(set(claves))


def test_material_filtra_resource_y_page():
    mats = _static(CURSO_HTML).material(62)
    assert mats, "material() debería devolver al menos un recurso"
    assert all(a.tipo in ("resource", "page") for a in mats)


def test_calendario_extrae_fecha_y_titulo():
    eventos = _static(CAL_HTML).calendario()
    assert len(eventos) == 1
    e = eventos[0]
    assert e.id == 7
    assert e.titulo == "Entrega semana 0"
    assert e.fecha.startswith("16/")


def test_curso_ref_ambiguo_lanza_error():
    with pytest.raises(ValueError, match="varios cursos"):
        _static(AMBIGUO_HTML).avisos("métodos")


def test_curso_ref_inexistente_lanza_error():
    with pytest.raises(ValueError, match="No se encontró el curso"):
        _static(MY_HTML).avisos("curso-inexistente")

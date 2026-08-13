"""Cliente de scraping para el EVA FING (Moodle).

Expone operaciones de lectura sobre la sesión autenticada: cursos,
avisos de foros, actividades por sección, calendario y descarga de
archivos. Selectores validados contra el EVA real (ago-2026).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from eva_cli.auth import EVA_BASE, EvaSession

_MOD_RE = re.compile(r"/mod/([a-z_]+)/view\.php\?id=(\d+)")
_EVENT_RE = re.compile(r"data-event-id=\"(\d+)\"[^>]*title=\"([^\"]+)\"")
_STAMP_RE = re.compile(r"datetime=\"([^\"]+)\"")
_EVENT_DATE_RE = re.compile(r"(\d{1,2})\s+(de\s+)?([a-záéíóúñ]+)", re.I)


@dataclass
class Curso:
    """Un curso del EVA."""

    id: int
    nombre: str
    codigo: str = ""

    @property
    def descripcion(self) -> str:
        return f"{self.codigo} {self.nombre}".strip()


@dataclass
class Aviso:
    """Una discusión del foro de avisos de un curso."""

    id: int
    titulo: str
    autor: str
    fecha: str
    respuestas: int
    url: str


@dataclass
class Actividad:
    """Una actividad/recursos dentro de una sección de un curso."""

    tipo: str  # resource | page | forum | assign | quiz | feedback | ...
    id: int
    nombre: str
    url: str
    seccion: str = ""


@dataclass
class EventoCalendario:
    """Un evento del calendario del EVA."""

    id: int
    titulo: str
    fecha: str
    url: str
    tipo: str = ""


@dataclass
class EvaClient:
    """Cliente de alto nivel sobre una sesión autenticada."""

    session: EvaSession
    _cache_cursos: list[Curso] | None = field(default=None, init=False)

    # ------------------------------------------------------------------ #
    # Cursos
    # ------------------------------------------------------------------ #
    def cursos(self, *, refresh: bool = False) -> list[Curso]:
        """Lista los cursos matriculados (del menú de navegación)."""
        if self._cache_cursos is not None and not refresh:
            return self._cache_cursos
        resp = self.session.client.get(f"{EVA_BASE}/my/")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        cursos: list[Curso] = []
        seen: set[int] = set()
        for a in soup.find_all("a", href=re.compile(r"/course/view\.php\?id=\d+")):
            m = re.search(r"id=(\d+)", a["href"])
            if not m:
                continue
            cid = int(m.group(1))
            nombre = a.get_text(strip=True)
            if not nombre or cid in seen:
                continue
            seen.add(cid)
            cursos.append(Curso(id=cid, nombre=nombre))
        cursos.sort(key=lambda c: c.nombre.lower())
        self._cache_cursos = cursos
        return cursos

    def buscar_curso(self, texto: str) -> list[Curso]:
        """Busca cursos por nombre/código (usa el buscador de Moodle)."""
        import urllib.parse

        q = urllib.parse.quote(texto)
        resp = self.session.client.get(f"{EVA_BASE}/course/search.php?search={q}")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        cursos: list[Curso] = []
        for card in soup.select(".coursebox, .courses .course"):
            link = card.find("a", href=re.compile(r"/course/view\.php\?id=\d+"))
            if not link:
                continue
            m = re.search(r"id=(\d+)", link["href"])
            nombre = link.get_text(strip=True)
            if not m or not nombre:
                continue
            cursos.append(Curso(id=int(m.group(1)), nombre=nombre))
        return cursos

    def _curso_por_ref(self, ref: str | int) -> Curso:
        """Resuelve una referencia de curso (id, código o substring)."""
        if isinstance(ref, int):
            return Curso(id=ref, nombre=str(ref))
        ref_l = ref.lower()
        # id numérico
        if ref.isdigit():
            return Curso(id=int(ref), nombre=ref)
        # por nombre/código entre los matriculados
        for c in self.cursos():
            if c.nombre.lower() == ref_l or c.codigo.lower() == ref_l:
                return c
        matches = [c for c in self.cursos() if ref_l in c.nombre.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            nombres = ", ".join(f"{c.id} ({c.nombre})" for c in matches)
            raise ValueError(
                f"La referencia '{ref}' coincide con varios cursos: {nombres}. Usá el id."
            )
        raise ValueError(f"No se encontró el curso '{ref}'. Usá 'eva cursos' para listar.")

    # ------------------------------------------------------------------ #
    # Foros de avisos
    # ------------------------------------------------------------------ #
    def _foros_curso(self, curso_id: int) -> list[tuple[int, str]]:
        """Encuentra los foros de un curso (prioriza el de avisos)."""
        resp = self.session.client.get(f"{EVA_BASE}/course/view.php?id={curso_id}")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        foros: list[tuple[int, str]] = []
        for a in soup.find_all("a", href=re.compile(r"/mod/forum/view\.php\?id=\d+")):
            m = re.search(r"id=(\d+)", a["href"])
            nombre = a.get_text(" ", strip=True)
            if m and nombre:
                foros.append((int(m.group(1)), nombre))
        # El foro de avisos primero si existe
        avisos = [f for f in foros if "aviso" in f[1].lower()]
        return (avisos + [f for f in foros if f not in avisos]) or foros

    def avisos(self, curso_ref: str | int, *, limite: int = 10) -> list[Aviso]:
        """Lee las discusiones del foro de avisos del curso."""
        curso = self._curso_por_ref(curso_ref)
        foros = self._foros_curso(curso.id)
        if not foros:
            return []
        forum_id, _ = foros[0]
        resp = self.session.client.get(f"{EVA_BASE}/mod/forum/view.php?id={forum_id}")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        avisos: list[Aviso] = []
        for tr in soup.select("tr.discussion"):
            link = tr.find("a", href=re.compile(r"discuss\.php\?d=\d+"))
            if not link:
                continue
            m = re.search(r"d=(\d+)", link["href"])
            tds = tr.find_all("td")
            # Autor: primer div.author-info .text-truncate (columna "Comenzado por")
            autor = ""
            ai = tr.select_one("td .author-info .text-truncate")
            if ai:
                autor = ai.get_text(strip=True)
            # Fecha: primer <time> con data-timestamp (última actividad)
            fecha = ""
            ts = tr.find("time", attrs={"data-timestamp": True})
            if ts:
                fecha = ts.get_text(strip=True)
            if not fecha:
                mf = re.search(r"(\d{1,2} \w+ \d{4})", tr.get_text(" ", strip=True))
                if mf:
                    fecha = mf.group(1)
            respuestas = 0
            if len(tds) > 3:
                mresp = re.search(r"\d+", tds[3].get_text())
                if mresp:
                    respuestas = int(mresp.group())
            avisos.append(
                Aviso(
                    id=int(m.group(1)),
                    titulo=link.get_text(strip=True),
                    autor=autor,
                    fecha=fecha,
                    respuestas=respuestas,
                    url=urljoin(EVA_BASE, link["href"]),
                )
            )
        return avisos[:limite]

    def aviso_detalle(self, discusion_id: int) -> str:
        """Devuelve el texto del mensaje principal de una discusión."""
        resp = self.session.client.get(f"{EVA_BASE}/mod/forum/discuss.php?d={discusion_id}")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        post = soup.select_one("article.forum-post, .forumpost, .post-content")
        if post is None:
            return ""
        return post.get_text("\n", strip=True)

    # ------------------------------------------------------------------ #
    # Actividades por sección
    # ------------------------------------------------------------------ #
    def actividades(self, curso_ref: str | int, *, seccion: str | None = None) -> list[Actividad]:
        """Lista las actividades del curso, opcionalmente filtradas por sección."""
        curso = self._curso_por_ref(curso_ref)
        resp = self.session.client.get(f"{EVA_BASE}/course/view.php?id={curso.id}")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Secciones disponibles: links del índice a ?id=N&section=M
        secciones_idx: list[int] = []
        for a in soup.find_all(
            "a", href=re.compile(rf"/course/view\.php\?id={curso.id}&section=\d+")
        ):
            m = re.search(r"section=(\d+)", a["href"])
            if m and int(m.group(1)) not in secciones_idx:
                secciones_idx.append(int(m.group(1)))

        act: list[Actividad] = []
        seen: set[tuple[str, int]] = set()

        def _parsear(html: str, nombre_sec: str) -> None:
            s = BeautifulSoup(html, "html.parser")
            for a in s.find_all("a", href=re.compile(r"/mod/[a-z_]+/view\.php\?id=\d+")):
                m = _MOD_RE.search(a["href"])
                nombre = a.get_text(" ", strip=True)
                if not m or not nombre:
                    continue
                clave = (m.group(1), int(m.group(2)))
                if clave in seen:
                    continue
                seen.add(clave)
                nombre = re.sub(r"\s+(Foro|Archivo|Página|URL|Cuestionario)$", "", nombre).strip()
                act.append(
                    Actividad(
                        tipo=m.group(1),
                        id=int(m.group(2)),
                        nombre=nombre,
                        url=urljoin(EVA_BASE, a["href"]),
                        seccion=nombre_sec,
                    )
                )

        # Sección general (0) del HTML inicial
        _parsear(resp.text, "General")
        # Resto de secciones: una request por sección (pestañas bajo demanda)
        for sec_id in secciones_idx:
            if sec_id == 0:
                continue
            r = self.session.client.get(
                f"{EVA_BASE}/course/view.php?id={curso.id}&section={sec_id}"
            )
            if r.status_code != 200:
                continue
            nombre_sec = f"Sección {sec_id}"
            h = BeautifulSoup(r.text, "html.parser").find(
                ["h2", "h3"], class_=re.compile(r"sectionname|section-title")
            )
            if h:
                nombre_sec = h.get_text(strip=True)
            _parsear(r.text, nombre_sec)

        if seccion:
            act = [a for a in act if seccion.lower() in a.seccion.lower()]
        return act

    # ------------------------------------------------------------------ #
    # Calendario
    # ------------------------------------------------------------------ #
    def calendario(
        self, *, mes: int | None = None, anio: int | None = None
    ) -> list[EventoCalendario]:
        """Eventos del calendario del mes (por defecto el actual)."""
        hoy = date.today()
        mes = mes or hoy.month
        anio = anio or hoy.year
        resp = self.session.client.get(
            f"{EVA_BASE}/calendar/view.php?view=month&course=1&m={anio:04d}{mes:02d}"
        )
        resp.raise_for_status()
        body = resp.text
        eventos: list[EventoCalendario] = []
        # Cada día del mes agrupa sus eventos; capturamos título + url
        for m in re.finditer(
            r'data-region="event-item"[^>]*>.*?<a[^>]*data-action="view-event"'
            r'[^>]*data-event-id="(\d+)"[^>]*href="([^"]+)"[^>]*title="([^"]+)"',
            body,
            re.S,
        ):
            eventos.append(
                EventoCalendario(
                    id=int(m.group(1)),
                    titulo=m.group(3),
                    url=urljoin(EVA_BASE, m.group(2)),
                    fecha="",
                )
            )
        # Fechas: cada día tiene el número en data-day-title o el li está
        # dentro de un td con data-day
        for td in re.finditer(r'<td[^>]*data-day="(\d+)"[^>]*>(.*?)</td>', body, re.S):
            dia = int(td.group(1))
            for m in re.finditer(r'data-event-id="(\d+)"', td.group(2)):
                for ev in eventos:
                    if ev.id == int(m.group(1)):
                        ev.fecha = f"{dia:02d}/{mes:02d}/{anio}"
        eventos.sort(key=lambda e: e.fecha)
        return eventos

    # ------------------------------------------------------------------ #
    # Descarga de material
    # ------------------------------------------------------------------ #
    def descargar(self, url: str, destino: Path) -> Path:
        """Descarga un recurso del EVA (pluginfile) a `destino`."""
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with self.session.client.stream("GET", url) as resp:
            resp.raise_for_status()
            with destino.open("wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        return destino

    def material(self, curso_ref: str | int, *, destino: Path | None = None) -> list[Actividad]:
        """Lista (y opcionalmente descarga) los archivos de un curso."""
        curso = self._curso_por_ref(curso_ref)
        act = [a for a in self.actividades(curso.id) if a.tipo in ("resource", "page")]
        if destino is None:
            return act
        destino = Path(destino)
        for a in act:
            try:
                ext = ".html" if a.tipo == "page" else ".pdf"
                archivo = destino / f"{curso.id}_{a.id}_{a.nombre[:40]}{ext}"
                self.descargar(a.url, archivo)
                a.nombre = f"{a.nombre} -> {archivo.name}"
            except httpx.HTTPError as e:
                a.nombre = f"{a.nombre} (error: {e})"
        return act

    def close(self) -> None:
        self.session.close()

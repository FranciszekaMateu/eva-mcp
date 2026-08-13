"""Interfaz de línea de comandos para el EVA FING.

Uso:
    eva login          Verifica credenciales y guarda la sesión
    eva cursos         Lista tus cursos matriculados
    eva avisos <cur>   Últimos avisos del foro de un curso
    eva aviso <id>     Texto completo de un aviso
    eva activ <cur>    Actividades de un curso (opcional --seccion)
    eva cal            Eventos del calendario
    eva material <cur> Materiales (archivos/páginas) de un curso

Credenciales: variables de entorno EVA_USER / EVA_PASS o archivo .env.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from eva_cli import credentials
from eva_cli.auth import EvaAuthError
from eva_cli.client import EvaClient
from eva_cli.paths import normalize_path
from eva_cli.session import clear_session, get_client

app = typer.Typer(help="CLI del EVA FING — acceso headless para humanos y agentes.")
console = Console()
err = Console(stderr=True)


def _get_client(*, reutilizar: bool = True) -> EvaClient:
    """Cliente autenticado, traduciendo errores de sesión a typer.Exit."""
    try:
        return get_client(reutilizar=reutilizar)
    except RuntimeError as e:
        raise typer.Exit(str(e)) from e
    except EvaAuthError as e:
        raise typer.Exit(f"Error de login: {e}") from e


@app.command()
def login(
    user: str | None = typer.Option(
        None, "--user", "-u", help="CI de bedelía (sin puntos ni guiones)"
    ),
) -> None:
    """Verifica credenciales y las guarda en el llavero del sistema (keyring).

    La contraseña se pide de forma interactiva (sin mostrarla) y se guarda
    cifrada por el sistema operativo — no en texto plano.
    """
    import getpass

    # ¿Ya hay credenciales y sesión válidas?
    try:
        existing = get_client()
    except (RuntimeError, EvaAuthError):
        existing = None
    if existing is not None:
        existing.close()
        if user is None:
            console.print(
                "[green]✓[/] Ya hay credenciales y sesión válidas. "
                "Para reloguear: eva login -u <CI>"
            )
            return

    if user is None:
        user = typer.prompt("CI de bedelía (sin puntos ni guiones)")
    password = getpass.getpass("Contraseña de bedelía: ")

    credentials.store_credentials(user, password)
    try:
        client = get_client(reutilizar=False)
    except EvaAuthError as e:
        err.print(f"[red]✗[/] {e}")
        raise typer.Exit(code=1) from e
    console.print(
        "[green]✓[/] Login correcto. Credenciales guardadas en el llavero del "
        "sistema (Windows Credential Manager / Keychain), no en texto plano."
    )
    client.close()


@app.command()
def logout() -> None:
    """Borra credenciales del llavero y la sesión guardada."""
    credentials.clear_credentials()
    clear_session()
    console.print("[green]✓[/] Credenciales y sesión borradas.")


@app.command()
def cursos() -> None:
    """Lista tus cursos matriculados."""
    client = _get_client()
    try:
        lista = client.cursos()
    finally:
        client.close()
    if not lista:
        console.print("No hay cursos matriculados.")
        return
    table = _tabla("Mis cursos (EVA FING)", ["ID", "Nombre"], ["cyan", None])
    for c in lista:
        table.add_row(str(c.id), c.nombre)
    console.print(table)


@app.command()
def avisos(curso: str, limite: int = typer.Option(10, "--limite", "-n")) -> None:
    """Últimos avisos del foro de un curso (nombre, código o id)."""
    client = _get_client()
    try:
        lista = client.avisos(curso, limite=limite)
    except ValueError as e:
        err.print(f"[red]✗[/] {e}")
        raise typer.Exit(code=1) from e
    finally:
        client.close()
    if not lista:
        console.print("Sin avisos en el foro.")
        return
    table = _tabla(
        f"Avisos — {curso}",
        ["ID", "Título", "Autor", "Fecha", "Resp."],
        ["cyan", None, "magenta", "green", None],
    )
    for a in lista:
        table.add_row(str(a.id), a.titulo, a.autor, a.fecha, str(a.respuestas))
    console.print(table)
    console.print("\n[dim]Detalle: eva aviso <ID>[/dim]")


@app.command()
def aviso(aviso_id: int) -> None:
    """Texto completo de un aviso del foro."""
    client = _get_client()
    try:
        texto = client.aviso_detalle(aviso_id)
    finally:
        client.close()
    if not texto:
        err.print("[red]✗[/] No se pudo leer el aviso.")
        raise typer.Exit(code=1)
    console.print(texto)


@app.command()
def actividades(
    curso: str,
    seccion: str | None = typer.Option(None, "--seccion", "-s"),
) -> None:
    """Actividades de un curso (opcional: filtrar por sección)."""
    client = _get_client()
    try:
        lista = client.actividades(curso, seccion=seccion)
    except ValueError as e:
        err.print(f"[red]✗[/] {e}")
        raise typer.Exit(code=1) from e
    finally:
        client.close()
    if not lista:
        console.print("Sin actividades.")
        return
    table = _tabla(
        f"Actividades — {curso}",
        ["Tipo", "ID", "Nombre", "Sección"],
        ["cyan", "cyan", None, None],
    )
    for a in lista:
        table.add_row(a.tipo, str(a.id), a.nombre, a.seccion)
    console.print(table)


@app.command()
def cal() -> None:
    """Eventos del calendario de este mes."""
    client = _get_client()
    try:
        lista = client.calendario()
    finally:
        client.close()
    if not lista:
        console.print("Sin eventos este mes.")
        return
    table = _tabla("Calendario EVA", ["Fecha", "Evento"], ["green", None])
    for e in lista:
        table.add_row(e.fecha, e.titulo)
    console.print(table)


@app.command()
def material(
    curso: str,
    destino: str | None = typer.Option(None, "--destino", "-d"),
) -> None:
    """Lista (o descarga con -d) los archivos/páginas de un curso.

    ``-d`` acepta rutas Windows nativas, ``~/...``, y rutas MSYS como
    ``/c/Users/...`` o ``/tmp/...`` (se normalizan automáticamente).
    """
    client = _get_client()
    try:
        destino_path = normalize_path(destino) if destino else None
        lista = client.material(curso, destino=destino_path)
    except ValueError as e:
        err.print(f"[red]✗[/] {e}")
        raise typer.Exit(code=1) from e
    finally:
        client.close()
    table = _tabla(f"Material — {curso}", ["Tipo", "Nombre"], ["cyan", None])
    for a in lista:
        table.add_row(a.tipo, a.nombre)
    console.print(table)


def _tabla(titulo: str, columnas: list[str], estilos: list[str | None]) -> Table:
    table = Table(title=titulo)
    for columna, estilo in zip(columnas, estilos, strict=True):
        table.add_column(columna, style=estilo)
    return table


if __name__ == "__main__":
    app()

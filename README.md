# eva-mcp

Servidor **MCP** y **CLI** para el **EVA FING** (Moodle de la Facultad de
Ingeniería, UdelaR), con acceso *headless*: autentica contra el SSO de UdelaR
(Shibboleth) sin navegador y deja que **agentes de IA** (Claude Desktop, Cursor,
Hermes, etc.) y **humanos** consulten cursos, avisos, actividades, calendario y
material de estudio.

> Hecho por y para estudiantes de la FING. Sin API de Moodle (está cerrada para
> estudiantes): todo funciona vía sesión autenticada por Shibboleth.

---

## Casos de uso

### "¿Hay algún aviso nuevo en Métodos Numéricos?"

Le preguntás a tu agente y te responde con los últimos avisos (título, autor,
fecha):

```
Vos: ¿Cuáles son los últimos avisos de MetNum?
Agente: llama eva_avisos("MetNum-2S") → te lista los avisos del foro.
```

Sin agente, desde la terminal: `eva avisos metnum`.

### "Bajame el material de una materia"

Enunciados de prácticos, notas de teórico, exámenes viejos — todo en una carpeta:

```
Vos: Bajame todo el material de BD NoSQL a ~/Documents/BDNR
Agente: llama eva_descargar_material("BDNR", destino) → descarga los PDFs.
```

Sin agente: `eva material bdnr -d ~/Documents/BDNR`.

### "¿Cuándo es el parcial / qué entregas tengo?"

El calendario del EVA tiene los vencimientos de entregas y cuestionarios:

```
Vos: ¿Qué tengo en el calendario del EVA este mes?
Agente: llama eva_calendario() → te lista los eventos con fecha.
```

Sin agente: `eva cal`.

### "¿Qué actividades tiene tal curso?"

Cuestionarios, foros, tareas y recursos por sección:

```
Vos: ¿Qué actividades tiene Sistemas Operativos en la sección de prácticos?
Agente: llama eva_actividades("Sistemas Operativos", seccion="prácticos").
```

Sin agente: `eva actividades so --seccion "Práctico"`.

### Automatizar / cron

Como es headless, podés correrlo desde un cron para recibir alertas sin abrir el
EVA:

```bash
# avisar si hay un aviso nuevo en MetNum (ej. vía un script que te notifique)
eva avisos metnum -n 3
```

### Armar notas / vault

Bajás todo el material de una materia y lo organizás en tu vault de notas
(Obsidian, etc.) con un solo comando — ideal para arrancar el semestre.

---

## Requisitos

- **Python 3.11+**
- [`uv`](https://docs.astral.sh/uv/) (o `pipx`) — para instalar desde GitHub.

---

## Instalación (desde GitHub)

> El proyecto **no está en PyPI**; se instala directo desde el repo.

### Para usarlo con un agente (MCP)

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eva": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/FranciszekaMateu/eva-mcp", "eva-mcp"]
    }
  }
}
```

**Cursor** — `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "eva": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/FranciszekaMateu/eva-mcp", "eva-mcp"]
    }
  }
}
```

**Hermes**:

```bash
hermes mcp add eva --command uvx --args --from git+https://github.com/FranciszekaMateu/eva-mcp eva-mcp
```

### Para usarlo desde la terminal (CLI)

Instalá los dos comandos (`eva` y `eva-mcp`) de una:

```bash
uv tool install "git+https://github.com/FranciszekaMateu/eva-mcp"
```

O correr sin instalar (one-shot):

```bash
uvx --from "git+https://github.com/FranciszekaMateu/eva-mcp" eva cursos
```

### Para desarrollo / contribuir

```bash
git clone https://github.com/FranciszekaMateu/eva-mcp
cd eva-mcp
uv venv .venv
uv pip install --python .venv/Scripts/python -e ".[dev]"
```

> ⚠️ El venv se crea con `uv` (sin `pip` propio). Instalá con `uv pip install
> --python .venv/Scripts/python`, no con `.venv/Scripts/python -m pip`.

---

## Configuración (credenciales)

La forma recomendada es usar el **llavero del sistema** (Windows Credential
Manager, macOS Keychain, Linux Secret Service). La contraseña queda **cifrada por
el sistema operativo**, nunca en texto plano:

```bash
eva login
```

Te pide el CI y la contraseña una sola vez (sin mostrarla) y las guarda cifradas.
La sesión también se cachea **cifrada** en `~/.eva-cli/cookies.enc` y se renueva
sola al expirar. Para borrar todo: `eva logout`.

Alternativa (fallback, texto plano): variables de entorno `EVA_USER`/`EVA_PASS`
o un archivo `.env`. El orden de resolución es: **entorno → llavero → `.env`**.

---

## Tools MCP

| Tool | Qué hace |
|---|---|
| `eva_cursos` | Lista los cursos matriculados (id, nombre) |
| `eva_avisos` | Últimos avisos del foro de un curso |
| `eva_aviso` | Texto completo de un aviso |
| `eva_actividades` | Actividades de un curso (filtrable por sección) |
| `eva_calendario` | Eventos del calendario (mes actual por defecto) |
| `eva_material` | Lista los archivos/páginas de un curso |
| `eva_descargar_material` | Descarga el material a una carpeta |
| `eva_login` | Fuerza un login fresco |

> En Hermes las tools aparecen como `mcp__eva__*` recién en una sesión nueva
> (no hay hot-reload de MCP).

---

## Comandos CLI

```bash
eva login            # guarda credenciales en el llavero del sistema (seguro)
eva logout           # borra credenciales y sesión
eva cursos           # lista tus cursos (id, nombre)
eva avisos metnum    # últimos avisos de un curso (nombre o id)
eva aviso 11740      # texto completo de un aviso
eva actividades metnum --seccion "Material teórico"
eva cal              # eventos del calendario
eva material metnum -d ./material   # descarga el material a una carpeta
```

`-d` acepta rutas Windows nativas, `~/...` y rutas MSYS (`/c/Users/...`, `/tmp/...`).

---

## Arquitectura

```
src/eva_cli/
├── auth.py       # login SAML Shibboleth (3 pasos, sin navegador)
├── client.py     # scraping: cursos, avisos, actividades, calendario, material
├── session.py    # credenciales (.env) + cache de sesión (compartido CLI/MCP)
├── paths.py      # normalización de rutas MSYS → Windows
├── cli.py        # comandos typer (eva)
└── mcp_server.py # servidor fastmcp (eva-mcp) → tools mcp__eva__*
```

Núcleo (`EvaClient`) + dos fachadas: `eva` (CLI) y `eva-mcp` (MCP).

---

## Desarrollo

```bash
uv run --python .venv/Scripts/python pytest   # 20 tests con httpx.MockTransport
uv run --python .venv/Scripts/python ruff check src tests scripts
```

> Nota para el desarrollo en Windows: el `PYTHONPATH` del entorno de Hermes puede
> contaminar el venv (apunta al site-packages del agente). Correr con
> `PYTHONPATH=` limpio, y el server MCP ya se blinda solo (`sys.path` limpio
> antes de importar fastmcp).

---

## Licencia

[MIT](LICENSE) © 2026 Francisco Escobar

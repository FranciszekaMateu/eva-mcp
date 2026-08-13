# eva-cli

CLI y **servidor MCP** para el **EVA FING** (Moodle de la Facultad de Ingeniería,
UdelaR) con acceso headless: pensado para humanos desde la terminal y para
**agentes de IA** (Hermes, cron jobs, scripts).

Autentica contra el SSO de UdelaR (Shibboleth) programáticamente y opera la sesión
con cookies — sin navegador, sin tokens de admin.

## Instalación

```bash
cd eva-cli
uv venv .venv
uv pip install --python .venv/Scripts/python -e ".[dev]"
```

> ⚠️ El venv se crea con `uv` (sin `pip` propio). Instalá con `uv pip install
> --python .venv/Scripts/python`, no con `.venv/Scripts/python -m pip`.

## Configuración

Crear un archivo `.env` en la raíz del proyecto (o variables de entorno):

```
EVA_USER=53087475
EVA_PASS=tu_contraseña
```

Las credenciales son las de **bedelía/SeCIU** (usuario = CI con dígito verificador).
El archivo `.env` está en `.gitignore` — no se commitea. Se busca en este orden:
`./.env`, `~/.eva-cli/.env`, y la raíz del proyecto.

## Uso (CLI)

```bash
eva login            # verifica credenciales y guarda la sesión en ~/.eva-cli/
eva cursos           # lista tus cursos matriculados (id, nombre)
eva avisos metnum    # últimos avisos del foro del curso (nombre o id)
eva aviso 11740      # texto completo de un aviso
eva actividades metnum --seccion "Material teórico"
eva cal              # eventos del calendario del mes
eva material metnum -d ./material   # descarga archivos/páginas del curso
```

La sesión se guarda en `~/.eva-cli/cookies.txt` y se reutiliza hasta que expira
(login fresco automático si hace falta).

`-d` acepta rutas Windows nativas, `~/...` y rutas MSYS (`/c/Users/...`, `/tmp/...`),
que se normalizan automáticamente.

## Uso con agentes (MCP)

El servidor MCP expone estas tools: `eva_cursos`, `eva_avisos`, `eva_aviso`,
`eva_actividades`, `eva_calendario`, `eva_material`, `eva_descargar_material`,
`eva_login`.

### 1. Credenciales

Crear `~/.eva-cli/.env` (o exportar `EVA_USER`/`EVA_PASS`):

```
EVA_USER=53087475
EVA_PASS=tu_contraseña
```

El servidor las lee de ahí, sin importar desde dónde lo lance tu agente.

### 2. Agregar el server a tu agente

Requisito: Python 3.11+ y [`uv`](https://docs.astral.sh/uv/) (o `pipx`) instalados.

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eva": {
      "command": "uvx",
      "args": ["--from", "eva-cli", "eva-mcp"]
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
      "args": ["--from", "eva-cli", "eva-mcp"]
    }
  }
}
```

**Hermes**:

```bash
hermes mcp add eva --command uvx --args --from eva-cli eva-mcp
```

### 3. Verificar sin agente

```bash
uvx --from eva-cli eva cursos        # CLI directo
uvx --from eva-cli eva-mcp           # servidor MCP (stdio)
```

> Las tools `mcp__eva__*` aparecen en Hermes recién en una sesión nueva (no hay
> hot-reload de MCP).

## Arquitectura

```
src/eva_cli/
├── auth.py       # flujo SAML Shibboleth (login programático UdelaR)
├── client.py     # scraping de Moodle: cursos, avisos, actividades, calendario
├── session.py    # credenciales + cache de sesión (compartido CLI/MCP)
├── paths.py      # normalización de rutas MSYS → Windows
├── cli.py        # comandos typer + rich
├── mcp_server.py # servidor MCP (fastmcp) → tools mcp__eva__*
└── __init__.py
```

## Para agentes

Todo lo que hace el CLI está expuesto como librería (`EvaSession`, `EvaClient`,
`get_client`):

```python
from eva_cli import EvaClient, EvaSession

session = EvaSession.login("usuario", "contraseña")
client = EvaClient(session=session)
for curso in client.cursos():
    print(curso.id, curso.nombre)
```

## Tests

```bash
uv run --python .venv/Scripts/python pytest
```

Los tests usan `httpx.MockTransport` (no tocan la red) y cubren el login SAML,
el scraping de cursos/avisos/actividades/calendario y la normalización de rutas.

## Notas técnicas

- El EVA no habilita tokens de servicio web para estudiantes (API REST cerrada),
  por eso el acceso es vía sesión autenticada por Shibboleth.
- El token `execution` del IdP es de un solo uso: cada login fresco empieza con
  un GET nuevo.
- Selectores HTML validados contra el EVA real en agosto 2026 — si Moodle
  actualiza el tema, pueden requerir ajustes.

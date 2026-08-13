"""Tests del flujo de login SAML Shibboleth (con httpx.MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from eva_cli.auth import EvaAuthError, EvaSession

# GET /auth/shibboleth/index.php → redirect al IdP con token execution
SAML_FORM_HTML = """
<html><body>
<form action="/idp/profile/SAML2/Redirect/SSO?execution=e1s1">
  <input type="text" name="j_username"/>
  <input type="password" name="j_password"/>
</form>
</body></html>
"""

# POST al IdP con credenciales correctas → form auto-submit SAML
SAML_RESPONSE_HTML = """
<html><body>
<form action="https://eva.fing.edu.uy/Shibboleth.sso/SAML2/POST">
  <input type="hidden" name="SAMLResponse" value="TOKEN_SAML"/>
  <input type="hidden" name="RelayState" value="relay123"/>
</form>
</body></html>
"""

# POST al IdP con credenciales incorrectas → pantalla de error
IDP_ERROR_HTML = """
<html><head><title>Acceso incorrecto</title></head>
<body>Usuario o contraseña inválidos</body></html>
"""

HOME_HTML = "<html><body>Página Principal | FING</body></html>"


def _login_handler(request: httpx.Request) -> httpx.Response:
    if "auth/shibboleth" in request.url.path:
        return httpx.Response(200, text=SAML_FORM_HTML)
    if request.url.host == "login.udelar.edu.uy":
        return httpx.Response(200, text=SAML_RESPONSE_HTML)
    if "SAML2/POST" in request.url.path:
        return httpx.Response(
            200,
            text=HOME_HTML,
            headers={"Set-Cookie": "MoodleSessionfing=abc123; Path=/"},
        )
    return httpx.Response(404, text="not found")


def test_login_flujo_completo():
    session = EvaSession.login("user", "pass", transport=httpx.MockTransport(_login_handler))
    try:
        cookies = {c.name: c.value for c in session.client.cookies.jar}
        assert "MoodleSessionfing" in cookies
    finally:
        session.close()


def test_login_envia_credenciales_al_idp():
    capturados: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.udelar.edu.uy":
            capturados["j_username"] = request.content.decode() if request.content else ""
            data = dict(request.url.params) if not request.content else _form(request)
            capturados["j_username"] = data.get("j_username", "")
            capturados["j_password"] = data.get("j_password", "")
            capturados["event"] = data.get("_eventId_proceed", "")
            return httpx.Response(200, text=SAML_RESPONSE_HTML)
        if "auth/shibboleth" in request.url.path:
            return httpx.Response(200, text=SAML_FORM_HTML)
        if "SAML2/POST" in request.url.path:
            return httpx.Response(
                200,
                text=HOME_HTML,
                headers={"Set-Cookie": "MoodleSessionfing=abc123; Path=/"},
            )
        return httpx.Response(404)

    session = EvaSession.login("53087475", "secreta", transport=httpx.MockTransport(handler))
    session.close()
    assert capturados["j_username"] == "53087475"
    assert capturados["j_password"] == "secreta"
    assert capturados["event"] == "Ingresar"


def _form(request: httpx.Request) -> dict[str, str]:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_login_credenciales_rechazadas():
    def handler(request: httpx.Request) -> httpx.Response:
        if "auth/shibboleth" in request.url.path:
            return httpx.Response(200, text=SAML_FORM_HTML)
        if request.url.host == "login.udelar.edu.uy":
            return httpx.Response(200, text=IDP_ERROR_HTML)
        return httpx.Response(404)

    with pytest.raises(EvaAuthError, match=r"[Cc]redenciales"):
        EvaSession.login("user", "badpass", transport=httpx.MockTransport(handler))


def test_login_sin_form_del_idp():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>sin form</body></html>")

    with pytest.raises(EvaAuthError, match="formulario del IdP"):
        EvaSession.login("user", "pass", transport=httpx.MockTransport(handler))

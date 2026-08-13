"""Autenticación contra el EVA FING vía Shibboleth (SSO UdelaR).

Flujo SAML validado (ago-2026):
1. GET https://eva.fing.edu.uy/auth/shibboleth/index.php
   -> 302 a login.udelar.edu.uy/idp/profile/SAML2/Redirect/SSO?execution=<token>
2. POST j_username + j_password + _eventId_proceed al IdP
   -> HTML con form auto-submit: SAMLResponse + RelayState
3. POST SAMLResponse + RelayState a eva.fing.edu.uy/Shibboleth.sso/SAML2/POST
   -> Set-Cookie MoodleSessionfing (sesión autenticada)

El token `execution` es de un solo uso: cada login debe hacer el GET fresco.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

EVA_BASE = "https://eva.fing.edu.uy"
SHIBBOLETH_URL = f"{EVA_BASE}/auth/shibboleth/index.php"
IDP_BASE = "https://login.udelar.edu.uy"
SAML_POST_URL = f"{EVA_BASE}/Shibboleth.sso/SAML2/POST"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class EvaAuthError(Exception):
    """Error de autenticación con el EVA/UdelaR."""


@dataclass
class EvaSession:
    """Sesión HTTP autenticada contra el EVA."""

    client: httpx.Client

    @classmethod
    def login(
        cls,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> EvaSession:
        """Realiza el flujo SAML completo y devuelve una sesión autenticada.

        ``transport`` permite inyectar un :class:`httpx.MockTransport` en tests.
        """
        client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )
        try:
            _do_shibboleth_login(client, username, password)
        except Exception:
            client.close()
            raise
        return cls(client=client)

    def close(self) -> None:
        self.client.close()


def _do_shibboleth_login(client: httpx.Client, username: str, password: str) -> None:
    """Ejecuta los 3 pasos del flujo SAML sobre un client ya creado."""
    # Paso 1: disparar el SSO y obtener el token de ejecución del IdP
    resp = client.get(SHIBBOLETH_URL)
    resp.raise_for_status()

    # El IdP responde con un form cuyo action contiene ?execution=<token>
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form", action=re.compile(r"execution="))
    if form is None:
        raise EvaAuthError(
            "No se encontró el formulario del IdP. ¿El EVA cambió su flujo de login?"
        )
    action = form["action"]
    execution = re.search(r"execution=([^&\"]+)", action)
    if not execution:
        raise EvaAuthError("El formulario del IdP no trae token execution.")
    idp_action = urljoin(IDP_BASE, action)

    # Paso 2: enviar credenciales al IdP
    resp = client.post(
        idp_action,
        data={
            "j_username": username,
            "j_password": password,
            "donotcache": "1",
            "_eventId_proceed": "Ingresar",
        },
    )
    resp.raise_for_status()

    # El IdP responde con un form auto-submit hacia el SP del EVA
    soup = BeautifulSoup(resp.text, "html.parser")
    saml_form = soup.find("form", action=re.compile(r"Shibboleth\.sso"))
    if saml_form is None:
        # Posible error de credenciales o pantalla de error del IdP
        title = soup.title.get_text(strip=True) if soup.title else ""
        if "acceso incorrecto" in title.lower() or "error" in title.lower():
            raise EvaAuthError(
                f"Credenciales rechazadas por UdelaR ('{title}'). Verificá usuario/contraseña."
            )
        raise EvaAuthError("El IdP no devolvió el form SAML esperado.")
    payload = {i.get("name"): i.get("value", "") for i in saml_form.find_all("input")}
    if "SAMLResponse" not in payload:
        raise EvaAuthError("El form SAML no contiene SAMLResponse.")

    # Paso 3: consumir el SAMLResponse en el SP del EVA (setea la cookie de sesión)
    resp = client.post(SAML_POST_URL, data=payload)
    resp.raise_for_status()

    if not _has_session_cookie(client):
        raise EvaAuthError("El login no dejó cookie de sesión Moodle.")


def _has_session_cookie(client: httpx.Client) -> bool:
    return any(c.name.startswith("MoodleSession") for c in client.cookies.jar)

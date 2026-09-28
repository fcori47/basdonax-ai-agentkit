"""Mandar mails con la Gmail API, con el permiso que se crea en Google Cloud.

Por qué así y no con una contraseña de aplicación por SMTP: el permiso que se
pide acá (`gmail.send`) sirve SOLO para mandar. Si alguien se mete en el
servidor y se lleva las variables, puede mandar mails desde esa cuenta, pero
no leer ni uno; una contraseña de aplicación abre la casilla entera. Y se
revoca desde la cuenta de Google sin cambiar ninguna contraseña.

Son tres datos, y los deja `conectar_gmail.py` en el .env:

    GMAIL_CLIENT_ID       el cliente OAuth de Google Cloud (tipo «App de escritorio»)
    GMAIL_CLIENT_SECRET   su clave
    GMAIL_REFRESH_TOKEN   el permiso de esa cuenta para mandar mails

Con el permiso se pide un acceso que dura una hora, y con el acceso se manda.

Este módulo usa solo la biblioteca estándar y no importa nada del resto del
paquete, a propósito: `conectar_gmail.py` lo carga suelto, para poder correr
en una computadora que no tiene instalado LangChain y compañía.
"""

from __future__ import annotations

import base64
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

URL_PARA_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_DE_PERMISOS = "https://oauth2.googleapis.com/token"
URL_PARA_MANDAR = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# El único permiso que se pide: mandar. No deja leer, borrar ni ver la casilla.
PERMISO_PARA_MANDAR = "https://www.googleapis.com/auth/gmail.send"

# Cuánto se espera a Google. Si tarda más, algo anda mal: mejor enterarse.
ESPERA = 20

# Lo que hay que hacer cuando el permiso guardado deja de valer. Aparece en
# varios mensajes: que diga siempre lo mismo.
VOLVER_A_CONECTAR = (
    "En tu computadora, en la carpeta del agente: python conectar_gmail.py. "
    "Después copiá GMAIL_REFRESH_TOKEN del .env a las variables del servidor, "
    "volvé a desplegar y probá con python probar_mail.py."
)


class ErrorDeGoogle(Exception):
    """Google dijo que no. El mensaje dice qué hacer para arreglarlo."""

    def __init__(self, mensaje: str, codigo: int = 0) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Una redirección se corta en vez de seguirse.

    Google no redirige estas direcciones. Si pasa, algo en el medio está
    cambiando las respuestas, y seguirla sería mandarle la clave del cliente
    o el permiso a otro servidor.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErrorDeGoogle(
            f"Google contestó con una redirección ({code}) y no la sigo, para no "
            "mandarle el permiso a otro lado. Si se repite, revisá la red del servidor "
            "(un proxy o un firewall que intercepta)."
        )


# El contexto de cifrado que VERIFICA el certificado y el nombre del servidor.
# Es lo que Python hace por defecto; va explícito para que nadie lo suponga.
_ABRIDOR = urllib.request.build_opener(
    _SinRedirecciones,
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
)


def direccion_para_autorizar(cliente: str, redireccion: str, estado: str, desafio: str) -> str:
    """La página de Google donde la persona elige la cuenta y acepta el permiso."""
    return URL_PARA_AUTORIZAR + "?" + urllib.parse.urlencode(
        {
            "client_id": cliente,
            "redirect_uri": redireccion,
            "response_type": "code",
            "scope": PERMISO_PARA_MANDAR,
            # offline + consent: que Google devuelva el permiso duradero
            # (refresh token) también la segunda vez que se conecta.
            "access_type": "offline",
            "prompt": "consent",
            "state": estado,
            "code_challenge": desafio,
            "code_challenge_method": "S256",
        }
    )


def canjear_codigo(cliente: str, secreto: str, codigo: str, verificador: str, redireccion: str) -> dict:
    """El código con el que vuelve el navegador, a cambio del permiso duradero."""
    return _pedir(
        URL_DE_PERMISOS,
        {
            "code": codigo,
            "client_id": cliente,
            "client_secret": secreto,
            "redirect_uri": redireccion,
            "grant_type": "authorization_code",
            "code_verifier": verificador,
        },
        cuando="canjear",
    )


def renovar_acceso(cliente: str, secreto: str, permiso: str) -> tuple[str, int]:
    """Con el permiso duradero, un acceso para mandar. Devuelve (acceso, segundos que dura)."""
    datos = _pedir(
        URL_DE_PERMISOS,
        {
            "client_id": cliente,
            "client_secret": secreto,
            "refresh_token": permiso,
            "grant_type": "refresh_token",
        },
        cuando="renovar",
    )
    acceso = datos.get("access_token")
    if not acceso:
        raise ErrorDeGoogle("Google contestó sin el acceso para mandar. Probá de nuevo en unos minutos.")
    try:
        dura = int(datos.get("expires_in") or 3600)
    except (TypeError, ValueError):
        dura = 3600
    return acceso, dura


def mandar(acceso: str, mensaje: bytes) -> dict:
    """Manda un mail ya armado (los bytes de un EmailMessage)."""
    crudo = base64.urlsafe_b64encode(mensaje).decode("ascii")
    return _pedir(URL_PARA_MANDAR, {"raw": crudo}, acceso=acceso, cuando="mandar")


def probar_sin_mandar(acceso: str) -> None:
    """Confirma que la Gmail API está habilitada y que el permiso alcanza, sin mandar nada.

    Le pide a Google que mande un mail vacío. Google primero revisa que la
    API esté habilitada en el proyecto y que el acceso sirva para mandar, y
    recién después mira el mail: si se queja del mail (400), lo anterior está
    bien, y no salió nada porque no había nada que mandar.
    """
    try:
        _pedir(URL_PARA_MANDAR, {"raw": ""}, acceso=acceso, cuando="mandar")
    except ErrorDeGoogle as e:
        if e.codigo == 400:
            return
        raise


def explicar(codigo: int, texto: str, cuando: str = "") -> str:
    """Lo que contestó Google, en castellano y con lo que hay que hacer."""
    try:
        datos = json.loads(texto)
    except ValueError:
        datos = {}
    error = datos.get("error") if isinstance(datos, dict) else None
    razones: list[str] = []

    # El servidor de permisos contesta {"error": "invalid_grant", ...}; la
    # Gmail API, {"error": {"code": 403, "message": ..., "status": ...}}.
    if isinstance(error, str):
        clave, detalle = error, str(datos.get("error_description") or "")
    elif isinstance(error, dict):
        clave, detalle = str(error.get("status") or ""), str(error.get("message") or "")
        for lista in (error.get("errors"), error.get("details")):
            razones += [str(x.get("reason")) for x in lista or [] if isinstance(x, dict)]
    else:
        clave, detalle = "", texto
    # Lo que dijo Google va a parar a los registros: en una sola línea y
    # corto, que un salto de línea no invente renglones.
    detalle = re.sub(r"[\x00-\x1f\x7f\s]+", " ", detalle).strip()[:300]

    if clave == "invalid_grant":
        if cuando == "canjear":
            return (
                "Google no aceptó el código que trajo el navegador (se venció o ya se "
                "usó). Corré python conectar_gmail.py de nuevo."
            )
        return (
            "Google ya no acepta el permiso guardado (GMAIL_REFRESH_TOKEN): se venció "
            "o se revocó. Pasa si la app de Google Cloud quedó «En prueba» (ahí el "
            "permiso dura 7 días), si se cambió la contraseña de esa cuenta de Google "
            "o si se le sacó el acceso desde la cuenta. " + VOLVER_A_CONECTAR
        )
    if clave in ("invalid_client", "unauthorized_client", "deleted_client"):
        return (
            "Google no reconoce el cliente (GMAIL_CLIENT_ID y GMAIL_CLIENT_SECRET): "
            "revisá que estén bien copiados y que el cliente siga existiendo en Google "
            "Cloud. Si lo cambiaste o le cambiaste la clave, el permiso también hay "
            "que sacarlo de nuevo. " + VOLVER_A_CONECTAR
        )
    if clave == "redirect_uri_mismatch":
        return (
            "El cliente de Google Cloud no es del tipo «App de escritorio». Creá uno "
            "de ese tipo (Clientes → Crear cliente) y usá ese."
        )
    if (
        "SERVICE_DISABLED" in texto
        or "accessNotConfigured" in razones
        or "has not been used" in detalle
    ):
        return (
            "La Gmail API no está habilitada en tu proyecto de Google Cloud. "
            "Habilitala: APIs y servicios → Biblioteca → «Gmail API» → Habilitar. "
            "Tarda un par de minutos en tomar; después probá de nuevo."
        )
    if (
        "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in texto
        or "insufficientPermissions" in razones
        or "insufficient authentication scopes" in detalle.lower()
    ):
        return (
            "El permiso no incluye mandar mails. Corré python conectar_gmail.py de "
            "nuevo y aceptá «Enviar correo electrónico en tu nombre»."
        )
    if codigo == 401 and cuando == "mandar":
        return (
            "Google no aceptó el acceso para mandar (401): se revocó o venció en el "
            "camino. El próximo aviso pide uno nuevo; si se repite, el permiso ya no "
            "vale. " + VOLVER_A_CONECTAR
        )
    if codigo == 400 and cuando == "mandar" and "invalid to header" in detalle.lower():
        return "Google no acepta la dirección de AVISOS_EMAIL: revisá que esté bien escrita."
    if codigo == 429:
        return "Google frenó por demasiados pedidos seguidos (429). Esperá unos minutos."
    if codigo >= 500:
        return f"Google tuvo un problema de su lado ({codigo}). Suele pasar solo: probá en unos minutos."
    return f"Google contestó {codigo}: {detalle or clave or 'sin detalle'}"


def _pedir(url: str, datos: dict, acceso: str = "", cuando: str = "") -> dict:
    """Un POST a Google. Los permisos van como formulario; lo de Gmail, como JSON."""
    if acceso:
        cuerpo = json.dumps(datos).encode("utf-8")
        tipo = "application/json"
    else:
        cuerpo = urllib.parse.urlencode(datos).encode("ascii")
        tipo = "application/x-www-form-urlencoded"

    pedido = urllib.request.Request(
        url,
        data=cuerpo,
        method="POST",
        headers={"Content-Type": tipo, "Accept": "application/json"},
    )
    if acceso:
        # «Sin redirigir»: aunque alguien cambie el abridor, el acceso no
        # viaja a otro servidor.
        pedido.add_unredirected_header("Authorization", f"Bearer {acceso}")

    try:
        with _ABRIDOR.open(pedido, timeout=ESPERA) as respuesta:
            texto = respuesta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            texto = e.read().decode("utf-8", "replace")
        except Exception:
            texto = ""
        # from None: la traza no suma nada y el pedido original lleva claves.
        raise ErrorDeGoogle(explicar(e.code, texto, cuando), e.code) from None

    try:
        return json.loads(texto) if texto.strip() else {}
    except ValueError:
        raise ErrorDeGoogle(f"Google contestó algo que no se entiende: {texto[:200]}") from None

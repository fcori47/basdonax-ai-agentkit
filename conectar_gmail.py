"""Conecta una cuenta de Google para mandar los avisos por mail.

    python conectar_gmail.py
    python conectar_gmail.py ruta/al/client_secret_….json

Se corre una vez, en tu computadora: abre el navegador para que elijas la
cuenta de Google que va a mandar los avisos y le des permiso al agente. Es un
permiso para MANDAR mails y nada más: no puede leer ni borrar nada de esa
casilla. (En el servidor no hay navegador; el permiso sirve igual allá.)

Antes hace falta, en Google Cloud: un proyecto, la Gmail API habilitada y un
cliente de tipo «App de escritorio», con su JSON descargado. Los pasos están
en el README, en «Cuatro decisiones antes de desplegar» (la 4). Sin ruta,
busca el JSON en esta carpeta y en Descargas.

Deja tres líneas en el .env: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET y
GMAIL_REFRESH_TOKEN. No las muestra, a propósito: son una llave. Van también a
las variables del servidor, y allá se prueba con python probar_mail.py.

Si el permiso se venció, correlo de nuevo sin el JSON: usa el cliente que ya
está en el .env.

Usa solo la biblioteca estándar: no hace falta instalar nada para correrlo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARCHIVO_ENV = RAIZ / ".env"

# Cuánto se espera a que vuelvas del navegador.
ESPERA_DEL_NAVEGADOR = 5 * 60

# Dónde se busca el JSON del cliente si no se indica: esta carpeta y Descargas.
LUGARES_DEL_JSON = [RAIZ, Path.home() / "Downloads", Path.home() / "Descargas"]

VERDE = "\033[92m"
AMARILLO = "\033[93m"
GRIS = "\033[90m"
ROJO = "\033[91m"
FIN = "\033[0m"


def _cargar(nombre: str):
    """Carga un módulo de src/agente suelto, sin importar el paquete entero.

    Importar `agente` arrastra LangChain y compañía; para conectar la cuenta
    alcanza con la biblioteca estándar, y así corre en cualquier computadora.
    """
    ruta = RAIZ / "src" / "agente" / f"{nombre}.py"
    especificacion = importlib.util.spec_from_file_location(f"_conectar_{nombre}", ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


gmail = _cargar("gmail")


class ErrorDeConexion(Exception):
    """Algo de este lado: el JSON, el navegador, una respuesta que no coincide."""


# -- El cliente de Google Cloud ------------------------------------------------


def buscar_el_json(indicado: str | None) -> Path | None:
    """El JSON del cliente: el que se indicó, o el más nuevo de esta carpeta o de Descargas."""
    if indicado:
        ruta = Path(indicado).expanduser()
        if not ruta.is_file():
            raise ErrorDeConexion(f"No encuentro el archivo {ruta}.")
        return ruta
    candidatos = [
        archivo
        for lugar in LUGARES_DEL_JSON
        if lugar.is_dir()
        for archivo in lugar.glob("client_secret*.json")
    ]
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def leer_el_cliente(ruta: Path) -> tuple[str, str]:
    """El id y la clave del cliente, del JSON que bajaste de Google Cloud."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ErrorDeConexion(
            f"{ruta.name} no se pudo leer: tiene que ser el JSON que da Google Cloud al crear el cliente."
        ) from None
    if not isinstance(datos, dict):
        datos = {}
    if "web" in datos:
        raise ErrorDeConexion(
            "Ese cliente es de tipo «Aplicación web», y hace falta uno de tipo «App de "
            "escritorio». En Google Cloud: Clientes → Crear cliente → Tipo de aplicación: "
            "App de escritorio. Bajá el JSON de ese."
        )
    instalado = datos.get("installed")
    if not isinstance(instalado, dict) or not instalado.get("client_id") or not instalado.get("client_secret"):
        raise ErrorDeConexion(
            f"{ruta.name} no trae el cliente adentro: bajá de nuevo el JSON del cliente «App de escritorio»."
        )
    return str(instalado["client_id"]).strip(), str(instalado["client_secret"]).strip()


# -- El .env ------------------------------------------------------------------


def leer_env(ruta: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not ruta.is_file():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        pelada = linea.strip()
        if not pelada or pelada.startswith("#") or "=" not in pelada:
            continue
        nombre, valor = pelada.split("=", 1)
        valores[nombre.strip()] = valor.strip().strip('"').strip("'")
    return valores


def guardar_en_env(ruta: Path, valores: dict[str, str]) -> None:
    """Escribe esas variables en el .env: cambia su línea, o las agrega al final.

    El resto del archivo queda como estaba, con sus comentarios. Una línea
    repetida de las mismas variables se saca: el .env se queda con la última,
    y podría ser la vieja.
    """
    for nombre, valor in valores.items():
        # Lo que da Google nunca trae espacios, comillas ni #; si aparecen,
        # algo vino mal, y escribirlo podría romper (o inventar) otra línea.
        if not re.fullmatch(r"[^\s#'\"]+", valor):
            raise ErrorDeConexion(f"{nombre} vino con caracteres raros, así que no lo guardo. Corré el script de nuevo.")
    lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.is_file() else []
    pendientes = dict(valores)
    salida: list[str] = []
    for linea in lineas:
        pelada = linea.strip()
        nombre = ""
        if "=" in pelada and not pelada.startswith("#"):
            nombre = pelada.split("=", 1)[0].strip()
        if nombre in valores:
            if nombre in pendientes:
                salida.append(f"{nombre}={pendientes.pop(nombre)}")
            continue
        salida.append(linea)
    if pendientes:
        if salida and salida[-1].strip():
            salida.append("")
        salida.append("# Avisos por Google: los dejó conectar_gmail.py")
        salida += [f"{nombre}={valor}" for nombre, valor in pendientes.items()]

    if os.name != "nt" and not ruta.exists():
        # Que nazca ya cerrado para los demás usuarios de la máquina.
        ruta.touch(mode=0o600)
    ruta.write_text("\n".join(salida) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(ruta, 0o600)


# -- La ida y vuelta con el navegador -----------------------------------------


def par_pkce() -> tuple[str, str]:
    """El verificador y su desafío (PKCE): el código que trae el navegador
    solo lo puede canjear quien tiene el verificador, o sea, este script."""
    verificador = secrets.token_urlsafe(64)
    resumen = hashlib.sha256(verificador.encode("ascii")).digest()
    desafio = base64.urlsafe_b64encode(resumen).rstrip(b"=").decode("ascii")
    return verificador, desafio


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0e0e10;
color:#f4f4f5;font:18px/1.5 system-ui,sans-serif">
<main style="max-width:30rem;padding:2rem;text-align:center">
<p style="font-size:44px;margin:0;color:{color}">{marca}</p>
<h1 style="font-size:24px;margin:.4em 0">{titulo}</h1>
<p style="color:#b8b8c0;margin:0">{texto}</p></main></body></html>"""


class _Vuelta(BaseHTTPRequestHandler):
    """Atiende al navegador cuando vuelve de Google con el código."""

    # Una conexión que se abre y no manda nada (Chrome abre de más, por las
    # dudas) se corta a los 10 segundos en vez de quedar colgada.
    timeout = 10

    def do_GET(self) -> None:
        partes = urllib.parse.urlsplit(self.path)
        if partes.path != "/":
            # El navegador también pide /favicon.ico y otras cosas: se ignoran.
            self.send_response(404)
            self.end_headers()
            return

        consulta = {k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()}
        coincide = hmac.compare_digest(consulta.get("state", "").encode(), self.server.estado.encode())
        if not coincide:
            # Una vuelta que no es de este pedido (una pestaña vieja, u otra
            # página que prueba puertos): no se usa ni corta la espera.
            self.server.ignoradas += 1
        elif self.server.vuelta is None:
            self.server.vuelta = consulta

        if coincide and "code" in consulta:
            pagina = PAGINA.format(
                titulo="Listo", marca="✓", color="#34d399",
                texto="Ya podés cerrar esta pestaña y volver a la terminal.",
            )
        else:
            pagina = PAGINA.format(
                titulo="No salió", marca="×", color="#f07565",
                texto="Volvé a la terminal: ahí dice qué pasó y qué hacer.",
            )
        cuerpo = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        # La dirección de esta página lleva el código de Google: que no se
        # guarde ni viaje a ningún lado.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args) -> None:
        # Callado a propósito: el registro normal escribe en la terminal la
        # dirección entera, con el código de Google adentro.
        pass


class _Servidor(ThreadingHTTPServer):
    """Un servidor de un solo uso en 127.0.0.1, en un puerto libre cualquiera."""

    daemon_threads = True
    block_on_close = False

    def __init__(self, estado: str) -> None:
        super().__init__(("127.0.0.1", 0), _Vuelta)
        self.estado = estado
        self.vuelta: dict[str, str] | None = None
        self.ignoradas = 0
        # handle_request() vuelve cada segundo, para poder cortar a tiempo.
        self.timeout = 1


def esperar_la_vuelta(servidor: _Servidor, espera: float | None = None) -> str:
    """Espera al navegador y devuelve el código de Google, o explica qué pasó."""
    espera = ESPERA_DEL_NAVEGADOR if espera is None else espera
    limite = time.monotonic() + espera
    avisadas = 0
    while servidor.vuelta is None:
        if time.monotonic() > limite:
            raise ErrorDeConexion(
                "Pasó el tiempo sin que vuelvas del navegador. Corré python "
                "conectar_gmail.py de nuevo cuando estés listo."
            )
        servidor.handle_request()
        if servidor.ignoradas > avisadas:
            avisadas = servidor.ignoradas
            print(
                f"{GRIS}Llegó una respuesta que no es de este pedido (¿una pestaña vieja?): "
                f"no la uso y sigo esperando.{FIN}"
            )

    vuelta = servidor.vuelta
    if "error" in vuelta:
        if vuelta["error"] == "access_denied":
            raise ErrorDeConexion(
                "No se dio el permiso (se apretó «Cancelar»). Corré python conectar_gmail.py "
                "de nuevo y aceptá: es solo para mandar mails."
            )
        error = re.sub(r"[^a-z_]", "", vuelta["error"].lower())[:40] or "sin detalle"
        raise ErrorDeConexion(f"Google devolvió un error ({error}). Corré python conectar_gmail.py de nuevo.")
    if not hmac.compare_digest(vuelta.get("state", "").encode(), servidor.estado.encode()):
        raise ErrorDeConexion(
            "La respuesta que llegó no corresponde a este pedido, así que no la uso. "
            "Corré python conectar_gmail.py de nuevo."
        )
    if not vuelta.get("code"):
        raise ErrorDeConexion("El navegador volvió sin el código de Google. Corré python conectar_gmail.py de nuevo.")
    return vuelta["code"]


# -- Todo junto -----------------------------------------------------------------


def conectar(indicado: str | None = None, archivo_env: Path = ARCHIVO_ENV) -> int:
    actuales = leer_env(archivo_env)
    archivo = buscar_el_json(indicado)
    if archivo is not None:
        cliente, secreto = leer_el_cliente(archivo)
        print(f"\nUso el cliente de {archivo.name}")
    elif actuales.get("GMAIL_CLIENT_ID") and actuales.get("GMAIL_CLIENT_SECRET"):
        cliente, secreto = actuales["GMAIL_CLIENT_ID"], actuales["GMAIL_CLIENT_SECRET"]
        print("\nUso el cliente que ya está en el .env")
    else:
        raise ErrorDeConexion(
            "No encuentro el JSON del cliente de Google Cloud (client_secret_….json). "
            "Bajalo al crear el cliente «App de escritorio» y pasame la ruta:  "
            "python conectar_gmail.py ruta/al/archivo.json  — los pasos están en el README, "
            "en «Cuatro decisiones antes de desplegar»."
        )

    verificador, desafio = par_pkce()
    estado = secrets.token_urlsafe(24)
    with _Servidor(estado) as servidor:
        redireccion = f"http://127.0.0.1:{servidor.server_port}"
        direccion = gmail.direccion_para_autorizar(cliente, redireccion, estado, desafio)
        print(
            "Se abre el navegador: elegí la cuenta de Google que va a MANDAR los avisos "
            "y aceptá el permiso."
        )
        print(
            f"{GRIS}Si aparece «Google no verificó esta app»: Avanzado → Ir a … (no seguro). "
            f"Es la app que creaste vos.{FIN}"
        )
        if not webbrowser.open(direccion):
            print("No se pudo abrir el navegador solo. Copiá esta dirección en el navegador:")
        else:
            print(f"{GRIS}Si no se abrió, copiá esta dirección en el navegador:{FIN}")
        print(f"  {direccion}\n")
        codigo = esperar_la_vuelta(servidor)

    permisos = gmail.canjear_codigo(cliente, secreto, codigo, verificador, redireccion)
    permiso = permisos.get("refresh_token")
    if not permiso:
        raise ErrorDeConexion("Google no devolvió el permiso duradero. Corré python conectar_gmail.py de nuevo.")
    if gmail.PERMISO_PARA_MANDAR not in str(permisos.get("scope") or "").split():
        raise ErrorDeConexion(
            "El permiso que se dio no incluye mandar mails. Corré python conectar_gmail.py "
            "de nuevo y aceptá «Enviar correo electrónico en tu nombre»."
        )

    guardar_en_env(
        archivo_env,
        {"GMAIL_CLIENT_ID": cliente, "GMAIL_CLIENT_SECRET": secreto, "GMAIL_REFRESH_TOKEN": permiso},
    )
    print(
        f"{VERDE}✓ Cuenta conectada.{FIN} El agente puede mandar mails desde ella "
        "(solo mandar: no puede leer nada)."
    )
    print(
        f"{GRIS}  En el .env quedaron GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET y "
        f"GMAIL_REFRESH_TOKEN. No se muestran acá: son una llave.{FIN}"
    )

    pendientes = 0
    try:
        dias = int(permisos.get("refresh_token_expires_in") or 0) / 86400
    except (TypeError, ValueError):
        dias = 0
    if dias:
        pendientes += 1
        if dias <= 8:
            print(
                f"\n{AMARILLO}Ojo: este permiso vence en {dias:.0f} días.{FIN} Pasa cuando la "
                "app de Google Cloud está «En prueba». Publicala (Plataforma de Google Auth → "
                "Público → Publicar app) y corré python conectar_gmail.py de nuevo: el permiso "
                "de una app publicada no vence solo."
            )
        else:
            print(
                f"\n{AMARILLO}Ojo: Google dice que este permiso vence en {dias:.0f} días.{FIN} "
                "Cuando venza, los avisos dejan de salir. Si al aceptar elegiste un acceso por "
                "tiempo limitado, conectalo de nuevo sin límite."
            )

    try:
        gmail.probar_sin_mandar(str(permisos.get("access_token") or ""))
        print(f"{VERDE}✓ La Gmail API responde{FIN} y el permiso alcanza para mandar.")
    except gmail.ErrorDeGoogle as e:
        pendientes += 1
        print(f"\n{AMARILLO}Falta una cosa:{FIN} {e}")

    if not actuales.get("AVISOS_EMAIL"):
        print(f"\n{AMARILLO}Completá AVISOS_EMAIL en el .env{FIN}: a quién le llega el aviso.")

    print("\nQué sigue:")
    print(
        "  1. Copiá esas tres líneas del .env a las variables del servidor (en Coolify, "
        "Environment Variables) y volvé a desplegar."
    )
    print("  2. En el servidor: python probar_mail.py  → te tiene que llegar un mail de prueba.")
    if archivo is not None:
        print(
            f"  3. El JSON que bajaste ({archivo.name}) ya no hace falta: lo que tenía quedó "
            "en el .env. Borralo, o guardalo donde guardás tus claves."
        )
    return 1 if pendientes else 0


def main(argv: list[str] | None = None) -> int:
    _cargar("consola").preparar()  # antes de imprimir: que las tildes no rompan Windows
    argumentos = sys.argv[1:] if argv is None else argv
    if argumentos and argumentos[0] in ("-h", "--help", "--ayuda"):
        print(__doc__)
        return 0
    try:
        return conectar(argumentos[0] if argumentos else None)
    except (ErrorDeConexion, gmail.ErrorDeGoogle) as e:
        print(f"\n{ROJO}{e}{FIN}")
        return 1
    except OSError as e:
        # Sin internet, un DNS que no resuelve, un firewall.
        print(f"\n{ROJO}No se pudo hablar con Google ({type(e).__name__}).{FIN} Revisá la conexión y probá de nuevo.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

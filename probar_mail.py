"""Manda un mail de prueba con lo que dice el .env.

    python probar_mail.py

Es el último paso de la instalación: si este mail llega, los avisos de
cuando algo se rompe también van a llegar. Mejor enterarse hoy que el día
que se vence un permiso. Se corre donde corre el agente (en el servidor): en
tu computadora prueba los datos, no que el servidor pueda mandar mails.

Solo lee lo del mail (AVISOS_EMAIL y GMAIL_* o SMTP_*): no hace falta tener
cargada la clave del modelo para probarlo.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agente.consola import preparar  # noqa: E402

preparar()  # antes de imprimir nada, para que las tildes no rompan Windows

from agente.avisos import Avisos  # noqa: E402
from agente.config import ErrorDeConfiguracion  # noqa: E402
from agente.gmail import ErrorDeGoogle  # noqa: E402

VERDE = "\033[92m"
GRIS = "\033[90m"
ROJO = "\033[91m"
FIN = "\033[0m"


def main() -> int:
    try:
        avisos = Avisos.desde_entorno()
    except ErrorDeConfiguracion as e:
        # Por ejemplo SMTP_PUERTO=587a: que lo diga en castellano, sin la traza.
        print(f"{ROJO}{e}{FIN}")
        return 1

    por_google = avisos.metodo != "smtp"
    print(f"\nMandando un mail de prueba a {avisos.para or '(sin AVISOS_EMAIL)'}")
    if por_google:
        print(f"{GRIS}   por Google (Gmail API, con el permiso de Google Cloud){FIN}\n")
    else:
        print(f"{GRIS}   por SMTP: {avisos.servidor or '(sin SMTP_SERVIDOR)'}:{avisos.puerto}"
              f" con {avisos.usuario or '(sin usuario)'}{FIN}\n")

    try:
        avisos.probar()
    except ValueError as e:
        print(f"{ROJO}{e}{FIN}")
        if por_google and any(v.startswith("GMAIL_") for v in avisos.faltan()):
            print("Los tres GMAIL_* los deja python conectar_gmail.py, corrido en tu "
                  "computadora (abre el navegador). Después se copian al servidor.")
        return 1
    except ErrorDeGoogle as e:
        # Ya viene en castellano y con lo que hay que hacer (ver gmail.py).
        print(f"{ROJO}{e}{FIN}")
        return 1
    except ssl.SSLCertVerificationError:
        # Antes que OSError (es uno de ellos): es la protección haciendo su
        # trabajo, no un problema de red.
        destino = "Google" if por_google else avisos.servidor
        print(f"{ROJO}El certificado del servidor no es válido para {destino}.{FIN}")
        if not por_google:
            print("Revisá SMTP_SERVIDOR. ", end="")
        print("Si está todo bien escrito, alguien en el medio de la red puede estar "
              "haciéndose pasar por el servidor: por eso no se mandó nada.")
        return 1
    except smtplib.SMTPServerDisconnected:
        print(f"{ROJO}{avisos.servidor}:{avisos.puerto} aceptó la conexión pero no "
              f"contestó.{FIN}")
        print("Revisá SMTP_PUERTO (suele ser 587) y que el servidor pueda salir por ese puerto.")
        return 1
    except smtplib.SMTPAuthenticationError:
        print(f"{ROJO}El servidor de mail no aceptó el usuario o la clave.{FIN}")
        print("Revisá SMTP_USUARIO y SMTP_CLAVE. Si tu mail es de Google (Gmail o "
              "Workspace), no va por SMTP: conectalo con python conectar_gmail.py.")
        return 1
    except smtplib.SMTPException as e:
        # Antes que OSError: en Python los errores de SMTP SON OSError, y si
        # no, esta rama nunca se alcanzaría.
        print(f"{ROJO}El servidor de mail contestó un error:{FIN} {e}")
        return 1
    except (socket.gaierror, ConnectionError, TimeoutError, OSError) as e:
        if por_google and isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            # urllib envuelve el error del certificado: es el mismo caso de arriba.
            print(f"{ROJO}El certificado no es válido para Google.{FIN}")
            print("Alguien en el medio de la red puede estar haciéndose pasar por Google "
                  "(o hay un proxy que intercepta): por eso no se mandó nada.")
        elif por_google:
            print(f"{ROJO}No se pudo conectar con Google.{FIN}")
            print(f"{GRIS}{type(e).__name__}: {e}{FIN}")
            print("Revisá que el servidor tenga salida a internet por HTTPS "
                  "(oauth2.googleapis.com y gmail.googleapis.com, puerto 443).")
        else:
            print(f"{ROJO}No se pudo conectar con {avisos.servidor}:{avisos.puerto}.{FIN}")
            print(f"{GRIS}{type(e).__name__}: {e}{FIN}")
            print("Revisá SMTP_SERVIDOR y SMTP_PUERTO. Si esto corre en un servidor, "
                  "puede ser que tenga cerrada la salida por ese puerto.")
        return 1

    print(f"{VERDE}Mail mandado.{FIN} Fijate en {avisos.para} "
          "(y en correo no deseado, la primera vez suele caer ahí).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

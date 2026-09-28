"""Manda un mail de prueba con lo que dice el .env.

    python probar_mail.py

Es el último paso de la instalación: si este mail llega, los avisos de
cuando algo se rompe también van a llegar. Mejor enterarse hoy que el día
que se vence una clave. Se corre donde corre el agente (en el servidor): en
tu computadora prueba la clave, no que el servidor pueda mandar mails.

Solo lee lo del mail (AVISOS_EMAIL y SMTP_*): no hace falta tener cargada
la clave del modelo para probarlo.
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

    print(f"\nMandando un mail de prueba a {avisos.para or '(sin AVISOS_EMAIL)'}")
    print(f"{GRIS}   por {avisos.servidor or '(sin SMTP_SERVIDOR)'}:{avisos.puerto}"
          f" con {avisos.usuario or '(sin usuario)'}{FIN}\n")

    try:
        avisos.probar()
    except ValueError as e:
        print(f"{ROJO}{e}{FIN}")
        return 1
    except ssl.SSLCertVerificationError:
        # Antes que OSError (es uno de ellos): es la protección haciendo su
        # trabajo, no un problema de red.
        print(f"{ROJO}El certificado del servidor de mail no es válido para "
              f"{avisos.servidor}.{FIN}")
        print("Revisá SMTP_SERVIDOR (con Gmail: smtp.gmail.com). Si el nombre está bien, "
              "alguien en el medio de la red puede estar haciéndose pasar por el servidor: "
              "por eso no se mandó la clave.")
        return 1
    except smtplib.SMTPServerDisconnected:
        print(f"{ROJO}{avisos.servidor}:{avisos.puerto} aceptó la conexión pero no "
              f"contestó.{FIN}")
        print("Revisá SMTP_PUERTO (con Gmail: 587) y que el servidor pueda salir por ese puerto.")
        return 1
    except smtplib.SMTPAuthenticationError:
        # El caso de casi todos la primera vez: pusieron su contraseña de
        # siempre y Gmail no la acepta para esto.
        print(f"{ROJO}El servidor de mail no aceptó el usuario o la clave.{FIN}")
        print("Con Gmail, SMTP_CLAVE tiene que ser una contraseña de aplicación "
              "(16 letras, sin espacios), no tu contraseña de siempre.")
        print("Se crea en https://myaccount.google.com/apppasswords "
              "(hace falta tener la verificación en dos pasos activada).")
        return 1
    except smtplib.SMTPException as e:
        # Antes que OSError: en Python los errores de SMTP SON OSError, y si
        # no, esta rama nunca se alcanzaría.
        print(f"{ROJO}El servidor de mail contestó un error:{FIN} {e}")
        return 1
    except (socket.gaierror, ConnectionError, TimeoutError, OSError) as e:
        print(f"{ROJO}No se pudo conectar con {avisos.servidor}:{avisos.puerto}.{FIN}")
        print(f"{GRIS}{type(e).__name__}: {e}{FIN}")
        print("Revisá SMTP_SERVIDOR y SMTP_PUERTO (con Gmail: smtp.gmail.com y 587). "
              "Si esto corre en un servidor, puede ser que tenga cerrada la salida por ese puerto.")
        return 1

    print(f"{VERDE}Mail mandado.{FIN} Fijate en {avisos.para} "
          "(y en correo no deseado, la primera vez suele caer ahí).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

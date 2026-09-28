"""Avisar por mail cuando algo se rompe.

En WhatsApp el error no se le muestra a la persona que escribió: lo que ve
el cliente de un negocio no puede ser "AuthenticationError: invalid x-api-key".
El error va a dos lugares donde sí sirve: una nota privada en la
conversación de Chatwoot (la ve el equipo) y un mail al dueño del agente.

El mail sale por SMTP, con la biblioteca estándar de Python: sin servicios
nuevos ni dependencias. Con Gmail alcanza una "contraseña de aplicación".

    AVISOS_EMAIL=vos@tuempresa.com
    SMTP_SERVIDOR=smtp.gmail.com
    SMTP_PUERTO=587
    SMTP_USUARIO=la-cuenta-que-manda@gmail.com
    SMTP_CLAVE=la-contraseña-de-aplicación

Dos cuidados:

  · Un mismo error no manda cien mails. Si se venció la clave del modelo,
    falla cada mensaje que entra: se avisa una vez por hora por tipo de
    error, y el mail siguiente dice cuántos se callaron en el medio.
  · Si el mail no sale, queda en los logs y nada más. Un aviso que se rompe
    no puede tirar abajo al agente que está avisando.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Callable

registro = logging.getLogger("agente.avisos")

UNA_HORA = 60 * 60

# Cuánto se espera al servidor de mail. Si tarda más, algo anda mal y no
# vale la pena quedarse colgado: el aviso queda en el log.
ESPERA_DEL_SERVIDOR = 20


class Avisos:
    """Manda un mail cuando algo se rompe, sin mandar el mismo cien veces."""

    def __init__(
        self,
        para: str = "",
        servidor: str = "",
        puerto: int = 587,
        usuario: str = "",
        clave: str = "",
        espera: float = UNA_HORA,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self.para = (para or "").strip()
        self.servidor = (servidor or "").strip()
        self.puerto = int(puerto or 587)
        self.usuario = (usuario or "").strip()
        # Google muestra la contraseña de aplicación en bloques de cuatro
        # («abcd efgh ijkl mnop»): los espacios no son parte de la clave.
        self.clave = (clave or "").replace(" ", "")
        self.espera = espera
        self._reloj = reloj
        self._ultimo: dict[str, float] = {}
        self._callados: dict[str, int] = {}

    @classmethod
    def desde_config(cls, config) -> "Avisos":
        return cls(
            para=config.avisos_email,
            servidor=config.smtp_servidor,
            puerto=config.smtp_puerto,
            usuario=config.smtp_usuario,
            clave=config.smtp_clave,
        )

    @classmethod
    def desde_entorno(cls) -> "Avisos":
        """Lee solo lo del mail, sin pedir la clave del modelo.

        Es lo que usa `probar_mail.py`: para probar el mail no hace falta
        tener todo el resto configurado.
        """
        import os

        # Importar config es lo que carga el .env (lo hace al importarse).
        # Sin esta línea, corriendo probar_mail.py, os.getenv no vería nada
        # de lo que está escrito en el archivo.
        from .config import _entero

        return cls(
            para=os.getenv("AVISOS_EMAIL", ""),
            servidor=os.getenv("SMTP_SERVIDOR", ""),
            puerto=_entero("SMTP_PUERTO", 587),
            usuario=os.getenv("SMTP_USUARIO", ""),
            clave=os.getenv("SMTP_CLAVE", ""),
        )

    def probar(self) -> None:
        """Manda un mail de prueba YA, sin esperar ni agrupar.

        A diferencia de avisar(), acá el error NO se traga: el que está
        instalando necesita ver exactamente qué contestó el servidor de mail.
        """
        if not self.activos:
            raise ValueError(
                "Faltan datos del mail: completá " + ", ".join(self.faltan()) + " en el .env."
            )
        self._enviar(
            "Prueba: los avisos del agente llegan",
            "Si estás leyendo esto, los avisos del agente llegan bien.\n\n"
            "Vas a recibir un mail así cada vez que algo se rompa: el modelo que no "
            "contesta, una clave vencida o Chatwoot que no acepta la respuesta. "
            "Del mismo error, uno por hora como mucho.",
        )

    @property
    def activos(self) -> bool:
        """Si hay a quién avisar y por dónde mandarlo."""
        return not self.faltan()

    def faltan(self) -> list[str]:
        """Las variables del .env que faltan para poder mandar un aviso."""
        datos = {
            "AVISOS_EMAIL": self.para,
            "SMTP_SERVIDOR": self.servidor,
            "SMTP_USUARIO": self.usuario,
            "SMTP_CLAVE": self.clave,
        }
        return [nombre for nombre, valor in datos.items() if not valor]

    def avisar(self, asunto: str, cuerpo: str, tipo: str) -> bool:
        """Manda el aviso si corresponde. Devuelve True si salió un mail.

        `tipo` agrupa los errores iguales: de un mismo tipo sale un mail por
        hora como mucho.
        """
        if not self.activos:
            registro.warning("Sin AVISOS_EMAIL: el aviso queda solo acá - %s", asunto)
            return False

        ahora = self._reloj()
        ultimo = self._ultimo.get(tipo)
        if ultimo is not None and ahora - ultimo < self.espera:
            self._callados[tipo] = self._callados.get(tipo, 0) + 1
            registro.info("Aviso repetido, no sale otro mail: %s", asunto)
            return False

        callados = self._callados.pop(tipo, 0)
        if callados:
            cuerpo += (
                f"\n\nDesde el aviso anterior pasó {callados} "
                f"{'vez' if callados == 1 else 'veces'} más lo mismo."
            )

        # Se anota antes de mandar: si el servidor de mail está caído, no
        # tiene sentido reintentar con cada mensaje que entra.
        self._ultimo[tipo] = ahora

        try:
            self._enviar(asunto, cuerpo)
        except Exception as e:
            # Por qué se traga: el aviso es para enterarse de un problema, y
            # si él mismo voltea el servidor se convierte en el problema.
            # El error del mail queda en el log, que es lo que queda.
            registro.error("No salió el mail de aviso (%s): %s", asunto, e)
            return False

        registro.info("Aviso mandado a %s: %s", self.para, asunto)
        return True

    def _enviar(self, asunto: str, cuerpo: str) -> None:
        mensaje = EmailMessage()
        mensaje["Subject"] = asunto
        mensaje["From"] = self.usuario or self.para
        mensaje["To"] = self.para
        mensaje.set_content(cuerpo)

        # El contexto que VERIFICA el certificado y el nombre del servidor.
        # Sin él, Python cifra igual pero le cree a cualquiera: alguien en el
        # medio de la red (un wifi, un DNS falso) se queda con la clave.
        contexto = ssl.create_default_context()

        # 465 es el puerto que ya viene cifrado; el resto (587) arranca en
        # texto y se cifra con STARTTLS antes de mandar la clave.
        if self.puerto == 465:
            with smtplib.SMTP_SSL(
                self.servidor, self.puerto, timeout=ESPERA_DEL_SERVIDOR, context=contexto
            ) as smtp:
                self._entrar(smtp)
                smtp.send_message(mensaje)
        else:
            with smtplib.SMTP(
                self.servidor, self.puerto, timeout=ESPERA_DEL_SERVIDOR
            ) as smtp:
                smtp.starttls(context=contexto)
                self._entrar(smtp)
                smtp.send_message(mensaje)

    def _entrar(self, smtp) -> None:
        if self.usuario and self.clave:
            smtp.login(self.usuario, self.clave)

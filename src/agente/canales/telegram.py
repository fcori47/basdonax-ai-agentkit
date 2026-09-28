"""El canal de Telegram.

Traduce en las dos direcciones: lo que llega de Telegram se convierte en un
`MensajeEntrante`, y lo que responde el agente sale como uno o varios mensajes
del bot. **El agente no se toca**: recibe texto y devuelve texto.

Telegram se puede escuchar de dos formas, y acá usamos la primera:

    polling  → tu programa le pregunta a Telegram "¿hay algo nuevo?"  ← esta
    webhook  → Telegram le pega a una URL tuya (necesita URL pública y HTTPS)

Polling es lo que hace que esto **funcione desde tu computadora**, sin dominio,
sin certificado y sin abrir puertos. Es la razón por la que Telegram es
el paso antes de WhatsApp: WhatsApp obliga a webhook, y ahí ya necesitás
un servidor de verdad.

El `conversacion` (el thread_id de LangGraph) es el **chat_id** de Telegram.
Eso es lo único que no se puede equivocar: si dos personas compartieran el
mismo valor, compartirían la memoria y leerían la conversación de otro.

Se usa `urllib`, de la biblioteca estándar, para no sumar una dependencia.
La API de Telegram son pedidos HTTP con JSON: no hace falta más.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import deque
from typing import Iterator

from .base import Canal, MensajeEntrante

API = "https://api.telegram.org"

# Cuánto se queda esperando cada consulta a Telegram. Esto es *long polling*:
# en vez de preguntar mil veces por segundo, la consulta queda abierta hasta
# que llega un mensaje o se cumple este tiempo. Menos tráfico y respuesta
# instantánea.
ESPERA_DE_ESCUCHA = 25

# El corte de urllib tiene que ser mayor que el de arriba: si fueran iguales,
# cortaríamos nosotros justo cuando Telegram está por contestar.
ESPERA_DE_RED = ESPERA_DE_ESCUCHA + 10

# Telegram rechaza cualquier mensaje más largo que esto.
LARGO_MAXIMO = 4096


class Telegram(Canal):
    """El bot de Telegram."""

    nombre = "telegram"

    def __init__(self, token: str, espera: int = ESPERA_DE_ESCUCHA) -> None:
        if not token:
            raise ValueError(
                "Falta el token de Telegram. Abrí el .env y completá "
                "TELEGRAM_TOKEN con el que te dio @BotFather."
            )

        self.token = token
        self.espera = espera

        # Desde qué novedad seguimos pidiendo. Telegram guarda los mensajes
        # hasta que le confirmás que los recibiste, y la confirmación es
        # justamente pedirle los siguientes.
        self._proxima = 0

        # Los últimos mensajes que ya contestamos. Telegram reenvía ante la
        # duda, y sin esto el agente contestaría dos veces lo mismo. Es una
        # cola corta: alcanza con acordarse de los últimos.
        self._ya_contestados: deque[str] = deque(maxlen=500)

    # -- Entrada ---------------------------------------------------------------

    def escuchar(self) -> Iterator[MensajeEntrante]:
        """Se queda esperando mensajes, para siempre.

        Devuelve un mensaje por vez, ya traducido. El que la recorre decide
        qué hacer con cada uno.
        """
        while True:
            for novedad in self._traer_novedades():
                # El offset se adelanta SIEMPRE, aunque el mensaje no nos
                # sirva. Si no, un mensaje que no sabemos atender (una foto,
                # por ejemplo) vuelve a llegar para siempre y el bot se
                # queda trabado en él.
                self._proxima = novedad["update_id"] + 1

                entrante = _traducir(novedad)
                if entrante is not None:
                    yield entrante

    def _traer_novedades(self) -> list[dict]:
        """Le pregunta a Telegram si hay mensajes nuevos."""
        # Por qué se traga el error: esto es la red, no el modelo. Que se
        # corte el wifi un segundo no puede matar al bot — si dejáramos que
        # explote, habría que levantarlo a mano cada vez. Devolvemos una
        # tanda vacía y en la próxima vuelta se intenta de nuevo. Un token
        # mal puesto sí se nota igual: no llega ningún mensaje nunca.
        try:
            respuesta = self._api(
                "getUpdates",
                {
                    "offset": self._proxima,
                    "timeout": self.espera,
                    # Solo mensajes: no nos interesan ediciones ni votos.
                    "allowed_updates": ["message"],
                },
                espera=ESPERA_DE_RED,
            )
        except Exception:
            return []

        return respuesta.get("result") or []

    def deberia_responder(self, mensaje: MensajeEntrante) -> bool:
        """Descarta lo que ya contestamos.

        Telegram reenvía un mensaje si no le confirmamos que llegó, así que
        sin esto el agente contesta dos veces lo mismo.
        """
        if not mensaje.texto.strip():
            return False

        if mensaje.identificador in self._ya_contestados:
            return False

        self._ya_contestados.append(mensaje.identificador)
        return True

    # -- Salida ----------------------------------------------------------------

    def enviar(self, conversacion: str, mensajes: list[str]) -> None:
        """Manda las respuestas a ese chat, en orden."""
        for mensaje in mensajes:
            # Un mensaje más largo que el tope lo rechaza Telegram entero, así
            # que lo cortamos. partir_respuesta() ya parte por sentido; esto es
            # la red de seguridad para el caso raro de una respuesta enorme.
            for pedazo in _cortar(mensaje, LARGO_MAXIMO):
                self._api("sendMessage", {"chat_id": conversacion, "text": pedazo})

    def escribiendo(self, conversacion: str) -> None:
        """Muestra el "escribiendo..." mientras el modelo piensa.

        No es decorativo: una respuesta puede tardar varios segundos y sin
        esto la persona no sabe si el bot la escuchó o se colgó.
        """
        # Que falle el aviso no puede voltear la respuesta: es cosmético.
        try:
            self._api("sendChatAction", {"chat_id": conversacion, "action": "typing"})
        except Exception:
            pass

    # -- La API ----------------------------------------------------------------

    def yo_soy(self) -> dict:
        """Los datos del bot. Sirve para avisar al arrancar con cuál se habla."""
        return self._api("getMe").get("result") or {}

    def _api(self, metodo: str, datos: dict | None = None, espera: int = 30) -> dict:
        """Una llamada a la API de Telegram."""
        url = f"{API}/bot{self.token}/{metodo}"
        cuerpo = json.dumps(datos or {}).encode("utf-8")

        pedido = urllib.request.Request(
            url,
            data=cuerpo,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(pedido, timeout=espera) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))


# -- Ayudantes ----------------------------------------------------------------


def _traducir(novedad: dict) -> MensajeEntrante | None:
    """Convierte lo que manda Telegram en algo que el agente entiende.

    Devuelve None si el mensaje no es texto (una foto, un sticker, un audio):
    el agente todavía no sabe leer eso.
    """
    mensaje = novedad.get("message") or {}
    texto = mensaje.get("text")
    chat = mensaje.get("chat") or {}
    quien = mensaje.get("from") or {}

    if not texto or not chat.get("id"):
        return None

    # Un bot contestándole a otro bot es un ida y vuelta infinito.
    if quien.get("is_bot"):
        return None

    return MensajeEntrante(
        texto=texto,
        # El chat_id es el thread_id: la memoria de cada persona por separado.
        conversacion=str(chat["id"]),
        identificador=str(novedad["update_id"]),
        datos=mensaje,
    )


def _cortar(texto: str, largo: int) -> list[str]:
    """Parte un texto que no entra en un mensaje de Telegram.

    Corta en el último renglón que entre, para no partir una palabra al medio.
    """
    if len(texto) <= largo:
        return [texto]

    pedazos = []
    resto = texto

    while len(resto) > largo:
        tajo = resto.rfind("\n", 0, largo)
        if tajo <= 0:
            tajo = resto.rfind(" ", 0, largo)
        if tajo <= 0:
            tajo = largo  # una parrafada sin espacios: cortamos y listo

        pedazos.append(resto[:tajo].strip())
        resto = resto[tajo:].strip()

    if resto:
        pedazos.append(resto)

    return pedazos

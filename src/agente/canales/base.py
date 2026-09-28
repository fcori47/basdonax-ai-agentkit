"""Qué es un canal.

Un canal es el pegamento entre un lugar donde la gente escribe (Telegram,
WhatsApp, tu web) y el agente. Traduce en las dos direcciones:

    mensaje que llega  →  agente.responder(texto, conversacion)  →  mensaje que sale

El agente no sabe nada de esto. Recibe texto y devuelve texto. Por eso se
puede enchufar a cualquier lado sin tocarlo.

Lo único que hay que resolver bien en cada canal es **de dónde sale el
`conversacion`** (el thread_id de LangGraph), porque eso es lo que hace que
las charlas de distintas personas no se mezclen:

    plataforma de pruebas  →  siempre "web", hay un solo usuario
    Telegram               →  el chat_id
    WhatsApp               →  el número de teléfono

Este archivo es solo la forma. Los canales de verdad están al lado:
`telegram.py` y `chatwoot.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MensajeEntrante:
    """Un mensaje que llega de afuera, ya traducido a algo que el agente entiende."""

    texto: str
    conversacion: str          # el thread_id: quién habla
    identificador: str = ""    # el id del mensaje en el canal, para no repetirlo
    datos: dict = field(default_factory=dict)  # lo crudo, por si el canal lo necesita


class Canal(ABC):
    """Un lugar por donde entran y salen mensajes."""

    nombre: str = "sin nombre"

    @abstractmethod
    def enviar(self, conversacion: str, mensajes: list[str]) -> None:
        """Manda una o varias respuestas a esa conversación.

        Es una lista y no un texto porque en mensajería conviene partir las
        respuestas largas en varios mensajes (ver respuesta.partir_respuesta).
        """

    def deberia_responder(self, mensaje: MensajeEntrante) -> bool:
        """Si el agente tiene que contestar este mensaje o dejarlo pasar.

        Acá va lo que en producción evita que el bot moleste:
          · que una persona haya tomado la conversación
          · que el bot esté apagado para ese contacto
          · que sea un mensaje que mandó el propio bot
          · que sea un reenvío repetido del mismo mensaje

        Por defecto contesta todo. Cada canal lo ajusta.
        """
        return True

    def lo_agarro_otro(self, conversacion: str) -> str:
        """Si mientras el agente esperaba para contestar, alguien le sacó la charla.

        Devuelve el motivo, o "" si la conversación sigue siendo suya. Por
        defecto nadie se la saca: un canal sin bandeja (Telegram) no tiene quién.
        """
        return ""

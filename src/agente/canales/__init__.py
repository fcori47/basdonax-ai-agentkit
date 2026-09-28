"""Los canales por donde el agente atiende.

    base.py       la forma que tiene un canal
    telegram.py   el bot de Telegram (sale a buscar los mensajes)
    chatwoot.py   WhatsApp, con Chatwoot en el medio
    buffer.py     junta la ráfaga de mensajes cortos

El agente no cambia entre uno y otro: cada canal es un archivo nuevo que
lo usa.
"""

from __future__ import annotations

from .base import Canal, MensajeEntrante

__all__ = ["Canal", "MensajeEntrante"]

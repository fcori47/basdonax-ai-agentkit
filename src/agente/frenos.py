"""El tope de mensajes: que nadie le haga gastar de más al agente.

Hay gente que se queda charlando de cualquier cosa con el agente de un
negocio. Cada respuesta se paga dos veces: los tokens del modelo y, desde el
1 de octubre de 2026, el mensaje de Meta. Con el tope, a partir de cierta
cantidad de mensajes en 24 horas la conversación pasa a una persona (la
etiqueta `humano`) y el agente se calla ahí.

    TOPE_MENSAJES_POR_DIA=50   →  el mensaje 51 del día ya no lo contesta

Está en memoria a propósito, como el buffer: hay un solo proceso atendiendo.
Si el contenedor se reinicia, los contadores arrancan de cero — pero una
conversación bloqueada sigue bloqueada, porque la etiqueta vive en Chatwoot,
no acá. Y si alguien del equipo se la saca, la persona arranca de cero: el
contador de esa conversación se borra en el momento de bloquearla.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

UN_DIA = 24 * 60 * 60

# Después de bloquear, Chatwoot tarda un momento en mandar los eventos con la
# etiqueta puesta. En ese rato los mensajes que siguen llegan "limpios", y sin
# esto el agente les contestaría. Pasado este tiempo manda la etiqueta.
GRACIA_DESPUES_DE_BLOQUEAR = 60

# Cada tanto se tiran los contadores de las conversaciones que no escribieron
# en el último día, para que la memoria no crezca para siempre.
LIMPIAR_CADA = 500

RESPONDER = "responder"
BLOQUEAR = "bloquear"
IGNORAR = "ignorar"


class TopeDeMensajes:
    """Cuenta los mensajes de cada conversación en las últimas 24 horas."""

    def __init__(
        self,
        tope: int,
        ventana: float = UN_DIA,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        `tope`     cuántos mensajes se contestan en la ventana (0 = sin tope)
        `ventana`  de cuántos segundos es la cuenta (un día)
        `reloj`    de dónde sale la hora; los tests pasan uno propio
        """
        self.tope = max(0, int(tope))
        self.ventana = ventana
        self._reloj = reloj
        self._mensajes: dict[str, deque[float]] = {}
        self._bloqueadas_en: dict[str, float] = {}
        self._anotados = 0

    def anotar(self, conversacion: str) -> str:
        """Cuenta un mensaje que entra y dice qué hacer con él.

        RESPONDER  → está dentro del tope
        BLOQUEAR   → es el que lo pasó: hay que pasar la conversación a una persona
        IGNORAR    → se acaba de bloquear; no hay que hacer nada más
        """
        if not self.tope:
            return RESPONDER

        ahora = self._reloj()

        bloqueada_en = self._bloqueadas_en.get(conversacion)
        if bloqueada_en is not None:
            if ahora - bloqueada_en < GRACIA_DESPUES_DE_BLOQUEAR:
                return IGNORAR
            del self._bloqueadas_en[conversacion]

        cola = self._mensajes.setdefault(conversacion, deque())
        while cola and ahora - cola[0] > self.ventana:
            cola.popleft()
        cola.append(ahora)

        self._anotados += 1
        if self._anotados % LIMPIAR_CADA == 0:
            self._limpiar(ahora)

        if len(cola) > self.tope:
            # Se borra la cuenta: si alguien del equipo le saca la etiqueta,
            # la persona arranca de cero y no queda bloqueada al toque.
            self._mensajes.pop(conversacion, None)
            self._bloqueadas_en[conversacion] = ahora
            return BLOQUEAR

        return RESPONDER

    def olvidar(self, conversacion: str) -> None:
        """Borra la cuenta de esa conversación: la usa /reset, para probar de cero."""
        self._mensajes.pop(conversacion, None)
        self._bloqueadas_en.pop(conversacion, None)

    def _limpiar(self, ahora: float) -> None:
        viejas = [
            conversacion
            for conversacion, cola in self._mensajes.items()
            if not cola or ahora - cola[-1] > self.ventana
        ]
        for conversacion in viejas:
            del self._mensajes[conversacion]
        # Pasado el rato de gracia manda la etiqueta de Chatwoot: guardar
        # para siempre cuándo se bloqueó cada una solo haría crecer la memoria.
        vencidas = [c for c, cuando in self._bloqueadas_en.items()
                    if ahora - cuando >= GRACIA_DESPUES_DE_BLOQUEAR]
        for conversacion in vencidas:
            del self._bloqueadas_en[conversacion]

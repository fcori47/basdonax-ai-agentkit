"""Juntar la ráfaga de mensajes.

La gente en WhatsApp no escribe un mensaje: escribe tres.

    "hola"
    "una consulta"
    "por el precio del plan"

Sin esto el agente contesta tres veces, y las tres mal: la primera no sabe
nada, la segunda tampoco, y recién la tercera tiene la pregunta entera. Peor
todavía, las tres respuestas se pisan entre sí en la pantalla del cliente.

Con esto, el agente espera, junta lo que llegue y contesta **una sola vez**
con todo junto.

    "hola
     una consulta
     por el precio del plan"

Cómo espera: cada mensaje nuevo reinicia el reloj (si sigue escribiendo,
seguimos esperando), pero hay un tope duro. Sin ese tope, alguien que manda
un mensaje cada tanto dejaría al agente esperando para siempre y nunca
recibiría respuesta.

Está en memoria a propósito. El AGENTS.md dice Redis, y va a hacer falta
cuando haya más de un proceso atendiendo: hoy hay uno solo, y una ráfaga que
se pierde si el contenedor se reinicia justo en esos segundos no justifica
sumar una base entera. Cuando se escale a varios procesos, se cambia esta
clase y nada más — el webhook no se entera.

Una parte de la ráfaga puede estar todavía leyéndose: una foto que describe
el modelo, un audio que se transcribe. Esa parte entra como una tarea, en su
lugar, y al soltar la ráfaga se la espera: así el orden es el de llegada y no
el de quién terminó primero de leerse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Union

registro = logging.getLogger("agente.buffer")

# Lo que se espera, como mucho, a que termine de leerse una parte (un audio
# largo, una foto con el proveedor lento). Pasado eso, la ráfaga sale sin ella.
ESPERA_DE_UNA_PARTE = 120

Parte = Union[str, "asyncio.Future[str]"]


async def _texto_de(parte: Parte) -> str:
    """El texto de una parte: tal cual, o el de la tarea cuando termina."""
    if isinstance(parte, str):
        return parte
    try:
        return await asyncio.wait_for(asyncio.shield(parte), ESPERA_DE_UNA_PARTE) or ""
    except Exception as e:
        registro.error("una parte de la ráfaga no se pudo leer: %s", e)
        return ""


class BufferDeMensajes:
    """Acumula los mensajes de cada conversación y avisa cuando paró la ráfaga."""

    def __init__(
        self,
        segundos: float,
        al_completar: Callable[[str, str], Awaitable[None]],
        tope: float | None = None,
    ) -> None:
        """
        `segundos`     cuánto se espera desde el último mensaje
        `al_completar` qué hacer con la ráfaga junta: (conversacion, texto)
        `tope`         cuánto se puede estirar la espera como máximo
        """
        self.segundos = max(0.0, float(segundos))
        self.al_completar = al_completar

        # El tope existe para el que escribe de a poco: sin él, un mensaje
        # cada 50 segundos con una espera de 60 no se contesta nunca.
        self.tope = float(tope) if tope is not None else self.segundos * 3

        self._pendientes: dict[str, list[Parte]] = {}
        self._relojes: dict[str, asyncio.Task] = {}
        self._arrancó_en: dict[str, float] = {}

    async def agregar(self, conversacion: str, texto: Parte) -> None:
        """Suma un mensaje a la ráfaga de esa conversación.

        `texto` puede ser el texto, o una tarea que lo va a devolver (un audio
        que se está transcribiendo): se espera recién al soltar la ráfaga.
        """
        # Sin espera configurada no hay ráfaga que juntar: se contesta y listo.
        if self.segundos <= 0:
            listo = await _texto_de(texto)
            if listo:
                await self.al_completar(conversacion, listo)
            return

        self._pendientes.setdefault(conversacion, []).append(texto)

        ahora = asyncio.get_running_loop().time()
        self._arrancó_en.setdefault(conversacion, ahora)

        # El reloj anterior ya no sirve: llegó un mensaje nuevo y hay que
        # volver a contar desde cero (salvo que ya nos pasamos del tope).
        reloj = self._relojes.pop(conversacion, None)
        if reloj is not None:
            reloj.cancel()

        gastado = ahora - self._arrancó_en[conversacion]
        espera = min(self.segundos, max(0.0, self.tope - gastado))

        self._relojes[conversacion] = asyncio.create_task(
            self._esperar_y_soltar(conversacion, espera)
        )

    async def _esperar_y_soltar(self, conversacion: str, espera: float) -> None:
        try:
            await asyncio.sleep(espera)
        except asyncio.CancelledError:
            # Llegó otro mensaje: este reloj queda descartado y el nuevo se
            # encarga. No hay nada que limpiar, los mensajes ya están juntos.
            return

        self._relojes.pop(conversacion, None)
        self._arrancó_en.pop(conversacion, None)
        partes = self._pendientes.pop(conversacion, [])

        texto = await _juntar(partes)
        if not texto:
            return

        await self.al_completar(conversacion, texto)

    def pendientes(self, conversacion: str) -> int:
        """Cuántos mensajes hay esperando. Lo usan los tests y el /salud."""
        return len(self._pendientes.get(conversacion, []))

    async def vaciar(self) -> None:
        """Suelta todo lo que esté esperando. Se llama al apagar el servidor.

        Sin esto, un deploy en el momento justo se come la ráfaga de alguien
        y esa persona se queda sin respuesta, sin que nadie se entere.
        """
        for reloj in list(self._relojes.values()):
            reloj.cancel()
        self._relojes.clear()
        self._arrancó_en.clear()

        pendientes = self._pendientes
        self._pendientes = {}

        for conversacion, partes in pendientes.items():
            texto = await _juntar(partes)
            if texto:
                await self.al_completar(conversacion, texto)


async def _juntar(partes: list[Parte]) -> str:
    """Las partes en el orden en que llegaron, sin las vacías."""
    textos = [await _texto_de(p) for p in partes]
    return "\n".join(t for t in textos if t)

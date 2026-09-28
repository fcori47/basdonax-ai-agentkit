"""Partir la respuesta en varios mensajes (o no partirla).

En un chat de web una respuesta larga se lee bien de un tirón. En WhatsApp
o Telegram no: un bloque de 800 caracteres se ve como un ladrillo y no
parece escrito por una persona.

Esta función parte el texto en mensajes cortos, respetando lo que el modelo
quiso separar. No se usa en la plataforma de pruebas — está acá lista para
cuando el agente atienda mensajería.

    partir_respuesta("Hola.\\n\\n¿Qué necesitás?")  →  ["Hola.", "¿Qué necesitás?"]

El criterio, en orden:

    1. Si el texto trae renglones en blanco, se respeta esa separación.
    2. Si no y entra en un solo mensaje, va entero.
    3. Si no, se parte por oraciones sin cortar ninguna al medio.

**Con `maximo=1` no se parte nada**: la respuesta sale entera, en un solo
mensaje, con sus renglones en blanco adentro. Es la opción para WhatsApp
cuando importa lo que cobra Meta: desde el 1 de octubre de 2026, cada
mensaje que manda el agente se cobra aparte, así que tres globos son tres
mensajes. Cuál conviene lo elige cada uno al instalar (`MENSAJES_POR_RESPUESTA`).

En los dos casos, ningún mensaje pasa de 4.096 caracteres: es el tope de
WhatsApp, y un mensaje más largo no se entrega.
"""

from __future__ import annotations

import re

# Un mensaje suelto de este largo o menos se manda entero.
LARGO_DE_UN_MENSAJE = 320

# Nunca mandamos más de esto: cinco globos seguidos ya es spam.
MAXIMO_DE_MENSAJES = 5

# El tope de WhatsApp para un mensaje de texto. Pasado esto, Meta lo rechaza
# y la persona no recibe nada, así que es lo único que obliga a partir
# aunque se haya pedido un solo mensaje.
LARGO_MAXIMO_DE_WHATSAPP = 4096

_FIN_DE_ORACION = re.compile(r"(?<=[.!?…])\s+")


def partir_respuesta(
    texto: str,
    largo_de_un_mensaje: int = LARGO_DE_UN_MENSAJE,
    maximo: int = MAXIMO_DE_MENSAJES,
) -> list[str]:
    """Devuelve la lista de mensajes a enviar, en orden."""
    texto = _limpiar(texto)
    if not texto:
        return []

    # Un solo mensaje: va entero, sin tocarle los renglones en blanco. Se
    # parte únicamente si no entra en WhatsApp.
    if maximo <= 1:
        return _que_entre_en_whatsapp([texto])

    # 1. El modelo ya separó con renglones en blanco: le hacemos caso.
    bloques = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]
    if len(bloques) > 1:
        return _que_entre_en_whatsapp(_juntar_hasta(bloques, maximo))

    # 2. Entra en un solo mensaje.
    if len(texto) <= largo_de_un_mensaje:
        return [texto]

    # 3. Partir por oraciones, sin cortar ninguna al medio.
    return _que_entre_en_whatsapp(
        _juntar_hasta(_por_oraciones(texto, largo_de_un_mensaje), maximo)
    )


def _limpiar(texto: str) -> str:
    """Normaliza los saltos de línea que mandan los modelos."""
    return (
        (texto or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )


def _por_oraciones(texto: str, largo: int) -> list[str]:
    """Agrupa oraciones hasta llenar cada mensaje."""
    mensajes: list[str] = []
    actual = ""

    for oracion in _FIN_DE_ORACION.split(texto):
        oracion = oracion.strip()
        if not oracion:
            continue

        if not actual:
            actual = oracion
        elif len(actual) + 1 + len(oracion) <= largo:
            actual += " " + oracion
        else:
            mensajes.append(actual)
            actual = oracion

    if actual:
        mensajes.append(actual)

    return mensajes


def _juntar_hasta(mensajes: list[str], maximo: int) -> list[str]:
    """Si quedaron más mensajes que el máximo, pega el sobrante al último."""
    if len(mensajes) <= maximo:
        return mensajes

    return mensajes[: maximo - 1] + ["\n\n".join(mensajes[maximo - 1 :])]


def _que_entre_en_whatsapp(mensajes: list[str]) -> list[str]:
    """Parte lo que no entre en un mensaje de WhatsApp.

    Puede sumar un mensaje más de los pedidos, pero solo cuando la
    alternativa es que no llegue nada: un mensaje de más de 4.096
    caracteres Meta no lo entrega.
    """
    resultado: list[str] = []

    for mensaje in mensajes:
        if len(mensaje) <= LARGO_MAXIMO_DE_WHATSAPP:
            resultado.append(mensaje)
            continue

        # Primero por renglones en blanco, después por oraciones: lo que
        # corte menos la lectura. Cada pedazo sabe si abre un párrafo, para
        # volver a pegarlos con el mismo separador que tenían.
        actual = ""
        for pedazo, abre_parrafo in _pedazos(mensaje):
            separador = "\n\n" if abre_parrafo else " "
            if not actual:
                actual = pedazo
            elif len(actual) + len(separador) + len(pedazo) <= LARGO_MAXIMO_DE_WHATSAPP:
                actual += separador + pedazo
            else:
                resultado.append(actual)
                actual = pedazo
        if actual:
            resultado.append(actual)

    return resultado


def _pedazos(texto: str) -> list[tuple[str, bool]]:
    """Los trozos que entran en un mensaje, sin cortar oraciones.

    Devuelve (trozo, abre_parrafo). Una oración sola de más de 4.096
    caracteres (no pasa, pero un modelo roto puede devolverla) se corta a la
    fuerza: mejor partida que perdida.
    """
    pedazos: list[tuple[str, bool]] = []

    for bloque in re.split(r"\n\s*\n", texto):
        bloque = bloque.strip()
        if not bloque:
            continue
        if len(bloque) <= LARGO_MAXIMO_DE_WHATSAPP:
            pedazos.append((bloque, True))
            continue

        primero = True
        for oracion in _por_oraciones(bloque, LARGO_MAXIMO_DE_WHATSAPP):
            while len(oracion) > LARGO_MAXIMO_DE_WHATSAPP:
                pedazos.append((oracion[:LARGO_MAXIMO_DE_WHATSAPP], primero))
                oracion = oracion[LARGO_MAXIMO_DE_WHATSAPP:]
                primero = False
            if oracion:
                pedazos.append((oracion, primero))
                primero = False

    return pedazos

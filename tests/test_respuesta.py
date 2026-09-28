"""Pruebas de cómo se parte una respuesta en varios mensajes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agente.respuesta import partir_respuesta  # noqa: E402


def test_texto_corto_va_en_un_solo_mensaje():
    assert partir_respuesta("Hola, ¿cómo va?") == ["Hola, ¿cómo va?"]


def test_vacio_no_manda_nada():
    assert partir_respuesta("") == []
    assert partir_respuesta("   \n  ") == []


def test_respeta_los_renglones_en_blanco():
    texto = "Hola.\n\n¿Qué necesitás?\n\nAvisame."
    assert partir_respuesta(texto) == ["Hola.", "¿Qué necesitás?", "Avisame."]


def test_un_salto_simple_no_parte():
    # Un solo salto de línea es parte del mismo mensaje
    texto = "Precio: 100\nEnvío: gratis"
    assert partir_respuesta(texto) == ["Precio: 100\nEnvío: gratis"]


def test_texto_largo_se_parte_por_oraciones():
    oracion = "Esta es una oración de prueba con la que llenamos el mensaje. "
    mensajes = partir_respuesta(oracion * 12, largo_de_un_mensaje=200)

    assert len(mensajes) > 1
    for m in mensajes:
        assert len(m) <= 210, "no debería pasarse mucho del largo pedido"
        assert m == m.strip(), "no tendría que quedar espacio al principio ni al final"


def test_no_corta_una_oracion_al_medio():
    texto = "Primera oración corta. " + "Segunda oración bastante más larga que la primera. " * 6
    for mensaje in partir_respuesta(texto, largo_de_un_mensaje=120):
        assert mensaje.endswith((".", "!", "?", "…")), f"quedó cortada: {mensaje!r}"


def test_nunca_manda_mas_del_maximo():
    texto = "\n\n".join(f"Bloque numero {i}." for i in range(20))
    mensajes = partir_respuesta(texto, maximo=5)

    assert len(mensajes) == 5
    # Nada se pierde: lo que sobraba quedó pegado al último
    assert "Bloque numero 19." in mensajes[-1]


def test_normaliza_los_saltos_de_windows():
    assert partir_respuesta("Hola.\r\n\r\nChau.") == ["Hola.", "Chau."]


# -- Un solo mensaje (lo que cobra Meta es por mensaje) -----------------------

TOPE = 4096


def test_un_solo_mensaje_va_entero_con_sus_parrafos():
    texto = "Hola.\n\n¿Qué necesitás?\n\nAvisame."
    assert partir_respuesta(texto, maximo=1) == [texto]


def test_un_solo_mensaje_largo_no_se_parte_por_oraciones():
    """Con maximo=1 el largo de 320 no aplica: se parte solo por WhatsApp."""
    texto = "Una oración cualquiera para llenar. " * 40  # ~1.400 caracteres
    assert partir_respuesta(texto, maximo=1) == [texto.strip()]


def test_un_solo_mensaje_que_no_entra_en_whatsapp_se_parte():
    """Más de 4.096 caracteres Meta no lo entrega: mejor dos que ninguno."""
    parrafo = "Esta es una oración de prueba para llenar el párrafo. " * 20
    texto = "\n\n".join([parrafo.strip()] * 8)  # ~8.600 caracteres

    mensajes = partir_respuesta(texto, maximo=1)

    assert len(mensajes) > 1
    assert all(len(m) <= TOPE for m in mensajes)
    # Nada se pierde en el camino
    assert sum(m.count("Esta es una oración") for m in mensajes) == 8 * 20


def test_como_persona_el_ultimo_tampoco_pasa_el_tope():
    """Lo que sobra se pega al último globo: ese globo tampoco puede pasarse."""
    bloques = [f"Bloque {i}. " + "Relleno para que pese. " * 60 for i in range(12)]
    mensajes = partir_respuesta("\n\n".join(bloques), maximo=3)

    assert all(len(m) <= TOPE for m in mensajes)
    assert "Bloque 11." in mensajes[-1]


def test_una_oracion_gigante_se_corta_a_la_fuerza():
    """Un modelo roto puede devolver 6.000 letras sin un punto: mejor partida que perdida."""
    mensajes = partir_respuesta("a" * 6000, maximo=1)

    assert [len(m) for m in mensajes] == [TOPE, 6000 - TOPE]

"""Pruebas del tope de mensajes y de su configuración. No gastan tokens.

La hora sale de un reloj de mentira: así se prueba "pasaron 25 horas" sin
esperar 25 horas.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agente.frenos as frenos  # noqa: E402
from agente.config import Config, ErrorDeConfiguracion  # noqa: E402
from agente.frenos import BLOQUEAR, IGNORAR, RESPONDER, TopeDeMensajes  # noqa: E402


class Reloj:
    """Un reloj que avanza cuando uno le dice."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora

    def pasan(self, segundos):
        self.ahora += segundos


def test_sin_tope_contesta_todo():
    tope = TopeDeMensajes(0)
    assert all(tope.anotar("12") == RESPONDER for _ in range(500))


def test_el_que_pasa_el_tope_se_bloquea():
    tope = TopeDeMensajes(3, reloj=Reloj())

    decisiones = [tope.anotar("12") for _ in range(4)]

    assert decisiones == [RESPONDER, RESPONDER, RESPONDER, BLOQUEAR]


def test_cada_conversacion_cuenta_la_suya():
    """Si se mezclaran, una persona pagaría lo que charló otra."""
    tope = TopeDeMensajes(2, reloj=Reloj())

    tope.anotar("111")
    tope.anotar("111")

    assert tope.anotar("222") == RESPONDER


def test_lo_de_ayer_no_cuenta():
    """El tope es por 24 horas: el que escribió mucho ayer, hoy arranca de cero."""
    reloj = Reloj()
    tope = TopeDeMensajes(2, reloj=reloj)

    tope.anotar("12")
    tope.anotar("12")
    reloj.pasan(25 * 60 * 60)

    assert tope.anotar("12") == RESPONDER
    assert tope.anotar("12") == RESPONDER


def test_recien_bloqueada_se_ignora_mientras_llega_la_etiqueta():
    """Chatwoot tarda un momento en mandar los eventos con la etiqueta puesta."""
    reloj = Reloj()
    tope = TopeDeMensajes(1, reloj=reloj)

    tope.anotar("12")
    assert tope.anotar("12") == BLOQUEAR
    reloj.pasan(5)

    assert tope.anotar("12") == IGNORAR


def test_si_le_sacan_la_etiqueta_arranca_de_cero():
    """Pasado el rato de gracia manda la etiqueta de Chatwoot.

    Si un mensaje llega hasta acá, es que alguien del equipo le sacó la
    etiqueta: la persona tiene que poder hablar de nuevo, no quedar
    bloqueada al primer mensaje.
    """
    reloj = Reloj()
    tope = TopeDeMensajes(2, reloj=reloj)

    for _ in range(3):
        tope.anotar("12")
    reloj.pasan(frenos.GRACIA_DESPUES_DE_BLOQUEAR + 1)

    assert tope.anotar("12") == RESPONDER
    assert tope.anotar("12") == RESPONDER


def test_la_memoria_no_crece_para_siempre(monkeypatch):
    """Las conversaciones que no escriben hace un día se olvidan."""
    monkeypatch.setattr(frenos, "LIMPIAR_CADA", 2)
    reloj = Reloj()
    tope = TopeDeMensajes(10, reloj=reloj)

    tope.anotar("vieja")
    reloj.pasan(25 * 60 * 60)
    tope.anotar("nueva")

    assert "vieja" not in tope._mensajes


# -- La configuración ---------------------------------------------------------


@pytest.fixture
def entorno(monkeypatch):
    """Un .env mínimo: solo lo que hace falta para armar la configuración."""
    for nombre in (
        "MENSAJES_POR_RESPUESTA",
        "TOPE_MENSAJES_POR_DIA",
        "LARGO_MAXIMO_DE_ENTRADA",
        "AVISOS_EMAIL",
        "SMTP_SERVIDOR",
        "SMTP_PUERTO",
    ):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("PROVEEDOR", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "no-hace-falta")
    monkeypatch.setenv("MODO", "test")
    return monkeypatch


def test_por_defecto_como_una_persona_y_sin_tope(entorno):
    """Sin tope por defecto: el que actualiza no se encuentra conversaciones
    bloqueadas de golpe. La instalación lo pregunta."""
    config = Config.desde_entorno()

    assert config.mensajes_por_respuesta == 3
    assert config.tope_mensajes_por_dia == 0
    assert config.largo_maximo_de_entrada == 2000
    assert config.avisos_email == ""


def test_lee_lo_que_se_eligio_al_instalar(entorno):
    entorno.setenv("MENSAJES_POR_RESPUESTA", "1")
    entorno.setenv("TOPE_MENSAJES_POR_DIA", "50")
    entorno.setenv("AVISOS_EMAIL", "duenio@ejemplo.com")
    entorno.setenv("SMTP_SERVIDOR", "smtp.gmail.com")
    entorno.setenv("SMTP_PUERTO", "465")

    config = Config.desde_entorno()

    assert config.mensajes_por_respuesta == 1
    assert config.tope_mensajes_por_dia == 50
    assert config.avisos_email == "duenio@ejemplo.com"
    assert config.smtp_puerto == 465


def test_cero_mensajes_por_respuesta_no_tiene_sentido(entorno):
    entorno.setenv("MENSAJES_POR_RESPUESTA", "0")

    with pytest.raises(ErrorDeConfiguracion, match="MENSAJES_POR_RESPUESTA"):
        Config.desde_entorno()


def test_un_tope_negativo_no_tiene_sentido(entorno):
    entorno.setenv("TOPE_MENSAJES_POR_DIA", "-5")

    with pytest.raises(ErrorDeConfiguracion, match="TOPE_MENSAJES_POR_DIA"):
        Config.desde_entorno()


def test_mas_de_cinco_mensajes_por_respuesta_no(entorno):
    """Cinco globos seguidos ya es spam, y cada uno se paga."""
    entorno.setenv("MENSAJES_POR_RESPUESTA", "40")

    with pytest.raises(ErrorDeConfiguracion, match="MENSAJES_POR_RESPUESTA"):
        Config.desde_entorno()


def test_un_recorte_absurdo_no(entorno):
    """Con 0 el agente no lee nada y todas las conversaciones pasarían a humano."""
    entorno.setenv("LARGO_MAXIMO_DE_ENTRADA", "0")

    with pytest.raises(ErrorDeConfiguracion, match="LARGO_MAXIMO_DE_ENTRADA"):
        Config.desde_entorno()


def test_las_claves_no_salen_si_se_imprime_la_configuracion(entorno):
    entorno.setenv("SMTP_CLAVE", "clave-secreta-del-mail")

    texto = repr(Config.desde_entorno())

    assert "no-hace-falta" not in texto, "la clave del modelo"
    assert "clave-secreta-del-mail" not in texto


def test_las_bloqueadas_viejas_tambien_se_olvidan(monkeypatch):
    monkeypatch.setattr(frenos, "LIMPIAR_CADA", 1)
    reloj = Reloj()
    tope = TopeDeMensajes(1, reloj=reloj)

    tope.anotar("12")
    tope.anotar("12")  # bloquea
    reloj.pasan(frenos.GRACIA_DESPUES_DE_BLOQUEAR + 1)
    tope.anotar("otra")

    assert "12" not in tope._bloqueadas_en

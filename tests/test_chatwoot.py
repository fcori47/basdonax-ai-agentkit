"""Pruebas del canal de Chatwoot. No salen a internet ni gastan tokens.

La API de Chatwoot se reemplaza por una de mentira que anota lo que se le
pidió. Lo que se prueba es lo nuestro: qué mensajes se contestan, cuáles no,
cómo se junta una ráfaga y qué sale para el otro lado.

El test más importante de este archivo es
`test_no_se_contesta_a_si_mismo`: sin ese filtro, cada respuesta del agente
vuelve como un mensaje nuevo y el bot se responde solo para siempre,
gastando tokens en cada vuelta.

    pytest
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agente.avisos import Avisos  # noqa: E402
from agente.canales.buffer import BufferDeMensajes  # noqa: E402
from agente.canales.chatwoot import Chatwoot, _tipo_de_mensaje  # noqa: E402
from agente.config import ErrorDeConfiguracion  # noqa: E402
from agente.frenos import TopeDeMensajes  # noqa: E402
from agente.web.webhook import TaparElToken, validar_token  # noqa: E402

# Un token como el que genera el README: largo y al azar.
TOKEN = "3f9a0c" * 8


def evento(
    texto="hola",
    conversacion=12,
    id_mensaje=1,
    tipo="incoming",
    privado=False,
    etiquetas=None,
    nombre="message_created",
    **extra,
) -> dict:
    """Un mensaje como lo manda el webhook de Chatwoot."""
    return {
        "event": nombre,
        "id": id_mensaje,
        "content": texto,
        "message_type": tipo,
        "private": privado,
        "conversation": {
            "id": conversacion,
            "status": "open",
            "labels": [] if etiquetas is None else etiquetas,
        },
        "sender": {"id": 300, "name": "Ana"},
        "account": {"id": 1},
        "inbox": {"id": 1, "name": "WhatsApp"},
        **extra,
    }


class ChatwootFalso(Chatwoot):
    """El canal, pero con la API de mentira. Anota todo lo que se mandó."""

    def __init__(self, etiqueta_humano="humano", etiquetas_remotas=None):
        super().__init__(
            url="https://chatwoot.ejemplo.com/",
            token="token-falso",
            cuenta_id=1,
            etiqueta_humano=etiqueta_humano,
        )
        self.llamadas: list[dict] = []
        self._etiquetas_remotas = etiquetas_remotas or []
        # Como el de verdad: lo que se le pone a una conversación queda puesto
        # (en esa y no en otra), y una conversación se puede resolver.
        self._etiquetas: dict[str, list[str]] = {}
        self.estado = "open"
        self.resueltas_del_contacto = False

    def etiquetas_de(self, conversacion) -> list[str]:
        return self._etiquetas.get(str(conversacion), list(self._etiquetas_remotas))

    def _api(self, metodo, camino, datos=None):
        self.llamadas.append({"metodo": metodo, "camino": camino, "datos": datos})
        partes = camino.split("?")[0].split("/")

        if camino.endswith("/labels"):
            if metodo == "POST":
                self._etiquetas[partes[1]] = list(datos["labels"])
            return {"payload": self.etiquetas_de(partes[1])}
        if partes[0] == "contacts" and partes[-1] == "conversations":
            estado = "resolved" if self.resueltas_del_contacto else "open"
            return {"payload": [{"id": 5, "status": estado}]}
        if metodo == "GET" and len(partes) == 2 and partes[0] == "conversations":
            return {"id": int(partes[1]), "status": self.estado, "labels": self.etiquetas_de(partes[1])}
        return {"id": 99}

    def envios(self) -> list[str]:
        """Solo los mensajes que salieron para la persona (sin las notas privadas)."""
        return [
            l["datos"]["content"]
            for l in self.llamadas
            if l["camino"].endswith("/messages")
            and l["datos"]
            and not l["datos"].get("private")
        ]

    def notas(self) -> list[str]:
        """Las notas privadas: las ve el equipo, nunca la persona."""
        return [
            l["datos"]["content"]
            for l in self.llamadas
            if l["camino"].endswith("/messages")
            and l["datos"]
            and l["datos"].get("private")
        ]

    def etiquetas_mandadas(self) -> list[list[str]]:
        """Cada lista de etiquetas que se le mandó a Chatwoot."""
        return [
            l["datos"]["labels"]
            for l in self.llamadas
            if l["metodo"] == "POST" and l["camino"].endswith("/labels")
        ]


# -- Traducir lo que llega ----------------------------------------------------


def test_traduce_un_mensaje_normal():
    entrante = ChatwootFalso().traducir(evento("¿que clima hace?", conversacion=77, id_mensaje=42))

    assert entrante is not None
    assert entrante.texto == "¿que clima hace?"
    assert entrante.conversacion == "77", "el id de conversación es el thread_id"
    assert entrante.identificador == "42"


def test_el_id_de_conversacion_va_como_texto():
    """Es el thread_id de LangGraph, y ahí un 12 y un "12" no son lo mismo."""
    entrante = ChatwootFalso().traducir(evento(conversacion=12))
    assert isinstance(entrante.conversacion, str)


@pytest.mark.parametrize(
    "nombre",
    ["conversation_created", "conversation_status_changed", "webwidget_triggered"],
)
def test_los_otros_eventos_se_dejan_pasar(nombre):
    """Chatwoot manda muchas cosas por el mismo webhook, no solo mensajes."""
    assert ChatwootFalso().traducir(evento(nombre=nombre)) is None


def test_un_mensaje_sin_texto_se_deja_pasar():
    """Un audio o una foto sueltos: el agente todavía no sabe leer eso."""
    assert ChatwootFalso().traducir(evento(texto="")) is None
    assert ChatwootFalso().traducir(evento(texto="   ")) is None


# -- Qué se contesta y qué no -------------------------------------------------


def test_no_se_contesta_a_si_mismo():
    """EL test de este archivo.

    Cada respuesta que manda el agente vuelve por el webhook como un evento
    nuevo, pero marcada como `outgoing`. Sin este filtro el agente la lee, la
    contesta, esa respuesta vuelve otra vez… y así para siempre, gastando
    tokens en cada vuelta.
    """
    canal = ChatwootFalso()
    entrante = canal.traducir(evento("mi propia respuesta", tipo="outgoing"))

    assert canal.deberia_responder(entrante) is False


def test_no_contesta_las_notas_privadas():
    """Una nota privada es para el equipo. Contestar ahí la manda al cliente."""
    canal = ChatwootFalso()
    entrante = canal.traducir(evento("ojo con este cliente", privado=True))

    assert canal.deberia_responder(entrante) is False


def test_no_contesta_dos_veces_el_mismo_mensaje():
    """Chatwoot reintenta el webhook si no le contestamos a tiempo."""
    canal = ChatwootFalso()
    entrante = canal.traducir(evento(id_mensaje=7))

    assert canal.deberia_responder(entrante) is True
    assert canal.deberia_responder(entrante) is False, "la segunda vez ya no"


def test_la_etiqueta_apaga_el_bot():
    """El traspaso a una persona: se pone la etiqueta y el bot se calla."""
    canal = ChatwootFalso()
    entrante = canal.traducir(evento(etiquetas=["humano"]))

    assert canal.deberia_responder(entrante) is False


def test_la_etiqueta_no_distingue_mayusculas():
    canal = ChatwootFalso()
    assert canal.deberia_responder(canal.traducir(evento(etiquetas=["Humano"]))) is False


def test_otras_etiquetas_no_lo_apagan():
    canal = ChatwootFalso()
    entrante = canal.traducir(evento(etiquetas=["ventas", "urgente"]))

    assert canal.deberia_responder(entrante) is True


def test_si_el_evento_no_trae_etiquetas_se_las_pregunta():
    """Dar por hecho que no hay ninguna sería hablar arriba de una persona."""
    canal = ChatwootFalso(etiquetas_remotas=["humano"])
    crudo = evento()
    del crudo["conversation"]["labels"]

    assert canal.deberia_responder(canal.traducir(crudo)) is False
    assert any(l["camino"].endswith("/labels") for l in canal.llamadas)


def test_un_mensaje_normal_se_contesta():
    canal = ChatwootFalso()
    assert canal.deberia_responder(canal.traducir(evento())) is True


@pytest.mark.parametrize(
    "crudo,esperado",
    [({"message_type": 0}, "incoming"), ({"message_type": 1}, "outgoing")],
)
def test_el_tipo_tambien_se_entiende_como_numero(crudo, esperado):
    """Según la versión, Chatwoot lo manda como texto o como número."""
    assert _tipo_de_mensaje(crudo) == esperado


# -- Lo que sale --------------------------------------------------------------


def test_envia_cada_mensaje_por_separado():
    canal = ChatwootFalso()

    canal.enviar("12", ["primero", "segundo"])

    assert canal.envios() == ["primero", "segundo"]


def test_lo_que_sale_va_marcado_como_outgoing():
    """Si no, Chatwoot no lo empuja a WhatsApp y queda solo en la bandeja."""
    canal = ChatwootFalso()

    canal.enviar("12", ["hola"])

    envio = [l for l in canal.llamadas if l["camino"].endswith("/messages")][0]
    assert envio["datos"]["message_type"] == "outgoing"
    assert envio["camino"] == "conversations/12/messages"


def test_no_manda_mensajes_vacios():
    canal = ChatwootFalso()

    canal.enviar("12", ["hola", "   ", ""])

    assert canal.envios() == ["hola"]


def test_la_barra_final_de_la_url_no_se_duplica():
    """Con "...com//api/v1" Chatwoot devuelve 404 y no se entiende por qué."""
    canal = ChatwootFalso()
    assert canal.url == "https://chatwoot.ejemplo.com"


def test_el_escribiendo_no_voltea_la_respuesta(monkeypatch):
    """Es cosmético: si falla, la respuesta tiene que salir igual."""
    canal = ChatwootFalso()

    def explota(*a, **k):
        raise ConnectionError("se cayó")

    monkeypatch.setattr(canal, "_api", explota)
    canal.escribiendo("12")  # no tiene que levantar nada


def test_sin_datos_avisa_que_faltan():
    with pytest.raises(ValueError, match="CHATWOOT_URL"):
        Chatwoot(url="", token="", cuenta_id=1)


def test_el_canal_ya_no_deja_notas_privadas():
    """Lo que el agente le cuenta al equipo va por la etiqueta y el mail, no por notas."""
    assert not hasattr(ChatwootFalso(), "nota_privada")


def test_pasar_a_persona_no_borra_las_otras_etiquetas():
    """En Chatwoot, mandar etiquetas REEMPLAZA la lista: hay que sumar, no pisar."""
    canal = ChatwootFalso(etiquetas_remotas=["ventas", "urgente"])

    canal.pasar_a_persona("12")

    assert canal.etiquetas_mandadas() == [["ventas", "urgente", "humano"]]


def test_si_ya_la_tiene_no_la_vuelve_a_poner():
    canal = ChatwootFalso(etiquetas_remotas=["Humano"])

    canal.pasar_a_persona("12")

    assert canal.etiquetas_mandadas() == []


def test_si_no_puede_leer_las_etiquetas_no_pisa_nada(monkeypatch):
    """Mejor no poner la etiqueta que borrarle al equipo las que puso a mano."""
    canal = ChatwootFalso()

    def falla_al_leer(metodo, camino, datos=None):
        canal.llamadas.append({"metodo": metodo, "camino": camino, "datos": datos})
        if metodo == "GET":
            raise ConnectionError("Chatwoot no contesta")
        return {}

    monkeypatch.setattr(canal, "_api", falla_al_leer)

    with pytest.raises(ConnectionError):
        canal.pasar_a_persona("12")
    assert canal.etiquetas_mandadas() == []


def test_el_enlace_lleva_a_la_conversacion():
    assert (
        ChatwootFalso().enlace("55")
        == "https://chatwoot.ejemplo.com/app/accounts/1/conversations/55"
    )


# -- Juntar la ráfaga ---------------------------------------------------------


def juntar(buffer: BufferDeMensajes, mensajes, conversacion="12", entre=0.0):
    """Manda varios mensajes seguidos y espera a que el buffer los suelte."""

    async def correr():
        for texto in mensajes:
            await buffer.agregar(conversacion, texto)
            if entre:
                await asyncio.sleep(entre)
        # Un rato más que la espera del buffer, para que llegue a soltar.
        await asyncio.sleep(buffer.segundos + 0.15)

    asyncio.run(correr())


def test_tres_mensajes_seguidos_son_una_sola_respuesta():
    """El caso de todos los días: "hola" / "una consulta" / "por el precio"."""
    sueltos = []
    buffer = BufferDeMensajes(
        0.05, lambda c, t: _anotar(sueltos, c, t)
    )

    juntar(buffer, ["hola", "una consulta", "por el precio"])

    assert len(sueltos) == 1, "tendría que haber contestado una sola vez"
    assert sueltos[0] == ("12", "hola\nuna consulta\npor el precio")


def test_cada_conversacion_junta_la_suya():
    """Si se mezclaran, una persona recibiría el mensaje de otra."""
    sueltos = []
    buffer = BufferDeMensajes(0.05, lambda c, t: _anotar(sueltos, c, t))

    async def correr():
        await buffer.agregar("111", "soy uno")
        await buffer.agregar("222", "soy dos")
        await asyncio.sleep(0.25)

    asyncio.run(correr())

    assert sorted(sueltos) == [("111", "soy uno"), ("222", "soy dos")]


def test_sin_espera_contesta_derecho():
    """BUFFER_SEGUNDOS=0 apaga el buffer."""
    sueltos = []
    buffer = BufferDeMensajes(0, lambda c, t: _anotar(sueltos, c, t))

    asyncio.run(buffer.agregar("12", "hola"))

    assert sueltos == [("12", "hola")]


def test_el_tope_corta_la_espera_infinita():
    """Sin tope, alguien que escribe de a poco no recibe respuesta nunca.

    Cada mensaje reinicia el reloj. Si la persona manda uno justo antes de
    que se cumpla la espera, y otro, y otro, el agente se quedaría esperando
    para siempre. El tope obliga a contestar igual.
    """
    sueltos = []
    buffer = BufferDeMensajes(
        0.20, lambda c, t: _anotar(sueltos, c, t), tope=0.30
    )

    # Seis mensajes cada 0,1s = 0,6s de charla. Con la espera de 0,2s
    # reiniciándose cada vez, sin tope no soltaría hasta el final.
    juntar(buffer, ["a", "b", "c", "d", "e", "f"], entre=0.1)

    assert sueltos, "el tope tendría que haber forzado la respuesta"
    assert len(sueltos[0][1].split("\n")) < 6, "soltó antes de que terminara"


def test_al_apagar_no_se_pierde_lo_que_estaba_esperando():
    """Un deploy justo en esos segundos dejaría a alguien sin respuesta."""
    sueltos = []
    buffer = BufferDeMensajes(30, lambda c, t: _anotar(sueltos, c, t))

    async def correr():
        await buffer.agregar("12", "hola")
        assert buffer.pendientes("12") == 1
        await buffer.vaciar()

    asyncio.run(correr())

    assert sueltos == [("12", "hola")]


async def _anotar(donde, conversacion, texto):
    donde.append((conversacion, texto))


# -- El webhook entero, de punta a punta --------------------------------------
#
# Acá se pegan todas las piezas: llega el pedido de Chatwoot, contesta el
# agente, sale la respuesta. Con un canal de mentira y un modelo de mentira,
# así que no toca la red ni gasta un token.

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AvisosFalsos(Avisos):
    """Los avisos por mail, pero anotados en vez de mandados."""

    def __init__(self, **opciones):
        super().__init__(
            para="duenio@ejemplo.com",
            servidor="smtp.ejemplo.com",
            usuario="agente@ejemplo.com",
            clave="clave-de-aplicacion",
            **opciones,
        )
        self.mandados: list[tuple[str, str]] = []

    def _enviar(self, asunto, cuerpo):
        self.mandados.append((asunto, cuerpo))


def cliente(
    canal,
    agente,
    token=TOKEN,
    buffer_segundos=0,
    avisos=None,
    tope=None,
    lector=None,
    **ajustes,
):
    """Levanta el webhook con las piezas de mentira adentro."""
    pytest.importorskip("httpx", reason="TestClient de FastAPI necesita httpx")
    from fastapi.testclient import TestClient

    from agente.web.webhook import crear_app

    from test_agente import agente_falso  # noqa: F401  (deja src en sys.path)

    # Sin la pausa entre globos, salvo que la prueba la pida: son segundos de
    # espera de verdad y acá no se mira el reloj.
    ajustes.setdefault("pausa_entre_globos", False)

    config = agente.config
    config.chatwoot_webhook_token = token
    config.buffer_segundos = buffer_segundos
    for nombre, valor in ajustes.items():
        setattr(config, nombre, valor)

    return TestClient(
        crear_app(
            config,
            agente=agente,
            canal=canal,
            avisos=avisos or AvisosFalsos(),
            tope=tope,
            lector=lector,
        )
    )


def esperar(condicion, segundos=2.0):
    """Lo que corre en segundo plano en el servidor de prueba termina solo."""
    import time

    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return condicion()


def test_el_mensaje_da_la_vuelta_completa():
    from test_agente import agente_falso

    canal = ChatwootFalso()
    agente = agente_falso(["¡Buenas! ¿En qué te ayudo?"])

    with cliente(canal, agente) as web:
        respuesta = web.post(f"/chatwoot/{TOKEN}", json=evento("hola", conversacion=55))

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "recibido"
    assert canal.envios() == ["¡Buenas! ¿En qué te ayudo?"]


def test_con_el_token_equivocado_no_entra():
    """Es lo único que separa a Chatwoot de cualquiera que sepa el dominio."""
    from test_agente import agente_falso

    canal = ChatwootFalso()

    with cliente(canal, agente_falso(["hola"])) as web:
        respuesta = web.post("/chatwoot/no-es-este", json=evento())

    assert respuesta.status_code == 401
    assert canal.envios() == [], "no tiene que haber contestado nada"


def test_su_propia_respuesta_no_dispara_otra():
    """El ida y vuelta infinito, probado de punta a punta."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    agente = agente_falso(["no debería usarse"])

    with cliente(canal, agente) as web:
        respuesta = web.post(f"/chatwoot/{TOKEN}", json=evento(tipo="outgoing"))

    assert respuesta.json()["estado"] == "ignorado"
    assert canal.envios() == []


def test_si_el_modelo_falla_el_cliente_no_ve_el_error():
    """Lo que ve el que escribió nunca es un error técnico.

    El error no se esconde: llega completo al mail del dueño, y la
    conversación pasa a una persona (la etiqueta) para que nadie quede
    esperando en silencio. Nota privada, ninguna.
    """
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()
    agente = agente_falso([])  # sin respuestas: el modelo falso revienta

    with cliente(canal, agente, avisos=avisos) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola", conversacion=55))

    assert canal.envios() == [], "al cliente no le tiene que llegar nada"
    assert canal.notas() == [], "sin notas privadas"
    assert canal.etiquetas_mandadas() == [["humano"]]

    assert len(avisos.mandados) == 1
    asunto, cuerpo = avisos.mandados[0]
    assert "no pudo responder" in asunto
    assert "conversations/55" in cuerpo, "el mail lleva a la conversación"


def test_el_mismo_error_no_manda_un_mail_por_persona():
    """Con la clave del modelo vencida falla todo: un mail, no cien."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()
    agente = agente_falso([])

    with cliente(canal, agente, avisos=avisos) as web:
        for i, conversacion in enumerate([55, 56, 57]):
            web.post(
                f"/chatwoot/{TOKEN}",
                json=evento("hola", conversacion=conversacion, id_mensaje=100 + i),
            )

    assert len(avisos.mandados) == 1
    assert canal.etiquetas_mandadas() == [["humano"]] * 3, "cada conversación queda con su etiqueta"


def test_si_chatwoot_no_acepta_la_respuesta_avisa_por_mail(monkeypatch):
    """Si falla la salida, queda el mail."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()

    def explota(conversacion, mensajes, *otros):
        raise ConnectionError("Chatwoot no contesta")

    monkeypatch.setattr(canal, "enviar", explota)

    with cliente(canal, agente_falso(["hola"]), avisos=avisos) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert len(avisos.mandados) == 1
    assert "Chatwoot no contesta" in avisos.mandados[0][1]
    # Aunque falló el envío, se intenta igual pasarla a una persona: muchas
    # veces lo que falla es solo ese mensaje, no Chatwoot.
    assert canal.etiquetas_mandadas() == [["humano"]]


# -- Cómo responde: como una persona o en un solo mensaje ---------------------


def test_como_una_persona_manda_hasta_tres():
    from test_agente import agente_falso

    canal = ChatwootFalso()
    respuesta = "\n\n".join(f"Parte {i}." for i in range(1, 6))

    with cliente(canal, agente_falso([respuesta]), mensajes_por_respuesta=3) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert len(canal.envios()) == 3
    assert "Parte 5." in canal.envios()[-1], "lo que sobra va al último: no se pierde"


def test_en_un_solo_mensaje_sale_uno():
    """Lo que cobra Meta es por mensaje: esto es un mensaje, no tres."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    respuesta = "Hola.\n\n¿Qué necesitás?\n\nAvisame."

    with cliente(canal, agente_falso([respuesta]), mensajes_por_respuesta=1) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert canal.envios() == [respuesta]


# -- Los frenos ---------------------------------------------------------------


def test_al_pasar_el_tope_pasa_a_una_persona_y_se_calla():
    """El que se queda charlando de cualquier cosa: al tope, a una persona."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    agente = agente_falso(["uno", "dos", "no debería usarse"])

    with cliente(canal, agente, tope=TopeDeMensajes(2)) as web:
        estados = [
            web.post(f"/chatwoot/{TOKEN}", json=evento("hola", id_mensaje=i)).json()[
                "estado"
            ]
            for i in (1, 2, 3, 4)
        ]
        assert esperar(lambda: canal.etiquetas_mandadas()), "tendría que haber puesto la etiqueta"

    assert estados == ["recibido", "recibido", "tope", "tope"]
    assert canal.envios() == ["uno", "dos"]
    assert canal.etiquetas_mandadas() == [["humano"]]
    assert canal.notas() == []


def test_un_pedido_gigante_se_descarta():
    """Medio mega ya no es un mensaje de WhatsApp."""
    from test_agente import agente_falso

    canal = ChatwootFalso()

    with cliente(canal, agente_falso(["no debería usarse"])) as web:
        respuesta = web.post(f"/chatwoot/{TOKEN}", json=evento("x" * 600_000))

    assert respuesta.status_code == 413
    assert canal.envios() == []


def test_lo_que_entra_se_recorta_antes_de_llegar_al_modelo():
    """Un texto pegado enorme se pagaría en este mensaje y en todos los que siguen."""
    from test_agente import agente_falso

    agente = agente_falso(["listo"])

    with cliente(ChatwootFalso(), agente, largo_maximo_de_entrada=50) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("a" * 5000, conversacion=77))

    lo_que_llego = [m for m in agente.historial("77") if m.type == "human"][0]
    assert len(lo_que_llego.content) == 50


def test_la_clave_no_queda_en_los_logs():
    """uvicorn anota la dirección de cada pedido, y la del webhook lleva la clave."""
    import logging

    from agente.web.webhook import TaparElToken

    registro = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "POST", "/chatwoot/la-clave-secreta", "1.1", 200),
        None,
    )

    TaparElToken().filter(registro)

    assert "la-clave-secreta" not in registro.getMessage()
    assert "/chatwoot/***" in registro.getMessage()


def test_el_salud_contesta():
    """Coolify le pega a esto; si no contesta, reinicia el contenedor."""
    from test_agente import agente_falso

    with cliente(ChatwootFalso(), agente_falso(["hola"])) as web:
        respuesta = web.get("/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


# -- Lo que se sumó con la auditoría -------------------------------------------


@pytest.mark.parametrize(
    "token",
    ["", "corto", "un-secreto-largo-y-al-azar", "x" * 40 + "!", "con espacios" * 4],
)
def test_sin_token_o_con_uno_debil_no_arranca(token):
    """Un token vacío deja al agente mudo; uno débil deja entrar a cualquiera."""
    with pytest.raises(ErrorDeConfiguracion, match="CHATWOOT_WEBHOOK_TOKEN"):
        validar_token(token)


def test_un_token_largo_y_al_azar_arranca():
    validar_token(TOKEN)  # no levanta nada


@pytest.mark.parametrize(
    "crudo",
    [
        [1, 2],
        "hola",
        {"event": "message_created", "content": "hola", "conversation": "12"},
        {"event": "message_created", "content": 123, "conversation": {"id": 12}},
        {"event": "message_created", "content": "hola", "conversation": {"id": "12; <a href>"}},
        {"event": "message_created", "content": "hola", "conversation": {"id": True}},
    ],
)
def test_un_evento_con_otra_forma_se_ignora(crudo):
    """Lo que viene de afuera se valida: no tira el servidor ni se cuela en un mail."""
    assert ChatwootFalso().traducir(crudo) is None


def test_un_cuerpo_que_no_es_un_objeto_da_400():
    from test_agente import agente_falso

    with cliente(ChatwootFalso(), agente_falso(["hola"])) as web:
        respuesta = web.post(f"/chatwoot/{TOKEN}", json=[1, 2])

    assert respuesta.status_code == 400


def test_una_respuesta_vacia_pasa_a_una_persona():
    """Si el modelo no dice nada, la persona no puede quedarse esperando en silencio."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()

    with cliente(canal, agente_falso([""]), avisos=avisos) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert canal.envios() == []
    assert canal.etiquetas_mandadas() == [["humano"]]
    assert len(avisos.mandados) == 1
    assert "vacía" in avisos.mandados[0][1]


def test_si_no_puede_poner_la_etiqueta_el_mail_no_miente(monkeypatch):
    """El mail no puede decir «quedó con la etiqueta» si no se pudo."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()

    def falla(conversacion):
        raise ConnectionError("Chatwoot no contesta")

    monkeypatch.setattr(canal, "pasar_a_persona", falla)

    with cliente(canal, agente_falso([]), avisos=avisos) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    cuerpo = avisos.mandados[0][1]
    assert "No se pudo poner la etiqueta" in cuerpo
    assert "quedó con la etiqueta" not in cuerpo


def test_no_hay_documentacion_publica_del_webhook():
    """/docs y /openapi.json le mostrarían a cualquiera qué rutas tiene."""
    from test_agente import agente_falso

    with cliente(ChatwootFalso(), agente_falso(["hola"])) as web:
        assert web.get("/docs").status_code == 404
        assert web.get("/openapi.json").status_code == 404


@pytest.mark.parametrize(
    "linea",
    [
        "POST /Chatwoot/{t} HTTP/1.1",
        "POST /chatwoot?token={t} HTTP/1.1",
        "POST /chatwoot//{t} HTTP/1.1",
        "algo falló con {t} adentro",
    ],
)
def test_la_clave_se_tapa_aunque_la_direccion_este_mal_escrita(linea):
    """Una URL mal configurada en Chatwoot se reintenta sola, y cada intento se anota."""
    import logging

    registro = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", (linea.format(t=TOKEN),), None)
    TaparElToken(TOKEN).filter(registro)

    assert TOKEN not in registro.getMessage()


# -- Con los avisos por Google, el permiso se usa aunque no haya nada que avisar --


def test_con_google_el_servidor_usa_el_permiso_al_arrancar(monkeypatch):
    """Google borra el permiso que pasa seis meses sin usarse."""
    from test_agente import agente_falso

    avisos = Avisos(para="duenio@ejemplo.com", gmail_cliente="c", gmail_secreto="s", gmail_permiso="p")
    usos = []
    monkeypatch.setattr(avisos, "revisar", lambda: usos.append(1))

    with cliente(ChatwootFalso(), agente_falso(["hola"]), avisos=avisos):
        assert esperar(lambda: usos), "al arrancar se usa el permiso"


def test_con_smtp_no_hay_nada_que_mantener(monkeypatch):
    from test_agente import agente_falso

    avisos = AvisosFalsos()
    usos = []
    monkeypatch.setattr(avisos, "revisar", lambda: usos.append(1))

    with cliente(ChatwootFalso(), agente_falso(["hola"]), avisos=avisos):
        esperar(lambda: usos, segundos=0.3)

    assert usos == []


def test_el_permiso_se_sigue_usando_aunque_una_vez_falle(caplog):
    """Si Google no acepta el permiso, queda en el registro y se vuelve a probar."""
    import logging

    from agente.web.webhook import mantener_el_permiso

    usos = []

    class AvisosDeGoogle:
        def revisar(self):
            usos.append(1)
            if len(usos) == 1:
                raise RuntimeError("Google ya no acepta el permiso guardado")

    async def correr():
        tarea = asyncio.create_task(mantener_el_permiso(AvisosDeGoogle(), cada=0.01))
        await asyncio.sleep(0.2)
        tarea.cancel()

    with caplog.at_level(logging.INFO, logger="agente.webhook"):
        asyncio.run(correr())

    assert len(usos) >= 2, "después de fallar, lo sigue intentando"
    assert "NO van a salir" in caplog.text
    assert "el permiso para mandar mails anda" in caplog.text


# -- Lo que llega que no es texto -----------------------------------------------------

ARCHIVO = "https://chat.publico.ejemplo.com/rails/active_storage/blobs/redirect/abc/foto.jpg?x=1"


def test_un_mensaje_sin_texto_pero_con_una_foto_se_traduce():
    """Antes se descartaba: el que manda solo una foto se quedaba sin respuesta."""
    e = evento(None, attachments=[{"id": 6, "file_type": "image", "data_url": ARCHIVO}])

    entrante = ChatwootFalso().traducir(e)

    assert entrante is not None and entrante.texto == ""


def test_una_respuesta_citando_sin_texto_propio_tambien_se_traduce():
    e = evento(None, content_attributes={"in_reply_to": 40}, attachments=[
        {"file_type": "location", "coordinates_lat": 1, "coordinates_long": 2}])

    assert ChatwootFalso().traducir(e) is not None


class RespuestaDeArchivo:
    def __init__(self, cuerpo=b"jpg", tipo="image/jpeg", largo=None):
        import email.message

        self._cuerpo = cuerpo
        self.headers = email.message.Message()
        self.headers["Content-Type"] = tipo
        if largo is not None:
            self.headers["Content-Length"] = str(largo)

    def read(self, cuanto=-1):
        return self._cuerpo if cuanto < 0 else self._cuerpo[:cuanto]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class AbridorDeArchivos:
    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta or RespuestaDeArchivo()
        self.error = error
        self.pedidos = []

    def open(self, pedido, timeout=None):
        self.pedidos.append(pedido)
        if self.error:
            raise self.error
        return self.respuesta


def test_los_archivos_se_bajan_solo_de_tu_chatwoot(monkeypatch):
    """Del evento se usa el camino; el servidor siempre sale contra CHATWOOT_URL, y sin el token."""
    import agente.canales.chatwoot as chatwoot_mod

    abridor = AbridorDeArchivos()
    monkeypatch.setattr(chatwoot_mod, "_ABRIDOR_DE_ARCHIVOS", abridor)

    datos, tipo = ChatwootFalso().bajar(ARCHIVO, 1024)

    assert (datos, tipo) == (b"jpg", "image/jpeg")
    pedido = abridor.pedidos[0]
    assert pedido.full_url == "https://chatwoot.ejemplo.com/rails/active_storage/blobs/redirect/abc/foto.jpg?x=1"
    assert not pedido.has_header("Api_access_token"), "el archivo ya viene firmado: el token no viaja"


def test_una_direccion_que_no_es_de_un_archivo_de_chatwoot_no_se_baja(monkeypatch):
    import agente.canales.chatwoot as chatwoot_mod

    abridor = AbridorDeArchivos()
    monkeypatch.setattr(chatwoot_mod, "_ABRIDOR_DE_ARCHIVOS", abridor)

    with pytest.raises(chatwoot_mod.ErrorDeChatwoot):
        ChatwootFalso().bajar("http://169.254.169.254/latest/meta-data/", 1024)
    assert abridor.pedidos == []


def test_un_archivo_que_pasa_el_tope_no_se_baja_entero(monkeypatch):
    import agente.canales.chatwoot as chatwoot_mod

    monkeypatch.setattr(chatwoot_mod, "_ABRIDOR_DE_ARCHIVOS", AbridorDeArchivos(RespuestaDeArchivo(b"x" * 50)))

    with pytest.raises(chatwoot_mod.ErrorDeChatwoot, match="pesa más"):
        ChatwootFalso().bajar(ARCHIVO, 10)


def test_si_chatwoot_todavia_no_tiene_el_archivo_se_puede_reintentar(monkeypatch):
    import io
    import urllib.error

    import agente.canales.chatwoot as chatwoot_mod
    from agente.canales.adjuntos import ArchivoTodaviaNoEsta

    error = urllib.error.HTTPError(ARCHIVO, 404, "no", {}, io.BytesIO(b""))
    monkeypatch.setattr(chatwoot_mod, "_ABRIDOR_DE_ARCHIVOS", AbridorDeArchivos(error=error))

    with pytest.raises(ArchivoTodaviaNoEsta):
        ChatwootFalso().bajar(ARCHIVO, 1024)


def test_busca_el_mensaje_citado_en_las_paginas_de_atras(monkeypatch):
    canal = ChatwootFalso()
    paginas = {
        "conversations/12/messages": [{"id": 90}, {"id": 80}],
        "conversations/12/messages?before=80": [{"id": 70, "content": "el citado"}, {"id": 60}],
    }
    monkeypatch.setattr(canal, "_api", lambda metodo, camino, datos=None: {"payload": paginas.get(camino, [])})

    assert canal.mensaje("12", 70) == {"id": 70, "content": "el citado"}
    assert canal.mensaje("12", 5) is None


def test_lo_agarro_otro_mira_la_etiqueta_y_si_la_resolvieron():
    canal = ChatwootFalso()
    assert canal.lo_agarro_otro("12") == ""

    canal.pasar_a_persona("12")
    assert "humano" in canal.lo_agarro_otro("12")

    otro = ChatwootFalso()
    otro.estado = "resolved"
    assert otro.lo_agarro_otro("12") == "la resolvieron"


def test_si_chatwoot_no_contesta_la_segunda_mirada_se_responde_igual(monkeypatch):
    canal = ChatwootFalso()

    def falla(*a, **k):
        raise ConnectionError("no contesta")

    monkeypatch.setattr(canal, "_api", falla)

    assert canal.lo_agarro_otro("12") == ""
    assert canal.ya_la_cerro("300") is False


def test_la_pausa_entre_globos_escribe_antes_de_cada_uno(monkeypatch):
    import agente.canales.chatwoot as chatwoot_mod

    pausas, puntitos = [], []
    monkeypatch.setattr(chatwoot_mod.time, "sleep", pausas.append)
    canal = ChatwootFalso()

    canal.enviar("12", ["Hola.", "", "A Córdoba llega en 3 a 5 días.", "¿Te lo armo?"],
                 lambda: puntitos.append(1), chatwoot_mod.tarda_en_escribir)

    assert canal.envios() == ["Hola.", "A Córdoba llega en 3 a 5 días.", "¿Te lo armo?"]
    assert len(pausas) == 2 and len(puntitos) == 2, "el primero sale derecho; los otros, escribiendo"
    assert all(chatwoot_mod.PAUSA_MINIMA <= p <= chatwoot_mod.PAUSA_MAXIMA for p in pausas)


def test_cuanto_tarda_en_escribir_tiene_piso_y_techo():
    from agente.canales.chatwoot import PAUSA_MAXIMA, PAUSA_MINIMA, tarda_en_escribir

    assert tarda_en_escribir("ok") == PAUSA_MINIMA
    assert tarda_en_escribir("x" * 5000) == PAUSA_MAXIMA
    assert PAUSA_MINIMA < tarda_en_escribir("x" * 66) < PAUSA_MAXIMA


# -- El webhook con todo lo nuevo -------------------------------------------------------


class LectorDeMentira:
    """Hace de lector de adjuntos: devuelve lo que se le diga."""

    def __init__(self, texto="", a_una_persona=""):
        from agente.canales.adjuntos import Leido

        self.leido = Leido(texto, a_una_persona=a_una_persona)
        self.leidos = []

    def leer(self, mensaje):
        self.leidos.append(mensaje)
        return self.leido


def ultimo_mensaje_de_la_persona(agente, conversacion):
    from langchain_core.messages import HumanMessage

    humanos = [m for m in agente.historial(conversacion) if isinstance(m, HumanMessage)]
    return humanos[-1].content if humanos else None


def test_una_foto_le_llega_al_agente_como_texto():
    from test_agente import agente_falso

    canal = ChatwootFalso()
    agente = agente_falso(["Sí, la tenemos en negro."])
    lector = LectorDeMentira("[La persona mandó una foto. Se ve: una zapatilla blanca]\n¿la tienen en negro?")
    e = evento("¿la tienen en negro?", conversacion=77,
               attachments=[{"id": 6, "file_type": "image", "data_url": ARCHIVO}])

    with cliente(canal, agente, lector=lector) as web:
        assert web.post(f"/chatwoot/{TOKEN}", json=e).json()["estado"] == "recibido"
        assert esperar(lambda: canal.envios())

    assert canal.envios() == ["Sí, la tenemos en negro."]
    assert ultimo_mensaje_de_la_persona(agente, "77").startswith("[La persona mandó una foto.")


def test_un_audio_sin_como_escucharlo_pasa_a_una_persona_y_el_agente_no_contesta():
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()
    lector = LectorDeMentira("[La persona mandó un audio y no lo puedo escuchar.]", a_una_persona="falta la clave")
    e = evento(None, attachments=[{"id": 5, "file_type": "audio", "data_url": ARCHIVO}])

    with cliente(canal, agente_falso([]), avisos=avisos, lector=lector) as web:
        web.post(f"/chatwoot/{TOKEN}", json=e)
        assert esperar(lambda: canal.etiquetas_mandadas())

    assert canal.etiquetas_mandadas() == [["humano"]]
    assert canal.envios() == [], "la segunda mirada ve la etiqueta: no contesta"
    assert avisos.mandados == [], "no es un error: nadie tiene que arreglar nada"


def test_si_la_agarran_mientras_esperaba_no_contesta(monkeypatch):
    """Pasó en producción: la etiquetaron a los 10 segundos y el agente contestó igual a los 100."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    avisos = AvisosFalsos()
    monkeypatch.setattr(canal, "lo_agarro_otro", lambda conversacion: "le pusieron «humano»")

    with cliente(canal, agente_falso([]), avisos=avisos) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert canal.envios() == []
    assert avisos.mandados == [], "no llegó a llamar al modelo: ni un token"


def test_se_mira_otra_vez_justo_antes_de_mandar(monkeypatch):
    from test_agente import agente_falso

    canal = ChatwootFalso()
    miradas = iter(["", "la resolvieron"])
    monkeypatch.setattr(canal, "lo_agarro_otro", lambda conversacion: next(miradas))

    with cliente(canal, agente_falso(["hola"])) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola"))

    assert canal.envios() == [], "la escribió, pero ya no le tocaba mandarla"


def test_resolver_deja_la_etiqueta_si_se_eligio_al_instalar():
    """Con Chatwoot que reabre la MISMA conversación: la etiqueta es lo que queda."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    resuelta = {"event": "conversation_status_changed", "id": 88, "status": "resolved"}

    with cliente(canal, agente_falso([]), respetar_resueltas=True) as web:
        assert web.post(f"/chatwoot/{TOKEN}", json=resuelta).json()["estado"] == "resuelta"
        assert esperar(lambda: canal.etiquetas_mandadas())

    assert canal.etiquetas_de(88) == ["humano"]


def test_resolver_no_cambia_nada_si_no_se_eligio():
    from test_agente import agente_falso

    canal = ChatwootFalso()
    resuelta = {"event": "conversation_status_changed", "id": 88, "status": "resolved"}

    with cliente(canal, agente_falso([]), respetar_resueltas=False) as web:
        assert web.post(f"/chatwoot/{TOKEN}", json=resuelta).json()["estado"] == "ignorado"

    assert canal.etiquetas_mandadas() == []


def test_con_una_conversacion_resuelta_de_antes_no_le_vuelve_a_hablar():
    """Con Chatwoot que abre una conversación NUEVA: se mira a la persona, no a la charla."""
    from test_agente import agente_falso

    canal = ChatwootFalso()
    canal.resueltas_del_contacto = True

    with cliente(canal, agente_falso(["no debería salir"]), respetar_resueltas=True) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola de nuevo", conversacion=91))
        assert esperar(lambda: canal.etiquetas_mandadas())

    assert canal.envios() == []
    assert canal.etiquetas_de(91) == ["humano"], "en la bandeja se ve que calla a propósito"


def test_contestar_solo_el_primero_pasa_la_charla_despues_de_mandar():
    from test_agente import agente_falso

    canal = ChatwootFalso()

    with cliente(canal, agente_falso(["¡Hola! Contame qué necesitás."]), solo_el_primer_mensaje=True) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola", conversacion=60))

    assert canal.envios() == ["¡Hola! Contame qué necesitás."]
    assert canal.etiquetas_de(60) == ["humano"]


def test_por_defecto_sigue_toda_la_charla():
    from test_agente import agente_falso

    canal = ChatwootFalso()

    with cliente(canal, agente_falso(["uno", "dos"])) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola", id_mensaje=1))
        web.post(f"/chatwoot/{TOKEN}", json=evento("otra", id_mensaje=2))

    assert canal.envios() == ["uno", "dos"]
    assert canal.etiquetas_mandadas() == []


def test_el_visto_y_los_puntitos_salen_con_los_datos_de_meta(monkeypatch):
    import agente.web.webhook as webhook_mod
    from test_agente import agente_falso

    vistos = []
    monkeypatch.setattr(webhook_mod, "marcar_visto_y_escribiendo", lambda *a: vistos.append(a))
    canal = ChatwootFalso()
    e = evento("hola", source_id="wamid.de-prueba-0001")

    with cliente(canal, agente_falso(["¡Hola!"]), whatsapp_token="token-de-meta",
                 whatsapp_phone_number_id="1234567890") as web:
        web.post(f"/chatwoot/{TOKEN}", json=e)

    assert vistos == [("wamid.de-prueba-0001", "token-de-meta", "1234567890")]


def test_sin_datos_de_meta_no_sale_el_visto(monkeypatch):
    import agente.web.webhook as webhook_mod
    from test_agente import agente_falso

    vistos = []
    monkeypatch.setattr(webhook_mod, "marcar_visto_y_escribiendo", lambda *a: vistos.append(a))

    with cliente(ChatwootFalso(), agente_falso(["¡Hola!"])) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola", source_id="wamid.de-prueba-0001"))

    assert vistos == []


def test_reset_borra_la_memoria_de_una_conversacion():
    from test_agente import agente_falso

    agente = agente_falso(["hola", "hola de nuevo"])

    with cliente(ChatwootFalso(), agente) as web:
        web.post(f"/chatwoot/{TOKEN}", json=evento("hola", conversacion=12))
        assert agente.historial("12")

        assert web.post(f"/reset/{TOKEN}", json={"conversacion": "12"}).json() == {
            "estado": "ok", "conversacion": "12"}

    assert agente.historial("12") == []


@pytest.mark.parametrize(
    "token, cuerpo, codigo",
    [
        ("otro-token-" + "x" * 30, {"conversacion": "12"}, 401),
        (TOKEN, {}, 400),
        (TOKEN, {"conversacion": "todas"}, 400),
        (TOKEN, {"conversacion": "12; DROP"}, 400),
    ],
)
def test_reset_pide_la_clave_y_de_a_una_conversacion(token, cuerpo, codigo):
    from test_agente import agente_falso

    with cliente(ChatwootFalso(), agente_falso([])) as web:
        assert web.post(f"/reset/{token}", json=cuerpo).status_code == codigo


def test_la_clave_se_tapa_tambien_en_el_reset():
    import logging

    linea = f"POST /reset/{TOKEN} HTTP/1.1"
    registro = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", (linea,), None)
    TaparElToken(TOKEN).filter(registro)

    assert TOKEN not in registro.getMessage()


# -- La ráfaga respeta el orden de llegada ---------------------------------------------


def test_una_foto_que_se_esta_leyendo_no_pierde_su_lugar():
    """La foto llega primero y tarda en leerse: igual va primero en la ráfaga."""
    sueltos = []

    async def correr():
        buffer = BufferDeMensajes(0.05, lambda c, t: _anotar(sueltos, c, t))

        async def leer_la_foto():
            await asyncio.sleep(0.1)
            return "[La persona mandó una foto. Se ve: un auto rojo]"

        await buffer.agregar("12", asyncio.create_task(leer_la_foto()))
        await buffer.agregar("12", "¿cuánto sale?")
        await asyncio.sleep(0.4)

    asyncio.run(correr())

    assert sueltos == [("12", "[La persona mandó una foto. Se ve: un auto rojo]\n¿cuánto sale?")]


def test_una_parte_que_no_dejo_nada_no_se_contesta():
    sueltos = []

    async def correr():
        buffer = BufferDeMensajes(0.02, lambda c, t: _anotar(sueltos, c, t))

        async def nada():
            return ""

        await buffer.agregar("12", asyncio.create_task(nada()))
        await asyncio.sleep(0.2)

    asyncio.run(correr())

    assert sueltos == []

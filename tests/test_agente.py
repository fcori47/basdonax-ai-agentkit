"""Pruebas del agente. No gastan un solo token: usan un modelo falso.

    pip install pytest
    pytest
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agente.agente import Agente  # noqa: E402
from agente.config import RAIZ, Config, ErrorDeConfiguracion  # noqa: E402
from agente.memoria import ram  # noqa: E402
from agente.prompts import leer_prompt  # noqa: E402


class ModeloFalso(GenericFakeChatModel):
    """El modelo de mentira, pero que se deja atar herramientas.

    GenericFakeChatModel no implementa bind_tools() y el grafo lo llama al
    construirse, así que sin esto no arranca ni un test. Como el modelo falso
    devuelve texto fijo y nunca pide una herramienta, alcanza con que se
    devuelva a sí mismo.
    """

    def bind_tools(self, herramientas, **kwargs):
        return self


def agente_falso(respuestas: list[str], memoria_mensajes: int = 20) -> Agente:
    """Un agente igual al de verdad, pero con un modelo de mentira adentro."""
    config = Config(
        proveedor="claude",
        modelo="modelo-de-prueba",
        api_key="no-hace-falta",
        max_tokens=1024,
        memoria_mensajes=memoria_mensajes,
        prompt_sistema=RAIZ / "prompts/sistema.md",
    )

    a = Agente.__new__(Agente)
    a.config = config
    a.modelo = ModeloFalso(messages=iter(AIMessage(t) for t in respuestas))
    a.checkpointer = ram()  # los tests no tocan el disco
    a.grafo = a._construir_grafo()
    return a


def test_responde():
    a = agente_falso(["Hola"])
    assert a.responder("hola").texto == "Hola"


def test_se_acuerda_de_la_conversacion():
    a = agente_falso(["primera", "segunda"])
    a.responder("uno")
    a.responder("dos")
    # 2 mensajes míos + 2 del agente
    assert len(a.historial()) == 4


def test_cada_conversacion_va_por_su_lado():
    a = agente_falso(["a", "b"])
    a.responder("hola", conversacion="chat-1")
    a.responder("hola", conversacion="chat-2")

    assert len(a.historial("chat-1")) == 2
    assert len(a.historial("chat-2")) == 2


def test_streaming_devuelve_lo_mismo_que_responder():
    a = agente_falso(["Esto llega de a pedacitos"])
    transmision = a.responder_en_vivo("dale")
    pedazos = list(transmision)

    assert "".join(pedazos) == "Esto llega de a pedacitos"
    assert transmision.resumen.texto == "Esto llega de a pedacitos"


def test_dos_conversaciones_a_la_vez_no_se_pisan():
    """El resumen vive en cada transmisión, no en el agente.

    Si viviera en el agente, dos conversaciones respondiendo al mismo tiempo
    se mezclarían los datos. Esto es lo que pasaría en produccion con varias
    personas escribiendo a la vez.
    """
    a = agente_falso(["respuesta para ana", "respuesta para beto"])

    ana = a.responder_en_vivo("hola", conversacion="ana")
    beto = a.responder_en_vivo("hola", conversacion="beto")

    # Se consumen intercalados, como pasaría de verdad
    lista_ana, lista_beto = [], []
    for pedazo in ana:
        lista_ana.append(pedazo)
    for pedazo in beto:
        lista_beto.append(pedazo)

    assert "".join(lista_ana) == "respuesta para ana"
    assert "".join(lista_beto) == "respuesta para beto"
    assert ana.resumen.texto == "respuesta para ana"
    assert beto.resumen.texto == "respuesta para beto"


def test_recorta_la_memoria_vieja():
    a = agente_falso([f"r{i}" for i in range(10)], memoria_mensajes=4)
    for i in range(6):
        a.responder(f"mensaje {i}")

    entrada = a._armar_entrada({"messages": a.historial()})

    assert isinstance(entrada[0], SystemMessage), "el prompt del sistema va primero"
    assert len(entrada) - 1 <= 4, "tendría que haber recortado los más viejos"


def conversacion_con_herramienta() -> list:
    """Tres turnos, y el del medio usa una herramienta.

    Los tres mensajes de esa vuelta (el pedido, el resultado y la respuesta)
    están atados entre sí: el proveedor los exige juntos.
    """
    return [
        HumanMessage("hola"),
        AIMessage("buenas"),

        HumanMessage("¿qué clima hace en Rosario?"),
        AIMessage(
            "",
            tool_calls=[{"name": "clima", "args": {"lugar": "Rosario"}, "id": "abc"}],
        ),
        ToolMessage("Clima en Rosario: 19.1 °C", tool_call_id="abc"),
        AIMessage("En Rosario hay 19 grados y está nublado."),

        HumanMessage("gracias"),
        AIMessage("de nada"),
    ]


def revisar_que_no_haya_huerfanos(mensajes: list) -> None:
    """Ningún pedido de herramienta sin su resultado, ni al revés.

    Esto es exactamente lo que el proveedor rechaza con un 400.
    """
    pedidos = {
        llamada["id"]
        for m in mensajes
        if isinstance(m, AIMessage)
        for llamada in (m.tool_calls or [])
    }
    resultados = {m.tool_call_id for m in mensajes if isinstance(m, ToolMessage)}

    assert pedidos == resultados, (
        f"quedaron colgados: pedidos sin resultado {pedidos - resultados}, "
        f"resultados sin pedido {resultados - pedidos}"
    )


@pytest.mark.parametrize("tope", [1, 2, 3, 4, 5, 6, 7, 8, 20])
def test_el_recorte_no_parte_una_vuelta_de_herramienta(tope):
    """La trampa que avisa AGENTS.md, y la razón por la que no usamos
    trim_messages().

    Recortando por mensajes sueltos, tarde o temprano el corte cae en el medio
    de una vuelta de herramienta y deja el pedido sin su resultado. El
    proveedor responde un 400 que no explica nada, y recién aparece cuando la
    conversación se hizo larga. Probamos todos los topes para que no haya un
    número que lo rompa.
    """
    a = agente_falso(["x"], memoria_mensajes=tope)

    entrada = a._armar_entrada({"messages": conversacion_con_herramienta()})
    recortado = entrada[1:]  # el [0] es el prompt del sistema

    revisar_que_no_haya_huerfanos(recortado)
    assert isinstance(recortado[0], HumanMessage), "tiene que arrancar en la persona"


def test_el_turno_de_ahora_entra_entero_aunque_no_quepa():
    """Con memoria en 1, la vuelta de herramienta igual tiene que ir completa.

    Es preferible pasarse del tope que mandar una conversación partida al
    medio: recortada así, la llamada directamente falla.
    """
    a = agente_falso(["x"], memoria_mensajes=1)

    # Una conversación que termina justo en medio de la vuelta de herramienta,
    # que es como llega el estado cuando el grafo vuelve al modelo.
    hasta_la_herramienta = conversacion_con_herramienta()[:5]
    recortado = a._armar_entrada({"messages": hasta_la_herramienta})[1:]

    revisar_que_no_haya_huerfanos(recortado)
    assert len(recortado) == 3, "el turno entero: pedido, resultado y su human"


def test_el_prompt_sale_del_archivo():
    a = agente_falso(["x"])
    a.config.cache = False  # sin caché el prompt viaja como texto pelado

    entrada = a._armar_entrada({"messages": []})

    assert entrada[0].content == leer_prompt(a.config.prompt_sistema)


def test_con_cache_el_prompt_va_marcado_para_claude():
    a = agente_falso(["x"])
    a.config.cache = True
    a.config.proveedor = "claude"

    bloque = a._armar_entrada({"messages": []})[0].content[0]

    assert bloque["cache_control"] == {"type": "ephemeral"}
    assert bloque["text"] == leer_prompt(a.config.prompt_sistema)


def test_sin_cache_el_prompt_va_pelado():
    a = agente_falso(["x"])
    a.config.cache = False

    assert isinstance(a._armar_entrada({"messages": []})[0].content, str)


def test_avisa_si_falta_la_clave(monkeypatch):
    monkeypatch.setenv("PROVEEDOR", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(ErrorDeConfiguracion, match="Falta la clave"):
        Config.desde_entorno()


def test_avisa_si_el_proveedor_no_existe():
    with pytest.raises(ErrorDeConfiguracion, match="no existe"):
        Config.desde_entorno("nube-magica")


def test_modo_produccion_sin_dsn_avisa(monkeypatch):
    from agente.memoria import crear_memoria

    config = Config(
        proveedor="claude", modelo="x", api_key="x", max_tokens=100,
        memoria_mensajes=10, prompt_sistema=RAIZ / "prompts/sistema.md",
        modo="produccion", postgres_dsn="",
    )

    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        crear_memoria(config)


def test_modo_test_guarda_en_sqlite(tmp_path):
    from agente.memoria import crear_memoria

    archivo = tmp_path / "prueba.db"
    config = Config(
        proveedor="claude", modelo="x", api_key="x", max_tokens=100,
        memoria_mensajes=10, prompt_sistema=RAIZ / "prompts/sistema.md",
        modo="test", sqlite_ruta=str(archivo),
    )

    crear_memoria(config)
    assert archivo.exists(), "tendría que haber creado el archivo de la base"


def test_la_conexion_de_postgres_no_se_la_lleva_el_recolector(monkeypatch):
    """El bug que solo aparece con el agente corriendo un rato.

    `PostgresSaver.from_conn_string()` es un generador: adentro tiene un
    `with Connection.connect(...)`. Si nadie se guarda una referencia, el
    recolector de basura lo destruye, y destruirlo cierra la conexión.

    No falla al conectar —ahí anda todo— sino en el primer mensaje que llega
    después, con un "the connection is closed" que no se parece en nada a su
    causa. En un script corto ni se nota, porque el proceso termina antes de
    que el recolector actúe.
    """
    # Necesita el paquete de producción (requirements-produccion.txt): sin él,
    # la prueba se saltea en vez de dejar en rojo una instalación recién hecha.
    pytest.importorskip("langgraph.checkpoint.postgres")
    import gc
    from contextlib import contextmanager

    import langgraph.checkpoint.postgres as postgres_de_langgraph

    from agente.memoria import postgres

    cerrada: list[bool] = []

    class GuardadorFalso:
        def setup(self):
            pass

    @contextmanager
    def conexion_falsa(dsn, **kwargs):
        try:
            yield GuardadorFalso()
        finally:
            cerrada.append(True)

    monkeypatch.setattr(
        postgres_de_langgraph.PostgresSaver,
        "from_conn_string",
        staticmethod(conexion_falsa),
    )

    guardador = postgres("postgresql://loquesea")
    gc.collect()  # el recolector, ahora y a propósito

    assert not cerrada, (
        "el recolector cerró la conexión: al checkpointer le falta guardarse "
        "el contexto, y el primer mensaje va a fallar con 'connection is closed'"
    )
    assert guardador is not None


def test_modo_invalido_avisa(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("MODO", "cualquier-cosa")

    with pytest.raises(ErrorDeConfiguracion, match="MODO"):
        Config.desde_entorno("claude")


def test_olvidar_borra_de_verdad():
    """El botón "borrar conversación" tiene que borrar.

    No alcanza con crear un agente nuevo: la conversación vive en el
    checkpointer, así que si no se borra de ahí, el agente nuevo la levanta
    igual y el botón miente.
    """
    a = agente_falso(["hola", "te llamas Martina", "no se como te llamas"])

    a.responder("me llamo Martina")
    assert len(a.historial()) == 2

    a.olvidar()

    assert a.historial() == [], "la conversación tenía que quedar vacía"


def test_la_transmision_se_puede_leer_dos_veces():
    """Consumirla y después pedir .texto() no tiene que devolver vacío.

    Los pedazos llegan del modelo y no vuelven, así que si alguien recorre la
    transmisión con un for y después llama a .texto(), le tenemos que dar lo
    que ya guardamos — no un vacío silencioso que además pise el resumen.
    """
    a = agente_falso(["hola que tal"])
    t = a.responder_en_vivo("dale")

    primero = "".join(t)
    segundo = t.texto()

    assert primero == "hola que tal"
    assert segundo == "hola que tal", "la segunda lectura no puede venir vacía"
    assert t.resumen.texto == "hola que tal", "el resumen no se tiene que pisar"

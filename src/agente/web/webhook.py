"""El servidor que atiende WhatsApp.

Esta es la app que corre en el servidor. **No es la plataforma de pruebas**
(`web/app.py`): son dos cosas distintas y a propósito. La de pruebas es para
tu máquina, tiene la pantalla con los ajustes y no sale de localhost. Esta no
tiene pantalla: es una puerta por donde entra Chatwoot y nada más.

Lo que hace, de punta a punta:

    Chatwoot pega en POST /chatwoot/<token>
      → contestamos 200 al toque              ← esto es obligatorio
      → ¿pasó el tope de mensajes del día?     (frenos.py)
      → juntamos la ráfaga de mensajes          (buffer.py)
      → responde el agente                      (agente.py)
      → se parte en 1 o varios mensajes         (respuesta.py)
      → la respuesta sale por la API de Chatwoot (canales/chatwoot.py)

**Por qué el 200 sale antes de responderle a la persona.** Chatwoot espera
que el webhook conteste rápido; si tardamos lo que tarda el modelo en
pensar, da el pedido por fallado y lo reintenta — y entonces el agente
contesta dos veces lo mismo. Así que primero decimos "recibido" y recién
después pensamos la respuesta, en segundo plano.

**La seguridad es el token en la URL.** Chatwoot no firma sus webhooks (no
hay HMAC como en Meta), así que lo único que separa un mensaje de verdad de
cualquiera que descubra el dominio es que la URL tenga el token. Por eso
tiene que ser largo y al azar (si no, el servidor no arranca), por eso no va
en el código y por eso se tapa en los registros.

**Si algo se rompe, el cliente no ve el error.** El error va a una nota
privada en la conversación y a un mail para vos (avisos.py), y la
conversación pasa a una persona.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..agente import Agente
from ..avisos import Avisos
from ..canales.buffer import BufferDeMensajes
from ..canales.chatwoot import Chatwoot
from ..config import Config, ErrorDeConfiguracion
from ..frenos import BLOQUEAR, IGNORAR, TopeDeMensajes
from ..respuesta import partir_respuesta

registro = logging.getLogger("agente.webhook")

# Un evento de Chatwoot trae la conversación y el contacto enteros, y pesa
# unos pocos KB. Medio mega ya no es un mensaje: es alguien probando qué
# pasa si nos manda cualquier cosa.
TAMANO_MAXIMO_DEL_PEDIDO = 512 * 1024

# El token del webhook: largo y al azar. 32 caracteres de [A-Za-z0-9_-] ya
# son imposibles de adivinar probando; el que genera el README tiene 48.
LARGO_MINIMO_DEL_TOKEN = 32
_TOKEN_VALIDO = re.compile(r"^[A-Za-z0-9_-]+$")
# El que aparece de ejemplo en la documentación: copiarlo tal cual es lo
# mismo que no tener token.
_TOKENS_DE_EJEMPLO = {"un-secreto-largo-y-al-azar"}

# Los caracteres de control no pasan a los registros: con un salto de línea
# adentro de un mensaje, alguien podría inventar líneas de registro falsas.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

NOTA_DE_ERROR = (
    "Aviso del agente: no pude responder en esta conversación.\n\n"
    "{error}\n\n"
    "La persona no recibió respuesta, y tampoco vio el error. {etiqueta}"
)
ETIQUETA_PUESTA = (
    "Le puse la etiqueta «{etiqueta}» para que la atienda alguien del equipo: "
    "no le voy a contestar hasta que se la saquen."
)
ETIQUETA_NO_PUESTA = (
    "No pude ponerle la etiqueta «{etiqueta}»: si querés que la atienda alguien "
    "del equipo y que yo no le conteste, ponésela a mano."
)

NOTA_DE_TOPE = (
    "Aviso del agente: esta persona me mandó más de {tope} mensajes en 24 horas, "
    "así que dejé de contestarle y le puse la etiqueta «{etiqueta}». No se va "
    "sola: si querés que la vuelva a atender, sacale la etiqueta."
)

MAIL_DE_ERROR = """El agente no pudo responder en una conversación.

El error:
{error}

Lo que ya se hizo:
· La persona que escribió no recibió respuesta, y tampoco vio el error.
· {etiqueta}
· {nota}

La conversación: {enlace}

Si pasa en todas las conversaciones, casi seguro es {causa}
Cuando lo arregles, buscá en Chatwoot las conversaciones con la etiqueta
«{nombre_etiqueta}» y sacásela a las que quieras devolverle al agente: hasta
entonces no les contesta. De un mismo error te llega un mail por hora como
mucho, así que puede haber más conversaciones que esta."""

CAUSA_MODELO = (
    "la clave del modelo (vencida o mal cargada en el servidor) o la cuenta del "
    "proveedor sin saldo."
)
CAUSA_CHATWOOT = "Chatwoot: revisá CHATWOOT_URL y CHATWOOT_TOKEN en el servidor."


def validar_token(token: str) -> None:
    """Frena el arranque si el token del webhook no sirve.

    Sin token, el servidor contestaría 401 a todo y el agente quedaría mudo
    sin que nadie se entere. Con uno corto o el del ejemplo, cualquiera que
    lo adivine puede inventarle mensajes al agente, y el agente le contesta
    al cliente real desde tu número.
    """
    if not token:
        raise ErrorDeConfiguracion(
            "Falta CHATWOOT_WEBHOOK_TOKEN. Generá uno con:  "
            'python -c "import secrets; print(secrets.token_hex(24))"'
        )
    if token in _TOKENS_DE_EJEMPLO:
        raise ErrorDeConfiguracion(
            "CHATWOOT_WEBHOOK_TOKEN es el del ejemplo del README: generá uno tuyo con  "
            'python -c "import secrets; print(secrets.token_hex(24))"'
        )
    if len(token) < LARGO_MINIMO_DEL_TOKEN or not _TOKEN_VALIDO.match(token):
        raise ErrorDeConfiguracion(
            f"CHATWOOT_WEBHOOK_TOKEN tiene que tener al menos {LARGO_MINIMO_DEL_TOKEN} "
            "caracteres, solo letras, números, - o _. Generá uno con:  "
            'python -c "import secrets; print(secrets.token_hex(24))"'
        )


def crear_app(
    config: Config | None = None,
    agente: Agente | None = None,
    canal: Chatwoot | None = None,
    avisos: Avisos | None = None,
    tope: TopeDeMensajes | None = None,
) -> FastAPI:
    """Arma el servidor.

    El agente, el canal y los avisos se pueden pasar armados: es lo que hacen
    los tests para probar todo esto sin salir a internet, sin mandar un mail
    y sin gastar un token.
    """
    config = config or Config.desde_entorno()
    validar_token(config.chatwoot_webhook_token)

    canal = canal or Chatwoot(
        url=config.chatwoot_url,
        token=config.chatwoot_token,
        cuenta_id=config.chatwoot_cuenta_id,
        etiqueta_humano=config.chatwoot_etiqueta_humano,
    )

    # El agente se arma una sola vez y atiende a todo el mundo. Es lo que
    # queremos: adentro tiene la conexión a Postgres, y armarlo por mensaje
    # sería abrir una conexión nueva cada vez.
    agente = agente or Agente(config)
    avisos = avisos or Avisos.desde_config(config)
    tope = tope or TopeDeMensajes(config.tope_mensajes_por_dia)
    etiqueta = config.chatwoot_etiqueta_humano

    # Un candado por conversación. Dos personas distintas se atienden a la
    # vez sin problema, pero dos mensajes de la MISMA persona no: si se
    # respondieran en paralelo, los dos leerían la memoria en el mismo punto
    # y el segundo pisaría lo que guardó el primero.
    candados: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # Las tareas que corren en segundo plano. Hay que guardarlas: asyncio
    # solo se queda con una referencia débil, y una tarea que nadie guarda
    # puede desaparecer a mitad de camino.
    en_curso: set[asyncio.Task] = set()

    def en_segundo_plano(corrutina) -> None:
        tarea = asyncio.create_task(corrutina)
        en_curso.add(tarea)
        tarea.add_done_callback(en_curso.discard)

    async def responder(conversacion: str, texto: str) -> None:
        """Le pasa la ráfaga al agente y manda la respuesta por Chatwoot."""
        async with candados[conversacion]:
            if len(texto) > config.largo_maximo_de_entrada:
                registro.warning(
                    "[%s] entraron %s caracteres, se recortan a %s",
                    conversacion,
                    len(texto),
                    config.largo_maximo_de_entrada,
                )
                texto = texto[: config.largo_maximo_de_entrada]

            registro.info("[%s] %s", conversacion, _CONTROL.sub(" ", texto)[:200])

            # El "escribiendo..." y el agente son código bloqueante (urllib y
            # el modelo). Van a un hilo aparte para no trabar el servidor:
            # mientras este mensaje se piensa, los demás siguen entrando.
            await asyncio.to_thread(canal.escribiendo, conversacion, True)

            try:
                try:
                    respuesta = await asyncio.to_thread(
                        agente.responder, texto, conversacion
                    )
                except Exception as e:
                    await algo_se_rompio(conversacion, e, CAUSA_MODELO, "modelo")
                    return

                mensajes = partir_respuesta(
                    respuesta.texto, maximo=config.mensajes_por_respuesta
                )
                if not mensajes:
                    # Una respuesta vacía también es una falla: sin esto, la
                    # persona se queda esperando y nadie se entera.
                    await algo_se_rompio(
                        conversacion,
                        ValueError("El modelo devolvió una respuesta vacía."),
                        CAUSA_MODELO,
                        "modelo",
                    )
                    return

                try:
                    await asyncio.to_thread(canal.enviar, conversacion, mensajes)
                except Exception as e:
                    await algo_se_rompio(conversacion, e, CAUSA_CHATWOOT, "envio")
                    return

                registro.info("[%s] -> %s mensaje(s)", conversacion, len(mensajes))
            finally:
                await asyncio.to_thread(canal.escribiendo, conversacion, False)

    async def algo_se_rompio(conversacion: str, error: Exception, causa: str, tipo: str) -> None:
        """El modelo o Chatwoot fallaron: el equipo se entera, el cliente no.

        El error no se esconde (es regla del proyecto): llega completo a la
        nota privada y al mail. Lo único que cambia es a quién le llega. Cada
        paso va por separado, y la etiqueta primero: que falle uno no puede
        impedir los otros, y la nota no puede decir que la puso si no pudo.
        """
        aviso = f"{type(error).__name__}: {error}"
        registro.error("[%s] %s", conversacion, _CONTROL.sub(" ", aviso))

        try:
            await asyncio.to_thread(canal.pasar_a_persona, conversacion)
            etiquetada = True
        except Exception as e:
            registro.error("[%s] no se pudo poner la etiqueta: %s", conversacion, e)
            etiquetada = False

        texto_etiqueta = (ETIQUETA_PUESTA if etiquetada else ETIQUETA_NO_PUESTA).format(
            etiqueta=etiqueta
        )
        try:
            await asyncio.to_thread(
                canal.nota_privada,
                conversacion,
                NOTA_DE_ERROR.format(error=aviso, etiqueta=texto_etiqueta),
            )
            nota = "En la conversación hay una nota privada con este mismo error."
        except Exception as e:
            registro.error("[%s] no se pudo dejar la nota: %s", conversacion, e)
            nota = "No se pudo dejar la nota privada en la conversación."

        await asyncio.to_thread(
            avisos.avisar,
            "El agente no pudo responder en una conversación",
            MAIL_DE_ERROR.format(
                error=aviso,
                etiqueta=(
                    f"La conversación quedó con la etiqueta «{etiqueta}»: el agente "
                    "no le contesta hasta que se la saques."
                    if etiquetada
                    else f"No se pudo poner la etiqueta «{etiqueta}»: el agente le va "
                    "a volver a contestar si escribe de nuevo."
                ),
                nota=nota,
                enlace=canal.enlace(conversacion),
                causa=causa,
                nombre_etiqueta=etiqueta,
            ),
            # Los errores iguales se agrupan: una clave vencida no manda un
            # mail por cada persona que escribe.
            f"{tipo}:{type(error).__name__}:{str(error)[:60]}",
        )

    async def pasar_por_tope(conversacion: str) -> None:
        """La conversación pasó el tope del día: a una persona, y el agente se calla."""
        registro.warning(
            "[%s] pasó los %s mensajes del día: pasa a una persona",
            conversacion,
            tope.tope,
        )
        try:
            await asyncio.to_thread(canal.pasar_a_persona, conversacion)
            await asyncio.to_thread(
                canal.nota_privada,
                conversacion,
                NOTA_DE_TOPE.format(tope=tope.tope, etiqueta=etiqueta),
            )
        except Exception as e:
            # Sin la etiqueta, pasado el rato de gracia la persona vuelve a
            # tener respuestas: eso sí hay que avisarlo.
            registro.error("[%s] no se pudo bloquear: %s", conversacion, e)
            await asyncio.to_thread(
                avisos.avisar,
                "El agente no pudo frenar una conversación",
                f"La conversación {conversacion} pasó el tope de {tope.tope} "
                f"mensajes en 24 horas, pero no se le pudo poner la etiqueta "
                f"«{etiqueta}».\n\n{type(e).__name__}: {e}\n\n"
                f"La conversación: {canal.enlace(conversacion)}",
                f"tope:{type(e).__name__}",
            )

    buffer = BufferDeMensajes(config.buffer_segundos, responder)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        # Acá y no antes: uvicorn arma sus registros al arrancar, y un filtro
        # puesto antes de eso se puede perder.
        tapar_el_token_en_los_registros(config.chatwoot_webhook_token)

        registro.info(
            "Agente escuchando - %s / %s - memoria %s - buffer %ss - "
            "%s mensaje(s) por respuesta - tope %s por día - avisos %s",
            config.proveedor,
            config.modelo,
            "Postgres" if config.modo == "produccion" else "SQLite",
            config.buffer_segundos,
            config.mensajes_por_respuesta,
            config.tope_mensajes_por_dia or "sin",
            "prendidos" if avisos.activos else "apagados",
        )
        yield
        # Al apagar, soltamos lo que estaba esperando y esperamos (un rato)
        # lo que corría en segundo plano. Sin esto, un deploy justo en esos
        # segundos se come la ráfaga de alguien o lo deja sin la etiqueta.
        await buffer.vaciar()
        if en_curso:
            await asyncio.wait(set(en_curso), timeout=10)

    # Sin /docs ni /openapi.json: esta puerta es para Chatwoot, no para
    # mostrarle a cualquiera qué rutas tiene.
    app = FastAPI(
        title="Agente - webhook de Chatwoot",
        lifespan=ciclo_de_vida,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # -- Las rutas -------------------------------------------------------------

    @app.get("/salud")
    async def salud() -> dict:
        """Para que el servidor sepa que la app está viva.

        Coolify le pega a esto cada tanto. Si no contesta, reinicia el
        contenedor.
        """
        return {
            "estado": "ok",
            "proveedor": config.proveedor,
            "modelo": config.modelo,
            "memoria": "postgres" if config.modo == "produccion" else "sqlite",
        }

    @app.post("/chatwoot/{token}")
    async def entrante(token: str, pedido: Request) -> JSONResponse:
        """Por acá entra todo lo que manda Chatwoot."""
        # compare_digest y no "!=": el "!=" corta en la primera letra
        # distinta, y midiendo cuánto tarda se puede adivinar la clave de a
        # una letra. compare_digest tarda siempre lo mismo.
        if not secrets.compare_digest(
            token.encode("utf-8"), config.chatwoot_webhook_token.encode("utf-8")
        ):
            # Sin detalles en la respuesta: al que probó la URL no le decimos
            # si el token existe, si es corto o si le erró por una letra.
            registro.warning("Llamada con token equivocado")
            return JSONResponse({"error": "no autorizado"}, status_code=401)

        cuerpo = await _leer_con_tope(pedido)
        if cuerpo is None:
            registro.warning("Pedido de más de %s bytes, descartado", TAMANO_MAXIMO_DEL_PEDIDO)
            return JSONResponse({"error": "pedido demasiado grande"}, status_code=413)

        try:
            evento = json.loads(cuerpo)
        except Exception:
            return JSONResponse({"error": "esperaba JSON"}, status_code=400)
        if not isinstance(evento, dict):
            return JSONResponse({"error": "esperaba un objeto JSON"}, status_code=400)

        entrante = canal.traducir(evento)

        if entrante is None or not canal.deberia_responder(entrante):
            # No es un error: es la mayoría de lo que llega. Cada respuesta
            # que manda el propio agente vuelve como un evento más.
            return JSONResponse({"estado": "ignorado"})

        decision = tope.anotar(entrante.conversacion)
        if decision == BLOQUEAR:
            en_segundo_plano(pasar_por_tope(entrante.conversacion))
            return JSONResponse({"estado": "tope"})
        if decision == IGNORAR:
            return JSONResponse({"estado": "tope"})

        # Se suma a la ráfaga y contestamos ya. Lo que sigue pasa solo.
        await buffer.agregar(entrante.conversacion, entrante.texto)

        return JSONResponse({"estado": "recibido"})

    return app


async def _leer_con_tope(pedido: Request) -> bytes | None:
    """Lee el cuerpo del pedido, o None si pasa el tamaño máximo.

    Se lee de a pedazos y se corta apenas se pasa: leerlo entero para
    después medirlo sería haberle dado igual la memoria al que manda 1 GB.
    """
    declarado = pedido.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > TAMANO_MAXIMO_DEL_PEDIDO:
        return None

    partes: list[bytes] = []
    total = 0
    async for pedazo in pedido.stream():
        total += len(pedazo)
        if total > TAMANO_MAXIMO_DEL_PEDIDO:
            return None
        partes.append(pedazo)

    return b"".join(partes)


class TaparElToken(logging.Filter):
    """Que la clave del webhook no quede escrita en los registros del servidor.

    uvicorn anota cada pedido con su dirección completa, y la dirección del
    webhook LLEVA la clave: `POST /chatwoot/<la clave>`. Sin esto, cualquiera
    que pueda ver los registros de Coolify tiene la clave.

    Tapa la clave misma, esté donde esté en el mensaje (también en una
    dirección mal escrita, como `/Chatwoot/<clave>` o `?token=<clave>`), y
    además cualquier cosa con la forma `/chatwoot/<algo>`.
    """

    _DIRECCION = re.compile(r"(/chatwoot/)[^/\s?\"]+", re.IGNORECASE)

    def __init__(self, token: str = "") -> None:
        super().__init__()
        self.token = token or ""

    def _tapar(self, texto: str) -> str:
        if self.token:
            texto = texto.replace(self.token, "***")
        return self._DIRECCION.sub(r"\1***", texto)

    def filter(self, registro_de_log: logging.LogRecord) -> bool:
        if isinstance(registro_de_log.msg, str):
            registro_de_log.msg = self._tapar(registro_de_log.msg)
        if isinstance(registro_de_log.args, tuple):
            # Se reemplaza adentro de cada valor, sin cambiar cuántos son: el
            # formateador de uvicorn espera exactamente los mismos.
            registro_de_log.args = tuple(
                self._tapar(a) if isinstance(a, str) else a for a in registro_de_log.args
            )
        return True


def tapar_el_token_en_los_registros(token: str) -> TaparElToken:
    """Pone el filtro en todos los lugares por donde puede salir un registro.

    En los loggers de uvicorn y en todos los manejadores (los del raíz
    incluidos): un filtro puesto solo en un logger no ve lo que llega desde
    sus hijos.
    """
    filtro = TaparElToken(token)
    nombres = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
    for nombre in nombres:
        logger = logging.getLogger(nombre)
        logger.addFilter(filtro)
        for manejador in logger.handlers:
            manejador.addFilter(filtro)
    return filtro

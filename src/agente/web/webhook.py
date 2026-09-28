"""El servidor que atiende WhatsApp.

Esta es la app que corre en el servidor. **No es la plataforma de pruebas**
(`web/app.py`): son dos cosas distintas y a propósito. La de pruebas es para
tu máquina, tiene la pantalla con los ajustes y no sale de localhost. Esta no
tiene pantalla: es una puerta por donde entra Chatwoot y nada más.

Lo que hace, de punta a punta:

    Chatwoot pega en POST /chatwoot/<token>
      → contestamos 200 al toque              ← esto es obligatorio
      → ¿pasó el tope de mensajes del día?     (frenos.py)
      → una foto, un audio o una cita se leen en segundo plano (canales/adjuntos.py)
      → juntamos la ráfaga de mensajes          (buffer.py)
      → ¿la agarró alguien del equipo mientras tanto? se vuelve a mirar
      → responde el agente                      (agente.py)
      → se parte en 1 o varios mensajes         (respuesta.py)
      → la respuesta sale por la API de Chatwoot, con pausa entre globos

**Por qué el 200 sale antes de responderle a la persona.** Chatwoot espera
que el webhook conteste rápido; si tardamos lo que tarda el modelo en
pensar, da el pedido por fallado y lo reintenta — y entonces el agente
contesta dos veces lo mismo. Así que primero decimos "recibido" y recién
después pensamos la respuesta, en segundo plano. Lo mismo con bajar y leer
una foto o un audio: nunca antes del 200, y nunca frenando a los demás.

**La seguridad es el token en la URL.** Chatwoot no firma sus webhooks (no
hay HMAC como en Meta), así que lo único que separa un mensaje de verdad de
cualquiera que descubra el dominio es que la URL tenga el token. Por eso
tiene que ser largo y al azar (si no, el servidor no arranca), por eso no va
en el código y por eso se tapa en los registros.

**Si algo se rompe, el cliente no ve el error.** La conversación pasa a una
persona (la etiqueta) y te llega un mail con el error (avisos.py).
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
from ..canales.adjuntos import DescriptorDeFotos, Lector, TranscriptorOpenAI
from ..canales.base import MensajeEntrante
from ..canales.buffer import BufferDeMensajes
from ..canales.chatwoot import Chatwoot, tarda_en_escribir
from ..canales.whatsapp_meta import marcar_visto_y_escribiendo, wamid_del_evento
from ..config import Config, ErrorDeConfiguracion
from ..frenos import BLOQUEAR, IGNORAR, TopeDeMensajes
from ..modelos import crear_modelo
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

# Los puntitos de WhatsApp duran 25 segundos: en una espera larga se renuevan.
RENOVAR_ESCRIBIENDO = 20

MAIL_DE_ERROR = """El agente no pudo responder en una conversación.

El error:
{error}

Lo que ya se hizo:
· La persona que escribió no recibió respuesta, y tampoco vio el error.
· {etiqueta}

La conversación: {enlace}

Si pasa en todas las conversaciones, casi seguro es {causa}
Cuando lo arregles, buscá en Chatwoot las conversaciones con la etiqueta
«{nombre_etiqueta}» y sacásela a las que quieras devolverle al agente: hasta
entonces no les contesta. De un mismo error te llega un mail por hora como
mucho, así que puede haber más conversaciones que esta."""

MAIL_DE_ADJUNTO = """El agente no pudo leer algo que le mandaron en una conversación.

{error}

A la persona se le pidió que lo cuente por escrito, así que la charla sigue.
La conversación: {enlace}

Si pasa con todos los audios, revisá OPENAI_API_KEY (la clave o el saldo).
De un mismo error te llega un mail por hora como mucho."""

CAUSA_MODELO = (
    "la clave del modelo (vencida o mal cargada en el servidor) o la cuenta del "
    "proveedor sin saldo."
)
CAUSA_CHATWOOT = "Chatwoot: revisá CHATWOOT_URL y CHATWOOT_TOKEN en el servidor."

UNA_HORA = 60 * 60
UN_DIA = 24 * UNA_HORA


async def mantener_el_permiso(avisos: Avisos, cada: float = UN_DIA) -> None:
    """Con los avisos por Google, usa el permiso al arrancar y una vez por día.

    Google borra el permiso que pasa seis meses sin usarse, y si el agente
    anda bien no manda ningún aviso: el día que hiciera falta, no saldría.
    Si el permiso no vale, queda en el registro (no hay mail que mandar:
    el mail es justamente lo que está roto) y se vuelve a probar en una
    hora: puede haber sido la red en el momento de arrancar.
    """
    anduvo = None
    while True:
        try:
            await asyncio.to_thread(avisos.revisar)
            if anduvo is not True:
                registro.info("Avisos por Google: el permiso para mandar mails anda.")
            anduvo = True
        except Exception as e:
            registro.error("Los avisos por mail NO van a salir: %s", e)
            anduvo = False
        await asyncio.sleep(cada if anduvo else min(cada, UNA_HORA))


def _como_avisa(avisos: Avisos) -> str:
    if not avisos.activos:
        return "apagados"
    return "por Google" if avisos.metodo == "google" else "por SMTP"


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


def armar_lector(config: Config, canal: Chatwoot) -> Lector:
    """El lector de adjuntos, con lo que se pueda según la configuración.

    Las fotos, con el mismo modelo del agente (o MODELO_IMAGENES, si se quiere
    uno más barato del mismo proveedor). Los audios, con OpenAI: sin su clave,
    un audio pasa a una persona en vez de quedar sin respuesta.
    """
    describir = None
    if config.describir_imagenes:
        describir = DescriptorDeFotos(
            lambda: crear_modelo(
                proveedor=config.proveedor,
                api_key=config.api_key,
                modelo=config.modelo_imagenes or config.modelo,
                max_tokens=800,
            )
        )
    transcribir = None
    if config.transcribir_audios and config.clave_openai:
        transcribir = TranscriptorOpenAI(config.clave_openai, config.modelo_transcripcion)
    return Lector(canal, describir=describir, transcribir=transcribir)


def _contacto_del(evento: dict) -> str:
    """El id del contacto que escribió (el remitente de un mensaje que entra)."""
    remitente = evento.get("sender") if isinstance(evento, dict) else None
    valor = remitente.get("id") if isinstance(remitente, dict) else None
    if isinstance(valor, bool) or not str(valor or "").isdigit():
        return ""
    return str(valor)


def crear_app(
    config: Config | None = None,
    agente: Agente | None = None,
    canal: Chatwoot | None = None,
    avisos: Avisos | None = None,
    tope: TopeDeMensajes | None = None,
    lector: Lector | None = None,
) -> FastAPI:
    """Arma el servidor.

    El agente, el canal, los avisos y el lector se pueden pasar armados: es
    lo que hacen los tests para probar todo esto sin salir a internet, sin
    mandar un mail y sin gastar un token.
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
    lector = lector or armar_lector(config, canal)
    etiqueta = config.chatwoot_etiqueta_humano
    con_meta = bool(config.whatsapp_token and config.whatsapp_phone_number_id)

    # Un candado por conversación. Dos personas distintas se atienden a la
    # vez sin problema, pero dos mensajes de la MISMA persona no: si se
    # respondieran en paralelo, los dos leerían la memoria en el mismo punto
    # y el segundo pisaría lo que guardó el primero.
    candados: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # Las tareas que corren en segundo plano. Hay que guardarlas: asyncio
    # solo se queda con una referencia débil, y una tarea que nadie guarda
    # puede desaparecer a mitad de camino.
    en_curso: set[asyncio.Task] = set()

    # El último mensaje de WhatsApp de cada conversación: el visto y los
    # puntitos en el celular de la persona van atados a ese id (ver
    # canales/whatsapp_meta.py).
    ultimo_wamid: dict[str, str] = {}

    # Las conversaciones a las que ya se les miró si esa persona tiene una
    # resuelta. Una vez por conversación alcanza: si estaba cerrada, desde ahí
    # la frena la etiqueta.
    revisadas: set[str] = set()

    def en_segundo_plano(corrutina) -> asyncio.Task:
        tarea = asyncio.create_task(corrutina)
        en_curso.add(tarea)
        tarea.add_done_callback(en_curso.discard)
        return tarea

    def visto_y_escribiendo(conversacion: str) -> None:
        """El visto y los puntitos en el celular de la persona, si hay datos de Meta."""
        wamid = ultimo_wamid.get(conversacion, "")
        if con_meta and wamid:
            marcar_visto_y_escribiendo(
                wamid, config.whatsapp_token, config.whatsapp_phone_number_id
            )

    async def esperar_como_persona(conversacion: str) -> None:
        """La espera antes de contestar (si se configuró), y recién ahí el visto y los puntitos.

        Primero un rato de nada y después los puntitos: empezar a escribir en
        el mismo segundo en que llega el mensaje y tardar un minuto queda peor
        que el silencio (nadie tipea tan lento). Con la pausa primero se lee
        como alguien que estaba en otra cosa, ve el mensaje y se pone a
        contestar. Sin espera configurada, el visto y los puntitos salen ya.
        """
        espera = max(0, config.espera_segundos)
        silencio = min(max(0, config.silencio_segundos), espera)
        if silencio:
            await asyncio.sleep(silencio)
        restante = espera - silencio

        await asyncio.to_thread(visto_y_escribiendo, conversacion)
        await asyncio.to_thread(canal.escribiendo, conversacion, True)
        while restante > 0:
            tramo = min(RENOVAR_ESCRIBIENDO, restante)
            await asyncio.sleep(tramo)
            restante -= tramo
            if restante > 0:
                await asyncio.to_thread(visto_y_escribiendo, conversacion)
                await asyncio.to_thread(canal.escribiendo, conversacion, True)

    async def ya_no_le_toca(conversacion: str) -> bool:
        """Si mientras esperaba alguien del equipo agarró la charla o la resolvió."""
        motivo = await asyncio.to_thread(canal.lo_agarro_otro, conversacion)
        if not motivo:
            return False
        registro.info("[%s] no contesto: mientras esperaba, %s", conversacion, motivo)
        return True

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

            try:
                # El "escribiendo..." y el agente son código bloqueante (urllib
                # y el modelo). Van a un hilo aparte para no trabar el servidor:
                # mientras este mensaje se piensa, los demás siguen entrando.
                await esperar_como_persona(conversacion)

                # Se vuelve a mirar ANTES del modelo: si ya no le toca, no se
                # gasta ni un token.
                if await ya_no_le_toca(conversacion):
                    return

                primera = config.solo_el_primer_mensaje and not await asyncio.to_thread(
                    agente.historial, conversacion
                )

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

                # Y una vez más con la respuesta escrita: el modelo tarda unos
                # segundos, y es el último momento en que se puede no mandar.
                if await ya_no_le_toca(conversacion):
                    return

                try:
                    await asyncio.to_thread(
                        canal.enviar,
                        conversacion,
                        mensajes,
                        (lambda: visto_y_escribiendo(conversacion)) if con_meta else None,
                        tarda_en_escribir if config.pausa_entre_globos else None,
                    )
                except Exception as e:
                    await algo_se_rompio(conversacion, e, CAUSA_CHATWOOT, "envio")
                    return

                registro.info("[%s] -> %s mensaje(s)", conversacion, len(mensajes))

                if primera:
                    # Lo eligió al instalar: el agente abre la charla y la sigue
                    # una persona. Va después de mandar: si el envío fallaba, la
                    # persona quedaba sin respuesta y sin nadie que la atienda.
                    try:
                        await asyncio.to_thread(canal.pasar_a_persona, conversacion)
                        registro.info("[%s] contestó el primero: sigue una persona", conversacion)
                    except Exception as e:
                        registro.error("[%s] no se pudo pasar a una persona: %s", conversacion, e)
            finally:
                await asyncio.to_thread(canal.escribiendo, conversacion, False)

    async def algo_se_rompio(conversacion: str, error: Exception, causa: str, tipo: str) -> None:
        """El modelo o Chatwoot fallaron: el equipo se entera, el cliente no.

        El error no se esconde (es regla del proyecto): llega completo al mail
        del dueño. Lo único que cambia es a quién le llega. La etiqueta va
        primero y por separado: que no se pueda poner no puede impedir el mail,
        y el mail no puede decir que se puso si no se puso.
        """
        aviso = f"{type(error).__name__}: {error}"
        registro.error("[%s] %s", conversacion, _CONTROL.sub(" ", aviso))

        try:
            await asyncio.to_thread(canal.pasar_a_persona, conversacion)
            etiquetada = True
        except Exception as e:
            registro.error("[%s] no se pudo poner la etiqueta: %s", conversacion, e)
            etiquetada = False

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

    async def marcar_resuelta(conversacion: str) -> None:
        """La resolvieron: queda con la etiqueta, así el agente no le vuelve a hablar.

        Hace falta porque, según cómo esté la bandeja, Chatwoot reabre ESA
        misma conversación cuando la persona vuelve a escribir (y ahí ya no
        figura como resuelta). La etiqueta, en cambio, se queda.
        """
        try:
            await asyncio.to_thread(canal.pasar_a_persona, conversacion)
            registro.info("[%s] la resolvieron: el agente no le vuelve a hablar", conversacion)
        except Exception as e:
            registro.error("[%s] no se pudo marcar como resuelta: %s", conversacion, e)

    async def preparar(entrante: MensajeEntrante, revisar: bool, leer: bool) -> str:
        """Lo que tarda, fuera del camino del 200: si ya se cerró con esa persona, y leer lo que no es texto.

        Devuelve el texto para la ráfaga, o "" si no hay que contestar.
        """
        conversacion = entrante.conversacion
        if revisar:
            contacto = _contacto_del(entrante.datos)
            if contacto and await asyncio.to_thread(canal.ya_la_cerro, contacto):
                registro.info(
                    "[%s] con esta persona ya se resolvió una conversación: no contesto",
                    conversacion,
                )
                # La etiqueta va igual: en la bandeja se tiene que ver que el
                # agente está callado a propósito y no que se colgó.
                await marcar_resuelta(conversacion)
                return ""

        if not leer:
            return entrante.texto

        try:
            leido = await asyncio.to_thread(lector.leer, entrante)
        except Exception as e:
            registro.error("[%s] no se pudo leer el mensaje: %s", conversacion, e)
            return entrante.texto or "[La persona mandó algo que no se pudo leer: preguntale qué es.]"

        if leido.a_una_persona:
            registro.info("[%s] pasa a una persona: %s", conversacion, leido.a_una_persona)
            try:
                await asyncio.to_thread(canal.pasar_a_persona, conversacion)
            except Exception as e:
                registro.error("[%s] no se pudo pasar a una persona: %s", conversacion, e)
        if leido.error:
            await asyncio.to_thread(
                avisos.avisar,
                "El agente no pudo leer algo que le mandaron",
                MAIL_DE_ADJUNTO.format(error=leido.error, enlace=canal.enlace(conversacion)),
                f"adjunto:{leido.error[:60]}",
            )
        return leido.texto

    buffer = BufferDeMensajes(config.buffer_segundos, responder)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        # Acá y no antes: uvicorn arma sus registros al arrancar, y un filtro
        # puesto antes de eso se puede perder.
        tapar_el_token_en_los_registros(config.chatwoot_webhook_token)

        registro.info(
            "Agente escuchando - %s / %s - memoria %s - buffer %ss - "
            "%s mensaje(s) por respuesta - tope %s por día - avisos %s - "
            "fotos %s - audios %s - resolver %s",
            config.proveedor,
            config.modelo,
            "Postgres" if config.modo == "produccion" else "SQLite",
            config.buffer_segundos,
            config.mensajes_por_respuesta,
            config.tope_mensajes_por_dia or "sin",
            _como_avisa(avisos),
            "sí" if getattr(lector, "describir", None) else "no",
            "sí" if getattr(lector, "transcribir", None) else "no (falta OPENAI_API_KEY: pasan a una persona)",
            "calla al agente" if config.respetar_resueltas else "no cambia nada",
        )
        cuidar_el_permiso = (
            asyncio.create_task(mantener_el_permiso(avisos))
            if avisos.activos and avisos.metodo == "google"
            else None
        )
        yield
        if cuidar_el_permiso is not None:
            cuidar_el_permiso.cancel()
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

    def token_valido(token: str) -> bool:
        # compare_digest y no "!=": el "!=" corta en la primera letra
        # distinta, y midiendo cuánto tarda se puede adivinar la clave de a
        # una letra. compare_digest tarda siempre lo mismo.
        return secrets.compare_digest(
            token.encode("utf-8"), config.chatwoot_webhook_token.encode("utf-8")
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

    @app.post("/reset/{token}")
    async def reset(token: str, pedido: Request) -> JSONResponse:
        """Le borra la memoria a una conversación, para volver a probar desde cero.

            curl -X POST https://tu-dominio.com/reset/<CHATWOOT_WEBHOOK_TOKEN> \\
                 -H "Content-Type: application/json" -d '{"conversacion": "12"}'

        El número es el de la conversación en Chatwoot (sale de su dirección).
        Borra lo que el agente recuerda de esa charla y su cuenta del tope del
        día: el próximo mensaje arranca como si nunca hubieran hablado. De a
        una conversación por vez, a propósito: borrar todas de un saque, con
        gente de verdad adentro, no tiene vuelta atrás.
        """
        if not token_valido(token):
            registro.warning("Reset con token equivocado")
            return JSONResponse({"error": "no autorizado"}, status_code=401)

        cuerpo = await _leer_con_tope(pedido)
        try:
            datos = json.loads(cuerpo) if cuerpo else {}
        except Exception:
            datos = {}
        conversacion = str((datos or {}).get("conversacion") if isinstance(datos, dict) else "").strip()
        if not conversacion.isdigit():
            return JSONResponse(
                {"error": "falta 'conversacion': el número de la conversación en Chatwoot"},
                status_code=400,
            )

        try:
            await asyncio.to_thread(agente.olvidar, conversacion)
        except Exception as e:
            registro.error("[%s] no se pudo borrar la memoria: %s", conversacion, e)
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)
        tope.olvidar(conversacion)
        revisadas.discard(conversacion)
        registro.info("[%s] memoria borrada: arranca de cero", conversacion)
        return JSONResponse({"estado": "ok", "conversacion": conversacion})

    @app.post("/chatwoot/{token}")
    async def entrante(token: str, pedido: Request) -> JSONResponse:
        """Por acá entra todo lo que manda Chatwoot."""
        if not token_valido(token):
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

        # Resolvieron una conversación: si se eligió así al instalar, queda
        # con la etiqueta y el agente no le vuelve a hablar a esa persona.
        if evento.get("event") == "conversation_status_changed":
            id_conversacion = evento.get("id")
            if (
                config.respetar_resueltas
                and str(evento.get("status") or "").strip().lower() == "resolved"
                and not isinstance(id_conversacion, bool)
                and str(id_conversacion or "").isdigit()
            ):
                en_segundo_plano(marcar_resuelta(str(id_conversacion)))
                return JSONResponse({"estado": "resuelta"})
            return JSONResponse({"estado": "ignorado"})

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

        wamid = wamid_del_evento(evento)
        if wamid:
            ultimo_wamid[entrante.conversacion] = wamid

        # Lo que tarda (preguntar si ya se cerró con esa persona, bajar y leer
        # una foto o un audio, buscar un mensaje citado) va en segundo plano,
        # pero en SU lugar de la ráfaga: el orden es el de llegada.
        revisar = config.respetar_resueltas and entrante.conversacion not in revisadas
        if revisar:
            revisadas.add(entrante.conversacion)
        leer = Lector.hay_que_leer(entrante)
        if revisar or leer:
            parte = en_segundo_plano(preparar(entrante, revisar, leer))
            await buffer.agregar(entrante.conversacion, parte)
        else:
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
    además cualquier cosa con la forma `/chatwoot/<algo>` o `/reset/<algo>`.
    """

    _DIRECCION = re.compile(r"(/(?:chatwoot|reset)/)[^/\s?\"]+", re.IGNORECASE)

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

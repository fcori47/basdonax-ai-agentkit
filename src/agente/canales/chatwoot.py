"""El canal de Chatwoot.

Es el que atiende WhatsApp de verdad, pero no le habla a Meta: le habla a
Chatwoot, que está en el medio. El recorrido completo de un mensaje es este:

    persona → WhatsApp → Meta → Chatwoot → (webhook) → agente
                                    ↑                     │
                                    └───── API REST ──────┘

Por qué con Chatwoot en el medio y no directo contra Meta:

  · Queda el historial y la bandeja de entrada, con buscador.
  · Una persona puede meterse en la conversación y seguirla a mano.
  · El mismo agente atiende Instagram, el widget de la web o Telegram sin
    tocar una línea: para nosotros todo entra por el mismo webhook.

A diferencia de Telegram, acá **nadie sale a buscar los mensajes**: Chatwoot
nos pega a una URL cuando pasa algo. Por eso esto necesita un servidor con
dominio y HTTPS, y por eso el webhook vive en su propia app (web/webhook.py).

El `conversacion` (el thread_id de LangGraph) es el **id de conversación de
Chatwoot**. Es la misma unidad que ves en la bandeja: un hilo en la pantalla
es un hilo de memoria del agente. También es lo que necesitamos para
contestar, así que sirve para las dos cosas.

Se usa `urllib`, de la biblioteca estándar, para no sumar una dependencia.
La API de Chatwoot son pedidos HTTP con JSON: no hace falta más.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Callable

from .adjuntos import ArchivoTodaviaNoEsta, adjuntos_de, id_citado
from .base import Canal, MensajeEntrante

# Cuánto esperamos a que Chatwoot conteste. Corre en el mismo servidor que
# el agente, así que si tarda más que esto es porque algo anda mal.
ESPERA_DE_RED = 20

# Un audio o una foto tardan más en bajar que una llamada a la API.
ESPERA_DE_ARCHIVO = 60

# Cuántas páginas de mensajes se miran para encontrar uno citado (20 por
# página): alcanza para lo que se cita en una charla.
PAGINAS_PARA_BUSCAR = 3

# Cuánto tarda una persona en escribir un globo, en segundos: ~22 caracteres
# por segundo es tipeo rápido de celular. El piso evita que dos globos cortos
# caigan pegados; el techo, que la persona mire los puntitos una eternidad.
LETRAS_POR_SEGUNDO = 22.0
PAUSA_MINIMA = 1.4
PAUSA_MAXIMA = 7.0


class ErrorDeChatwoot(Exception):
    """Chatwoot contestó algo que no esperábamos."""


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Una redirección se corta en vez de seguirse.

    urllib la seguiría reenviando la cabecera con el token de Chatwoot, a
    cualquier servidor. Chatwoot no redirige su API: si pasa, CHATWOOT_URL
    está mal y conviene enterarse.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErrorDeChatwoot(
            f"Chatwoot contestó con una redirección ({code}). No la sigo, para no "
            "mandarle el token a otro lado: revisá CHATWOOT_URL."
        )


_ABRIDOR = urllib.request.build_opener(_SinRedirecciones)

# Para bajar archivos SÍ se siguen redirecciones: Chatwoot manda a su
# almacenamiento (el disco del servidor, o S3). Es seguro porque ese pedido
# no lleva el token: la dirección del archivo ya viene firmada.
_ABRIDOR_DE_ARCHIVOS = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ssl.create_default_context())
)


class Chatwoot(Canal):
    """La bandeja de Chatwoot: por acá entran y salen los mensajes."""

    nombre = "chatwoot"

    def __init__(
        self,
        url: str,
        token: str,
        cuenta_id: str | int,
        etiqueta_humano: str = "humano",
    ) -> None:
        if not url or not token:
            raise ValueError(
                "Faltan datos de Chatwoot. Abrí el .env y completá "
                "CHATWOOT_URL y CHATWOOT_TOKEN."
            )

        # La barra final sobra y duplicada rompe la URL ("...com//api/v1").
        self.url = url.rstrip("/")
        self.token = token
        self.cuenta_id = str(cuenta_id)
        self.etiqueta_humano = (etiqueta_humano or "").strip().lower()

        # Los mensajes que ya contestamos. Chatwoot reintenta el webhook si no
        # le respondemos rápido, y sin esto el agente contesta dos veces lo
        # mismo. Alcanza con acordarse de los últimos.
        self._ya_contestados: deque[str] = deque(maxlen=1000)

    # -- Entrada ---------------------------------------------------------------

    def traducir(self, evento: dict) -> MensajeEntrante | None:
        """Convierte un evento del webhook en algo que el agente entiende.

        Devuelve None si el evento no es un mensaje que tengamos que mirar:
        otro tipo de evento, o un mensaje vacío. Un mensaje sin texto pero con
        un adjunto (un audio, una foto, una ubicación) SÍ pasa: el texto queda
        vacío y lo arma después el lector de adjuntos (adjuntos.py), en segundo
        plano, porque bajar y leer un archivo tarda.
        """
        # Lo que llega de afuera se valida antes de usarlo: un evento con otra
        # forma (una lista, un texto, un id con letras) no puede tirar el
        # servidor ni colarse en un mail o en un enlace.
        if not isinstance(evento, dict) or evento.get("event") != "message_created":
            return None

        conversacion = evento.get("conversation")
        if not isinstance(conversacion, dict):
            return None
        id_conversacion = conversacion.get("id")
        if isinstance(id_conversacion, bool) or not str(id_conversacion or "").isdigit():
            return None

        contenido = evento.get("content")
        texto = contenido.strip() if isinstance(contenido, str) else ""
        if not texto and not adjuntos_de(evento) and id_citado(evento) is None:
            return None

        return MensajeEntrante(
            texto=texto,
            # El id de conversación es el thread_id: la memoria de cada
            # persona por separado.
            conversacion=str(id_conversacion),
            identificador=str(evento.get("id") or ""),
            datos=evento,
        )

    def deberia_responder(self, mensaje: MensajeEntrante) -> bool:
        """Si el agente tiene que contestar este mensaje o dejarlo pasar.

        Acá está casi toda la diferencia entre un bot de demo y uno que
        atiende clientes de verdad. Son cuatro filtros y los cuatro importan:
        """
        evento = mensaje.datos

        # 1. Solo los mensajes que ENTRAN. Los que salen son las respuestas
        #    del propio agente y las de las personas del equipo. Sin este
        #    filtro el agente se lee a sí mismo y se contesta para siempre:
        #    es el error más caro de todos, porque cada vuelta gasta tokens.
        if _tipo_de_mensaje(evento) != "incoming":
            return False

        # 2. Las notas privadas son para el equipo, no para el cliente. Si el
        #    agente contestara ahí, mandaría al chat algo que era interno.
        if evento.get("private"):
            return False

        # 3. El mismo mensaje dos veces. Chatwoot reintenta si el webhook no
        #    contestó a tiempo, y el reintento trae el mismo id.
        if mensaje.identificador and mensaje.identificador in self._ya_contestados:
            return False

        # 4. El traspaso a una persona. Si la conversación tiene la etiqueta,
        #    el bot se calla: la está atendiendo alguien del equipo. Es *el*
        #    diferencial de tener Chatwoot en el medio — se apaga con un clic
        #    desde la bandeja, sin tocar el servidor.
        if self._la_atiende_una_persona(evento):
            return False

        if mensaje.identificador:
            self._ya_contestados.append(mensaje.identificador)

        return True

    def _la_atiende_una_persona(self, evento: dict) -> bool:
        """Si la conversación está marcada con la etiqueta de traspaso."""
        if not self.etiqueta_humano:
            return False

        conversacion = evento.get("conversation") or {}
        etiquetas = conversacion.get("labels")

        # Chatwoot manda las etiquetas en el evento casi siempre. Cuando no
        # las manda (cambia entre versiones y entre tipos de evento) hay que
        # preguntarle, porque dar por hecho que no hay ninguna sería dejar al
        # bot hablando arriba de una persona.
        if etiquetas is None:
            etiquetas = self._etiquetas_de(conversacion.get("id"))

        return self.etiqueta_humano in {
            str(e).strip().lower() for e in etiquetas or []
        }

    def _etiquetas_de(self, id_conversacion) -> list[str]:
        """Le pregunta a Chatwoot qué etiquetas tiene una conversación."""
        if not id_conversacion:
            return []

        # Por qué se traga el error: si Chatwoot no contesta esta consulta, la
        # alternativa es no responderle al cliente. Preferimos responder. El
        # riesgo del otro lado (el bot habla arriba de una persona) existe,
        # pero solo en el caso raro de que justo esta llamada falle.
        try:
            respuesta = self._api(
                "GET", f"conversations/{id_conversacion}/labels"
            )
        except Exception:
            return []

        return respuesta.get("payload") or []

    def lo_agarro_otro(self, conversacion: str) -> str:
        """Vuelve a mirar la conversación JUSTO ANTES de contestar.

        `deberia_responder` mira las etiquetas que traía el aviso, en el
        segundo cero. Pero entre ese segundo y la respuesta pasa un rato (se
        junta la ráfaga, piensa el modelo), y en ese rato alguien del equipo
        puede haberle puesto `humano` o haberla resuelto. Sin volver a mirar,
        el agente contesta arriba de una persona.

        Devuelve el motivo, o "" si la conversación sigue siendo suya. Si
        Chatwoot no contesta, se responde igual: perder a alguien por una
        consulta caída es peor que el caso raro de contestar encima.
        """
        try:
            datos = self._api("GET", f"conversations/{conversacion}")
        except Exception:
            return ""

        if str(datos.get("status") or "").strip().lower() == "resolved":
            return "la resolvieron"
        etiquetas = {str(e).strip().lower() for e in datos.get("labels") or []}
        if self.etiqueta_humano and self.etiqueta_humano in etiquetas:
            return f"le pusieron «{self.etiqueta_humano}»"
        return ""

    def ya_la_cerro(self, contacto_id: str) -> bool:
        """Si esa persona tiene alguna conversación RESUELTA.

        Resolver es una decisión: el agente no le vuelve a hablar a esa
        persona. Se mira el CONTACTO y no la conversación porque, según cómo
        esté la bandeja, Chatwoot abre una conversación NUEVA cuando alguien
        escribe después de que la suya se resolvió, y las etiquetas no viajan.

        Si no se puede preguntar, se contesta: el riesgo del otro lado
        (hablarle a alguien que se cerró) es una molestia; callarse con alguien
        que está esperando es perderlo.
        """
        if not contacto_id:
            return False
        try:
            respuesta = self._api("GET", f"contacts/{contacto_id}/conversations")
        except Exception:
            return False
        return any(
            str(c.get("status") or "").strip().lower() == "resolved"
            for c in respuesta.get("payload") or []
            if isinstance(c, dict)
        )

    def mensaje(self, conversacion: str, id_mensaje) -> dict | None:
        """Un mensaje de la conversación, por su id: para leer lo que se citó.

        La API devuelve los mensajes de a 20, del más nuevo al más viejo: se
        miran unas pocas páginas y, si no aparece, se da por no encontrado.
        """
        try:
            buscado = int(id_mensaje)
        except (TypeError, ValueError):
            return None

        camino = f"conversations/{conversacion}/messages"
        for _ in range(PAGINAS_PARA_BUSCAR):
            pagina = [m for m in self._api("GET", camino).get("payload") or [] if isinstance(m, dict)]
            for m in pagina:
                if m.get("id") == buscado:
                    return m
            ids = [m.get("id") for m in pagina if isinstance(m.get("id"), int)]
            if not ids or min(ids) <= buscado:
                return None
            camino = f"conversations/{conversacion}/messages?before={min(ids)}"
        return None

    def bajar(self, direccion: str, tope: int) -> tuple[bytes, str]:
        """Baja el archivo de un adjunto. Devuelve (los bytes, el tipo).

        Solo de TU Chatwoot: de la dirección que trae el evento se usa el
        camino (`/rails/active_storage/…`) y se pide siempre a CHATWOOT_URL.
        Así, un evento armado a mano no puede hacer que el servidor baje otra
        cosa (una dirección interna, por ejemplo). Y anda aunque Chatwoot
        publique sus archivos con otro dominio que el que usa el agente.
        """
        partes = urllib.parse.urlsplit(direccion or "")
        if not partes.path.startswith("/rails/active_storage/"):
            raise ErrorDeChatwoot("Ese adjunto no apunta a un archivo de Chatwoot: no lo bajo.")
        url = self.url + partes.path + (f"?{partes.query}" if partes.query else "")

        pedido = urllib.request.Request(url, headers={"User-Agent": "basdonax-agentkit"})
        try:
            with _ABRIDOR_DE_ARCHIVOS.open(pedido, timeout=ESPERA_DE_ARCHIVO) as respuesta:
                declarado = respuesta.headers.get("Content-Length")
                if declarado and declarado.isdigit() and int(declarado) > tope:
                    raise ErrorDeChatwoot(f"El archivo pesa más de {tope // (1024 * 1024)} MB: no lo bajo.")
                # Se lee uno de más: si llega, el archivo pasa el tope.
                datos = respuesta.read(tope + 1)
                tipo = respuesta.headers.get_content_type()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                raise ArchivoTodaviaNoEsta(f"Chatwoot todavía no tiene el archivo ({e.code}).") from None
            raise ErrorDeChatwoot(f"Chatwoot devolvió {e.code} al bajar un archivo.") from None
        if len(datos) > tope:
            raise ErrorDeChatwoot(f"El archivo pesa más de {tope // (1024 * 1024)} MB: no lo bajo.")
        return datos, tipo

    # -- Salida ----------------------------------------------------------------

    def enviar(
        self,
        conversacion: str,
        mensajes: list[str],
        antes_de_cada: Callable[[], None] | None = None,
        pausa: Callable[[str], float] | None = None,
    ) -> None:
        """Manda las respuestas a esa conversación, en orden.

        Salen como `outgoing`, que es lo que Chatwoot entiende por "esto lo
        dice nuestro lado". Desde ahí Chatwoot lo empuja al canal que
        corresponda: WhatsApp, Instagram, el widget de la web.

        Con `pausa`, entre globo y globo se espera lo que tardaría una persona
        en tipear el siguiente, con el «escribiendo…» prendido: tres mensajes
        que caen en el mismo segundo se leen como un bot aunque el texto sea
        perfecto. `antes_de_cada` es para renovar los puntitos en el celular
        de la persona (ver whatsapp_meta.py).
        """
        primero = True
        for texto in mensajes:
            if not texto.strip():
                continue

            if not primero and pausa is not None:
                if antes_de_cada is not None:
                    try:
                        antes_de_cada()
                    except Exception:
                        pass  # cosmético: no puede frenar la respuesta
                self.escribiendo(conversacion, True)
                time.sleep(pausa(texto))
            primero = False

            self._api(
                "POST",
                f"conversations/{conversacion}/messages",
                {"content": texto, "message_type": "outgoing"},
            )

    def pasar_a_persona(self, conversacion: str) -> None:
        """Le pone la etiqueta del traspaso: el agente se calla en esa conversación.

        Ojo con esto, que borra datos si se hace mal: en Chatwoot, mandar las
        etiquetas REEMPLAZA la lista entera. Si mandáramos solo `humano`, se
        irían las que ya tenía (ventas, urgente, lo que sea). Por eso primero
        se leen y después se suman.

        Y si no se pueden leer, no se sigue: mejor no poner la etiqueta que
        borrarle al equipo las que puso a mano.
        """
        if not self.etiqueta_humano:
            return

        respuesta = self._api("GET", f"conversations/{conversacion}/labels")
        etiquetas = [str(e) for e in respuesta.get("payload") or []]

        if self.etiqueta_humano in {e.strip().lower() for e in etiquetas}:
            return

        self._api(
            "POST",
            f"conversations/{conversacion}/labels",
            {"labels": etiquetas + [self.etiqueta_humano]},
        )

    def enlace(self, conversacion: str) -> str:
        """La dirección de la conversación en la bandeja. Va en los avisos por mail."""
        return f"{self.url}/app/accounts/{self.cuenta_id}/conversations/{conversacion}"

    def escribiendo(self, conversacion: str, encendido: bool = True) -> None:
        """El "escribiendo..." mientras el modelo piensa.

        No es decorativo: una respuesta puede tardar varios segundos y sin
        esto la persona no sabe si la escucharon o si se colgó.
        """
        # Que falle el aviso no puede voltear la respuesta: es cosmético.
        try:
            self._api(
                "POST",
                f"conversations/{conversacion}/toggle_typing_status",
                {"typing_status": "on" if encendido else "off"},
            )
        except Exception:
            pass

    # -- La API ----------------------------------------------------------------

    def yo_soy(self) -> dict:
        """Los datos de la cuenta. Sirve para avisar al arrancar con cuál se habla."""
        return self._api("GET", "conversations?status=open&page=1")

    def _api(self, metodo: str, camino: str, datos: dict | None = None) -> dict:
        """Una llamada a la API de Chatwoot."""
        url = f"{self.url}/api/v1/accounts/{self.cuenta_id}/{camino}"

        pedido = urllib.request.Request(
            url,
            data=json.dumps(datos).encode("utf-8") if datos is not None else None,
            method=metodo,
            headers={
                "Content-Type": "application/json",
                # Así se autentica Chatwoot: no es un Bearer, es este header.
                "api_access_token": self.token,
            },
        )

        try:
            with _ABRIDOR.open(pedido, timeout=ESPERA_DE_RED) as respuesta:
                cuerpo = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            # El cuerpo del error es lo único que dice qué pasó de verdad
            # (token vencido, conversación que no existe, cuenta equivocada).
            # Sin esto solo se ve "HTTP Error 404" y no se puede arreglar nada.
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ErrorDeChatwoot(
                f"Chatwoot devolvió {e.code} en {metodo} {camino}: {detalle}"
            ) from None

        return json.loads(cuerpo) if cuerpo else {}


# -- Ayudantes ----------------------------------------------------------------


def _tipo_de_mensaje(evento: dict) -> str:
    """Si el mensaje entra o sale.

    Chatwoot lo manda como texto ("incoming"), pero según la versión y el
    endpoint puede venir como número (0 = incoming, 1 = outgoing). Traducimos
    los dos para que un cambio de versión no vuelva loco al bot.
    """
    tipo = evento.get("message_type")

    if isinstance(tipo, int):
        return {0: "incoming", 1: "outgoing"}.get(tipo, "otro")

    return str(tipo or "").strip().lower()


def tarda_en_escribir(texto: str) -> float:
    """Cuánto tardaría una persona en tipear este globo, en segundos."""
    return max(PAUSA_MINIMA, min(PAUSA_MAXIMA, len(texto or "") / LETRAS_POR_SEGUNDO))

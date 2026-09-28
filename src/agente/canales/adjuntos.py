"""Lo que llega por WhatsApp y no es texto: fotos, audios, ubicaciones y demás.

Chatwoot manda cada mensaje con su texto en `content` y lo demás en
`attachments`: una foto, un audio, un archivo, una ubicación o un contacto
compartido. El agente trabaja con texto, así que acá cada cosa se convierte
en una línea que el modelo entiende, entre corchetes para que no la confunda
con algo que escribió la persona:

    audio      [La persona mandó un audio. Dice: «…»]           se transcribe
    foto       [La persona mandó una foto. Se ve: …]             la describe el modelo
    sticker    llega como foto
    ubicación  [La persona mandó una ubicación: … (link del mapa)]
    contacto   [La persona compartió un contacto: nombre, teléfono]
    archivo    [La persona mandó un archivo (…) que no puedo abrir…]
    video      [La persona mandó un video que no puedo ver…]

Y si contesta citando un mensaje, se busca el citado y va adelante:

    [Respondiendo a: «…»]            o a un audio (transcripto), a una foto (descripta)…

Es lo que hace un buen agente de WhatsApp armado en n8n, tipo por tipo. La
memoria guarda este texto, no los archivos.

Tres cuidados:
  · Solo se baja de TU Chatwoot (ver Chatwoot.bajar): la dirección del evento
    se usa solo por el camino, así nadie usa al agente para leer otra cosa.
  · Con tope de tamaño, para no bajar entero un archivo gigante.
  · Si algo falla, no se cae nada: el agente se entera de que llegó algo que
    no se pudo leer, y pregunta.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from .base import MensajeEntrante

registro = logging.getLogger("agente.adjuntos")

# Un mensaje de WhatsApp trae un adjunto; si alguna vez vienen más, se leen
# los primeros y listo: cada foto es una llamada al modelo.
MAXIMO_DE_ADJUNTOS = 3

# Topes de tamaño. El del audio es el de la API de transcripción de OpenAI.
TOPE_FOTO = 10 * 1024 * 1024
TOPE_AUDIO = 25 * 1024 * 1024

# Lo que se recuerda ya leído (por id del adjunto): si alguien cita una foto
# que ya se describió, no se paga de nuevo.
RECORDADOS = 200

# El archivo puede no estar listo todavía cuando llega el aviso de Chatwoot
# (el aviso sale antes de que termine de bajarlo de Meta): se reintenta.
ESPERAS_PARA_REINTENTAR = (2, 4)

PEDIDO_DE_DESCRIPCION = (
    "Describí esta imagen para alguien que no la puede ver, en 2 a 5 oraciones: "
    "qué es, qué texto se lee (precios, nombres, códigos, números) y cualquier "
    "detalle que ayude a responderle a quien la mandó. Sin saludar ni opinar."
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


@dataclass
class Leido:
    """Lo que el agente va a leer de un mensaje."""

    texto: str
    # Si no hay forma de entenderlo (un audio sin cómo escucharlo), el motivo:
    # la conversación pasa a una persona en vez de quedar sin respuesta.
    a_una_persona: str = ""
    # Algo se rompió leyendo (una clave vencida, por ejemplo): va al mail.
    error: str = ""


class Lector:
    """Convierte en texto todo lo que trae un mensaje de Chatwoot."""

    def __init__(
        self,
        canal,
        describir: Callable[[bytes, str], str] | None = None,
        transcribir: Callable[[bytes, str, str], str] | None = None,
        dormir: Callable[[float], None] = time.sleep,
        esperas: tuple[float, ...] = ESPERAS_PARA_REINTENTAR,
    ) -> None:
        """
        `describir(datos, tipo)`            la foto a texto (el modelo del agente)
        `transcribir(datos, tipo, nombre)`  el audio a texto (OpenAI)
        Sin alguno de los dos, esa cosa se avisa en vez de leerse.
        """
        self.canal = canal
        self.describir = describir
        self.transcribir = transcribir
        self.dormir = dormir
        self.esperas = esperas
        self._recordados: OrderedDict[str, str] = OrderedDict()

    # -- Lo que usa el webhook -----------------------------------------------------

    @staticmethod
    def hay_que_leer(mensaje: MensajeEntrante) -> bool:
        """Si el mensaje trae algo más que texto: un adjunto o una cita."""
        evento = mensaje.datos or {}
        return bool(adjuntos_de(evento)) or id_citado(evento) is not None

    def leer(self, mensaje: MensajeEntrante) -> Leido:
        """Todo lo del mensaje, en texto: la cita, los adjuntos y lo que escribió."""
        evento = mensaje.datos or {}
        partes: list[str] = []
        a_una_persona = ""
        errores: list[str] = []

        citado = id_citado(evento)
        if citado is not None:
            nota, error = self._cita(mensaje.conversacion, citado)
            partes.append(nota)
            if error:
                errores.append(error)

        for adjunto in adjuntos_de(evento)[:MAXIMO_DE_ADJUNTOS]:
            nota, motivo, error = self._adjunto(
                adjunto, mensaje.conversacion, evento.get("id"), citando=False
            )
            partes.append(nota)
            a_una_persona = a_una_persona or motivo
            if error:
                errores.append(error)

        if mensaje.texto:
            partes.append(mensaje.texto)

        return Leido(
            "\n".join(p for p in partes if p),
            a_una_persona=a_una_persona,
            error="; ".join(errores),
        )

    # -- Cada tipo -------------------------------------------------------------------

    def _adjunto(
        self, adjunto: dict, conversacion: str, id_mensaje, citando: bool
    ) -> tuple[str, str, str]:
        """Un adjunto a texto. Devuelve (nota, motivo para pasar a persona, error)."""
        tipo = str(adjunto.get("file_type") or "").strip().lower()

        if tipo == "audio":
            return self._audio(adjunto, conversacion, id_mensaje, citando)
        if tipo == "image":
            return self._foto(adjunto, conversacion, id_mensaje, citando)
        if tipo == "location":
            return _ubicacion(adjunto, citando), "", ""
        if tipo == "contact":
            return _contacto(adjunto, citando), "", ""
        if tipo == "video":
            if citando:
                return "[Respondiendo a un video.]", "", ""
            return (
                "[La persona mandó un video que no puedo ver: preguntale de qué se trata.]",
                "",
                "",
            )
        if tipo == "file":
            nombre = _nombre_del_archivo(adjunto)
            cual = f" ({nombre})" if nombre else ""
            if citando:
                return f"[Respondiendo a un archivo{cual}.]", "", ""
            return (
                f"[La persona mandó un archivo{cual} que no puedo abrir: preguntale de qué se trata.]",
                "",
                "",
            )

        # Instagram y otros canales de Chatwoot tienen tipos propios (una
        # historia, un posteo compartido): que el agente sepa que llegó algo.
        cual = f" ({_limpio(tipo)[:30]})" if tipo else ""
        if citando:
            return f"[Respondiendo a algo que no puedo ver{cual}.]", "", ""
        return f"[La persona mandó algo que no puedo ver{cual}.]", "", ""

    def _audio(self, adjunto, conversacion, id_mensaje, citando) -> tuple[str, str, str]:
        if self.transcribir is None:
            if citando:
                return "[Respondiendo a un audio que no puedo escuchar.]", "", ""
            return (
                "[La persona mandó un audio y no lo puedo escuchar.]",
                "llegó un audio y no hay cómo escucharlo (falta OPENAI_API_KEY)",
                "",
            )

        clave = f"audio:{adjunto.get('id') or adjunto.get('data_url')}"
        texto = self._recordado(clave)
        if texto is None:
            try:
                datos, tipo = self._bajar(adjunto, conversacion, id_mensaje, TOPE_AUDIO)
                texto = _limpio(
                    self.transcribir(datos, tipo, _nombre_del_archivo(adjunto) or "audio.ogg")
                )
            except Exception as e:
                registro.warning("[%s] no se pudo escuchar un audio: %s", conversacion, e)
                if citando:
                    return "[Respondiendo a un audio que no se pudo escuchar.]", "", ""
                return (
                    "[La persona mandó un audio que no se pudo escuchar: pedile que te lo escriba.]",
                    "",
                    f"No se pudo escuchar un audio: {type(e).__name__}: {e}",
                )
            self._recordar(clave, texto)

        if not texto:
            texto = "(no se entiende ninguna palabra)"
        if citando:
            return f"[Respondiendo a un audio que dice: «{texto}»]", "", ""
        return f"[La persona mandó un audio. Dice: «{texto}»]", "", ""

    def _foto(self, adjunto, conversacion, id_mensaje, citando) -> tuple[str, str, str]:
        if self.describir is None:
            if citando:
                return "[Respondiendo a una foto que no puedo ver.]", "", ""
            return "[La persona mandó una foto y no la puedo ver: preguntale qué es.]", "", ""

        clave = f"foto:{adjunto.get('id') or adjunto.get('data_url')}"
        descripcion = self._recordado(clave)
        if descripcion is None:
            try:
                datos, tipo = self._bajar(adjunto, conversacion, id_mensaje, TOPE_FOTO)
                if not tipo.startswith("image/"):
                    raise ValueError(f"el archivo no es una imagen ({tipo})")
                descripcion = _limpio(self.describir(datos, tipo))
            except Exception as e:
                registro.warning("[%s] no se pudo ver una foto: %s", conversacion, e)
                if citando:
                    return "[Respondiendo a una foto que no se pudo ver.]", "", ""
                return (
                    "[La persona mandó una foto que no se pudo ver: preguntale qué es.]",
                    "",
                    f"No se pudo ver una foto: {type(e).__name__}: {e}",
                )
            self._recordar(clave, descripcion)

        if citando:
            return f"[Respondiendo a una foto. Se ve: {descripcion}]", "", ""
        return f"[La persona mandó una foto. Se ve: {descripcion}]", "", ""

    def _cita(self, conversacion: str, id_mensaje: int) -> tuple[str, str]:
        """El mensaje citado, en texto. Devuelve (nota, error)."""
        try:
            citado = self.canal.mensaje(conversacion, id_mensaje)
        except Exception as e:
            registro.warning("[%s] no se pudo leer el mensaje citado: %s", conversacion, e)
            citado = None
        if not citado:
            return "[Respondiendo a un mensaje anterior.]", ""

        texto = _limpio(citado.get("content"))[:500]
        adjuntos = adjuntos_de(citado)
        if adjuntos:
            nota, _, error = self._adjunto(
                adjuntos[0], conversacion, citado.get("id"), citando=True
            )
            if texto:
                nota = f"{nota[:-1]} Con el texto: «{texto}»]"
            return nota, error

        if not texto:
            return "[Respondiendo a un mensaje anterior.]", ""
        if _sale(citado):
            return f"[Respondiendo a lo que le dijiste: «{texto}»]", ""
        return f"[Respondiendo a: «{texto}»]", ""

    # -- Bajar, con reintento ---------------------------------------------------------

    def _bajar(self, adjunto: dict, conversacion: str, id_mensaje, tope: int) -> tuple[bytes, str]:
        """Baja el archivo del adjunto. Si todavía no está, espera y pide la dirección de nuevo."""
        url = str(adjunto.get("data_url") or "")
        ultimo: Exception | None = None
        for espera in (0, *self.esperas):
            if espera:
                self.dormir(espera)
                url = self._direccion_fresca(conversacion, id_mensaje, adjunto) or url
            if not url:
                continue
            try:
                return self.canal.bajar(url, tope)
            except ArchivoTodaviaNoEsta as e:
                ultimo = e
        raise ultimo or ValueError("el adjunto llegó sin dirección para bajarlo")

    def _direccion_fresca(self, conversacion, id_mensaje, adjunto) -> str:
        """La dirección del archivo según la API de mensajes: la del aviso puede no andar todavía."""
        try:
            mensaje = self.canal.mensaje(conversacion, id_mensaje)
        except Exception:
            return ""
        for otro in adjuntos_de(mensaje or {}):
            if otro.get("id") == adjunto.get("id") and otro.get("data_url"):
                return str(otro["data_url"])
        return ""

    # -- Lo ya leído --------------------------------------------------------------------

    def _recordado(self, clave: str) -> str | None:
        if clave in self._recordados:
            self._recordados.move_to_end(clave)
            return self._recordados[clave]
        return None

    def _recordar(self, clave: str, texto: str) -> None:
        self._recordados[clave] = texto
        self._recordados.move_to_end(clave)
        while len(self._recordados) > RECORDADOS:
            self._recordados.popitem(last=False)


class ArchivoTodaviaNoEsta(Exception):
    """Chatwoot todavía no tiene el archivo (404): vale la pena reintentar."""


# -- Leer el evento ---------------------------------------------------------------------


def adjuntos_de(evento: dict) -> list[dict]:
    """Los adjuntos de un mensaje de Chatwoot, solo los que tienen la forma esperada."""
    adjuntos = evento.get("attachments") if isinstance(evento, dict) else None
    if not isinstance(adjuntos, list):
        return []
    return [a for a in adjuntos if isinstance(a, dict)]


def id_citado(evento: dict) -> int | None:
    """El id del mensaje al que responde, si contesta citando uno."""
    atributos = evento.get("content_attributes") if isinstance(evento, dict) else None
    if not isinstance(atributos, dict):
        return None
    valor = atributos.get("in_reply_to")
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int) and valor > 0:
        return valor
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _ubicacion(adjunto: dict, citando: bool) -> str:
    titulo = _limpio(adjunto.get("fallback_title"))[:200]
    lat, lon = _numero(adjunto.get("coordinates_lat")), _numero(adjunto.get("coordinates_long"))
    partes = []
    if titulo:
        partes.append(titulo)
    if lat is not None and lon is not None:
        partes.append(f"en el mapa: https://www.google.com/maps?q={lat},{lon}")
    lugar = ", ".join(partes) or "sin datos del lugar"
    if citando:
        return f"[Respondiendo a una ubicación: {lugar}]"
    return f"[La persona mandó una ubicación: {lugar}]"


def _contacto(adjunto: dict, citando: bool) -> str:
    meta = adjunto.get("meta") if isinstance(adjunto.get("meta"), dict) else {}
    nombre = " ".join(
        _limpio(meta.get(campo)) for campo in ("firstName", "lastName") if _limpio(meta.get(campo))
    )[:120]
    telefono = _limpio(adjunto.get("fallback_title"))[:40]
    datos = ", ".join(x for x in (nombre, telefono) if x) or "sin datos"
    if citando:
        return f"[Respondiendo a un contacto: {datos}]"
    return f"[La persona compartió un contacto: {datos}]"


def _nombre_del_archivo(adjunto: dict) -> str:
    """El nombre del archivo, sacado del final de su dirección."""
    url = str(adjunto.get("data_url") or "")
    nombre = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]) if url else ""
    return _limpio(nombre)[:80]


def _numero(valor) -> float | None:
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if -180 <= numero <= 180 else None


def _sale(mensaje: dict) -> bool:
    """Si el mensaje lo mandó nuestro lado (el agente o el equipo)."""
    tipo = mensaje.get("message_type")
    return tipo in (1, "outgoing")


def _limpio(valor) -> str:
    """Una sola línea, sin caracteres de control: lo que llega de afuera no arma renglones."""
    if not isinstance(valor, str):
        return ""
    return _CONTROL.sub(" ", valor).strip()


# -- Las fotos: las describe el modelo del agente -----------------------------------------


class DescriptorDeFotos:
    """Describe una foto con el mismo modelo del agente (Claude, OpenAI y Gemini ven imágenes).

    El modelo se arma la primera vez que llega una foto, no al arrancar: armarlo
    le pregunta al proveedor los topes del modelo, y es una espera que no hace
    falta si nunca llega ninguna.
    """

    def __init__(self, armar_modelo: Callable[[], object]) -> None:
        self._armar_modelo = armar_modelo
        self._modelo = None

    def __call__(self, datos: bytes, tipo: str) -> str:
        from langchain_core.messages import HumanMessage

        if self._modelo is None:
            self._modelo = self._armar_modelo()
        respuesta = self._modelo.invoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": PEDIDO_DE_DESCRIPCION},
                        # El formato de imagen estándar de LangChain: cada
                        # proveedor lo traduce al suyo.
                        {
                            "type": "image",
                            "base64": base64.b64encode(datos).decode("ascii"),
                            "mime_type": tipo,
                        },
                    ]
                )
            ]
        )
        # En LangChain 1.x `.text` es una propiedad (un texto): junta las partes
        # de texto aunque el proveedor devuelva la respuesta en bloques.
        texto = getattr(respuesta, "text", None)
        if not isinstance(texto, str):
            texto = respuesta.content if isinstance(respuesta.content, str) else ""
        return str(texto).strip()


# -- Los audios: los transcribe OpenAI ----------------------------------------------------

URL_DE_TRANSCRIPCION = "https://api.openai.com/v1/audio/transcriptions"
ESPERA_DE_TRANSCRIPCION = 90  # un audio largo tarda


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """OpenAI no redirige: seguirla sería mandarle la clave a otro lado."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"OpenAI contestó con una redirección ({code}): no la sigo.")


_ABRIDOR_OPENAI = urllib.request.build_opener(
    _SinRedirecciones,
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
)


class TranscriptorOpenAI:
    """Pasa un audio a texto con la API de OpenAI (sin dependencias nuevas)."""

    def __init__(self, clave: str, modelo: str = "gpt-4o-mini-transcribe") -> None:
        self.clave = clave
        self.modelo = modelo

    def __repr__(self) -> str:
        return f"TranscriptorOpenAI(modelo={self.modelo!r})"  # sin la clave

    def __call__(self, datos: bytes, tipo: str, nombre: str) -> str:
        limite = "agentkit-" + uuid.uuid4().hex
        nombre = re.sub(r'[^\w.\-]', "_", nombre or "audio.ogg") or "audio.ogg"
        cuerpo = b"".join(
            [
                _campo(limite, "model", self.modelo),
                _campo(limite, "response_format", "json"),
                (
                    f"--{limite}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
                    f"Content-Type: {tipo or 'application/octet-stream'}\r\n\r\n"
                ).encode("utf-8"),
                datos,
                f"\r\n--{limite}--\r\n".encode("utf-8"),
            ]
        )
        pedido = urllib.request.Request(
            URL_DE_TRANSCRIPCION,
            data=cuerpo,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
        )
        # «Sin redirigir»: aunque alguien cambie el abridor, la clave no viaja a otro servidor.
        pedido.add_unredirected_header("Authorization", f"Bearer {self.clave}")
        try:
            with _ABRIDOR_OPENAI.open(pedido, timeout=ESPERA_DE_TRANSCRIPCION) as respuesta:
                datos_de_vuelta = json.loads(respuesta.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:200] if e.fp else ""
            if e.code == 401:
                raise ValueError("OpenAI no acepta la clave (OPENAI_API_KEY) para transcribir.") from None
            if e.code == 429:
                raise ValueError("OpenAI frenó la transcripción: sin saldo o demasiados pedidos (429).") from None
            raise ValueError(f"OpenAI contestó {e.code} al transcribir: {_limpio(detalle)}") from None
        return str(datos_de_vuelta.get("text") or "").strip()


def _campo(limite: str, nombre: str, valor: str) -> bytes:
    return (
        f"--{limite}\r\n"
        f'Content-Disposition: form-data; name="{nombre}"\r\n\r\n'
        f"{valor}\r\n"
    ).encode("utf-8")

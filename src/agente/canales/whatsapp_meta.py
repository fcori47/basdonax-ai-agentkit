"""El visto azul y el «escribiendo…», en el WhatsApp de la persona.

Chatwoot tiene su «escribiendo…», pero no lo pasa a WhatsApp: se ve solo
adentro de su bandeja. Para que la persona lo vea en su celular hay que
pedírselo a Meta directo, y eso pide dos datos de tu cuenta de WhatsApp
Business (los mismos que usa Chatwoot):

    WHATSAPP_TOKEN              el token de acceso
    WHATSAPP_PHONE_NUMBER_ID    el id del número

Es opcional: sin esos datos todo anda igual, solo que la persona no ve el
visto ni los puntitos. Y es cosmético: si Meta no contesta, la respuesta
sale igual. No cuenta como mensaje: Meta no lo cobra.

Los dos van en el MISMO pedido, que es lo que hace que se vea bien: primero
el visto y enseguida los puntitos, como alguien que abre el chat y se pone a
escribir. Los puntitos duran 25 segundos, o hasta que llega la respuesta.

Esto le suma al agente un segundo interlocutor además de Chatwoot, que es lo
que el diseño evitaba: es a propósito y es el único camino.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request

registro = logging.getLogger("agente.whatsapp")

VERSION_DE_LA_API = "v26.0"
ESPERA = 10


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Meta no redirige esta API: seguirla sería mandar el token a otro lado."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"Meta contestó con una redirección ({code}): no la sigo.")


_ABRIDOR = urllib.request.build_opener(
    _SinRedirecciones,
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
)


def wamid_del_evento(evento: dict) -> str:
    """El id que le puso WhatsApp al mensaje que llegó, o "".

    Chatwoot lo guarda en `source_id`. Es el único que Meta acepta para el
    visto: el id de Chatwoot no le sirve.
    """
    valor = evento.get("source_id") if isinstance(evento, dict) else ""
    valor = str(valor or "")
    # Solo los que entran se pueden marcar como leídos, y tienen esta forma.
    if valor.startswith("wamid.") and len(valor) < 200 and valor.isprintable():
        return valor
    return ""


def marcar_visto_y_escribiendo(wamid: str, token: str, numero_id: str) -> bool:
    """El visto en el mensaje y los puntitos. Devuelve True si salió.

    Nunca levanta un error: es cosmético y no puede voltear una respuesta.
    """
    if not (wamid and token and numero_id) or not str(numero_id).isdigit():
        return False

    cuerpo = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": wamid,
        "typing_indicator": {"type": "text"},
    }
    pedido = urllib.request.Request(
        f"https://graph.facebook.com/{VERSION_DE_LA_API}/{numero_id}/messages",
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    pedido.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with _ABRIDOR.open(pedido, timeout=ESPERA) as respuesta:
            respuesta.read()
        return True
    except Exception as e:
        registro.info("no salió el visto (%s…): %s", wamid[:16], type(e).__name__)
        return False

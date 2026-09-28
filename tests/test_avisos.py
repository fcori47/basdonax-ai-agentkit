"""Pruebas de los avisos por mail. No mandan ningún mail de verdad.

El servidor de mail se reemplaza por uno de mentira que anota qué se le
pidió: con qué puerto, si se cifró, con qué cuenta y qué mensaje. Google
(la Gmail API), por uno que anota los pedidos y contesta lo que se le pide.
"""

from __future__ import annotations

import base64
import email
import email.policy
import io
import json
import logging
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agente.avisos as avisos_mod  # noqa: E402
from agente import gmail  # noqa: E402
from agente.avisos import Avisos  # noqa: E402


class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora

    def pasan(self, segundos):
        self.ahora += segundos


def _verifica(contexto) -> bool:
    """Si ese contexto de cifrado verifica el certificado y el nombre del servidor."""
    import ssl

    return bool(contexto) and contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname


class ServidorDeMailFalso:
    """Hace de smtplib.SMTP / SMTP_SSL y anota todo en `registro`."""

    registro: list = []

    def __init__(self, servidor, puerto, timeout=None, context=None):
        self.registro.append(("conectar", servidor, puerto))
        if context is not None:
            self.registro.append(("cifrado", _verifica(context)))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.registro.append(("starttls",))
        self.registro.append(("cifrado", _verifica(context)))

    def login(self, usuario, clave):
        self.registro.append(("login", usuario))

    def send_message(self, mensaje):
        self.registro.append(("mandar", mensaje["To"], mensaje["Subject"]))


def avisos_de_prueba(reloj=None, puerto=587, monkeypatch=None):
    ServidorDeMailFalso.registro = []
    if monkeypatch is not None:
        monkeypatch.setattr(avisos_mod.smtplib, "SMTP", ServidorDeMailFalso)
        monkeypatch.setattr(avisos_mod.smtplib, "SMTP_SSL", ServidorDeMailFalso)
    return Avisos(
        para="duenio@ejemplo.com",
        servidor="smtp.ejemplo.com",
        puerto=puerto,
        usuario="agente@ejemplo.com",
        clave="clave-de-aplicacion",
        reloj=reloj or Reloj(),
    )


def mandados():
    return [r for r in ServidorDeMailFalso.registro if r[0] == "mandar"]


def test_sin_mail_configurado_no_manda_ni_rompe():
    """Es opcional: sin AVISOS_EMAIL el aviso queda en el log y listo."""
    assert Avisos().activos is False
    assert Avisos().avisar("algo", "pasó algo", "tipo") is False


def test_manda_el_aviso(monkeypatch):
    avisos = avisos_de_prueba(monkeypatch=monkeypatch)

    assert avisos.avisar("Se rompió algo", "detalle", "tipo") is True
    assert mandados() == [("mandar", "duenio@ejemplo.com", "Se rompió algo")]


def test_587_cifra_antes_de_mandar_la_clave(monkeypatch):
    """Sin STARTTLS la contraseña viajaría en texto plano."""
    avisos = avisos_de_prueba(puerto=587, monkeypatch=monkeypatch)

    avisos.avisar("a", "b", "tipo")

    pasos = [r[0] for r in ServidorDeMailFalso.registro]
    assert pasos.index("starttls") < pasos.index("login")


def test_465_ya_viene_cifrado(monkeypatch):
    avisos = avisos_de_prueba(puerto=465, monkeypatch=monkeypatch)

    avisos.avisar("a", "b", "tipo")

    assert ("starttls",) not in ServidorDeMailFalso.registro
    assert ("cifrado", True) in ServidorDeMailFalso.registro, "465 también verifica el certificado"
    assert ("login", "agente@ejemplo.com") in ServidorDeMailFalso.registro


def test_el_mismo_error_una_vez_por_hora(monkeypatch):
    """Una clave vencida hace fallar cada mensaje: un mail, no cien."""
    reloj = Reloj()
    avisos = avisos_de_prueba(reloj=reloj, monkeypatch=monkeypatch)

    assert avisos.avisar("falla", "1", "clave-vencida") is True
    assert avisos.avisar("falla", "2", "clave-vencida") is False
    assert avisos.avisar("falla", "3", "clave-vencida") is False
    assert len(mandados()) == 1


def test_pasada_la_hora_avisa_de_nuevo_y_cuenta_los_callados(monkeypatch):
    reloj = Reloj()
    avisos = avisos_de_prueba(reloj=reloj, monkeypatch=monkeypatch)
    cuerpos = []
    monkeypatch.setattr(avisos, "_enviar", lambda asunto, cuerpo: cuerpos.append(cuerpo))

    avisos.avisar("falla", "primero", "clave-vencida")
    avisos.avisar("falla", "segundo", "clave-vencida")
    avisos.avisar("falla", "tercero", "clave-vencida")
    reloj.pasan(61 * 60)
    avisos.avisar("falla", "cuarto", "clave-vencida")

    assert len(cuerpos) == 2
    assert "2 veces más" in cuerpos[1], "el mail siguiente dice cuántos se callaron"


def test_errores_distintos_avisan_cada_uno(monkeypatch):
    avisos = avisos_de_prueba(monkeypatch=monkeypatch)

    avisos.avisar("falla el modelo", "a", "modelo")
    avisos.avisar("falla chatwoot", "b", "envio")

    assert len(mandados()) == 2


def test_la_prueba_sale_aunque_recien_haya_salido_un_aviso(monkeypatch):
    """La prueba de la instalación no espera la hora de los avisos repetidos."""
    avisos = avisos_de_prueba(monkeypatch=monkeypatch)

    avisos.avisar("falla", "a", "tipo")
    avisos.probar()

    assert len(mandados()) == 2
    assert "Prueba" in mandados()[-1][2]


def test_la_prueba_no_se_traga_el_error(monkeypatch):
    """El que instala tiene que ver qué contestó el servidor de mail."""
    import smtplib

    import pytest

    avisos = avisos_de_prueba(monkeypatch=monkeypatch)

    def rechaza(asunto, cuerpo):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(avisos, "_enviar", rechaza)

    with pytest.raises(smtplib.SMTPAuthenticationError):
        avisos.probar()


def test_la_prueba_sin_datos_dice_que_falta():
    import pytest

    with pytest.raises(ValueError, match="AVISOS_EMAIL"):
        Avisos().probar()


def test_desde_el_entorno_no_pide_la_clave_del_modelo(monkeypatch):
    """Para probar el mail no hace falta tener cargado el resto."""
    for nombre in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
                   "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("AVISOS_EMAIL", "duenio@ejemplo.com")
    monkeypatch.setenv("SMTP_SERVIDOR", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PUERTO", "465")
    monkeypatch.setenv("SMTP_USUARIO", "agente@ejemplo.com")
    monkeypatch.setenv("SMTP_CLAVE", "abcd efgh ijkl mnop")

    avisos = Avisos.desde_entorno()

    assert avisos.activos
    assert avisos.puerto == 465


def test_si_el_mail_no_sale_no_voltea_nada(monkeypatch):
    """El aviso es para enterarse de un problema, no para ser otro."""
    avisos = avisos_de_prueba(monkeypatch=monkeypatch)

    def explota(asunto, cuerpo):
        raise ConnectionError("el servidor de mail no contesta")

    monkeypatch.setattr(avisos, "_enviar", explota)

    assert avisos.avisar("a", "b", "tipo") is False


def test_587_verifica_el_certificado(monkeypatch):
    """Sin verificar, alguien en el medio de la red se queda con la clave."""
    avisos = avisos_de_prueba(puerto=587, monkeypatch=monkeypatch)

    avisos.avisar("a", "b", "tipo")

    assert ("cifrado", True) in ServidorDeMailFalso.registro


def test_sin_usuario_o_clave_no_estan_activos():
    """Con datos a medias el servidor diría «avisos prendidos» y no saldría nada."""
    a = Avisos(para="duenio@ejemplo.com", servidor="smtp.ejemplo.com")

    assert a.activos is False
    assert a.faltan() == ["SMTP_USUARIO", "SMTP_CLAVE"]


def test_la_prueba_dice_que_variable_falta():
    import pytest

    with pytest.raises(ValueError, match="SMTP_CLAVE"):
        Avisos(para="duenio@ejemplo.com", servidor="smtp.ejemplo.com", usuario="agente@ejemplo.com").probar()


def test_los_espacios_de_la_clave_se_sacan():
    """Hay proveedores que muestran la clave en bloques de cuatro."""
    assert Avisos(clave="abcd efgh ijkl mnop").clave == "abcdefghijklmnop"


# -- Por Google (Gmail API) ------------------------------------------------------

SECRETO = "secreto-del-cliente-de-mentira"
PERMISO = "permiso-duradero-de-mentira"


class RespuestaFalsa:
    def __init__(self, cuerpo: bytes):
        self._cuerpo = cuerpo

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class GoogleFalso:
    """Hace de Google: anota cada pedido y contesta lo que se le programó."""

    def __init__(self):
        self.pedidos: list[urllib.request.Request] = []
        self.renovaciones = 0
        self.al_renovar = lambda: (200, {
            "access_token": f"acceso-{self.renovaciones}",
            "expires_in": 3599,
            "scope": gmail.PERMISO_PARA_MANDAR,
            "token_type": "Bearer",
        })
        self.al_mandar = lambda: (200, {"id": "1", "threadId": "1", "labelIds": ["SENT"]})

    def open(self, pedido, timeout=None):
        self.pedidos.append(pedido)
        if pedido.full_url == gmail.URL_DE_PERMISOS:
            self.renovaciones += 1
            codigo, datos = self.al_renovar()
        elif pedido.full_url == gmail.URL_PARA_MANDAR:
            codigo, datos = self.al_mandar()
        else:
            raise AssertionError(f"pedido a una dirección que no es de Google: {pedido.full_url}")
        cuerpo = json.dumps(datos).encode()
        if codigo >= 400:
            raise urllib.error.HTTPError(pedido.full_url, codigo, "error", {}, io.BytesIO(cuerpo))
        return RespuestaFalsa(cuerpo)

    def mandados(self):
        return [p for p in self.pedidos if p.full_url == gmail.URL_PARA_MANDAR]


@pytest.fixture
def google(monkeypatch):
    falso = GoogleFalso()
    monkeypatch.setattr(gmail, "_ABRIDOR", falso)
    return falso


def avisos_por_google(reloj=None):
    return Avisos(
        para="duenio@ejemplo.com",
        gmail_cliente="123-abc.apps.googleusercontent.com",
        gmail_secreto=SECRETO,
        gmail_permiso=PERMISO,
        reloj=reloj or Reloj(),
    )


def mail_mandado(pedido):
    crudo = json.loads(pedido.data)["raw"]
    return email.message_from_bytes(base64.urlsafe_b64decode(crudo), policy=email.policy.default)


def test_por_google_pide_el_acceso_y_manda(google):
    avisos = avisos_por_google()
    assert avisos.metodo == "google" and avisos.activos

    assert avisos.avisar("Se rompió algo", "el detalle", "tipo") is True

    renovar, mandar = google.pedidos
    assert urllib.parse.parse_qs(renovar.data.decode()) == {
        "client_id": ["123-abc.apps.googleusercontent.com"],
        "client_secret": [SECRETO],
        "refresh_token": [PERMISO],
        "grant_type": ["refresh_token"],
    }
    mail = mail_mandado(mandar)
    assert mail["To"] == "duenio@ejemplo.com"
    assert mail["Subject"] == "Se rompió algo"
    assert "el detalle" in mail.get_content()
    assert mail["From"] is None, "el remitente lo pone Google: la cuenta que dio el permiso"


def test_el_acceso_viaja_solo_a_google(google):
    """Va como cabecera «sin redirigir»: una redirección no se lo lleva a otro lado."""
    avisos_por_google().avisar("a", "b", "tipo")

    mandar = google.mandados()[0]
    assert mandar.unredirected_hdrs.get("Authorization") == "Bearer acceso-1"
    assert "Authorization" not in mandar.headers


def test_el_acceso_se_reusa_mientras_vale(google):
    """El acceso dura una hora: no se pide uno por mail."""
    reloj = Reloj()
    avisos = avisos_por_google(reloj)

    avisos.avisar("a", "1", "uno")
    avisos.avisar("b", "2", "dos")
    assert google.renovaciones == 1

    reloj.pasan(60 * 60)
    avisos.avisar("c", "3", "tres")
    assert google.renovaciones == 2, "vencido, se pide uno nuevo"
    assert len(google.mandados()) == 3


def test_revisar_usa_el_permiso_sin_mandar_nada(google):
    """Google borra el permiso que pasa seis meses sin usarse."""
    avisos = avisos_por_google()

    avisos.revisar()
    avisos.revisar()

    assert google.renovaciones == 2, "revisar siempre lo usa, aunque haya un acceso guardado"
    assert google.mandados() == []


def test_revisar_con_smtp_no_hace_nada():
    Avisos(para="d@ejemplo.com", servidor="smtp.ejemplo.com", usuario="a@ejemplo.com", clave="x").revisar()


def test_permiso_vencido_dice_que_hacer(google):
    google.al_renovar = lambda: (400, {
        "error": "invalid_grant", "error_description": "Token has been expired or revoked."
    })
    avisos = avisos_por_google()

    with pytest.raises(gmail.ErrorDeGoogle, match="conectar_gmail.py") as error:
        avisos.probar()
    assert "7 días" in str(error.value), "nombra la trampa de la app «En prueba»"
    assert avisos.avisar("a", "b", "otro") is False, "y el aviso no voltea nada"


def test_si_el_acceso_deja_de_valer_el_proximo_aviso_pide_otro(google):
    """Revocado a mitad de hora: el acceso guardado no se sigue usando."""
    rechazos = [True]

    def mandar():
        if rechazos and rechazos.pop():
            return 401, {"error": {"code": 401, "message": "Request had invalid authentication credentials.",
                                   "status": "UNAUTHENTICATED"}}
        return 200, {"id": "1"}

    google.al_mandar = mandar
    avisos = avisos_por_google()

    with pytest.raises(gmail.ErrorDeGoogle, match="conectar_gmail.py"):
        avisos.probar()
    assert avisos.avisar("a", "b", "tipo") is True
    assert google.renovaciones == 2, "después del 401 se pidió un acceso nuevo"


def test_gmail_api_sin_habilitar_dice_donde_se_habilita(google):
    google.al_mandar = lambda: (403, {"error": {
        "code": 403,
        "message": "Gmail API has not been used in project 123 before or it is disabled.",
        "status": "PERMISSION_DENIED",
        "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "SERVICE_DISABLED"}],
    }})

    with pytest.raises(gmail.ErrorDeGoogle, match="Habilitala"):
        avisos_por_google().probar()


def test_las_claves_de_google_no_aparecen_en_ningun_lado(google, caplog):
    google.al_renovar = lambda: (401, {"error": "invalid_client", "error_description": "Unauthorized"})
    avisos = avisos_por_google()

    with caplog.at_level(logging.DEBUG):
        avisos.avisar("a", "b", "tipo")
    with pytest.raises(gmail.ErrorDeGoogle) as error:
        avisos.probar()

    for secreto in (SECRETO, PERMISO):
        assert secreto not in caplog.text
        assert secreto not in str(error.value)
        assert secreto not in repr(avisos)


def test_elige_por_donde_sale_solo():
    assert Avisos(para="d@ejemplo.com").metodo == ""
    assert Avisos(servidor="smtp.ejemplo.com").metodo == "smtp"
    assert Avisos(gmail_permiso="x").metodo == "google"
    assert Avisos(servidor="smtp.ejemplo.com", gmail_cliente="x").metodo == "google", (
        "con las dos cargadas, va por Google"
    )


def test_sin_nada_cargado_pide_lo_de_google():
    """Es el camino recomendado: lo que falta se nombra por ahí."""
    assert Avisos().faltan() == [
        "AVISOS_EMAIL", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"
    ]


def test_google_a_medias_no_esta_activo():
    a = Avisos(para="d@ejemplo.com", gmail_cliente="c", gmail_secreto="s")

    assert a.activos is False
    assert a.faltan() == ["GMAIL_REFRESH_TOKEN"]


def test_desde_el_entorno_lee_lo_de_google(monkeypatch):
    for nombre in ("SMTP_SERVIDOR", "SMTP_USUARIO", "SMTP_CLAVE"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("AVISOS_EMAIL", "duenio@ejemplo.com")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", SECRETO)
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", PERMISO)

    avisos = Avisos.desde_entorno()

    assert avisos.metodo == "google" and avisos.activos


def test_con_google_se_verifica_el_certificado_y_no_se_siguen_redirecciones():
    https = [h for h in gmail._ABRIDOR.handlers if isinstance(h, urllib.request.HTTPSHandler)]
    assert https and _verifica(https[0]._context)

    redirecciones = [h for h in gmail._ABRIDOR.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert redirecciones and all(isinstance(h, gmail._SinRedirecciones) for h in redirecciones)
    with pytest.raises(gmail.ErrorDeGoogle):
        gmail._SinRedirecciones().redirect_request(None, None, 302, "Found", {}, "https://otro.ejemplo.com/")


def test_probar_sin_mandar_toma_la_queja_por_el_mail_vacio_como_que_anda(google):
    """Google revisa la API y el permiso antes que el mail: si se queja del mail, lo demás anda."""
    google.al_mandar = lambda: (400, {"error": {
        "code": 400,
        "message": "'raw' RFC822 payload message string or uploading message via /upload/* URL required",
        "status": "INVALID_ARGUMENT",
    }})

    gmail.probar_sin_mandar("acceso")


def test_probar_sin_mandar_avisa_si_la_api_no_esta_habilitada(google):
    google.al_mandar = lambda: (403, {"error": {
        "code": 403, "message": "Gmail API has not been used in project 123 before or it is disabled.",
        "status": "PERMISSION_DENIED",
    }})

    with pytest.raises(gmail.ErrorDeGoogle, match="Habilitala"):
        gmail.probar_sin_mandar("acceso")


@pytest.mark.parametrize(
    "codigo, cuerpo, cuando, dice",
    [
        (400, {"error": "invalid_grant"}, "renovar", "En prueba"),
        (400, {"error": "invalid_grant"}, "canjear", "se venció o ya se usó"),
        (401, {"error": "invalid_client"}, "renovar", "GMAIL_CLIENT_ID"),
        (401, {"error": "deleted_client"}, "renovar", "siga existiendo"),
        (400, {"error": "redirect_uri_mismatch"}, "canjear", "App de escritorio"),
        (403, {"error": {"code": 403, "message": "Request had insufficient authentication scopes.",
                         "status": "PERMISSION_DENIED",
                         "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}},
         "mandar", "Enviar correo"),
        (400, {"error": {"code": 400, "message": "Invalid To header", "status": "INVALID_ARGUMENT"}},
         "mandar", "AVISOS_EMAIL"),
        (429, {}, "mandar", "Esperá"),
        (503, {}, "mandar", "de su lado"),
        (418, "esto no es JSON", "mandar", "418"),
    ],
)
def test_lo_que_contesta_google_se_explica(codigo, cuerpo, cuando, dice):
    texto = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
    assert dice in gmail.explicar(codigo, texto, cuando)


def test_lo_que_dice_google_llega_al_registro_en_una_sola_linea():
    """Un salto de línea en la respuesta no puede inventar renglones en el registro."""
    texto = json.dumps({"error": {"code": 418, "message": "uno\nERROR falso\r\notro"}})

    explicado = gmail.explicar(418, texto, "mandar")

    assert "\n" not in explicado and "\r" not in explicado
    assert "uno ERROR falso otro" in explicado

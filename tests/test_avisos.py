"""Pruebas de los avisos por mail. No mandan ningún mail de verdad.

El servidor de mail se reemplaza por uno de mentira que anota qué se le
pidió: con qué puerto, si se cifró, con qué cuenta y qué mensaje.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agente.avisos as avisos_mod  # noqa: E402
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
    for nombre in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
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
    """Google muestra la contraseña de aplicación en bloques de cuatro."""
    assert Avisos(clave="abcd efgh ijkl mnop").clave == "abcdefghijklmnop"

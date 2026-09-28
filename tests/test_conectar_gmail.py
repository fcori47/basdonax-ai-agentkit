"""Pruebas de conectar_gmail.py. No salen a internet ni abren el navegador.

Google se reemplaza por uno de mentira, y el navegador por un hilo que
vuelve al servidor local con el código, como haría el navegador de verdad
después de que la persona acepta el permiso.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _cargar_el_script():
    especificacion = importlib.util.spec_from_file_location("conectar_gmail_en_prueba", RAIZ / "conectar_gmail.py")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


cg = _cargar_el_script()

CLIENTE = "123-abc.apps.googleusercontent.com"
SECRETO = "secreto-del-cliente-de-mentira"
PERMISO = "permiso-duradero-de-mentira"
CODIGO = "codigo-que-trae-el-navegador"


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
    """Canjea el código por el permiso y contesta la prueba sin mandar."""

    def __init__(self):
        self.pedidos: list[urllib.request.Request] = []
        self.canje = {
            "access_token": "acceso-de-mentira",
            "expires_in": 3599,
            "refresh_token": PERMISO,
            "scope": cg.gmail.PERMISO_PARA_MANDAR,
            "token_type": "Bearer",
        }
        # Lo normal: la API anda y se queja del mail vacío (no se manda nada).
        self.al_mandar = (400, {"error": {
            "code": 400,
            "message": "'raw' RFC822 payload message string or uploading message via /upload/* URL required",
            "status": "INVALID_ARGUMENT",
        }})

    def open(self, pedido, timeout=None):
        self.pedidos.append(pedido)
        if pedido.full_url == cg.gmail.URL_DE_PERMISOS:
            codigo, datos = 200, self.canje
        elif pedido.full_url == cg.gmail.URL_PARA_MANDAR:
            codigo, datos = self.al_mandar
        else:
            raise AssertionError(f"pedido a una dirección que no es de Google: {pedido.full_url}")
        cuerpo = json.dumps(datos).encode()
        if codigo >= 400:
            raise urllib.error.HTTPError(pedido.full_url, codigo, "error", {}, io.BytesIO(cuerpo))
        return RespuestaFalsa(cuerpo)


def navegador(estado=None, error=None, vuelve=True):
    """Hace de navegador: agarra la dirección que abrió el script y vuelve con el código."""
    abiertas: list[str] = []

    def abrir(direccion):
        abiertas.append(direccion)
        if not vuelve:
            return True
        consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(direccion).query)
        datos = {"state": consulta["state"][0] if estado is None else estado}
        if error:
            datos["error"] = error
        else:
            datos["code"] = CODIGO
        destino = consulta["redirect_uri"][0] + "/?" + urllib.parse.urlencode(datos)

        def volver():
            # Sin proxies: la vuelta es a esta misma computadora.
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(destino, timeout=10).read()

        threading.Thread(target=volver, daemon=True).start()
        return True

    abrir.abiertas = abiertas
    return abrir


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Una carpeta con el JSON de escritorio, un .env y Google de mentira."""
    json_del_cliente = tmp_path / f"client_secret_{CLIENTE}.json"
    json_del_cliente.write_text(json.dumps({"installed": {
        "client_id": CLIENTE,
        "client_secret": SECRETO,
        "redirect_uris": ["http://localhost"],
    }}), encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(
        "# mi configuración\nPROVEEDOR=claude\nAVISOS_EMAIL=duenio@ejemplo.com\n"
        "GMAIL_CLIENT_ID=\nGMAIL_CLIENT_SECRET=\nGMAIL_REFRESH_TOKEN=\nOTRA=cosa\n",
        encoding="utf-8",
    )
    google = GoogleFalso()
    monkeypatch.setattr(cg.gmail, "_ABRIDOR", google)
    monkeypatch.setattr(cg, "LUGARES_DEL_JSON", [tmp_path])
    return json_del_cliente, env, google


def test_conecta_y_guarda_en_el_env_sin_mostrar_las_claves(entorno, monkeypatch, capsys):
    json_del_cliente, env, google = entorno
    monkeypatch.setattr(cg.webbrowser, "open", navegador())

    assert cg.conectar(str(json_del_cliente), archivo_env=env) == 0

    texto = env.read_text(encoding="utf-8")
    assert texto == (
        "# mi configuración\nPROVEEDOR=claude\nAVISOS_EMAIL=duenio@ejemplo.com\n"
        f"GMAIL_CLIENT_ID={CLIENTE}\nGMAIL_CLIENT_SECRET={SECRETO}\n"
        f"GMAIL_REFRESH_TOKEN={PERMISO}\nOTRA=cosa\n"
    ), "cada una en su línea, y el resto del archivo como estaba"

    salida = capsys.readouterr()
    for secreto in (SECRETO, PERMISO, CODIGO):
        assert secreto not in salida.out + salida.err, "ni las claves ni el código se muestran"


def test_pide_solo_el_permiso_de_mandar_con_pkce(entorno, monkeypatch):
    json_del_cliente, env, google = entorno
    abrir = navegador()
    monkeypatch.setattr(cg.webbrowser, "open", abrir)

    cg.conectar(str(json_del_cliente), archivo_env=env)

    pedido = urllib.parse.parse_qs(urllib.parse.urlsplit(abrir.abiertas[0]).query)
    assert pedido["scope"] == [cg.gmail.PERMISO_PARA_MANDAR], "un solo permiso: mandar"
    assert pedido["access_type"] == ["offline"] and pedido["prompt"] == ["consent"]
    assert pedido["redirect_uri"][0].startswith("http://127.0.0.1:"), "vuelve a esta computadora y nada más"
    assert pedido["code_challenge_method"] == ["S256"]

    canje = urllib.parse.parse_qs(google.pedidos[0].data.decode())
    verificador = canje["code_verifier"][0]
    resumen = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    assert resumen == pedido["code_challenge"][0], "el código solo lo canjea quien tiene el verificador"
    assert canje["code"] == [CODIGO]
    assert canje["redirect_uri"] == pedido["redirect_uri"]


def test_una_vuelta_que_no_es_de_este_pedido_se_ignora(entorno, monkeypatch, capsys):
    """Ni se usa ni corta la espera: otra página no puede meter su código ni frenar el trámite."""
    json_del_cliente, env, google = entorno
    antes = env.read_text(encoding="utf-8")
    monkeypatch.setattr(cg.webbrowser, "open", navegador(estado="otro-pedido"))
    monkeypatch.setattr(cg, "ESPERA_DEL_NAVEGADOR", 2)

    with pytest.raises(cg.ErrorDeConexion, match="Pasó el tiempo"):
        cg.conectar(str(json_del_cliente), archivo_env=env)

    assert google.pedidos == [], "no se canjeó nada"
    assert env.read_text(encoding="utf-8") == antes
    assert "no es de este pedido" in capsys.readouterr().out


def test_si_se_cancela_lo_dice(entorno, monkeypatch):
    json_del_cliente, env, _ = entorno
    monkeypatch.setattr(cg.webbrowser, "open", navegador(error="access_denied"))

    with pytest.raises(cg.ErrorDeConexion, match="Cancelar"):
        cg.conectar(str(json_del_cliente), archivo_env=env)


def test_si_no_vuelve_del_navegador_corta(entorno, monkeypatch):
    json_del_cliente, env, _ = entorno
    monkeypatch.setattr(cg.webbrowser, "open", navegador(vuelve=False))
    monkeypatch.setattr(cg, "ESPERA_DEL_NAVEGADOR", 1)

    with pytest.raises(cg.ErrorDeConexion, match="Pasó el tiempo"):
        cg.conectar(str(json_del_cliente), archivo_env=env)


def test_sin_el_permiso_de_mandar_no_guarda_nada(entorno, monkeypatch):
    json_del_cliente, env, google = entorno
    google.canje["scope"] = "openid"
    antes = env.read_text(encoding="utf-8")
    monkeypatch.setattr(cg.webbrowser, "open", navegador())

    with pytest.raises(cg.ErrorDeConexion, match="no incluye mandar"):
        cg.conectar(str(json_del_cliente), archivo_env=env)

    assert env.read_text(encoding="utf-8") == antes


def test_avisa_si_la_app_quedo_en_prueba(entorno, monkeypatch, capsys):
    """«En prueba», Google da un permiso de 7 días: el día 8 los avisos dejan de salir callados."""
    json_del_cliente, env, google = entorno
    google.canje["refresh_token_expires_in"] = 604799
    monkeypatch.setattr(cg.webbrowser, "open", navegador())

    assert cg.conectar(str(json_del_cliente), archivo_env=env) == 1

    salida = capsys.readouterr().out
    assert "7 días" in salida and "Publicar app" in salida


def test_avisa_si_falta_habilitar_la_gmail_api(entorno, monkeypatch, capsys):
    json_del_cliente, env, google = entorno
    google.al_mandar = (403, {"error": {
        "code": 403, "message": "Gmail API has not been used in project 123 before or it is disabled.",
        "status": "PERMISSION_DENIED",
    }})
    monkeypatch.setattr(cg.webbrowser, "open", navegador())

    assert cg.conectar(str(json_del_cliente), archivo_env=env) == 1

    assert "Habilitala" in capsys.readouterr().out
    assert f"GMAIL_REFRESH_TOKEN={PERMISO}" in env.read_text(encoding="utf-8"), (
        "el permiso está bien: queda guardado, falta habilitar la API"
    )


def test_sin_json_usa_el_cliente_que_ya_esta_en_el_env(entorno, monkeypatch, capsys):
    """Para cuando el permiso se venció: se conecta de nuevo sin buscar el JSON."""
    json_del_cliente, env, google = entorno
    json_del_cliente.unlink()
    env.write_text(f"AVISOS_EMAIL=duenio@ejemplo.com\nGMAIL_CLIENT_ID={CLIENTE}\n"
                   f"GMAIL_CLIENT_SECRET={SECRETO}\nGMAIL_REFRESH_TOKEN=vencido\n", encoding="utf-8")
    monkeypatch.setattr(cg.webbrowser, "open", navegador())

    assert cg.conectar(None, archivo_env=env) == 0

    assert "ya está en el .env" in capsys.readouterr().out
    assert f"GMAIL_REFRESH_TOKEN={PERMISO}" in env.read_text(encoding="utf-8")


def test_sin_json_ni_cliente_explica_de_donde_sale(entorno, monkeypatch):
    json_del_cliente, env, _ = entorno
    json_del_cliente.unlink()

    with pytest.raises(cg.ErrorDeConexion, match="App de escritorio"):
        cg.conectar(None, archivo_env=env)


def test_rechaza_el_cliente_web(tmp_path):
    """Un cliente «Aplicación web» no acepta la vuelta a 127.0.0.1."""
    ruta = tmp_path / "client_secret_web.json"
    ruta.write_text(json.dumps({"web": {"client_id": CLIENTE, "client_secret": SECRETO}}), encoding="utf-8")

    with pytest.raises(cg.ErrorDeConexion, match="App de escritorio"):
        cg.leer_el_cliente(ruta)


def test_guardar_agrega_lo_que_falta_y_saca_las_lineas_repetidas(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nGMAIL_CLIENT_ID=viejo\n# comentario\nGMAIL_CLIENT_ID=otro-viejo\n", encoding="utf-8")

    cg.guardar_en_env(env, {"GMAIL_CLIENT_ID": "nuevo", "GMAIL_REFRESH_TOKEN": "p"})

    assert env.read_text(encoding="utf-8") == (
        "A=1\nGMAIL_CLIENT_ID=nuevo\n# comentario\n\n"
        "# Avisos por Google: los dejó conectar_gmail.py\nGMAIL_REFRESH_TOKEN=p\n"
    )


def test_un_valor_raro_no_se_escribe_en_el_env(tmp_path):
    """Un salto de línea adentro de un valor inventaría otra variable."""
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")

    with pytest.raises(cg.ErrorDeConexion, match="caracteres raros"):
        cg.guardar_en_env(env, {"GMAIL_REFRESH_TOKEN": "algo\nMODO=test"})

    assert env.read_text(encoding="utf-8") == "A=1\n"


def test_el_servidor_local_solo_escucha_en_esta_computadora():
    with cg._Servidor("estado") as servidor:
        assert servidor.server_address[0] == "127.0.0.1"

"""Prueba scripts/n8n_format_chain.py y probar_format_chain.js contra un n8n de MENTIRA.

El n8n de mentira corre en un hilo y es estricto como el real: el PUT devuelve
400 si llega un campo de más o una clave de settings que no acepta, y la lista
de flujos pagina con nextCursor. No se toca ningún n8n de verdad.

    python tests/actualizador/probar_todo.py   → imprime el resultado
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

AQUI = Path(__file__).resolve().parent
SKILL = AQUI.parents[1] / ".claude" / "skills" / "actualizar-agente-whatsapp"
SCRIPT = SKILL / "scripts" / "n8n_format_chain.py"
PROBADOR = SKILL / "scripts" / "probar_format_chain.js"
V32 = (SKILL / "referencias" / "format_chain_v3_2.js").read_text(encoding="utf-8")
V4 = (SKILL / "referencias" / "format_chain_v4.js").read_text(encoding="utf-8")

CLAVE = "clave-de-prueba-QUE-NO-SE-IMPRIME-9f8e7d"
SIN_VENTANA = 0x08000000 if os.name == "nt" else 0

PUT_PERMITIDOS = {"name", "nodes", "connections", "settings"}
SETTINGS_PERMITIDOS = {
    "executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveExecutionProgress",
    "saveManualExecutions", "executionTimeout", "errorWorkflow", "timezone", "callerPolicy",
}


# ---------------------------------------------------------------------------
# El n8n de mentira
# ---------------------------------------------------------------------------


def nodo(nombre, tipo, codigo=None):
    n = {"id": nombre.lower().replace(" ", "-"), "name": nombre, "type": tipo, "typeVersion": 2,
         "position": [0, 0], "parameters": {}}
    if codigo is not None:
        n["parameters"]["jsCode"] = codigo
    return n


def flujo(id_, nombre, activo, nodos):
    conexiones = {}
    for a, b in zip(nodos, nodos[1:]):
        conexiones[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    return {
        "id": id_, "name": nombre, "active": activo, "nodes": nodos, "connections": conexiones,
        # Dos claves que el PUT NO acepta: si el script no las filtra, el n8n de mentira da 400.
        "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "binaryMode": "separate",
                     "availableInMCP": False},
        "staticData": None, "tags": [{"id": "1", "name": "whatsapp"}], "pinData": {},
        "versionId": "v-1", "createdAt": "2026-09-01T10:00:00.000Z", "updatedAt": "2026-09-01T10:00:00.000Z",
    }


TOCADA = V32.replace(
    "raw = String(raw || '')",
    "// Filtro propio: saca lo que quedó entre corchetes\nraw = String(raw || '').replace(/\\[[^\\]]{1,50}\\]/g, '')",
)
assert TOCADA != V32
V4_HUMANO_5 = V4.replace("const MAXIMO_DE_MENSAJES = 3;", "const MAXIMO_DE_MENSAJES = 5;")

FLUJOS_INICIALES = {
    "A1": flujo("A1", "Agente WhatsApp", True, [
        nodo("Webhook", "n8n-nodes-base.webhook"), nodo("Input Agente", "n8n-nodes-base.set"),
        nodo("AI Agent", "@n8n/n8n-nodes-langchain.agent"),
        # La v3.2 tal cual, pero con saltos de Windows: tiene que reconocerse igual.
        nodo("Format Chain", "n8n-nodes-base.code", V32.replace("\n", "\r\n")),
        nodo("Split Out", "n8n-nodes-base.splitOut")]),
    "B2": flujo("B2", "Agente paralelo", True, [
        nodo("Webhook", "n8n-nodes-base.webhook"), nodo("Format Chain", "n8n-nodes-base.code", TOCADA)]),
    "C3": flujo("C3", "Recordatorios", False, [
        nodo("Cron", "n8n-nodes-base.scheduleTrigger"),
        nodo("Armar mensaje", "n8n-nodes-base.code", "return [{ json: { hola: 1 } }];")]),
    "D4": flujo("D4", "Agente viejo", False, [
        nodo("Webhook", "n8n-nodes-base.webhook"), nodo("Format Chain1", "n8n-nodes-base.code", V4_HUMANO_5)]),
    "E5": flujo("E5", "Agente con nombre cambiado", False, [
        nodo("Webhook", "n8n-nodes-base.webhook"), nodo("Formatear respuesta", "n8n-nodes-base.code", V32)]),
}


class N8nDeMentira:
    def __init__(self, lista_sin_nodos=False, publicar_falla=False, redirigir_a=None,
                 cursor_repetido=False):
        self.redirigir_a = redirigir_a
        self.cursor_repetido = cursor_repetido
        self.listados = 0
        self.flujos = copy.deepcopy(FLUJOS_INICIALES)
        self.puts: list[dict] = []
        self.publicados: list[str] = []
        self.lista_sin_nodos = lista_sin_nodos
        self.publicar_falla = publicar_falla
        self.cuerpos_no_ascii = 0
        mentira = self

        class Atender(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self, codigo, datos):
                cuerpo = json.dumps(datos).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def _autorizado(self):
                if self.headers.get("X-N8N-API-KEY") != CLAVE:
                    self._responder(401, {"message": "unauthorized"})
                    return False
                return True

            def do_GET(self):
                if not self._autorizado():
                    return
                u = urlparse(self.path)
                if u.path == "/api/v1/workflows" and mentira.redirigir_a:
                    self.send_response(302)
                    self.send_header("Location", mentira.redirigir_a + "/api/v1/workflows")
                    self.end_headers()
                    return
                if u.path == "/api/v1/workflows":
                    mentira.listados += 1
                    ids = sorted(mentira.flujos)
                    inicio = int((parse_qs(u.query).get("cursor") or ["0"])[0])
                    pagina = ids[inicio:inicio + 2]  # de a 2, para obligar a seguir el cursor
                    datos = [copy.deepcopy(mentira.flujos[i]) for i in pagina]
                    if mentira.lista_sin_nodos:
                        for d in datos:
                            d.pop("nodes", None)
                            d.pop("connections", None)
                    siguiente = str(inicio + 2) if inicio + 2 < len(ids) else None
                    if mentira.cursor_repetido:
                        siguiente = "0"  # un servidor que repite el cursor para siempre
                    return self._responder(200, {"data": datos, "nextCursor": siguiente})
                m = re.fullmatch(r"/api/v1/workflows/(\w+)", u.path)
                if m and m.group(1) in mentira.flujos:
                    return self._responder(200, mentira.flujos[m.group(1)])
                return self._responder(404, {"message": "Not Found"})

            def do_POST(self):
                if not self._autorizado():
                    return
                m = re.fullmatch(r"/api/v1/workflows/(\w+)/activate", urlparse(self.path).path)
                if not m or m.group(1) not in mentira.flujos:
                    return self._responder(404, {"message": "Not Found"})
                if mentira.publicar_falla:
                    return self._responder(400, {"message": "Workflow could not be activated"})
                mentira.publicados.append(m.group(1))
                mentira.flujos[m.group(1)]["active"] = True
                return self._responder(200, mentira.flujos[m.group(1)])

            def do_PUT(self):
                if not self._autorizado():
                    return
                crudo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    crudo.decode("ascii")
                except UnicodeDecodeError:
                    mentira.cuerpos_no_ascii += 1
                datos = json.loads(crudo)
                m = re.fullmatch(r"/api/v1/workflows/(\w+)", urlparse(self.path).path)
                if not m or m.group(1) not in mentira.flujos:
                    return self._responder(404, {"message": "Not Found"})
                sobran = set(datos) - PUT_PERMITIDOS
                if sobran:
                    return self._responder(400, {"message": "request/body must NOT have additional properties"})
                if PUT_PERMITIDOS - set(datos):
                    return self._responder(400, {"message": "request/body must have required properties"})
                if set(datos["settings"]) - SETTINGS_PERMITIDOS:
                    return self._responder(400, {"message": "request/body/settings must NOT have additional properties"})
                mentira.puts.append({"id": m.group(1), "claves": sorted(datos)})
                f = mentira.flujos[m.group(1)]
                for campo in PUT_PERMITIDOS:
                    f[campo] = datos[campo]
                f["updatedAt"] = "2026-09-28T12:00:00.000Z"
                return self._responder(200, f)

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Atender)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def cerrar(self):
        self.servidor.shutdown()

    def codigo(self, id_, nombre_nodo):
        return next(n for n in self.flujos[id_]["nodes"] if n["name"] == nombre_nodo)["parameters"]["jsCode"]


# ---------------------------------------------------------------------------
# Las pruebas
# ---------------------------------------------------------------------------

lineas: list[str] = []
fallas = 0
todo_lo_impreso: list[str] = []


def anotar(texto=""):
    lineas.append(texto)
    print(texto)


def chequear(nombre, condicion, detalle=""):
    global fallas
    if not condicion:
        fallas += 1
    anotar(f"  {'✓' if condicion else '✗'} {nombre}" + (f"  → {detalle}" if detalle and not condicion else ""))


DIR_TRABAJO: Path | None = None


def correr(args, url, clave=CLAVE, cwd=None):
    cwd = cwd or DIR_TRABAJO
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    entorno.pop("N8N_API_URL", None)
    entorno.pop("N8N_API_KEY", None)
    if url is not None:
        entorno["N8N_API_URL"] = url
    if clave is not None:
        entorno["N8N_API_KEY"] = clave
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                       encoding="utf-8", env=entorno, cwd=cwd, creationflags=SIN_VENTANA)
    salida = r.stdout + r.stderr
    todo_lo_impreso.append(salida)
    return r.returncode, salida


def normal(c):
    return re.sub(r"\s+", " ", c.replace("\r\n", "\n")).strip()


def con_eleccion(forma, maximo):
    return (V4.replace("const FORMA_DE_RESPONDER = 'humano';", f"const FORMA_DE_RESPONDER = '{forma}';")
              .replace("const MAXIMO_DE_MENSAJES = 3;", f"const MAXIMO_DE_MENSAJES = {maximo};"))


def main():
    global DIR_TRABAJO
    tmp = Path(tempfile.mkdtemp(prefix="prueba-skill-"))
    DIR_TRABAJO = tmp / "trabajo"
    DIR_TRABAJO.mkdir()
    respaldos = tmp / "respaldos"
    n8n = N8nDeMentira()
    try:
        anotar("== El n8n de mentira es estricto como el real")
        pedido = urllib.request.Request(
            n8n.url + "/api/v1/workflows/A1", method="PUT",
            data=json.dumps({"name": "x", "nodes": [], "connections": {}, "settings": {}, "active": True}).encode(),
            headers={"X-N8N-API-KEY": CLAVE, "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(pedido)
            codigo = 200
        except urllib.error.HTTPError as e:
            codigo = e.code
        chequear("un PUT con un campo de más («active») da 400", codigo == 400, str(codigo))

        anotar("\n== --help")
        cod, sal = correr(["--help"], n8n.url)
        chequear("responde y está en español", cod == 0 and "Busca, respalda y actualiza" in sal, sal[:200])

        anotar("\n== buscar (5 flujos, de a 2 por página)")
        cod, sal = correr(["buscar"], n8n.url)
        anotar("    " + sal.strip().replace("\n", "\n    "))
        chequear("sale bien", cod == 0, sal)
        chequear("encuentra los 4 nodos Format Chain (3 páginas)", "Encontré 4 nodo(s)" in sal, sal)
        chequear("no lista el flujo sin Format Chain", "Recordatorios" not in sal)
        cod, sal = correr(["buscar", "--json"], n8n.url)
        lista = json.loads(sal)
        estados = {(e["flujo"], e["nodo"]): e["estado"] for e in lista}
        chequear("A1: la v3.2 genérica (con saltos de Windows)", estados.get(("A1", "Format Chain")) == "v3.2", estados)
        chequear("B2: tocada", estados.get(("B2", "Format Chain")) == "tocada", estados)
        chequear("D4: ya es la v4", estados.get(("D4", "Format Chain1")) == "v4", estados)
        chequear("E5: reconocida por la primera línea aunque se llame distinto",
                 estados.get(("E5", "Formatear respuesta")) == "v3.2", estados)

        anotar("\n== buscar cuando la lista viene sin los nodos")
        n8n_b = N8nDeMentira(lista_sin_nodos=True)
        cod, sal = correr(["buscar"], n8n_b.url)
        chequear("pide cada flujo y encuentra los 4 igual", cod == 0 and "Encontré 4 nodo(s)" in sal, sal)
        n8n_b.cerrar()

        anotar("\n== respaldar")
        cod, sal = correr(["respaldar", "--flujo", "A1", "--carpeta", str(respaldos)], n8n.url)
        archivos = list(respaldos.glob("A1-*.json"))
        chequear("guarda el .json con fecha", cod == 0 and len(archivos) == 1, sal)
        if archivos:
            chequear("el respaldo es el flujo entero, idéntico",
                     json.loads(archivos[0].read_text(encoding="utf-8")) == n8n.flujos["A1"])

        anotar("\n== aplicar sobre la v3.2 genérica (humano, máximo 3)")
        antes = copy.deepcopy(n8n.flujos["A1"])
        cod, sal = correr(["aplicar", "--flujo", "A1", "--forma", "humano", "--maximo", "3",
                           "--carpeta", str(respaldos)], n8n.url)
        anotar("    " + sal.strip().replace("\n", "\n    "))
        despues = n8n.flujos["A1"]
        chequear("sale bien", cod == 0, sal)
        chequear("el nodo quedó con la v4 y esa elección", normal(n8n.codigo("A1", "Format Chain")) == normal(con_eleccion("humano", 3)))
        chequear("los otros nodos no se tocaron",
                 [n for n in despues["nodes"] if n["name"] != "Format Chain"] ==
                 [n for n in antes["nodes"] if n["name"] != "Format Chain"])
        chequear("las conexiones no se tocaron", despues["connections"] == antes["connections"])
        chequear("sigue activo (no se prendió ni se apagó)", despues["active"] is True)
        chequear("estaba prendido: lo publicó una vez (n8n nuevos: si no, queda en borrador)",
                 n8n.publicados.count("A1") == 1, n8n.publicados)
        chequear("el PUT llevó solo los 4 campos", n8n.puts and n8n.puts[-1]["claves"] == sorted(PUT_PERMITIDOS), n8n.puts)
        chequear("settings filtrado (sin binaryMode ni availableInMCP)",
                 set(despues["settings"]) <= SETTINGS_PERMITIDOS and despues["settings"].get("executionOrder") == "v1",
                 despues["settings"])
        chequear("respaldó antes de cambiar", len(list(respaldos.glob("A1-*.json"))) >= 2)

        anotar("\n== verificar")
        cod, sal = correr(["verificar", "--flujo", "A1"], n8n.url)
        chequear("dice que es la v4, humano, máximo 3", cod == 0 and "forma humano, máximo 3" in sal, sal)

        anotar("\n== aplicar sobre una Format Chain tocada")
        puts_antes = len(n8n.puts)
        cod, sal = correr(["aplicar", "--flujo", "B2", "--forma", "un_mensaje", "--carpeta", str(respaldos)], n8n.url)
        anotar("    " + sal.strip().replace("\n", "\n    "))
        chequear("se niega (código 2)", cod == 2, sal)
        chequear("no mandó ningún PUT", len(n8n.puts) == puts_antes)
        chequear("el código quedó igual", n8n.codigo("B2", "Format Chain") == TOCADA)

        anotar("\n== subir un código propio (la tocada con la elección agregada)")
        propia = tmp / "format_chain_propia.js"
        propia.write_text("// Filtro propio conservado\n" + con_eleccion("un_mensaje", 3), encoding="utf-8")
        cod, sal = correr(["subir", "--flujo", "B2", "--archivo", str(propia), "--carpeta", str(respaldos)], n8n.url)
        chequear("sale bien", cod == 0, sal)
        chequear("el nodo tiene exactamente ese código", normal(n8n.codigo("B2", "Format Chain")) == normal(propia.read_text(encoding="utf-8")))

        anotar("\n== restaurar el respaldo de B2")
        respaldo_b2 = sorted(respaldos.glob("B2-*.json"))[0]
        cod, sal = correr(["restaurar", "--flujo", "B2", "--archivo", str(respaldo_b2),
                           "--carpeta", str(respaldos)], n8n.url)
        chequear("vuelve a como estaba", cod == 0 and n8n.codigo("B2", "Format Chain") == TOCADA, sal)

        anotar("\n== aplicar --forzar sobre la tocada")
        cod, sal = correr(["aplicar", "--flujo", "B2", "--forma", "un_mensaje", "--forzar", "--carpeta", str(respaldos)], n8n.url)
        chequear("la pisa con la v4 (y respaldó antes)",
                 cod == 0 and normal(n8n.codigo("B2", "Format Chain")) == normal(con_eleccion("un_mensaje", 3)), sal)

        anotar("\n== aplicar sobre una que ya es v4 (cambiar la elección)")
        cod, sal = correr(["aplicar", "--flujo", "D4", "--forma", "un_mensaje", "--nodo", "Format Chain1",
                           "--carpeta", str(respaldos)], n8n.url)
        chequear("cambia la elección", cod == 0 and "const FORMA_DE_RESPONDER = 'un_mensaje';" in n8n.codigo("D4", "Format Chain1"), sal)
        chequear("sigue apagado", n8n.flujos["D4"]["active"] is False)
        chequear("a un flujo apagado no lo publica", "D4" not in n8n.publicados, n8n.publicados)

        anotar("\n== si publicar falla")
        n8n_c = N8nDeMentira(publicar_falla=True)
        cod, sal = correr(["aplicar", "--flujo", "A1", "--forma", "humano", "--carpeta", str(respaldos)], n8n_c.url)
        chequear("avisa que quedó guardado y hay que tocar «Publish»",
                 cod == 1 and "quedó guardado" in sal and "Publish" in sal, sal)
        n8n_c.cerrar()

        anotar("\n== errores que tiene que explicar bien")
        cod, sal = correr(["aplicar", "--flujo", "A1", "--forma", "humano", "--maximo", "7"], n8n.url)
        chequear("máximo 7 → error claro", cod == 1 and "de 1 a 5" in sal, sal)
        cod, sal = correr(["verificar", "--flujo", "C3"], n8n.url)
        chequear("flujo sin Format Chain → lo dice", cod == 1 and "no tiene un nodo Format Chain" in sal, sal)
        cod, sal = correr(["buscar"], n8n.url, clave="otra-clave-equivocada")
        chequear("clave equivocada → 401 explicado", cod == 1 and "rechazó la clave (401)" in sal, sal)
        cod, sal = correr(["buscar"], "http://127.0.0.1:9", clave=CLAVE)
        chequear("n8n que no contesta → revisá N8N_API_URL", cod == 1 and "N8N_API_URL" in sal, sal)
        cod, sal = correr(["buscar"], None, clave=None)
        chequear("sin entorno → dice qué falta", cod == 1 and "Falta la dirección" in sal, sal)


        anotar("\n== los arreglos de la auditoría")
        # Dos cambios seguidos, en el mismo segundo: el primer respaldo (el que
        # tiene la v3.2 original) no puede perderse.
        n8n_r = N8nDeMentira()
        seguidos = tmp / "seguidos"
        correr(["aplicar", "--flujo", "A1", "--forma", "humano", "--carpeta", str(seguidos)], n8n_r.url)
        correr(["aplicar", "--flujo", "A1", "--forma", "un_mensaje", "--carpeta", str(seguidos)], n8n_r.url)
        hechos = sorted(seguidos.glob("A1-*.json"))
        chequear("dos cambios seguidos dejan dos respaldos", len(hechos) == 2, [h.name for h in hechos])
        if hechos:
            primero = json.loads(hechos[0].read_text(encoding="utf-8"))
            codigo_primero = next(n for n in primero["nodes"] if n["name"] == "Format Chain")["parameters"]["jsCode"]
            chequear("el primero tiene la v3.2 original", normal(codigo_primero) == normal(V32))

        # restaurar: el flujo lo dice la persona, no el archivo
        puts_antes = len(n8n_r.puts)
        cod, sal = correr(["restaurar", "--flujo", "B2", "--archivo", str(hechos[0]), "--carpeta", str(seguidos)],
                          n8n_r.url)
        chequear("un respaldo de A1 no se restaura sobre B2", cod == 1 and "No lo restauro" in sal, sal)
        chequear("y no mandó nada", len(n8n_r.puts) == puts_antes)
        antes_de_restaurar = len(list(seguidos.glob("A1-*.json")))
        cod, sal = correr(["restaurar", "--flujo", "A1", "--archivo", str(hechos[0]), "--carpeta", str(seguidos)],
                          n8n_r.url)
        chequear("restaurar respalda lo que había antes de pisarlo",
                 cod == 0 and len(list(seguidos.glob("A1-*.json"))) == antes_de_restaurar + 1, sal)
        n8n_r.cerrar()

        # La clave solo viaja cifrada, y no se va con una redirección
        cod, sal = correr(["buscar"], "http://n8n.ejemplo.com")
        chequear("http:// que no es esta máquina → se niega", cod == 1 and "https://" in sal, sal)
        atrapador = N8nDeMentira()
        atrapador_claves: list = []
        original = atrapador.servidor.RequestHandlerClass.do_GET

        def espiar(self):
            atrapador_claves.append(self.headers.get("X-N8N-API-KEY"))
            return original(self)

        atrapador.servidor.RequestHandlerClass.do_GET = espiar
        redirige = N8nDeMentira(redirigir_a=atrapador.url)
        cod, sal = correr(["buscar"], redirige.url)
        chequear("una redirección no se sigue", cod == 1 and "redirección" in sal, sal)
        chequear("y la clave no le llegó al otro servidor", not atrapador_claves, atrapador_claves)
        redirige.cerrar()
        atrapador.cerrar()

        # Un cursor que se repite no cuelga el script
        repite = N8nDeMentira(cursor_repetido=True)
        cod, sal = correr(["buscar"], repite.url)
        chequear("un cursor repetido no lo cuelga", cod == 0 and repite.listados <= 3, (cod, repite.listados))
        repite.cerrar()

        # Un id con «../» no llega ni a la API ni al nombre de un archivo
        cod, sal = correr(["respaldar", "--flujo", "../../etc", "--carpeta", str(respaldos)], n8n.url)
        chequear("un id con ../ se rechaza", cod == 1 and "no es un id" in sal, sal)

        # La clave la lee el script solo: del archivo o del .mcp.json
        con_archivo = tmp / "con_archivo"
        con_archivo.mkdir()
        (con_archivo / "n8n-acceso.env").write_text(f"N8N_API_URL={n8n.url}\nN8N_API_KEY={CLAVE}\n", encoding="utf-8")
        cod, sal = correr(["buscar"], None, clave=None, cwd=con_archivo)
        chequear("lee la conexión de n8n-acceso.env", cod == 0 and "Encontré" in sal, sal)
        con_mcp = tmp / "con_mcp"
        con_mcp.mkdir()
        (con_mcp / ".mcp.json").write_text(json.dumps({"mcpServers": {"n8n": {
            "command": "npx", "env": {"N8N_API_URL": n8n.url, "N8N_API_KEY": CLAVE}}}}), encoding="utf-8")
        cod, sal = correr(["buscar"], None, clave=None, cwd=con_mcp)
        chequear("lee la conexión del .mcp.json", cod == 0 and "Encontré" in sal, sal)

        # Reconocer: la v3.2 con el campo original y la v4 desfigurada por una copia
        spec = importlib.util.spec_from_file_location("n8n_format_chain", SCRIPT)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        original_v32 = V32.replace("mensaje_para_cliente", "mensaje_para_mi_negocio")
        chequear("la v3.2 con otro nombre de campo mensaje_para_… sigue siendo la v3.2",
                 modulo.version(original_v32)["estado"] == "v3.2")
        desfigurada = V4.encode("utf-8").decode("cp1252", errors="replace")
        chequear("la v4 copiada sin UTF-8 (comentarios desfigurados) sigue siendo la v4",
                 modulo.version(desfigurada)["estado"] == "v4", modulo.version(desfigurada))

        anotar("\n== seguridad")
        chequear("la clave no aparece en NADA de lo que imprimió el script",
                 all(CLAVE not in s for s in todo_lo_impreso))
        chequear("todos los cuerpos de los PUT viajaron en ASCII", n8n.cuerpos_no_ascii == 0, n8n.cuerpos_no_ascii)

        anotar("\n== probar_format_chain.js")
        node = shutil.which("node")
        if not node:
            anotar("  (no hay node: se saltea)")
        else:
            def probar_js(codigo, nombre):
                archivo = tmp / nombre
                archivo.write_text(codigo, encoding="utf-8")
                r = subprocess.run([node, str(PROBADOR), str(archivo)], capture_output=True, text=True,
                                   encoding="utf-8", creationflags=SIN_VENTANA)
                return r.returncode, r.stdout + r.stderr

            cod, sal = probar_js(con_eleccion("humano", 3), "v4_humano_3.js")
            anotar("    " + sal.strip().replace("\n", "\n    "))
            chequear("v4 humano 3 → «Todo bien»", cod == 0 and "Todo bien" in sal, sal)
            cod, sal = probar_js(con_eleccion("un_mensaje", 3), "v4_un_mensaje.js")
            chequear("v4 un_mensaje → «Todo bien»", cod == 0 and "Todo bien" in sal, sal)
            cod, sal = probar_js(V32, "v3_2.js")
            chequear("la v3.2 (sin elección) → corre y avisa que no tiene elección", cod == 0 and "sin elección" in sal, sal)
            cod, sal = probar_js("return [{ json: { respuesta: 'hola' } }];", "mala_forma.js")
            chequear("un código con otra salida → lo rechaza", cod == 1 and "falta json.response" in sal, sal)
            cod, sal = probar_js("const x = ;", "roto.js")
            chequear("un código roto → lo rechaza", cod == 1 and "explotó" in sal, sal)
            marca = tmp / "NO-DEBERIA-EXISTIR.txt"
            malicioso = f"require('fs').writeFileSync({json.dumps(str(marca))}, 'x');\n" + V4
            cod, sal = probar_js(malicioso, "malicioso.js")
            chequear("un código que quiere escribir en tu compu queda encerrado",
                     cod == 1 and not marca.exists(), sal[-300:])
    finally:
        n8n.cerrar()
        shutil.rmtree(tmp, ignore_errors=True)

    anotar(f"\n{'TODO BIEN' if not fallas else f'{fallas} FALLA(S)'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

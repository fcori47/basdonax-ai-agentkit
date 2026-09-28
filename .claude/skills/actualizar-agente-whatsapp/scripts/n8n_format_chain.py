"""Busca, respalda y actualiza el nodo «Format Chain» de un agente de WhatsApp en n8n.

Usa la API de n8n. Python estándar: no hay que instalar nada.

La conexión la lee el script solo, nunca de un argumento (los argumentos
quedan en el historial de la terminal). La busca en este orden:

    1. el entorno: N8N_API_URL y N8N_API_KEY
    2. el archivo n8n-acceso.env de esta carpeta (lo escribe la persona, a
       mano, con esas dos líneas; está en el .gitignore)
    3. el .mcp.json de esta carpeta, si tiene un MCP de n8n con esas variables

La clave no se imprime nunca, ni cuando algo falla. Y solo viaja cifrada:
la dirección tiene que ser https:// (salvo localhost), y el script no sigue
redirecciones, para no mandarle la clave a otro lado.

Comandos:

    buscar                                   los flujos que tienen un nodo «Format Chain» y en qué versión está
    respaldar --flujo ID                     guarda el flujo entero en un .json (con fecha)
    aplicar   --flujo ID --forma F --maximo N   pone la Format Chain v4 con esa elección (respalda antes)
    subir     --flujo ID --archivo codigo.js    sube un código propio al nodo (respalda antes)
    restaurar --flujo ID --archivo respaldo.json   vuelve ESE flujo a como estaba en el respaldo
    verificar --flujo ID                     muestra cómo quedó el nodo

Lo que la API de n8n no perdona, y este script respeta:

  · El PUT acepta SOLO name, nodes, connections y settings. Cualquier otro
    campo (id, active, tags, pinData…) da error 400.
  · `active` es de solo lectura: el script no prende ni apaga el flujo.
  · En settings solo entran algunas claves; las demás también dan 400.
  · Después de cada PUT se vuelve a pedir el flujo para confirmar que quedó.
  · En los n8n nuevos (con «Publish»), guardar deja un borrador: si el flujo
    estaba prendido, se publica para que el agente use el código nuevo. Un
    flujo apagado se queda apagado.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REFERENCIAS = AQUI.parent / "referencias"
V4 = REFERENCIAS / "format_chain_v4.js"
V32 = REFERENCIAS / "format_chain_v3_2.js"

FORMAS = ("humano", "un_mensaje")

# Las únicas claves de settings que acepta el PUT de la API pública de n8n.
SETTINGS_PERMITIDOS = (
    "executionOrder",
    "saveDataErrorExecution",
    "saveDataSuccessExecution",
    "saveExecutionProgress",
    "saveManualExecutions",
    "executionTimeout",
    "errorWorkflow",
    "timezone",
    "callerPolicy",
)

_LINEA_FORMA = re.compile(r"const FORMA_DE_RESPONDER = '([^']*)';")
_LINEA_MAXIMO = re.compile(r"const MAXIMO_DE_MENSAJES = ([^;]*);")

# Un id de flujo de n8n. Todo lo que viene de afuera (un argumento, un
# respaldo, la respuesta del servidor) se valida contra esto antes de ir a una
# dirección o al nombre de un archivo: un id con «../» no puede salir de la
# carpeta de respaldos ni caer en otra ruta de la API.
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Tope de páginas al listar: un servidor que repite el cursor no puede dejar
# al script dando vueltas para siempre.
PAGINAS_COMO_MUCHO = 200

ARCHIVO_DE_ACCESO = "n8n-acceso.env"
# Los respaldos van a la carpeta de la persona, FUERA del proyecto: son
# flujos enteros, con ids de credenciales, y en el proyecto de otro nadie
# garantiza que el .gitignore los deje afuera.
CARPETA_DE_RESPALDOS = Path.home() / "respaldos-n8n"
_EN_LA_MISMA_MAQUINA = {"localhost", "127.0.0.1", "::1"}


class ErrorDeN8n(Exception):
    """n8n contestó algo que no esperábamos (o no contestó)."""


def _id_valido(id_flujo) -> str:
    id_flujo = str(id_flujo or "").strip()
    if not _ID.match(id_flujo):
        raise ErrorDeN8n(f"Ese no es un id de flujo de n8n válido: {id_flujo[:80]!r}.")
    return id_flujo


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Una redirección se corta: urllib la seguiría reenviando la clave, a
    cualquier servidor y hasta sin cifrar."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ErrorDeN8n(
            f"n8n contestó con una redirección ({code}) a otra dirección. No la sigo, "
            "para no mandarle tu clave a otro lado: revisá que N8N_API_URL sea la "
            "dirección exacta de tu n8n, con https://."
        )


_ABRIDOR = urllib.request.build_opener(_SinRedirecciones)


# ---------------------------------------------------------------------------
# La conexión
# ---------------------------------------------------------------------------


class N8n:
    def __init__(self, url: str, clave: str) -> None:
        if not url:
            raise ErrorDeN8n(
                "Falta la dirección de tu n8n: poné N8N_API_URL en el entorno o en "
                f"{ARCHIVO_DE_ACCESO} (por ejemplo https://n8n.tuempresa.com)."
            )
        if not clave:
            raise ErrorDeN8n(
                f"Falta la clave de API de n8n: poné N8N_API_KEY en el entorno o en "
                f"{ARCHIVO_DE_ACCESO}. Se crea en n8n → Settings → n8n API."
            )
        url = url.strip().rstrip("/")
        # Da igual si la pasan con o sin /api/v1 al final.
        url = re.sub(r"/api/v1$", "", url)
        partes = urllib.parse.urlsplit(url)
        if partes.scheme != "https" and partes.hostname not in _EN_LA_MISMA_MAQUINA:
            raise ErrorDeN8n(
                f"La dirección de n8n tiene que empezar con https:// (dice «{partes.scheme}://»). "
                "Sin cifrar, la clave viaja a la vista de cualquiera en el medio. "
                "Solo se acepta http si n8n corre en esta misma máquina (localhost)."
            )
        self.base = url + "/api/v1"
        self._clave = clave.strip()

    def _pedir(self, metodo: str, camino: str, datos: dict | None = None) -> dict:
        cuerpo = None
        encabezados = {
            "X-N8N-API-KEY": self._clave,
            "Accept": "application/json",
            "User-Agent": "actualizar-agente-whatsapp/1.0",
        }
        if datos is not None:
            # ensure_ascii: el cuerpo viaja en ASCII puro (las tildes como á).
            # Así no depende de la codificación de la terminal ni del proxy.
            cuerpo = json.dumps(datos, ensure_ascii=True).encode("ascii")
            encabezados["Content-Type"] = "application/json"

        pedido = urllib.request.Request(
            self.base + camino, data=cuerpo, method=metodo, headers=encabezados
        )
        try:
            with _ABRIDOR.open(pedido, timeout=30) as r:
                texto = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            if e.code == 401:
                raise ErrorDeN8n(
                    "n8n rechazó la clave (401). Revisá N8N_API_KEY: puede estar "
                    "mal copiada o vencida."
                ) from None
            raise ErrorDeN8n(f"n8n devolvió {e.code} en {metodo} {camino}: {detalle}") from None
        except urllib.error.URLError as e:
            raise ErrorDeN8n(
                f"No se pudo llegar a {self.base} ({e.reason}). Revisá N8N_API_URL."
            ) from None
        return json.loads(texto) if texto else {}

    def flujos(self) -> list[dict]:
        """Todos los flujos, siguiendo las páginas (n8n las corta con nextCursor)."""
        todos: list[dict] = []
        cursor = None
        vistos: set[str] = set()
        for _ in range(PAGINAS_COMO_MUCHO):
            consulta = {"limit": "100"}
            if cursor:
                consulta["cursor"] = cursor
            respuesta = self._pedir("GET", "/workflows?" + urllib.parse.urlencode(consulta))
            pagina = respuesta.get("data") or []
            todos += pagina
            cursor = respuesta.get("nextCursor")
            # Sin cursor, con una página vacía o con un cursor repetido, se terminó.
            if not cursor or not pagina or cursor in vistos:
                return todos
            vistos.add(cursor)
        raise ErrorDeN8n(f"n8n devolvió más de {PAGINAS_COMO_MUCHO} páginas de flujos: corto acá.")

    def flujo(self, id_flujo: str) -> dict:
        id_flujo = _id_valido(id_flujo)
        return self._pedir("GET", f"/workflows/{urllib.parse.quote(id_flujo, safe='')}")

    def guardar(self, flujo: dict) -> dict:
        """PUT con los cuatro campos que acepta n8n, y nada más."""
        id_flujo = _id_valido(flujo.get("id"))
        cuerpo = {
            "name": flujo["name"],
            "nodes": flujo["nodes"],
            "connections": flujo.get("connections") or {},
            "settings": {
                k: v for k, v in (flujo.get("settings") or {}).items() if k in SETTINGS_PERMITIDOS
            },
        }
        return self._pedir("PUT", f"/workflows/{urllib.parse.quote(id_flujo, safe='')}", cuerpo)

    def publicar(self, id_flujo: str) -> dict:
        """Que el flujo que ya estaba prendido corra con lo que se acaba de guardar.

        En los n8n nuevos (los que tienen «Publish»), guardar deja un borrador y
        el flujo prendido sigue con la versión anterior hasta que se publica.
        En los anteriores no cambia nada: el flujo ya está prendido.
        """
        id_flujo = _id_valido(id_flujo)
        return self._pedir("POST", f"/workflows/{urllib.parse.quote(id_flujo, safe='')}/activate")


def _leer_acceso() -> tuple[str, str]:
    """La dirección y la clave de n8n, sin mostrarlas nunca.

    El orden: el entorno, después el archivo n8n-acceso.env que escribe la
    persona a mano, después el .mcp.json (si tiene un MCP de n8n). Así la
    clave no tiene que pasar por el chat ni por una línea de comando.
    """
    url = os.getenv("N8N_API_URL", "")
    clave = os.getenv("N8N_API_KEY", "")
    if url and clave:
        return url, clave

    archivo = Path(ARCHIVO_DE_ACCESO)
    if archivo.is_file():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, valor = (x.strip() for x in linea.split("=", 1))
            valor = valor.strip('"').strip("'")
            if nombre == "N8N_API_URL" and not url:
                url = valor
            elif nombre == "N8N_API_KEY" and not clave:
                clave = valor
        if url and clave:
            return url, clave

    mcp = Path(".mcp.json")
    if mcp.is_file():
        try:
            servidores = (json.loads(mcp.read_text(encoding="utf-8")) or {}).get("mcpServers") or {}
        except (ValueError, OSError):
            servidores = {}
        for datos in servidores.values():
            entorno = (datos or {}).get("env") or {}
            if entorno.get("N8N_API_URL") and entorno.get("N8N_API_KEY"):
                return url or entorno["N8N_API_URL"], clave or entorno["N8N_API_KEY"]

    return url, clave


def conectar() -> N8n:
    return N8n(*_leer_acceso())


# ---------------------------------------------------------------------------
# Reconocer la Format Chain
# ---------------------------------------------------------------------------


def _normalizar(codigo: str) -> str:
    """Sin diferencias de espacios ni de saltos de línea.

    También da igual el nombre del campo `mensaje_para_…` que lee la v3.2: la
    plantilla original lo traía con el nombre de un negocio, y en la referencia
    quedó genérico. Sin esto, la v3.2 de todos los que tienen la plantilla
    saldría como «tocada».
    """
    codigo = re.sub(r"mensaje_para_\w+", "mensaje_para_X", codigo or "")
    # Los comentarios no cuentan: cambiarlos (o que una copia los desfigure)
    # no hace que la Format Chain sea «otra». Solo se sacan los renglones que
    # son enteros un comentario, y lo que va después de un «;».
    lineas = [
        re.sub(r";\s*//.*$", ";", linea)
        for linea in codigo.replace("\r\n", "\n").split("\n")
        if not linea.lstrip().startswith("//")
    ]
    return re.sub(r"\s+", " ", "\n".join(lineas)).strip()


def _sin_eleccion(codigo: str) -> str:
    """El código con las dos constantes de la elección en un valor fijo."""
    codigo = _LINEA_FORMA.sub("const FORMA_DE_RESPONDER = '*';", codigo)
    return _LINEA_MAXIMO.sub("const MAXIMO_DE_MENSAJES = *;", codigo)


def es_format_chain(nodo: dict) -> bool:
    """Un nodo de código que se llama Format Chain, o que arranca como una."""
    if not str(nodo.get("type", "")).endswith(".code"):
        return False
    nombre = str(nodo.get("name", ""))
    codigo = str((nodo.get("parameters") or {}).get("jsCode", ""))
    return bool(re.search(r"format\s*chain", nombre, re.I)) or codigo.lstrip().startswith(
        "// Format Chain"
    )


def version(codigo: str) -> dict:
    """Qué Format Chain es: la v3.2 genérica, la v4 (y con qué elección) o una tocada."""
    v32 = V32.read_text(encoding="utf-8")
    v4 = V4.read_text(encoding="utf-8")

    if _normalizar(codigo) == _normalizar(v32):
        return {"estado": "v3.2", "detalle": "la v3.2 genérica, sin cambios", "se_puede_aplicar": True}

    if _normalizar(_sin_eleccion(codigo)) == _normalizar(_sin_eleccion(v4)):
        forma = _LINEA_FORMA.search(codigo)
        maximo = _LINEA_MAXIMO.search(codigo)
        return {
            "estado": "v4",
            "detalle": f"ya es la v4: forma {forma.group(1) if forma else '?'}, "
            f"máximo {maximo.group(1).strip() if maximo else '?'}",
            "se_puede_aplicar": True,
        }

    base = "basada en la v3.2" if "Format Chain v3.2" in codigo else "propia"
    return {
        "estado": "tocada",
        "detalle": f"tiene cambios propios ({base}): no se reemplaza entera",
        "se_puede_aplicar": False,
    }


def codigo_v4(forma: str, maximo: int) -> str:
    """La v4 con la elección puesta."""
    if forma not in FORMAS:
        raise ValueError(f"La forma tiene que ser {' o '.join(FORMAS)}, no '{forma}'.")
    if not 1 <= int(maximo) <= 5:
        raise ValueError(f"El máximo tiene que ir de 1 a 5, no {maximo}.")
    codigo = V4.read_text(encoding="utf-8")
    codigo = _LINEA_FORMA.sub(f"const FORMA_DE_RESPONDER = '{forma}';", codigo, count=1)
    return _LINEA_MAXIMO.sub(f"const MAXIMO_DE_MENSAJES = {int(maximo)};", codigo, count=1)


def nodos_format_chain(flujo: dict) -> list[dict]:
    return [n for n in flujo.get("nodes") or [] if es_format_chain(n)]


def _elegir_nodo(flujo: dict, nombre: str | None) -> dict:
    nodos = nodos_format_chain(flujo)
    if nombre:
        nodos = [n for n in nodos if n.get("name") == nombre]
    if not nodos:
        raise ErrorDeN8n(
            f"El flujo «{flujo.get('name')}» no tiene un nodo Format Chain"
            + (f" llamado «{nombre}»." if nombre else ".")
        )
    if len(nodos) > 1:
        nombres = ", ".join(f"«{n.get('name')}»" for n in nodos)
        raise ErrorDeN8n(f"Hay más de un nodo Format Chain ({nombres}): elegí uno con --nodo.")
    return nodos[0]


# ---------------------------------------------------------------------------
# Los comandos
# ---------------------------------------------------------------------------


def _respaldar(flujo: dict, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    id_flujo = _id_valido(flujo.get("id"))
    nombre = re.sub(r"[^a-zA-Z0-9]+", "-", str(flujo.get("name", "flujo"))).strip("-").lower()[:40]
    # Con microsegundos, y abriendo con "x" (falla si ya existe): dos cambios
    # en el mismo segundo no pueden pisar el respaldo del primero, que es el
    # único que tiene el flujo como estaba antes de todo.
    sello = _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    ruta = carpeta / f"{id_flujo}-{nombre or 'flujo'}-{sello}.json"
    with open(ruta, "x", encoding="utf-8") as archivo:
        archivo.write(json.dumps(flujo, ensure_ascii=False, indent=2))
    # El respaldo es el flujo entero, con los ids de sus credenciales: solo
    # para quien lo guardó (en Windows esto hace lo que puede, que es poco).
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    return ruta


def _poner_codigo(n8n: N8n, flujo: dict, nodo_nombre: str, codigo: str) -> dict:
    """Cambia SOLO el código de ese nodo, guarda y confirma leyendo de nuevo."""
    for nodo in flujo["nodes"]:
        if nodo.get("name") == nodo_nombre:
            nodo.setdefault("parameters", {})["jsCode"] = codigo
            break
    n8n.guardar(flujo)

    guardado = n8n.flujo(flujo["id"])
    nodo = next((n for n in guardado.get("nodes") or [] if n.get("name") == nodo_nombre), None)
    codigo_guardado = str(((nodo or {}).get("parameters") or {}).get("jsCode", ""))
    if _normalizar(codigo_guardado) != _normalizar(codigo):
        raise ErrorDeN8n(
            "n8n aceptó el cambio pero al volver a leerlo el código no es el que se mandó. "
            "No sigas: restaurá el respaldo."
        )
    if len(guardado.get("nodes") or []) != len(flujo["nodes"]):
        raise ErrorDeN8n("Cambió la cantidad de nodos del flujo. Restaurá el respaldo.")
    _publicar_si_estaba_prendido(n8n, flujo)
    return guardado


def _publicar_si_estaba_prendido(n8n: N8n, flujo: dict) -> None:
    """Solo los que estaban prendidos: un flujo apagado se queda apagado."""
    if not flujo.get("active"):
        print("El flujo estaba apagado y así queda: el cambio está guardado para cuando lo prendas.")
        return
    try:
        n8n.publicar(flujo["id"])
    except ErrorDeN8n as e:
        raise ErrorDeN8n(
            "El cambio quedó guardado, pero no se pudo publicar en el flujo prendido "
            f"({e}). Abrilo en n8n y tocá «Publish» (o apagalo y prendelo) para que "
            "el agente use el código nuevo."
        ) from None
    print("El flujo estaba prendido: quedó publicado con el cambio.")


def cmd_buscar(n8n: N8n, a) -> int:
    encontrados = []
    for resumen in n8n.flujos():
        flujo = resumen if resumen.get("nodes") is not None else n8n.flujo(resumen["id"])
        for nodo in nodos_format_chain(flujo):
            v = version(str((nodo.get("parameters") or {}).get("jsCode", "")))
            encontrados.append(
                {
                    "flujo": flujo["id"],
                    "nombre": flujo.get("name"),
                    "activo": bool(flujo.get("active")),
                    "nodo": nodo.get("name"),
                    **v,
                }
            )

    if a.json:
        print(json.dumps(encontrados, ensure_ascii=False, indent=2))
        return 0

    if not encontrados:
        print("No encontré ningún flujo con un nodo Format Chain.")
        return 0

    print(f"Encontré {len(encontrados)} nodo(s) Format Chain:\n")
    for e in encontrados:
        print(f"  · {e['nombre']}  (id {e['flujo']}, {'activo' if e['activo'] else 'apagado'})")
        print(f"      nodo «{e['nodo']}»: {e['detalle']}")
    return 0


def cmd_respaldar(n8n: N8n, a) -> int:
    ruta = _respaldar(n8n.flujo(a.flujo), Path(a.carpeta))
    print(f"Respaldo guardado: {ruta}")
    return 0


def cmd_aplicar(n8n: N8n, a) -> int:
    codigo = codigo_v4(a.forma, a.maximo)
    flujo = n8n.flujo(a.flujo)
    nodo = _elegir_nodo(flujo, a.nodo)
    v = version(str((nodo.get("parameters") or {}).get("jsCode", "")))

    if not v["se_puede_aplicar"] and not a.forzar:
        print(
            f"No la reemplazo: el nodo «{nodo.get('name')}» {v['detalle']}.\n"
            "Si se reemplaza entera se pierden sus cambios. Lo que corresponde es agregarle\n"
            "solo la elección a su código y subirlo con `subir --archivo`.\n"
            "(Si igual querés pisarla con la v4, usá --forzar: el respaldo queda hecho.)"
        )
        return 2

    ruta = _respaldar(flujo, Path(a.carpeta))
    print(f"Respaldo guardado: {ruta}")
    _poner_codigo(n8n, flujo, nodo["name"], codigo)
    print(
        f"Listo: «{nodo.get('name')}» de «{flujo.get('name')}» quedó en la v4, "
        f"forma {a.forma}, máximo {a.maximo}. Verificado leyendo el flujo de nuevo."
    )
    print("El flujo sigue prendido o apagado como estaba: este script no toca eso.")
    return 0


def cmd_subir(n8n: N8n, a) -> int:
    codigo = Path(a.archivo).read_text(encoding="utf-8")
    if "return" not in codigo:
        raise ErrorDeN8n("Ese archivo no parece el código de un nodo (no tiene ningún return).")
    flujo = n8n.flujo(a.flujo)
    nodo = _elegir_nodo(flujo, a.nodo)
    ruta = _respaldar(flujo, Path(a.carpeta))
    print(f"Respaldo guardado: {ruta}")
    _poner_codigo(n8n, flujo, nodo["name"], codigo)
    print(f"Listo: el código de «{nodo.get('name')}» se reemplazó y se verificó.")
    return 0


def cmd_restaurar(n8n: N8n, a) -> int:
    respaldo = json.loads(Path(a.archivo).read_text(encoding="utf-8"))
    if not isinstance(respaldo, dict):
        raise ErrorDeN8n("Ese archivo no es un respaldo de un flujo.")
    for campo in ("id", "name", "nodes"):
        if campo not in respaldo:
            raise ErrorDeN8n(f"Ese archivo no es un respaldo de un flujo (le falta «{campo}»).")
    # El flujo lo dice la persona, no el archivo: un .json cualquiera no puede
    # pisar otro flujo del mismo n8n.
    if _id_valido(respaldo["id"]) != _id_valido(a.flujo):
        raise ErrorDeN8n(
            f"Ese respaldo es del flujo {respaldo['id']}, no del {a.flujo}. No lo restauro."
        )
    # Lo que hay ahora también se respalda: restaurar es pisar, y lo que se
    # pisa tiene que poder volver.
    actual = _respaldar(n8n.flujo(respaldo["id"]), Path(a.carpeta))
    print(f"Respaldo de cómo estaba antes de restaurar: {actual}")
    n8n.guardar(respaldo)
    guardado = n8n.flujo(respaldo["id"])
    iguales = all(
        _normalizar(json.dumps(n.get("parameters"), sort_keys=True))
        == _normalizar(json.dumps(m.get("parameters"), sort_keys=True))
        for n, m in zip(respaldo["nodes"], guardado.get("nodes") or [])
    )
    if not iguales or len(respaldo["nodes"]) != len(guardado.get("nodes") or []):
        raise ErrorDeN8n("Se mandó el respaldo, pero el flujo que quedó no coincide. Revisalo en n8n.")
    print(f"Listo: «{respaldo.get('name')}» volvió a como estaba en {Path(a.archivo).name}.")
    # Si ahora está prendido, que corra con lo restaurado y no con el cambio.
    _publicar_si_estaba_prendido(n8n, guardado)
    return 0


def cmd_verificar(n8n: N8n, a) -> int:
    flujo = n8n.flujo(a.flujo)
    nodos = nodos_format_chain(flujo)
    if not nodos:
        print(f"«{flujo.get('name')}» no tiene un nodo Format Chain.")
        return 1
    print(f"«{flujo.get('name')}» ({'activo' if flujo.get('active') else 'apagado'}):")
    for nodo in nodos:
        v = version(str((nodo.get("parameters") or {}).get("jsCode", "")))
        print(f"  · nodo «{nodo.get('name')}»: {v['detalle']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Sin esto, en Windows una tilde o una flecha tiran el script al imprimir.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(
        prog="n8n_format_chain.py",
        description="Busca, respalda y actualiza el nodo «Format Chain» de tu agente en n8n. "
        "La conexión sale de N8N_API_URL y N8N_API_KEY: del entorno, del archivo "
        f"{ARCHIVO_DE_ACCESO} o del .mcp.json (nunca como argumento).",
    )
    sub = p.add_subparsers(dest="comando", required=True, metavar="comando")

    b = sub.add_parser("buscar", help="los flujos con un nodo Format Chain y su versión")
    b.add_argument("--json", action="store_true", help="la lista en JSON")

    for nombre, ayuda in (
        ("respaldar", "guarda el flujo entero en un .json con fecha"),
        ("aplicar", "pone la Format Chain v4 con la elección (respalda antes)"),
        ("subir", "sube un código propio al nodo (respalda antes)"),
        ("verificar", "muestra cómo quedó el nodo"),
    ):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--flujo", required=True, help="el id del flujo (sale de `buscar`)")
        if nombre in ("respaldar", "aplicar", "subir"):
            s.add_argument("--carpeta", default=str(CARPETA_DE_RESPALDOS), help="dónde van los respaldos")
        if nombre in ("aplicar", "subir"):
            s.add_argument("--nodo", help="el nombre del nodo, si el flujo tiene más de uno")
        if nombre == "aplicar":
            s.add_argument("--forma", required=True, choices=FORMAS, help="humano o un_mensaje")
            s.add_argument("--maximo", type=int, default=3, help="de 1 a 5 (solo cuenta en humano)")
            s.add_argument("--forzar", action="store_true", help="pisa una Format Chain con cambios propios")
        if nombre == "subir":
            s.add_argument("--archivo", required=True, help="el .js con el código del nodo")

    r = sub.add_parser("restaurar", help="vuelve el flujo a como estaba en un respaldo")
    r.add_argument("--flujo", required=True, help="el id del flujo: tiene que ser el del respaldo")
    r.add_argument("--archivo", required=True, help="el .json que guardó `respaldar`")
    r.add_argument("--carpeta", default=str(CARPETA_DE_RESPALDOS), help="dónde va el respaldo de lo actual")

    a = p.parse_args(argv)
    comandos = {
        "buscar": cmd_buscar,
        "respaldar": cmd_respaldar,
        "aplicar": cmd_aplicar,
        "subir": cmd_subir,
        "restaurar": cmd_restaurar,
        "verificar": cmd_verificar,
    }
    try:
        return comandos[a.comando](conectar(), a)
    except (ErrorDeN8n, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

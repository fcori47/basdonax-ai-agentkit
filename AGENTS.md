# AGENTS.md — contexto para agentes de IA

Este archivo lo leen solos los agentes de programación cuando abren el
proyecto: **Codex, Claude Code, Cursor, Devin, Jules** y cualquier otro que
siga la convención `AGENTS.md`. Está para que entiendan el repo sin que se lo
tengas que explicar cada vez.

Si sos una persona: leé el `README.md`, es el que está escrito para vos.

---

## Qué es esto

**Agent Kit.** Un agente de IA conversacional que arranca en la máquina
del usuario, sin servidor. Telegram lo atiende desde ahí; WhatsApp, desde un
servidor, con Chatwoot en el medio. Funciona con Claude, OpenAI o Gemini,
intercambiables desde el `.env`.

Construido sobre **LangChain + LangGraph**. La memoria son los *checkpointers*
de LangGraph, indexados por `thread_id`.

Se armó por etapas: primero local, después Telegram, después WhatsApp. Todo
lo que se diseñó acá apunta a que cada etapa nueva no obligue a reescribir
el agente.

**Idioma del código: español.** Nombres de funciones, variables, comentarios,
docstrings y mensajes de error, todo en español rioplatense (voseo: *tenés*,
*podés*, *guardás*). Excepciones: los identificadores que vienen de librerías
(`messages`, `thread_id`, `checkpointer`, `StateGraph`) y los nombres de los
proveedores. **Si escribís código nuevo acá, seguí esa convención.**

---

## Estructura

El árbol de archivos está en el **[README](README.md#qué-hay-adentro)**.
Lo que importa acá es qué hace cada uno:

| Archivo | Qué resuelve |
|---|---|
| `agente.py` | **El agente.** El grafo de LangGraph. Empezá por acá. |
| `herramientas.py` | Lo que el agente puede hacer además de conversar. Hoy: el clima. |
| `modelos.py` | Crea el modelo y le pregunta al proveedor cuáles tiene |
| `memoria.py` | Los checkpointers: `ram` / `sqlite` / `postgres` |
| `prompts.py` | Lee y guarda `prompts/sistema.md` |
| `respuesta.py` | Parte la respuesta en varios mensajes, o la deja en uno (`MENSAJES_POR_RESPUESTA`) |
| `frenos.py` | El tope de mensajes por conversación y por día |
| `avisos.py` | El mail al dueño cuando algo se rompe: por Google (lo recomendado) o por SMTP |
| `gmail.py` | Habla con Google: el permiso de Google Cloud y la Gmail API. Solo biblioteca estándar y **sin importar nada del paquete**: `conectar_gmail.py` lo carga suelto |
| `consola.py` | Que la terminal de Windows no rompa con las tildes |
| `config.py` | Lee el `.env`. Única fuente de configuración. |
| `canales/base.py` | La forma de un canal |
| `canales/telegram.py` | **El bot de Telegram.** Polling, corre en tu máquina. |
| `canales/chatwoot.py` | **El canal de WhatsApp**, con Chatwoot en el medio |
| `canales/buffer.py` | Junta la ráfaga de mensajes cortos y contesta una vez. Una parte puede ser una tarea que todavía se está leyendo (una foto): se espera en su lugar |
| `canales/adjuntos.py` | **Lo que no es texto, a texto:** audios (OpenAI), fotos y stickers (el modelo del agente), ubicaciones, contactos, archivos, videos y citas |
| `canales/whatsapp_meta.py` | El visto azul y el «escribiendo…» en el celular de la persona, pidiéndoselos a Meta (opcional) |
| `web/webhook.py` | **El servidor que atiende WhatsApp.** Es lo que corre en producción. |
| `../webhook_chatwoot.py` | El punto de entrada del webhook |
| `../Dockerfile` | Empaqueta el **webhook** (`webhook_chatwoot.py`); el bot de Telegram queda adentro por si lo querés correr |
| `web/app.py` | La plataforma de pruebas (FastAPI + un solo HTML) — **no es** el webhook |
| `../conectar_gmail.py` | Conecta la cuenta de Google que manda los avisos. Se corre una vez, **en la computadora** de la persona (abre el navegador), y deja los tres `GMAIL_*` en el `.env` sin mostrarlos |
| `../probar_mail.py` | Manda un mail de prueba de los avisos. Es el último paso de la instalación, y se corre **en el servidor** |
| `../n8n/format_chain_v4.js` | La Format Chain nueva, para el que tiene el agente en n8n y la pega a mano. **Es copia exacta** de la que usa el actualizador: un test lo cuida |
| `../.claude/skills/actualizar-agente-whatsapp/` | El actualizador: una skill de Claude Code que adapta al cobro de Meta un agente hecho en n8n, en este kit o que todavía no existe. Sus pruebas (contra un n8n de mentira) están en `tests/actualizador/` |
| `../docs/img/` | Las imágenes del README. Se generan aparte; no son parte del agente |

---

## Las cuatro decisiones de diseño

Entender esto evita romper cosas:

**1. El agente recibe texto y devuelve texto.**
No sabe si lo llaman desde la terminal, la web, Telegram o WhatsApp. Esa
frontera es deliberada: es lo que permite agregar canales sin tocarlo.
`Agente.responder(texto, conversacion) -> Respuesta`.

**2. La memoria es un checkpointer intercambiable.**
`ram()` / `sqlite()` / `postgres()` en `memoria.py`. El `MODO` del `.env`
elige. Cambiar dónde se guardan las conversaciones no toca `agente.py`.

**3. El prompt del sistema vive en un archivo, no en el código.**
`prompts/sistema.md`, leído en **cada** mensaje (no una vez al arrancar).
Por eso se puede editar con el agente corriendo.

**4. Toda la configuración sale del `.env`, vía `config.py`.**
Ninguna credencial en el código, ni una. Las claves se leen únicamente en
`config.py`.

---

## Dónde tocar cada cosa

| Querés… | Archivo | Cómo |
|---|---|---|
| Agregar un proveedor nuevo | `modelos.py` | Una rama en `crear_modelo()` + una en `listar_modelos()` |
| Cambiar dónde se guardan las charlas | `.env` (`MODO`) | O una función nueva en `memoria.py` |
| Cambiar la personalidad | `prompts/sistema.md` | Es texto plano |
| **Agregar herramientas** | `herramientas.py` | Una función con `@tool` + sumarla a `HERRAMIENTAS`. El grafo ya está armado. |
| Agregar un canal (Telegram, WhatsApp) | archivo nuevo | Traducir mensaje entrante → `agente.responder(texto, conversacion=<chat_id>)` |
| Nueva variable de configuración | `config.py` | Campo en `Config` + lectura en `desde_entorno()` + línea en `.env.example` |
| Que se pueda editar desde la web | `config.py` | Agregarla a `AJUSTABLES` + campo en `AjustesEntrantes` (`web/app.py`) + control en la barra de estado |
| Tocar la interfaz | `web/static/index.html` | Un solo archivo, sin build ni npm |

---

## Reglas al escribir código acá

- **Ninguna credencial en el código.** Todas viven en el `.env` y se leen en
  `config.py`. Hay dos excepciones, a propósito: `Avisos.desde_entorno()` lee
  solo lo del mail (para que `probar_mail.py` no pida la clave del modelo) y
  `conectar_gmail.py` escribe en el `.env` los tres datos de Google. Fuera de
  eso, algún `os.getenv()` suelto es para rutas, nunca para una clave.
- **Español**, según la convención de arriba.
- **Comentar el *por qué*, no el *qué*.** Este repo es material didáctico: si
  algo se hace de una forma no obvia, explicá la razón.
- **El error del proveedor nunca se esconde.** Si Anthropic, OpenAI o Google
  devuelven un error, tiene que llegar tal cual a quien lo puede arreglar: en
  la terminal y la plataforma de pruebas, a la pantalla; en WhatsApp, al
  mail del dueño (`AVISOS_EMAIL`), y la conversación pasa a `humano`. **Al cliente
  que escribió por WhatsApp no le llega nunca**: para él, un error técnico es
  un negocio que no anda.
  Sí se pueden tragar fallas que no son del modelo y no deben voltear la app.
  Hoy son estas, todas a propósito y comentadas: `listar_modelos()` (sin
  lista, la app sigue), `consola.preparar()` (si la terminal no acepta UTF-8,
  se sigue igual), `_mensajes_en_memoria()` (es un contador para la pantalla),
  `Avisos.avisar()` (un mail que no sale no puede tirar abajo al agente que
  avisa), los pasos de `algo_se_rompio()` en `web/webhook.py` (que no se
  pueda poner la etiqueta no puede impedir el mail), `mantener_el_permiso()`
  en el mismo archivo (si Google no acepta el permiso, queda en el registro y
  se vuelve a probar), `Chatwoot.escribiendo()` y `marcar_visto_y_escribiendo()`
  (cosméticos), `Chatwoot._etiquetas_de()`, `Chatwoot.lo_agarro_otro()` y
  `Chatwoot.ya_la_cerro()` (si no se pueden leer, se responde igual: perder a
  alguien por una consulta caída es peor), y la lectura de un adjunto en
  `Lector` (si una foto o un audio no se pueden leer, el agente pregunta y el
  error va al mail). **No agregues otra sin dejar el motivo escrito al lado.**
- **Los tests no gastan tokens.** Usan `GenericFakeChatModel`. Si agregás una
  función que llama a un proveedor, el test va con modelo falso.
- **Sin dependencias nuevas** salvo que resuelvan algo que no se puede hacer
  con lo que ya está.

---

## Cómo se corre

La instalación paso a paso está en el
**[README](README.md#arrancar-en-3-pasos)** — no la repito acá para que no se
desincronicen. Lo que hace falta saber:

```bash
python servidor.py         # la plataforma de pruebas, en http://localhost:8000
python chat.py             # lo mismo pero por terminal
python bot_telegram.py     # el agente atendiendo en Telegram (polling, local)
python webhook_chatwoot.py # el agente atendiendo WhatsApp (necesita servidor)
```

El último es el único que **no** sirve en tu máquina: es un webhook, así que
Chatwoot tiene que poder entrar. Levantalo local solo para confirmar que
arranca (`GET /salud`); para probarlo de verdad tiene que estar desplegado.

El bot se llama `bot_telegram.py` y no `telegram.py` a propósito: un módulo
llamado `telegram` en la raíz taparía la librería del mismo nombre si algún
día se instala.

Para `MODO=produccion` hacen falta dos paquetes que **no** están en el
`requirements.txt`, y en Windows el segundo no es opcional:

```bash
pip install "langgraph-checkpoint-postgres>=3.1,<4" "psycopg[binary]"
```

Para los tests hace falta pytest, que **no** está en `requirements.txt`:

```bash
pip install -r requirements-dev.txt
pytest
```

No hay `pyproject.toml`: el paquete no se instala. Cada punto de entrada y
cada test hace `sys.path.insert(0, "src")`, así que `pytest` se corre desde la
raíz del repo y no desde otro lado.

---

## Al instalar: seis preguntas antes de desplegar

Si te piden instalarlo o desplegarlo para WhatsApp, **preguntale estas seis
cosas a la persona antes de completar el `.env`**. Son decisiones de su
negocio: no las llenes con el valor por defecto. Explicale cada una en
palabras simples, sin jerga, y recién después escribí la respuesta. Si algo
no lo tiene hecho, **guialo paso a paso hasta que quede hecho**: no le
dejes la tarea para después.

**1. ¿Querés que responda como una persona, en varios mensajes cortos, o todo
en un solo mensaje?** → `MENSAJES_POR_RESPUESTA` (va de `1` a `5`; lo
habitual es `3` o `1`)

Contale esto antes de que elija: desde el 1 de octubre de 2026, Meta cobra
los mensajes que manda el agente, pasados los 1.000 gratis de cada mes (por
número). Tres mensajes cortos se leen como una persona, pero son hasta tres
mensajes cobrados. Si la mayoría de la gente le llega por anuncios de clic a
WhatsApp y escribe desde el celular, esas conversaciones son gratis durante
72 horas desde la primera respuesta y la diferencia casi no se siente; donde
pesa es en lo que entra directo.

**2. ¿Tenés una tarjeta cargada en tu cuenta de WhatsApp de Meta?**

Contale por qué importa: sin tarjeta, pasados los 1.000 mensajes gratis del
mes, Meta deja de entregar lo que manda el agente, y el agente no se entera
(Chatwoot ya había aceptado el mensaje): no sale ningún aviso. Si no la
tiene, guialo con los pasos de la ayuda oficial de Meta (artículo «Añadir
una tarjeta de crédito a una cuenta de la plataforma de WhatsApp Business»):

1. Entrá al administrador de WhatsApp: https://business.facebook.com/wa/manage/home/
2. En la página de información general, buscá la cuenta y hacé clic en los
   tres puntos.
3. **Administrar la configuración de la cuenta** → pestaña **Configuración**
   → **Configuración de pago**.
4. **Añadir método de pago**, completá los datos de pago → **Siguiente**.
5. Los datos de la tarjeta → **Guardar**. Los datos de la empresa → **Guardar**.

Meta está cambiando esta parte: la versión en inglés del mismo artículo ya
muestra otro camino, **Meta Business Suite → Configuración → la sección de
pagos (*Billing & payments*) → cuentas de mensajería (*Messaging accounts*)
→ Añadir método de pago**. Si no encuentra «Configuración de pago», probá por
ahí; si tampoco está, le falta el permiso: tiene que pedírselo al dueño del
portfolio comercial.

Hace falta permiso para administrar los pagos de esa cuenta (el dueño ya lo
tiene) y una tarjeta de crédito Visa o Mastercard: no aceptan American
Express ni PayPal. Al terminar, que te confirme que la tarjeta aparece en la
pestaña **Configuración**.

**3. ¿Cuántos mensajes de una misma persona atiende por día?** →
`TOPE_MENSAJES_POR_DIA`

Contale: hay gente que se queda charlando de cualquier cosa con el agente, y
cada respuesta se paga. Cuentan los mensajes que manda la persona en esa
conversación, en 24 horas (no las respuestas: tres mensajes seguidos cuentan
tres). Al pasar el tope, el agente le pone la etiqueta `humano` a esa
conversación y se calla. **La etiqueta no se va sola**: vuelve a
contestar cuando alguien del equipo se la saca. Si no sabe qué poner, 50. `0`
es sin tope. Recomendale además un tope de gasto en la consola del proveedor
del modelo: es el único freno que no depende del agente.

**4. ¿A qué mail te aviso si algo se rompe?** → `AVISOS_EMAIL` y los tres
`GMAIL_*`

Contale: si falla el modelo o Chatwoot no acepta la respuesta, la persona
que escribió no ve ningún error; la conversación pasa a `humano` y a él le
llega un mail con el error (de un mismo error, uno por hora como mucho). Preguntale a qué dirección le llega (`AVISOS_EMAIL`) y desde qué
cuenta de Google sale (puede ser la misma).

El mail sale **con Google Cloud**: un permiso que sirve solo para mandar
(`gmail.send`). El agente no puede leer ni borrar nada de esa casilla, el
permiso se revoca desde la cuenta sin cambiar contraseñas, y es gratis (no
pide tarjeta). Guialo paso a paso, con los enlaces directos, y que te
confirme cada uno antes de seguir:

1. **Un proyecto**: https://console.cloud.google.com/projectcreate (el
   nombre da igual, por ejemplo «agente»). Que se asegure de que quedó
   elegido arriba, en el selector de proyectos.
2. **La Gmail API**: https://console.cloud.google.com/apis/library/gmail.googleapis.com
   → **Habilitar**.
3. **La pantalla del permiso**: https://console.cloud.google.com/auth/overview
   → **Comenzar**. El nombre de la app es lo que va a ver al aceptar (por
   ejemplo «Avisos del agente»), el mail de asistencia es el suyo, y en
   **Público** (*Audience*):
   - si la cuenta que manda es de empresa (Google Workspace): **Interno**.
     No hace falta nada más.
   - si es un Gmail común: **Externo**, y al terminar, en
     https://console.cloud.google.com/auth/audience → **Publicar app** →
     Confirmar. **Que no quede «En prueba»**: en prueba, Google da un permiso
     de 7 días, `probar_mail.py` anda el primer día y el octavo los avisos se
     cortan sin que nadie se entere. No hace falta mandarla a verificar.
4. **El cliente**: https://console.cloud.google.com/auth/clients → **Crear
   cliente** → tipo **App de escritorio** (no «Aplicación web») → Crear →
   **Descargar JSON**. Que lo baje en ese momento: después Google no vuelve a
   mostrar la clave (si se le pasó, en el cliente, *Agregar secreto*).
5. **Conectar la cuenta**: corré `python conectar_gmail.py` en su
   computadora, en la carpeta del kit (busca el JSON ahí y en Descargas; si
   está en otro lado, pasale la ruta). Abre su navegador: que elija la cuenta
   que va a mandar y acepte «Enviar correo electrónico en tu nombre». Si
   aparece «Google no verificó esta app», es la suya: **Avanzado → Ir a …
   (no seguro)**. El script espera hasta 5 minutos: corrélo con tiempo
   (en Claude Code, con un timeout largo o en segundo plano).
   Deja en el `.env` `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` y
   `GMAIL_REFRESH_TOKEN`, y avisa si falta algo (la API sin habilitar, la app
   en prueba). **No leas ni muestres esos valores**: son una llave. Si hay
   que pasarlos al servidor, que los copie la persona desde su `.env`.
6. **La prueba se hace donde corre el agente**: con las variables cargadas en
   el servidor y desplegado, en la terminal del contenedor (en Coolify, la
   terminal de la aplicación; con Docker, `docker exec agente python
   probar_mail.py`). Preguntale si le llegó (que mire también en correo no
   deseado) y desde qué cuenta salió. **No des la instalación por terminada
   sin ese mail.**

Contale también: el permiso no vence solo, pero se corta si cambia la
contraseña de esa cuenta de Google o si le saca el acceso desde
https://myaccount.google.com/connections. Para reconectar: `python
conectar_gmail.py` de nuevo (sin el JSON: usa el cliente que ya está en el
`.env`) y copiar `GMAIL_REFRESH_TOKEN` al servidor. Si el permiso deja de
valer, el registro del servidor dice «Los avisos por mail NO van a salir».

Si su mail no es de Google (Outlook, Zoho, el de su dominio), van las
`SMTP_*` con los datos de su proveedor, en vez de las `GMAIL_*`. Si no
quiere avisos, `AVISOS_EMAIL` vacío: todo lo demás anda igual.

**5. Si resolvés una conversación en Chatwoot, ¿el agente no le vuelve a
hablar a esa persona?** → `RESPETAR_RESUELTAS`

Contale: hay equipos para los que resolver es «con esta persona ya terminé»,
y otros que resuelven de rutina todo lo que ya se contestó. Con `1`, el
agente no le vuelve a hablar a quien tenga una conversación resuelta (aunque
escriba días después): le pone `humano` y aparece en la bandeja. Para
devolvérsela al agente, se reabre y se le saca la etiqueta. Si resuelven de
rutina, `0`: si no, el agente se calla con los clientes que vuelven. Lo
recomendado para un negocio que atiende ventas es `1`.

Con `1`, en el webhook de Chatwoot va tildado también el evento
`conversation_status_changed`: hay bandejas que reabren la misma conversación
cuando la persona vuelve a escribir, y la única forma de saber que se había
resuelto es enterarse en el momento.

**6. ¿El agente atiende toda la charla, o contesta solo el primer mensaje y
te la pasa?** → `SOLO_EL_PRIMER_MENSAJE`

Contale: por defecto (`0`) atiende toda la charla. Con `1`, contesta el primer
mensaje de cada conversación y le pone `humano`: sirve si quiere que el
agente abra la charla y la siga una persona.

**Además, sin preguntar:** si tiene `OPENAI_API_KEY` (aunque use otro
proveedor), los audios se transcriben; si no, pasan a una persona. Y si
quiere el visto azul y los puntitos en el celular, van `WHATSAPP_TOKEN` y
`WHATSAPP_PHONE_NUMBER_ID` de su cuenta de WhatsApp Business (los mismos que
usa Chatwoot). Contáselo en una línea cada uno; no lo trabes por eso.

**En el servidor van todas las variables**: las de Chatwoot y las de estas
seis decisiones (en Coolify, *Environment Variables* de la aplicación). La
lista completa está en el README, en «Con Coolify».

---

## Detalles que ya mordieron

Cosas que parecen bugs y no lo son, o que cuestan de encontrar:

- **`stream_usage=True` en `ChatOpenAI`**: sin eso, OpenAI no informa tokens
  cuando la respuesta llega en streaming. Quedan en 0.
- **`use_responses_api=True` en `ChatOpenAI`, y no se puede sacar.** Por el
  endpoint viejo (`/v1/chat/completions`), pedirle herramientas a un modelo que
  razona —toda la familia gpt-5— devuelve un 400: *"Function tools with
  reasoning_effort are not supported... use /v1/responses"*. La otra salida que
  ofrece el propio error es apagarle el razonamiento al modelo, que es pagar
  por uno y usar otro. Con modelos viejos (gpt-4.1) el problema no aparece, así
  que si lo sacás no lo vas a ver hasta probar con un gpt-5.
- **Los resultados de las herramientas también salen por el stream.**
  `responder_en_vivo()` filtra los `ToolMessage` a propósito: sin ese filtro, la
  persona ve el texto crudo de la consulta al clima en pantalla y después la
  respuesta de verdad.
- **Con herramientas el modelo habla dos veces**, así que la suma de chunks de
  `responder_en_vivo()` termina juntando el gasto de las dos llamadas. Es lo que
  querés: es lo que costó la respuesta. Ojo que `responder()` (sin streaming)
  informa solo los tokens del último mensaje, porque mira `messages[-1]`.
- **`GenericFakeChatModel` no implementa `bind_tools()`** y el grafo lo llama al
  construirse. Por eso los tests usan `ModeloFalso`, que lo agrega. Si armás un
  modelo falso nuevo, acordate o no arranca ni un test.
- **Los chunks se suman** (`chunk_a + chunk_b`) en `responder_en_vivo()`. No es
  cosmético: varios proveedores mandan el conteo de tokens recién en el
  último chunk, y sumando es la única forma de tenerlo completo.
- **El caché de Claude es un bloque, no un string.** El `SystemMessage` pasa a
  ser `[{"type": "text", "text": ..., "cache_control": {...}}]`. Cualquier
  código que asuma que `content` es `str` se rompe. Ver `Agente._sistema()`.
- **El caché no se activa con prompts cortos** (~1.000 tokens mínimo). No es
  un bug: es cómo funciona. Con un prompt corto simplemente no cachea.
- **`check_same_thread=False`** en la conexión de SQLite: el servidor web
  atiende en varios hilos y sin eso rompe.
- **El pool de Postgres se deja abierto a propósito** en `memoria.postgres()`.
  Si se cierra el context manager, el checkpointer muere en el primer mensaje.
- **`langgraph-checkpoint-postgres` tiene que ser 3.x.** La 2.x arrastra un
  `langgraph-checkpoint` viejo (2.1) que se pelea con `langgraph` 1.2 y con el
  checkpointer de SQLite. `pip install` lo deja instalar igual y lo avisa como
  un warning que es fácil pasar por alto; el entorno queda roto.
- **`psycopg` va con `[binary]` en Windows.** Sin eso el import falla con
  *"no pq wrapper available"* porque no encuentra la libpq del sistema. El
  paquete está instalado y el error igual aparece.
- **El offset de Telegram se adelanta aunque el mensaje no sirva**
  (`Telegram.escuchar()`). Telegram reenvía todo lo que no le confirmaste, así
  que si alguien manda una foto y no avanzamos, esa foto vuelve para siempre y
  el bot se queda trabado ahí sin atender a nadie más.
- **El `chat_id` va como texto** al usarse de `thread_id`. Un `555` y un
  `"555"` son dos conversaciones distintas para LangGraph.
- **El bot de Telegram no expone puerto y eso confunde a los PaaS.** Al
  desplegarlo, el panel le asigna un dominio solo y después lo marca como
  *unhealthy* porque nadie contesta ahí. No está roto: con polling nadie
  entra al bot, sale él. Hay que borrarle el dominio y dejar el health check
  apagado. **Ojo que con el webhook de WhatsApp es al revés**: ese sí escucha
  en el 8000, sí necesita dominio y sí tiene que tener el health check
  prendido apuntando a `/salud`. Son dos formas opuestas de desplegar el
  mismo repo, y el Dockerfile hoy trae la segunda.
- **Dos instancias del bot se roban los mensajes.** Telegram le entrega cada
  mensaje a quien lo pide primero, así que si corren el servidor y la máquina
  local a la vez, las respuestas salen la mitad de cada lado. Es la falla más
  confusa de todas, porque *parece* que anda a veces sí y a veces no.
- **En un contenedor, `MODO=test` pierde las conversaciones en cada deploy**:
  el archivo de SQLite vive en el disco del contenedor y ese disco se
  descarta. En un servidor va Postgres.
- **`MEMORIA_MENSAJES=20` son 20 mensajes, no 20 tokens.** Acá había un
  `trim_messages(token_counter=len)`; ahora es `_recortar()`, que corta por
  turnos completos (ver la sección de herramientas). La unidad no cambió: se
  siguen contando mensajes. Lo que cambió es que el corte cae siempre en el
  borde de un turno, así que el total puede quedar unos mensajes abajo del tope
  antes que partir una vuelta de herramienta al medio.
- **La lista de modelos de OpenAI trae todo junto** (imágenes, audio,
  embeddings) y hay que filtrarla; la de Anthropic ya viene limpia y ordenada.
- **`max_salida` solo lo informan Anthropic y Google.** OpenAI no lo expone en
  su listado, así que queda en `None` y el tope no se ajusta para esos modelos.
  **Consecuencia real:** si venís de un modelo de Claude con tope alto y pasás
  a OpenAI, el `MAX_TOKENS` guardado queda pegado del anterior. No rompe (OpenAI
  no valida el tope como Anthropic), pero el número que ves en la barra no es
  el de ese modelo.
- **`guardar_ajustes()` reescribe el `.env` línea por línea**, no lo regenera:
  los comentarios y el orden se conservan. También actualiza `os.environ` para
  que el proceso vivo vea los valores nuevos sin reiniciar.
- **`AJUSTABLES` es una lista corta a propósito.** Fuera quedan las claves de
  API (no se editan desde el navegador), `MODO` (la plataforma es para probar:
  siempre test) y `CACHE` (siempre activado). Lo que no está en esa lista se
  ignora aunque el navegador lo mande. **No agregues nada ahí sin que te lo
  pidan.**
- **`MAX_TOKENS` lo manda la plataforma, no el usuario.** Es el tope de salida
  del modelo elegido; se acomoda solo al cambiar de modelo. El único campo que
  toca una persona en la barra es `MEMORIA_MENSAJES`.
- **Avisos por Google: una app «En prueba» da un permiso de 7 días.** El día 1
  `probar_mail.py` anda y el día 8 los avisos se cortan callados. Por eso la
  instalación la publica (o la hace Interna), y `conectar_gmail.py` avisa si
  Google devuelve el permiso con fecha de vencimiento
  (`refresh_token_expires_in`).
- **Google borra el permiso que pasa seis meses sin usarse**, y un agente que
  anda bien no manda avisos. `mantener_el_permiso()` (`web/webhook.py`) lo usa
  al arrancar y una vez por día (`Avisos.revisar()`).
- **`gmail.py` no puede importar nada del paquete.** `conectar_gmail.py` lo
  carga suelto para correr en una computadora sin LangChain instalado:
  importar `agente` arrastraría todo.
- **Se pide un solo permiso, `gmail.send`.** Con dos o más, Google muestra una
  casilla por permiso y la persona puede destildar justo el de mandar; igual,
  `conectar_gmail.py` revisa que haya vuelto y, si no, no guarda nada.

- **El aviso de Chatwoot sale antes de que el archivo esté.** Chatwoot avisa
  el mensaje nuevo mientras todavía baja el audio de Meta: la dirección del
  aviso puede dar 404. `Lector._bajar()` espera y le pide la dirección de nuevo
  a la API de mensajes.
- **Bajar y leer un audio adentro del pedido traba el servidor entero**: nadie
  más es atendido hasta que termina, y Chatwoot reintenta. Por eso la lectura
  va en una tarea aparte, que entra a la ráfaga en su lugar.
- **Los puntitos de WhatsApp duran 25 segundos**, y van atados al id del
  mensaje que llegó (`source_id`, empieza con `wamid.`). En una espera larga
  se renuevan cada 20.
- **Resolver no alcanza con mirar la conversación**: según la bandeja,
  Chatwoot abre una NUEVA cuando la persona vuelve a escribir (y las etiquetas
  no viajan) o reabre la misma (y deja de figurar como resuelta).
- **Lo que llega adentro de un adjunto no arma renglones**: un nombre de lugar
  con saltos de línea podría inventar otra línea entre corchetes. `_limpio()`
  deja todo en una.

---

## Lo que NO tiene (todavía)

No lo agregues salvo que te lo pidan: son las próximas etapas.

- Más herramientas (hay una sola: el clima)
- Leer PDF y videos (llegan, el agente sabe que llegaron y pregunta)
- Contestar con audio
- RAG / base de conocimiento
- Autenticación en la plataforma de pruebas (es local, un solo usuario)
- Varias conversaciones en paralelo en la web (usa un `thread_id` fijo)

---

## Cómo se agrega una herramienta

**El grafo ya es un ciclo** (modelo → herramientas → modelo, hasta que el
modelo deja de pedirlas), así que agregar una es una sola cosa: escribir la
función en `herramientas.py` y sumarla a `HERRAMIENTAS`. `agente.py` no se
toca.

```python
@tool
def clima(lugar: str) -> str:
    """Dice el clima que hace ahora mismo en una ciudad."""  # ← esto lee el modelo
    ...

HERRAMIENTAS = [clima]   # ← la única lista que mira el grafo
```

Tres cosas que importan:

- **El docstring es el prompt.** Es lo único que el modelo lee para decidir si
  la herramienta le sirve y qué mandarle. Escribilo pensando en eso, no en un
  programador que lee el código.
- **Una herramienta no levanta excepciones: devuelve el problema como texto.**
  Si explota, LangGraph corta la respuesta entera y la persona ve un error
  crudo. Devolviéndolo, el modelo lo lee y lo explica. Está comentado en
  `clima()`.
- **Sin claves nuevas.** `clima` usa Open-Meteo justamente porque no pide
  registro ni tarjeta: arrancar el repo no tiene que depender de sacar una
  credencial más.

> ✅ **La trampa que estaba acá ya está resuelta**, pero conviene entenderla
> antes de tocar `_armar_entrada()`. Una vuelta de herramienta son tres
> mensajes atados (el modelo la pide, la herramienta contesta, el modelo
> responde) y los proveedores los exigen juntos. El `trim_messages()` que
> había recortaba por mensaje suelto, así que tarde o temprano el corte caía
> en el medio y dejaba un `AIMessage` con `tool_calls` **sin** su
> `ToolMessage` → 400 del proveedor, sin explicación, y recién cuando la
> conversación se hacía larga. Ahora `_recortar()` corta por **turnos**
> completos y nunca los parte. `MEMORIA_MENSAJES` sigue contando mensajes.
> Los tests que lo cuidan son `test_el_recorte_no_parte_una_vuelta_de_herramienta`
> (probado con nueve topes distintos) y `test_el_turno_de_ahora_entra_entero_aunque_no_quepa`.

---

## Cómo se agrega un canal

`Canal` (en `canales/base.py`) define la **salida**: cómo le mandás mensajes a
una persona. La **entrada** la resuelve cada canal como le convenga, porque
cambia mucho entre uno y otro:

| | Cómo llegan los mensajes | Necesita URL pública |
|---|---|---|
| **Telegram** | *Polling*: tu programa pregunta "¿hay mensajes?" cada tanto | No |
| **WhatsApp (Meta)** | *Webhook*: Meta le pega a una URL tuya | Sí |

La forma de los dos, igual:

```python
# 1. Llega algo del canal y lo traducís
entrante = MensajeEntrante(texto=..., conversacion=<id del chat>, identificador=<id del mensaje>)

# 2. Le preguntás al canal si hay que contestar
#    (persona atendiendo, bot apagado, mensaje repetido, mensaje propio)
if not canal.deberia_responder(entrante):
    return

# 3. El agente. Esta línea es la misma en todos los canales.
mensajes = agente.responder_partido(entrante.texto, conversacion=entrante.conversacion)

# 4. La respuesta sale por donde entró
canal.enviar(entrante.conversacion, mensajes)
```

**El webhook de WhatsApp se monta en su propia app FastAPI**, no en la de la
plataforma de pruebas: son dos cosas distintas y la de pruebas no sale de
`localhost`.

**`conversacion` es el `thread_id` de LangGraph.** Es lo único que no se puede
equivocar: si dos personas comparten el mismo valor, comparten la conversación.

---

## Hacia dónde va (para no diseñar en contra)

Esto todavía **no está implementado** y no hay que implementarlo sin que lo
pidan. Está acá para que cualquier cosa que se agregue al núcleo no lo haga
imposible después.

**Etapa 2 — Telegram. ✅ Hecha.** `canales/telegram.py` implementa `Canal`,
`conversacion` = el `chat_id`, y el bucle que las pega está en
`bot_telegram.py` (raíz). Anda por *polling*, así que corre en la máquina de
uno sin dominio ni puertos abiertos. Sirve igual con `MODO=test` (SQLite) que
con `MODO=produccion` (Postgres): el agente no cambia.

**Etapa 3 — WhatsApp. ✅ Hecha, con Chatwoot en el medio.**

El agente **no le habla a Meta**: le habla a Chatwoot, que ya está conectado
a WhatsApp. Eso cambia el diseño respecto de lo que decía este archivo antes,
y para mejor: la mitad de las piezas las resuelve Chatwoot.

    persona → WhatsApp → Meta → Chatwoot → webhook → agente
                                   ↑                    │
                                   └──── API REST ──────┘

| Pieza | Dónde quedó | Cómo se resolvió |
|---|---|---|
| Autenticar quién llama al webhook | `web/webhook.py` | Chatwoot **no firma** sus webhooks (no hay HMAC como en Meta): la seguridad es un token secreto en la URL, `CHATWOOT_WEBHOOK_TOKEN` |
| Responder 200 rápido y procesar aparte | `web/webhook.py` | El 200 sale antes de pensar la respuesta; si no, Chatwoot reintenta y el agente contesta de más |
| Descartar el mensaje repetido por id | `Chatwoot.deberia_responder()` | Cola de los últimos 1.000 ids |
| **Que el agente no se conteste a sí mismo** | `Chatwoot.deberia_responder()` | Solo se atiende `message_type == "incoming"`. Sin esto es un ida y vuelta infinito que gasta tokens en cada vuelta |
| Juntar la ráfaga de mensajes | `canales/buffer.py` | En memoria, no Redis: hay un solo proceso atendiendo. `BUFFER_SEGUNDOS` |
| Partir la respuesta en varios globos | `respuesta.partir_respuesta()` | `MENSAJES_POR_RESPUESTA`: `3` como una persona, `1` todo junto. Meta cobra por mensaje desde el 1/10/2026. Ningún globo pasa los 4.096 caracteres de WhatsApp |
| Traspaso a una persona | `Chatwoot.deberia_responder()` | La etiqueta `CHATWOOT_ETIQUETA_HUMANO` apaga al bot en esa conversación, con un clic desde la bandeja |
| Si el modelo o Chatwoot fallan | `web/webhook.py` → `algo_se_rompio()` | Nada al cliente: etiqueta `humano` (primero, y el mail dice si se pudo) y mail al dueño (`avisos.py`), uno por hora por tipo de error. Una respuesta vacía del modelo cuenta como falla. **Sin notas privadas**, a propósito |
| El que charla de más | `frenos.TopeDeMensajes` | `TOPE_MENSAJES_POR_DIA`: al pasarlo, etiqueta `humano`. Poner la etiqueta **suma** a las que ya había: en Chatwoot, mandar etiquetas reemplaza la lista |
| Fotos, audios, ubicaciones, citas | `canales/adjuntos.py` → `Lector` | Todo a texto, en segundo plano y en su lugar de la ráfaga. Se baja solo de `CHATWOOT_URL` (del evento se usa el camino), con tope de tamaño y reintento si el archivo todavía no está |
| No contestar arriba de una persona | `Chatwoot.lo_agarro_otro()` | Se vuelve a mirar la conversación antes del modelo y antes de mandar: si le pusieron `humano` o la resolvieron, no contesta |
| Resolver calla al agente | `Chatwoot.ya_la_cerro()` + el evento `conversation_status_changed` | Con `RESPETAR_RESUELTAS=1`. Las dos piezas hacen falta: una bandeja abre conversación nueva (se mira al contacto), otra reabre la misma (se pone la etiqueta al resolver) |
| Ritmo de persona | `Chatwoot.enviar()` + `canales/whatsapp_meta.py` | Pausa entre globos (`tarda_en_escribir`), espera opcional, y el visto azul y los puntitos con los datos de Meta |
| Probar de cero | `POST /reset/<token>` | Borra la memoria y la cuenta del tope de UNA conversación. No hay «todas», a propósito |
| Textos pegados enormes | `web/webhook.py` | Se recortan a `LARGO_MAXIMO_DE_ENTRADA` antes del modelo: quedan en la memoria y se pagarían en cada mensaje |
| La clave en los registros | `web/webhook.TaparElToken` | uvicorn anota la dirección de cada pedido, y la del webhook lleva la clave: se tapa el valor exacto en todos los registros (también en una dirección mal escrita), y además cualquier `/chatwoot/<algo>` |
| Lo que llega con otra forma | `Chatwoot.traducir()` | Un evento que no es un objeto, un contenido que no es texto o un id de conversación con letras se ignoran: no tiran el servidor ni se cuelan en un mail |
| Pedidos gigantes y claves débiles | `web/webhook.py` | Más de 512 KB se corta leyendo de a pedazos. El token tiene que tener 32 caracteres o más: si falta, es corto o es el del ejemplo, el servidor no arranca (`validar_token()`). **No se bloquea por dirección**: detrás de Coolify todos llegan con la del proxy y se bloquearía al propio Chatwoot |
| Notas privadas | `Chatwoot.deberia_responder()` | Son para el equipo: el agente no las contesta |
| Ventana de 24h y plantillas | Lo maneja Chatwoot | Por eso no está acá |

**El `conversacion` (thread_id) es el id de conversación de Chatwoot.** Un
hilo en la bandeja es un hilo de memoria del agente, y es también lo que se
necesita para contestar: sirve para las dos cosas.

**Decisiones ya tomadas** (no volver a discutirlas):

- **Un solo repo.** Cada canal es un archivo nuevo; el núcleo no se toca.
  Se cumplió: `agente.py` no se tocó para que atienda WhatsApp.
- **Chatwoot es opcional**, no obligatorio. El agente sigue andando por
  terminal, web y Telegram sin él.
- ~~**Redis** para juntar los mensajes~~ → **quedó en memoria**
  (`canales/buffer.py`). Redis resolvía compartir la ráfaga entre varios
  procesos, y hoy hay uno solo atendiendo. Sumar una base entera para eso era
  pagar un problema que todavía no tenemos. Cuando se escale a varios
  procesos se cambia esa clase y el webhook ni se entera.

**Ya preparado en el núcleo para que eso entre sin reescribir nada:**

- `canales/base.py` — la forma de un canal y el gancho `deberia_responder()`
- `respuesta.partir_respuesta()` — la respuesta en varios mensajes
- `Agente.responder_partido()` — lo mismo, listo para usar
- `Transmision` — el resumen vive en cada respuesta, **no** en el agente, así
  varias conversaciones a la vez no se pisan los datos

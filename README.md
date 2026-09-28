<p align="center">
  <img src="docs/img/portada.png" alt="Agent Kit de Basdonax AI: tu agente de IA en WhatsApp, listo para producción y para lo que cobra Meta" width="100%">
</p>

# Agent Kit

Un agente de IA hecho en código para que lo manejes con **Claude Code**.
Arranca en tu computadora, sin servidor: Telegram lo atiende desde ahí mismo;
para **WhatsApp**, lo subís a un servidor tuyo. Funciona con **Claude, OpenAI
o Gemini**: los elegís de una lista, sin tocar código.

No es una demo. Trae lo que separa a un bot de prueba de uno que atiende
clientes todos los días: junta los mensajes cortados, se calla con un clic
cuando alguien del equipo toma la conversación, no se contesta a sí mismo,
frena al que charla de más y, si algo se rompe, el cliente no ve el error y a
vos te llega un mail.

> **La versión 1.1 ya contempla el cambio de Meta del 1 de octubre de 2026:**
> desde ese día Meta cobra los mensajes que manda el agente, pasados los 1.000
> gratis del mes. Al instalarlo elegís si responde como una persona, en varios
> mensajes, o todo en uno, y te guía para dejar lista la cuenta de Meta.
> [Cómo funciona →](#lo-de-meta-desde-el-1-de-octubre-cada-mensaje-se-cobra)

<p align="center">
  <img src="docs/img/mapa.png" alt="Cómo viaja un mensaje: de WhatsApp a Chatwoot, al agente, y de vuelta" width="100%">
</p>

---

## Si no sos técnico: instalalo con Claude Code

1. Bajá este repo (en GitHub: botón verde **Code** → **Download ZIP**) y
   descomprimilo.
2. Abrí esa carpeta con Claude Code y decile: **«ayudame a instalar el agente
   para WhatsApp»**.
3. Antes de tocar nada te hace seis preguntas: si responde como una persona
   o en un solo mensaje, si tenés la tarjeta cargada en Meta, cuántos mensajes
   de una misma persona atiende por día, a qué mail te avisa si algo se
   rompe, si resolver una conversación lo calla con esa persona y si atiende
   toda la charla o solo el primer mensaje. Lo que no tengas hecho, te guía
   hasta que quede.
4. Cierra con un mail de prueba desde el servidor: si llega, los avisos
   funcionan.

Para WhatsApp vas a necesitar:

- **Chatwoot**, con tu número de WhatsApp conectado por la API oficial de Meta.
- **Un servidor con dominio y HTTPS** (por ejemplo, con Coolify) y una base
  **Postgres**.
- **Una clave** de Claude, OpenAI o Gemini, con saldo.
- **Una tarjeta de crédito Visa o Mastercard cargada en Meta** (abajo, por qué).
- **Una cuenta de Google** (Gmail o Workspace) para los avisos: se conecta
  con Google Cloud, gratis y sin tarjeta, con un permiso que solo deja mandar.

---

## Índice

1. [Si no sos técnico: instalalo con Claude Code](#si-no-sos-técnico-instalalo-con-claude-code)
2. [Novedades de la 1.1](#novedades-de-la-11)
3. [Lo de Meta: desde el 1 de octubre, cada mensaje se cobra](#lo-de-meta-desde-el-1-de-octubre-cada-mensaje-se-cobra)
4. [¿Tu agente está en n8n? Hay un actualizador](#tu-agente-está-en-n8n-hay-un-actualizador)
5. [Arrancar en 3 pasos](#arrancar-en-3-pasos)
6. [Qué hay adentro](#qué-hay-adentro)
7. [Elegir el modelo](#elegir-el-modelo)
8. [La barra de ajustes](#la-barra-de-ajustes)
9. [La memoria: cómo funciona](#la-memoria-cómo-funciona)
10. [Modo test y modo producción](#modo-test-y-modo-producción)
11. [El caché: gastar menos](#el-caché-gastar-menos)
12. [El clima: la primera herramienta](#el-clima-la-primera-herramienta)
13. [Ponerlo en Telegram](#ponerlo-en-telegram)
14. [Seis decisiones antes de desplegar](#seis-decisiones-antes-de-desplegar)
15. [Lo que entiende: fotos, audios, ubicaciones](#lo-que-entiende-fotos-audios-ubicaciones)
16. [Que parezca una persona](#que-parezca-una-persona)
17. [Ponerlo en WhatsApp](#ponerlo-en-whatsapp)
18. [Dejarlo corriendo en un servidor](#dejarlo-corriendo-en-un-servidor)
19. [Cambiar la personalidad](#cambiar-la-personalidad)
20. [Usarlo desde tu código](#usarlo-desde-tu-código)
21. [Todas las variables del .env](#todas-las-variables-del-env)
22. [Preguntas que aparecen siempre](#preguntas-que-aparecen-siempre)

---

## Novedades de la 1.1

- **Elegís cómo responde:** como una persona (hasta 3 mensajes) o todo en
  uno. Lo pregunta la instalación y te explica lo que cuesta cada opción.
- **Tope de mensajes por conversación y por día:** el que charla de cualquier
  cosa pasa a una persona del equipo y el agente deja de gastar.
- **Entiende todo lo que llega por WhatsApp:** fotos (también con texto y
  stickers), audios, ubicaciones, contactos compartidos y respuestas citando
  un mensaje. Los PDF y los videos no los abre, pero sabe que llegaron y
  pregunta. Antes, todo lo que no era texto se quedaba sin respuesta.
  [Está más abajo](#lo-que-entiende-fotos-audios-ubicaciones).
- **Si algo se rompe, el cliente no ve el error:** la conversación pasa a una
  persona (la etiqueta) y te llega un mail. El mail sale con **Google Cloud**,
  con un permiso que solo deja mandar: el agente no puede leer tu casilla.
  `python conectar_gmail.py` conecta la cuenta y `python probar_mail.py` lo
  prueba antes de dar la instalación por terminada.
- **No pisa al equipo:** justo antes de contestar vuelve a mirar la charla. Si
  alguien le puso `humano` o la resolvió mientras tanto, no contesta.
- **Resolver es decidir** (se elige al instalar): si resolvés una conversación,
  el agente no le vuelve a hablar a esa persona.
- **Ritmo de persona:** una pausa entre globo y globo y, con los datos de Meta,
  el visto azul y el «escribiendo…» en el celular de la persona.
- **Más seguro:** la clave del webhook ya no queda en los registros del
  servidor y tiene que ser larga (si no, el agente no arranca); un pedido de
  más de medio mega se descarta sin terminar de leerlo; un texto pegado enorme
  se recorta a 2.000 caracteres antes de llegar al modelo; y el mail de avisos
  verifica el certificado del servidor y no sigue redirecciones.
- **Ningún mensaje pasa los 4.096 caracteres**, el tope de WhatsApp: uno más
  largo, Meta no lo entrega.
- **¿Tu agente está en n8n?** Claude Code te lo actualiza con una skill que
  viene en este repo. [Está más abajo](#tu-agente-está-en-n8n-hay-un-actualizador).

<p align="center">
  <img src="docs/img/cuando-se-rompe.png" alt="Cuando algo se rompe: el cliente no ve el error, la conversación pasa a una persona y te llega un mail" width="100%">
</p>

---

## Lo de Meta: desde el 1 de octubre, cada mensaje se cobra

Hasta el 30 de septiembre de 2026, lo que el agente contestaba adentro de las
24 horas de una conversación era gratis (lo fue desde noviembre de 2024).
**Desde el 1 de octubre de 2026, Meta cobra los mensajes que manda el
agente.** Lo que cambia para vos:

- **Cada número tiene 1.000 mensajes gratis por mes para contestar** (Meta los
  llama «de servicio»: los que manda el agente dentro de una charla que empezó
  el cliente). No se acumulan de un mes al otro. Después se paga cada mensaje
  entregado, a un precio que pone Meta según el código de país del número que
  recibe. Las plantillas (campañas, recordatorios) van aparte y no entran en
  esos 1.000.
- **Lo que entra por un anuncio de clic a WhatsApp (o por el botón de
  WhatsApp de tu página de Facebook) es gratis durante 72 horas**, se manden
  los mensajes que se manden. Las 72 horas corren desde la primera respuesta,
  que tiene que salir dentro de las 24 horas (el agente contesta en segundos),
  y la persona tiene que escribir desde la app del celular: desde WhatsApp Web
  o la compu no cuenta. Si casi toda tu gente llega por anuncios, el cambio te
  toca poco: se paga lo que te escriben directo, como el que vuelve a comprar
  semanas después.
- **Sin un método de pago en Meta, pasados los 1.000 del mes, las respuestas
  del agente dejan de llegar.** Meta las frena después de que Chatwoot ya las
  aceptó, así que el agente no se entera, el cliente se queda sin respuesta y
  a vos no te llega ningún mail. Es el golpe real del cambio, y el kit no lo
  puede detectar: por eso la tarjeta se carga antes.

Y un detalle que casi nadie mira: un agente que parte cada respuesta en tres
globos para parecer una persona **paga hasta tres mensajes en vez de uno**.
Por eso ahora lo elegís:

<p align="center">
  <img src="docs/img/tres-o-uno.png" alt="La misma respuesta en 3 mensajes o en 1, y cuántos cuenta Meta en cada caso" width="100%">
</p>

No hay una respuesta correcta: tres globos se leen más humanos, uno solo
cuesta menos. En respuestas cortas, un mensaje con saltos de línea se lee
bien; en las largas, un solo bloque se parece más a un mail. **Lo elegís al
instalar** (`MENSAJES_POR_RESPUESTA`). En el mismo momento se revisa la
tarjeta y se definen el tope de mensajes por día y el mail de avisos: está
todo en [Seis decisiones antes de desplegar](#seis-decisiones-antes-de-desplegar).

---

## ¿Tu agente está en n8n? Hay un actualizador

Si armaste tu agente en n8n con un nodo **«Format Chain»** (el que limpia la
respuesta y la parte en varios mensajes), este repo trae un actualizador para
adaptarlo al cobro de Meta sin romper nada. Es una skill de Claude Code:

1. Bajá este repo (en GitHub: botón verde **Code** → **Download ZIP**) y
   descomprimilo. Si preferís usarlo desde tu propio proyecto, copiá la
   carpeta `.claude/skills/actualizar-agente-whatsapp` adentro de
   `.claude/skills/` de ese proyecto (está explicado en su
   [`LEEME.md`](.claude/skills/actualizar-agente-whatsapp/LEEME.md)).
2. Abrí esa carpeta con Claude Code y decile: **«actualizá mi agente de
   WhatsApp, que está en n8n»**.

Para que lo haga por la API de n8n hace falta Python 3 en tu computadora; si
no lo tenés, te guía para hacerlo a mano adentro de n8n. Claude Code te
pregunta primero dónde está tu agente y sigue el camino que corresponde:

| Si tu agente está… | Lo que hace |
|---|---|
| **En n8n, con una clave de la API** | Busca los flujos con Format Chain, respalda cada uno, le pone la versión nueva (o, si la tocaste, le agrega solo la elección sin tocar tus filtros), verifica y lo publica |
| **En n8n, pero preferís no crear una clave** | Te guía paso a paso adentro de n8n: duplicar el flujo, pegar el código, elegir, guardar y publicar |
| **En este kit** | Trae la versión nueva sin pisar tu `.env` ni tu prompt, y te hace las seis preguntas de la instalación |
| **Todavía no lo armaste** | Te explica el cambio y te guía para cargar la tarjeta en Meta |

En todos los casos te explica qué cambia, te pregunta cómo querés que
responda y **te guía para cargar la tarjeta en Meta** si no la tenés. Nunca
prende ni apaga un flujo y nunca toca otros nodos. **La clave de n8n la cargás
vos** en un archivo que no se sube a ningún lado: Claude Code no la ve, y al
terminar te recuerda borrarla.

**¿Sin Claude Code?** El código está en [`n8n/format_chain_v4.js`](n8n/format_chain_v4.js).
Duplicá tu flujo (ese duplicado es tu respaldo), abrí el nodo «Format Chain»
del original y reemplazá su código por este. Elegí las dos opciones de arriba
de todo (`FORMA_DE_RESPONDER` y `MAXIMO_DE_MENSAJES`), guardá y, si tu n8n
tiene el botón **Publish**, tocalo. Ojo: si le habías hecho cambios propios a
tu Format Chain, pegar este código los pisa; en ese caso, mejor que lo haga
Claude Code. Con el máximo en 5 sale igual que la versión anterior (la v3.2),
y la salida es la misma (`part_1` a `part_5`), así que el resto del flujo no
se toca.

---

## Arrancar en 3 pasos

### 1. Instalar

```bash
git clone https://github.com/fcori47/basdonax-ai-agentkit
cd basdonax-ai-agentkit

python -m venv .venv
```

Activar el entorno:

```bash
# Windows
.venv\Scripts\activate

# Mac o Linux
source .venv/bin/activate
```

Instalar:

```bash
pip install -r requirements.txt
```

### 2. Poner una clave

```bash
# Windows
copy .env.example .env

# Mac o Linux
cp .env.example .env
```

Abrí el `.env` y completá **un solo** proveedor:

| Proveedor | Dónde sacar la clave | Qué completás |
|---|---|---|
| **Claude** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | `ANTHROPIC_API_KEY` |
| **OpenAI** | [platform.openai.com](https://platform.openai.com/api-keys) | `OPENAI_API_KEY` |
| **Gemini** | [aistudio.google.com](https://aistudio.google.com/apikey) | `GOOGLE_API_KEY` |

Con uno alcanza. Si cargás más de uno, los cambiás desde la web con un botón.

> El `.env` está en `.gitignore`. **Nunca se sube a GitHub.**

### 3. Probarlo

```bash
python servidor.py
```

Abrí **http://localhost:8000**.

¿Preferís la terminal? `python chat.py`

---

## Qué hay adentro

```
basdonax-ai-agentkit/
├── prompts/
│   └── sistema.md          ← la personalidad del agente (editalo)
├── src/agente/
│   ├── agente.py           ← EL AGENTE. El grafo de LangGraph.
│   ├── herramientas.py     ← lo que sabe hacer además de hablar (el clima)
│   ├── modelos.py          ← Claude / OpenAI / Gemini
│   ├── memoria.py          ← dónde se guardan las conversaciones
│   ├── prompts.py          ← lee el prompt del archivo
│   ├── respuesta.py        ← la respuesta en varios mensajes, o en uno
│   ├── frenos.py           ← el tope de mensajes por persona y por día
│   ├── avisos.py           ← el mail cuando algo se rompe
│   ├── gmail.py            ← el permiso de Google Cloud y la Gmail API
│   ├── config.py           ← lee el .env
│   ├── canales/
│   │   ├── base.py         ← la forma de un canal
│   │   ├── telegram.py     ← EL BOT DE TELEGRAM
│   │   ├── chatwoot.py     ← EL CANAL DE WHATSAPP
│   │   ├── adjuntos.py     ← fotos, audios, ubicaciones y citas, a texto
│   │   ├── whatsapp_meta.py ← el visto azul y los puntitos en el celular
│   │   └── buffer.py       ← junta los mensajes cortos seguidos
│   └── web/
│       ├── app.py          ← la plataforma de pruebas
│       └── webhook.py      ← el servidor que atiende WhatsApp
├── tests/                  ← los tests: ninguno gasta un solo token
├── n8n/
│   └── format_chain_v4.js  ← la Format Chain nueva, para pegar en n8n
├── .claude/skills/
│   └── actualizar-agente-whatsapp/  ← el actualizador (Claude Code)
├── docs/img/               ← las imágenes de este README
├── chat.py                 ← hablarle desde la terminal
├── servidor.py             ← levantar la web
├── bot_telegram.py         ← levantar el bot de Telegram
├── webhook_chatwoot.py     ← levantar el webhook de WhatsApp
├── conectar_gmail.py       ← conectar la cuenta de Google de los avisos
├── probar_mail.py          ← mandar un mail de prueba de los avisos
├── AGENTS.md               ← contexto para Codex, Claude Code, Cursor…
├── CLAUDE.md               ← apunta a AGENTS.md
└── .env                    ← tus claves (no se sube)
```

**Si vas a leer un solo archivo, leé `src/agente/agente.py`.** Ahí está todo
el agente: el grafo son 12 líneas, el resto es explicación y los ayudantes.

---

## Elegir el modelo

La plataforma **le pregunta a cada proveedor qué modelos tiene hoy** y te los
muestra en una lista, con el más nuevo arriba. No hay una lista escrita a mano
que envejezca: si mañana sale un modelo nuevo, aparece solo.

- El selector de arriba muestra los modelos disponibles.
- El botón **↻** vuelve a preguntar (por si acaba de salir uno).
- Cambiar de modelo **no borra la conversación**: podés arrancar con uno,
  cambiar a otro y seguir la misma charla.
- **El máximo de respuesta se acomoda solo.** Cada modelo aguanta una cantidad
  distinta de tokens de respuesta; la plataforma le pregunta cuánto es y lo
  pone. No es algo que tengas que saber ni tocar.

¿No querés tocar la web? Ponelo en el `.env` y listo:

```bash
PROVEEDOR=claude
MODELO_CLAUDE=claude-opus-5
```

Si el modelo del `.env` no existe o la lista no carga (sin internet, clave
vencida), la plataforma usa igual lo que diga el `.env`.

---

## La barra de ajustes

Debajo de los modelos hay una barra con el estado del agente:

```
modo test    memoria SQLite    caché activado    máx. respuesta 128.000 tokens    recuerda [20] mensajes
```

**Lo único editable ahí es "recuerda".** Escribís el número y listo: se guarda
en el `.env` y se aplica al instante, sin reiniciar el servidor.

El resto está fijo a propósito:

| | Por qué |
|---|---|
| **modo** | La plataforma es para probar en tu máquina: siempre `test`. Para pasar a producción se edita el `.env`. |
| **caché** | Siempre activado. No hay razón para apagarlo salvo que estés midiendo cuánto ahorra. |
| **máx. respuesta** | **Lo define el modelo, no vos.** Cada modelo aguanta un máximo distinto, así que la plataforma le pregunta cuánto es y lo pone. Cambiás de modelo y se acomoda solo. |

Todo lo demás se cambia editando el `.env`. Cuando la plataforma escribe ahí,
**respeta los comentarios y el orden** del archivo: solo reemplaza la línea de
esa variable. Y las claves de API nunca se editan desde el navegador.

---

## La memoria: cómo funciona

Esto es lo que más confunde y lo que casi nadie explica:

> **Las APIs de los modelos no recuerdan nada.**
> Cada llamada es independiente. Que el agente "se acuerde" de lo que hablaron
> es puro trabajo tuyo: le volvés a mandar la conversación entera cada vez.

LangGraph resuelve eso con dos ideas:

- **`thread_id`** — el identificador de una conversación. Cada valor distinto
  es una charla separada, con su propia memoria.
- **checkpointer** — dónde se guardan esas conversaciones.

```python
agente.responder("Hola, me llamo Martina", conversacion="chat-1")
agente.responder("¿Cómo me llamo?",     conversacion="chat-1")  # → "Martina"
agente.responder("¿Cómo me llamo?",     conversacion="chat-2")  # → no sabe
```

Ese `thread_id` es exactamente lo que después va a ser el número de WhatsApp
o el chat de Telegram de cada persona. **Ahí está el truco de todo esto:**
el mismo agente atiende a mil personas sin mezclar las conversaciones.

### Cuánto recuerda

`MEMORIA_MENSAJES=20` en el `.env`, o el campo **recuerda** en la plataforma.
Son **mensajes**, no tokens (cuentan los tuyos y los del agente).

Ojo con la diferencia:

- **Se guardan todos.** El historial completo queda en la base.
- **Se le mandan al modelo solo los últimos N.** Eso es lo que controla este
  número.

Por eso es la palanca más directa sobre el costo: la conversación viaja entera
en cada mensaje, así que bajar de 20 a 10 es, más o menos, la mitad del gasto
en charlas largas. La contra es que el agente se olvida antes.

Para verlo funcionar: ponelo en 4, decile tu nombre, mandale tres mensajes
cualquiera y después preguntale cómo te llamás. No se va a acordar.

---

## Modo test y modo producción

Una sola variable decide dónde se guardan las conversaciones:

```bash
# SQLite: un archivo. No instalás nada.
MODO=test
# Postgres: para varios procesos atendiendo a la vez.
MODO=produccion
```

|  | `test` | `produccion` |
|---|---|---|
| Guarda en | Un archivo `.db` | Postgres |
| Sobrevive al reinicio | Sí | Sí |
| Varios procesos a la vez | No | Sí |
| Hay que instalar algo | No | Sí (ver abajo) |
| Para qué sirve | Desarrollar · un bot chico de Telegram | WhatsApp · producción de verdad |

### Pasar a producción

```bash
pip install "langgraph-checkpoint-postgres>=3.1,<4" "psycopg[binary]"
```

Dos detalles que cuestan una tarde si no te los avisan:

- **La versión 3.x no es un capricho.** La 2.x se lleva por delante el
  `langgraph` que usa el resto del proyecto. `pip` te deja instalarla igual y
  lo avisa en un renglón perdido entre otros veinte.
- **`psycopg[binary]`, con los corchetes.** Sin eso, en Windows falla con
  *"no pq wrapper available"* aunque el paquete figure instalado.

En el `.env`:

```bash
MODO=produccion
POSTGRES_DSN=postgresql://usuario:clave@servidor:5432/agente
```

Nada más. **Las tablas las crea solo** la primera vez que arranca. Y el agente
no se toca: es la misma clase, el mismo grafo, el mismo código.

> ¿No tenés Postgres? Con Docker, en una línea:
> ```bash
> docker run -d --name agente-pg -p 5432:5432 \
>   -e POSTGRES_PASSWORD=clave -e POSTGRES_DB=agente postgres:17
> ```
> Y el DSN queda: `postgresql://postgres:clave@localhost:5432/agente`

### Y si querés memoria que no guarde nada

Existe una tercera, para tests o para ver el agente en su forma más simple:

```python
from agente import Agente
from agente.memoria import ram

a = Agente(checkpointer=ram())   # se borra al cerrar el programa
```

---

## El caché: gastar menos

El prompt del sistema viaja **entero, en cada mensaje**. Si tu prompt tiene
2.000 tokens y mandás 100 mensajes, pagaste 200.000 tokens por el mismo texto.

El caché hace que el proveedor lo guarde de su lado y te cobre una fracción a
partir del segundo mensaje.

```bash
# en el .env: viene activado, dejalo así
CACHE=true
```

| Proveedor | Cómo funciona |
|---|---|
| **Claude** | Hay que marcarlo a mano — es lo que hace este repo por vos |
| **OpenAI** | Automático, no hay que hacer nada |
| **Gemini** | Automático, no hay que hacer nada |

**Dos cosas para tener en cuenta:**

1. El caché **recién se activa cuando el prompt supera cierto tamaño**
   (alrededor de 1.000 tokens). Con un prompt corto no pasa nada malo:
   simplemente no se cachea. No es un error.
2. La plataforma te muestra el ahorro en cada mensaje: cuando el caché entra,
   aparece **⚡ N desde caché** debajo de la respuesta.

---

## El clima: la primera herramienta

Hasta acá el agente solo conversaba: contestaba con lo que sabía de antes. Una
**herramienta** es una función que puede usar cuando la necesita, y con eso
deja de adivinar y sale a buscar el dato.

Probá:

```
¿qué clima hace en Rosario?
¿me llevo campera a Mar del Plata?
¿está lloviendo en Madrid?
```

Fijate que **vos no le decís que use la herramienta**. El modelo lee la
pregunta, se da cuenta de que necesita el clima, la pide, recibe el resultado
y recién ahí te contesta. Si le preguntás cualquier otra cosa, ni la toca.

### No hay que pagar ni registrarse

Usa [Open-Meteo](https://open-meteo.com): gratis, sin clave de API y sin
tarjeta para uso no comercial. Es a propósito — arrancar este repo no tiene
que depender de sacar una credencial más. Lo único que seguís pagando es el
modelo, como siempre.

### Lo que sí cuesta un poco más

Una pregunta con herramienta son **dos llamadas al modelo**, no una: la
primera para que pida el clima, la segunda para que te lo cuente. En la barra
vas a ver los tokens de las dos sumados. Es el precio de que el dato sea real.

### Si la ciudad no existe o se cae internet

Te lo dice y la charla sigue. La herramienta nunca voltea la conversación:
cuando algo falla, le devuelve el problema al modelo y el modelo te lo
explica.

---

## Ponerlo en Telegram

Hasta acá el agente vivía en tu navegador. Con esto lo tenés en el teléfono, y
**sin pagar hosting**: corre en tu computadora igual que todo lo demás.

### Los tres pasos

**1. Pedile un bot a Telegram.** Abrí [@BotFather](https://t.me/BotFather),
mandale `/newbot` y seguile la conversación. Al final te da un token, que es
una tira larga tipo `123456789:ABCdef...`.

**2. Pegalo en el `.env`:**

```bash
TELEGRAM_TOKEN=el-que-te-dio-BotFather
```

**3. Arrancalo:**

```bash
python bot_telegram.py
```

Buscá tu bot por nombre en Telegram, escribile, y listo.

### Por qué no hace falta un servidor

Telegram se puede escuchar de dos formas. Este bot usa la primera:

|  | Cómo funciona | ¿Necesita URL pública? |
|---|---|---|
| **Polling** ← esta | Tu programa le pregunta a Telegram si hay algo nuevo | **No** |
| **Webhook** | Telegram le pega a una URL tuya | Sí, con HTTPS |

Por eso Telegram viene antes que WhatsApp: WhatsApp obliga a webhook, y ahí sí
necesitás un servidor de verdad con dominio y certificado.

**Mientras la ventana esté abierta, el bot contesta.** Si la cerrás, deja de
contestar — y los mensajes que le lleguen mientras tanto los va a atender
cuando lo vuelvas a levantar (Telegram los guarda 24 horas).

¿Querés que conteste siempre, sin tener la compu prendida? Está en
[Dejarlo corriendo en un servidor](#dejarlo-corriendo-en-un-servidor).

### Cada persona, su propia conversación

Acá está lo que hace que esto sirva de verdad: el `chat_id` de Telegram es el
`thread_id` de LangGraph.

```
vos          → chat_id 555  → tu conversación
tu hermana   → chat_id 888  → la de ella, aparte
```

**El mismo bot atiende a mil personas sin mezclar nada.** No hay que hacer
nada especial: es la misma línea de siempre, con el chat de cada uno como
`conversacion`.

Eso sí, si son muchos a la vez conviene `MODO=produccion` (Postgres): SQLite
es un archivo y no le gusta que varios procesos le escriban al mismo tiempo.

### Cosas que ya están resueltas

- **Contesta en varios mensajitos**, no en un ladrillo (`partir_respuesta`).
- **No contesta dos veces lo mismo.** Telegram reenvía cuando duda.
- **Muestra "escribiendo…"** mientras el modelo piensa.
- **Las fotos y los audios los deja pasar** sin trabarse: en Telegram todavía
  no los lee (el canal de WhatsApp, sí).
- **Un error con una persona no voltea el bot** ni deja sin respuesta al resto.

---

## Seis decisiones antes de desplegar

Si lo instalás con Claude Code, te las pregunta él y te guía en lo que
falte. Si lo hacés a mano, son estas.

**1. ¿Responde como una persona o en un solo mensaje?**

Desde el **1 de octubre de 2026, Meta cobra los mensajes que manda el
agente**, pasados los 1.000 gratis de cada mes por número. Tres globos cortos
se leen como una persona, pero son hasta tres mensajes cobrados; uno solo
cuesta, como mucho, un tercio (muchas respuestas cortas salen en un globo
igual) y se lee menos humano.

Si la gente te llega por **anuncios de clic a WhatsApp** y escribe desde el
celular, esa conversación es gratis durante 72 horas desde la primera
respuesta, y la diferencia casi no se siente. Donde pesa es en lo que entra
directo: la web, la bio, el boca a boca.

```bash
# como una persona, hasta 3 globos (va de 1 a 5)
MENSAJES_POR_RESPUESTA=3
# o todo en un solo mensaje
MENSAJES_POR_RESPUESTA=1
```

**2. ¿Tenés una tarjeta cargada en Meta?**

Sin tarjeta, pasados los 1.000 mensajes gratis del mes, Meta **deja de
entregar** lo que manda el agente. El kit no se entera (Chatwoot ya había
aceptado el mensaje) y no te manda mail. Se carga así (pasos de la ayuda
oficial de Meta):

1. Entrá al administrador de WhatsApp: https://business.facebook.com/wa/manage/home/
2. En la información general, buscá tu cuenta y hacé clic en los tres puntos.
3. **Administrar la configuración de la cuenta** → **Configuración** →
   **Configuración de pago**.
4. **Añadir método de pago**: los datos de pago, la tarjeta y los de la
   empresa, guardando en cada paso.

Meta está cambiando esta parte: la versión en inglés del mismo artículo ya
muestra otro camino, **Meta Business Suite → Configuración → la sección de
pagos (*Billing & payments*) → cuentas de mensajería (*Messaging accounts*) →
Añadir método de pago**. Si no encontrás «Configuración de pago», probá por ahí.

Hace falta permiso para administrar los pagos de esa cuenta (el dueño ya lo
tiene) y una tarjeta de crédito Visa o Mastercard: no aceptan American Express
ni PayPal. Puede que te pidan los datos fiscales de la empresa. Queda bien
cuando la tarjeta aparece en la pestaña **Configuración**.

**3. ¿Cuántos mensajes de una misma persona atiende por día?**

Hay gente que se queda charlando de cualquier cosa con el agente, y cada
respuesta se paga. Se cuentan los mensajes que **manda la persona** en esa
conversación, en las últimas 24 horas, no las respuestas: el que escribe en
ráfagas («hola» / «una consulta» / «por el precio») suma tres aunque el agente
conteste una vez. Al pasar el tope, el agente le pone la etiqueta `humano`
y se calla ahí. **No se destraba solo al otro día:** vuelve a contestar cuando alguien del equipo le saca la
etiqueta.

```bash
# 0 = sin tope
TOPE_MENSAJES_POR_DIA=50
```

Es un freno para la charla de más, no un límite de gasto: para eso, poné
también un tope de gasto en la consola del proveedor del modelo.

**4. ¿A qué mail te avisa si algo se rompe?**

Si falla el modelo (una clave vencida, sin saldo) o Chatwoot no acepta la
respuesta, **la persona que escribió no ve ningún error**: la conversación
pasa a `humano` y te llega un mail con el error. De un mismo error sale un mail
por hora como mucho, no uno por cada persona.

El mail sale de una cuenta de Google (Gmail o Workspace) **con un permiso de
Google Cloud que sirve solo para mandar**: el agente no puede leer ni borrar
nada de esa casilla, y el permiso se revoca desde tu cuenta sin cambiar
ninguna contraseña. Es gratis y no pide tarjeta. Se arma una vez:

1. **Un proyecto:** https://console.cloud.google.com/projectcreate (el nombre
   da igual, por ejemplo «agente»). Fijate que quede elegido arriba, en el
   selector de proyectos.
2. **La Gmail API habilitada:**
   https://console.cloud.google.com/apis/library/gmail.googleapis.com →
   **Habilitar**.
3. **La pantalla del permiso:** https://console.cloud.google.com/auth/overview
   → **Comenzar**. El nombre de la app es lo que vas a ver al aceptar (por
   ejemplo «Avisos del agente»), el mail de asistencia es el tuyo, y en
   **Público** (*Audience*):
   - si tu cuenta es de empresa (Google Workspace): **Interno**, y listo.
   - si es un Gmail común: **Externo**, y al terminar, en
     https://console.cloud.google.com/auth/audience → **Publicar app** →
     Confirmar. **No la dejes «En prueba»:** en prueba, Google da un permiso
     de 7 días, y el día 8 los avisos dejan de salir sin que nadie se entere.
     No hace falta mandarla a verificar.
4. **El cliente:** https://console.cloud.google.com/auth/clients → **Crear
   cliente** → tipo **App de escritorio** → Crear → **Descargar JSON**.
   Bajalo en ese momento: después Google no te vuelve a mostrar la clave.
5. **Conectá la cuenta**, en tu computadora, en la carpeta del agente:

   ```bash
   python conectar_gmail.py
   ```

   Busca el JSON en la carpeta y en Descargas (si está en otro lado, pasale
   la ruta), abre el navegador, elegís la cuenta que va a mandar los avisos y
   aceptás «Enviar correo electrónico en tu nombre». Si aparece «Google no
   verificó esta app», es la tuya: **Avanzado → Ir a … (no seguro)**. Deja en
   el `.env` tres líneas sin mostrarlas (son una llave), y te avisa si falta
   algo, como la API sin habilitar o la app en prueba.

Queda así:

```bash
AVISOS_EMAIL=vos@tuempresa.com
# estas tres las deja conectar_gmail.py
GMAIL_CLIENT_ID=…
GMAIL_CLIENT_SECRET=…
GMAIL_REFRESH_TOKEN=…
```

El permiso no vence solo. Se corta si cambiás la contraseña de esa cuenta de
Google o si le sacás el acceso en https://myaccount.google.com/connections:
para reconectar, `python conectar_gmail.py` de nuevo (ya sin el JSON: usa el
cliente que quedó en el `.env`) y copiás `GMAIL_REFRESH_TOKEN` al servidor.
Google también borra un permiso que pasa seis meses sin usarse; el agente lo
usa al arrancar y una vez por día, así que eso no pasa. Si alguna vez deja de
valer, el registro del servidor lo dice: «Los avisos por mail NO van a salir».

¿Tu mail no es de Google (Outlook, Zoho, el de tu dominio)? En vez de las
tres `GMAIL_*`, completá las `SMTP_*` con los datos de tu proveedor. Y si
dejás `AVISOS_EMAIL` vacío, todo lo demás funciona igual y el aviso queda
solo en los registros del servidor.

Después, probalo **en el servidor donde corre el agente**, antes de dar la
instalación por terminada. En Coolify, desde la terminal de la aplicación;
con Docker:

```bash
docker exec agente python probar_mail.py
```

Si el mail llega desde ahí, los avisos también. Probarlo en tu computadora
sirve para revisar los datos, pero no prueba que el servidor pueda mandar
mails. Si falla, el script te dice qué pasó y qué hacer.

**5. ¿Resolver una conversación calla al agente con esa persona?**

Si en tu equipo resolver una conversación quiere decir «con esta persona ya
terminé», el agente lo respeta: no le vuelve a hablar, aunque escriba días
después. La conversación queda con la etiqueta `humano` y aparece en tu
bandeja. Para que la vuelva a atender, reabrila y sacale la etiqueta.

Si en tu equipo se resuelve de rutina (todo lo que ya se contestó), dejalo
apagado: si no, el agente se calla con los clientes que vuelven.

```bash
# 1 = resolver calla al agente con esa persona · 0 = resolver no cambia nada
RESPETAR_RESUELTAS=1
```

Anda con las dos formas de Chatwoot, la que reabre la misma conversación y
la que abre una nueva. Para la primera, el webhook tiene que avisar también
los cambios de estado (está en «El webhook, en Chatwoot», más abajo).

**6. ¿Atiende toda la charla o solo el primer mensaje?**

Por defecto atiende toda la charla. Si preferís que el agente abra la
conversación y la siga alguien del equipo, contesta el primer mensaje y le
pone la etiqueta `humano`: desde ahí no vuelve a hablar en esa conversación.

```bash
# 0 = toda la charla · 1 = solo el primer mensaje
SOLO_EL_PRIMER_MENSAJE=0
```

---

## Lo que entiende: fotos, audios, ubicaciones

En WhatsApp la gente no solo escribe: manda audios, fotos, la ubicación,
contesta citando un mensaje. El agente convierte cada cosa en texto antes de
pensar la respuesta, y en la memoria queda ese texto:

| Llega | Lo que lee el agente |
|---|---|
| Un audio | Lo que dice, transcripto (con una clave de OpenAI) |
| Una foto o un sticker | Qué se ve, descripto por el mismo modelo del agente, y el texto que tenga abajo |
| Una ubicación | El nombre del lugar y el link al mapa |
| Un contacto compartido | El nombre y el teléfono |
| Un PDF, un archivo o un video | Que llegó, para que pregunte de qué se trata: no los abre |
| Una respuesta citando un mensaje | Lo que se citó: el texto, el audio transcripto o la foto descripta |

- **Las fotos no piden otra clave:** Claude, OpenAI y Gemini ven imágenes.
  Cada foto es una llamada al modelo; si querés que la describa uno más
  barato del mismo proveedor, ponelo en `MODELO_IMAGENES`.
- **Los audios los transcribe OpenAI**, aunque el agente use otro proveedor:
  hace falta `OPENAI_API_KEY`. Sin ella, un audio no queda sin respuesta: la
  conversación pasa a `humano` y lo atiende alguien del equipo.
- **Nada de esto frena al resto:** bajar y leer una foto o un audio pasa en
  segundo plano, y en su lugar de la ráfaga (si mandan la foto y después
  «¿cuánto sale?», el agente las lee en ese orden).
- **Solo se baja de tu Chatwoot,** con tope de tamaño. De la dirección del
  archivo se usa solo el camino y se pide siempre a `CHATWOOT_URL`.
- Si algo no se puede leer, el agente se entera y le pide a la persona que lo
  cuente; si fue un error (una clave vencida, por ejemplo), te llega por mail.

```bash
DESCRIBIR_IMAGENES=1        # 0 = las fotos no se leen: el agente pregunta qué son
TRANSCRIBIR_AUDIOS=1        # 0 = los audios pasan a una persona
MODELO_IMAGENES=            # vacío = el mismo modelo del agente
MODELO_TRANSCRIPCION=gpt-4o-mini-transcribe
```

---

## Que parezca una persona

Tres globos que caen en el mismo segundo se leen como un bot, aunque el texto
sea perfecto. Por eso:

- **Entre globo y globo hay una pausa** de lo que tardaría alguien en
  tipearlo (de 1,4 a 7 segundos), con el «escribiendo…» prendido
  (`PAUSA_ENTRE_GLOBOS=1`).
- **El visto azul y los puntitos en el celular de la persona.** Chatwoot no
  los pasa a WhatsApp: hay que pedírselos a Meta, y para eso van dos datos de
  tu cuenta de WhatsApp Business, los mismos que usa Chatwoot. Sin ellos todo
  anda igual, sin el visto. No cuentan como mensaje: Meta no los cobra.
- **Una espera antes de contestar** (apagada): un rato de silencio y después
  los puntitos, como alguien que estaba en otra cosa. Contestar al instante
  cada vez también delata al bot.

```bash
PAUSA_ENTRE_GLOBOS=1
WHATSAPP_TOKEN=               # el token de tu cuenta de WhatsApp Business en Meta
WHATSAPP_PHONE_NUMBER_ID=     # el id del número (solo dígitos: no es el teléfono)
ESPERA_SEGUNDOS=0             # la espera total antes de contestar (0 = apagada)
SILENCIO_SEGUNDOS=25          # cuánto de esa espera va sin puntitos
```

---

## Ponerlo en WhatsApp

Acá el agente pasa a atender clientes de verdad.

**El agente no le habla a Meta: le habla a Chatwoot.** Esa es la decisión que
hace que todo lo demás sea más fácil.

```
persona → WhatsApp → Meta → Chatwoot → tu webhook → el agente
                               ↑                        │
                               └──── la respuesta ──────┘
```

Qué te ahorra tener Chatwoot en el medio:

- **No necesitás el token de WhatsApp, ni el App Secret, ni verificar la firma
  HMAC de Meta.** Eso lo hace Chatwoot cuando conectás el inbox.
- Te queda la **bandeja de entrada** con el historial y el buscador.
- Una persona puede **meterse en la conversación** y seguirla a mano.
- El mismo agente atiende Instagram o el widget de la web sin tocar una línea:
  para el webhook, todo entra igual.

Lo que sí necesitás: **un servidor con dominio y HTTPS**. WhatsApp va por
webhook, así que alguien tiene que poder entrar. Esto no corre en tu compu.

### 1. Conectá WhatsApp a Chatwoot

En Chatwoot, **Configuración → Bandejas de entrada → Agregar** y elegí
WhatsApp. Seguí los pasos con los datos de tu app de Meta.

Cuando termines, mandate un mensaje al número desde tu teléfono: **si aparece
en la bandeja, esta parte ya está.** No sigas hasta que eso funcione — todo lo
demás depende de que Meta le esté entregando a Chatwoot.

### 2. Completá el `.env`

```bash
CHATWOOT_URL=https://tu-chatwoot.com
CHATWOOT_TOKEN=el-token-de-tu-perfil
CHATWOOT_CUENTA_ID=1
CHATWOOT_WEBHOOK_TOKEN=un-secreto-largo-y-al-azar
```

- **El token** sale de tu foto de perfil → *Configuración del perfil* → abajo
  de todo, **Token de acceso a la API**.
- **La cuenta** es el número que ves en la URL: `/app/accounts/1/...`
- **El secreto del webhook** generalo, no lo escribas a mano (si dejás el
  del ejemplo o uno corto, el agente no arranca):

  ```bash
  python -c "import secrets; print(secrets.token_hex(24))"
  ```

Y antes de desplegar, las [seis decisiones](#seis-decisiones-antes-de-desplegar):
cómo responde, la tarjeta en Meta, el tope de mensajes por día y el mail de
avisos.

### 3. Desplegalo

Está en [Dejarlo corriendo en un servidor](#dejarlo-corriendo-en-un-servidor).
Cuando termine, entrá a `https://tu-dominio.com/salud`. Tiene que contestar:

```json
{"estado":"ok","proveedor":"openai","modelo":"...","memoria":"postgres"}
```

**Si eso no contesta, no sigas**: el webhook que vas a cargar en el paso 4 no
va a tener a quién pegarle.

### 4. El webhook, en Chatwoot

En **Configuración → Integraciones → Webhooks → Agregar webhook**:

| Campo | Qué va |
|---|---|
| URL | `https://tu-dominio.com/chatwoot/<CHATWOOT_WEBHOOK_TOKEN>` |
| Eventos | **`message_created`**, y **`conversation_status_changed`** si elegiste que resolver calle al agente |

Dos avisos que valen el rato que ahorran:

**Marcá solo esos.** Si tildás todos, tu servidor recibe cada actualización de
contacto y de conversación para nada. El del estado hace falta para la
decisión 5: si tu bandeja reabre la misma conversación cuando alguien vuelve a
escribir, es la única forma de enterarse de que la habías resuelto.

**El token va pegado en la URL, no en un campo aparte.** Chatwoot no firma sus
webhooks —no tiene un secreto compartido como Meta—, así que esa tira en la
dirección es lo único que separa un mensaje de verdad de cualquiera que
descubra tu dominio. Si la URL no lo lleva, el agente contesta **404**; si lo
lleva mal, **401**. En los dos casos no pasa nada.

### 5. La etiqueta `humano`

En **Configuración → Etiquetas → Agregar etiqueta**, creá una que se llame
exactamente **`humano`** (o lo que hayas puesto en `CHATWOOT_ETIQUETA_HUMANO`).

Para qué sirve: se la ponés a una conversación desde la bandeja y **el agente
se calla en ese chat**. Es el traspaso a una persona, y es *el* diferencial de
tener Chatwoot — se hace con un clic, sin tocar el servidor ni reiniciar nada.
Se la sacás y el bot vuelve.

El agente también se la pone solo: **cuando algo se rompe**, **cuando
alguien pasa el tope de mensajes del día**, cuando llega un audio y no tiene
cómo escucharlo y, según lo que elegiste al instalar, cuando resolvés una
conversación o después de contestar el primer mensaje. Lo que pasó queda en
los registros del servidor, y si fue un error, te llega por mail.

Ojo con los cortes: si se vence la clave o se acaba el saldo, cada
conversación que escriba en ese rato queda con `humano`. Cuando lo arregles,
filtrá por esa etiqueta en Chatwoot y sacásela a las que quieras devolverle
al agente.

### Probalo

Escribile al número desde tu teléfono. Vas a ver la respuesta en WhatsApp y en
la bandeja de Chatwoot.

Si no contesta, mirá los registros del contenedor (en Coolify, *Logs*): cada
mensaje que entra deja una línea con el número de conversación y el texto.

Para volver a probar desde cero con la misma conversación, borrale la memoria
(el número sale de la dirección de la conversación en Chatwoot):

```bash
curl -X POST https://tu-dominio.com/reset/<CHATWOOT_WEBHOOK_TOKEN> \
     -H "Content-Type: application/json" -d '{"conversacion": "12"}'
```

De a una conversación por vez, a propósito: borrar todas de un saque, con
gente de verdad adentro, no tiene vuelta atrás.

### Lo que ya está resuelto

- **El agente no se contesta a sí mismo.** Cada respuesta suya vuelve por el
  webhook como un evento nuevo; solo se atienden los `incoming`. Sin ese
  filtro es un ida y vuelta infinito que gasta tokens en cada vuelta.
- **Junta los mensajes cortados.** "hola" / "una consulta" / "por el precio"
  es una sola respuesta, no tres (`BUFFER_SEGUNDOS`).
- **Contesta 200 al toque** y piensa después. Si tardara lo que tarda el
  modelo, Chatwoot daría el webhook por fallado y lo reintentaría — y el
  agente contestaría dos veces.
- **No repite** si Chatwoot reintenta el mismo mensaje.
- **No contesta las notas privadas**: esas son del equipo.
- **Cada conversación tiene su memoria**, con el id de Chatwoot como
  `thread_id`.
- **El cliente nunca ve un error técnico.** Te llega a vos por mail, y la
  conversación pasa a una persona.
- **Entiende fotos, audios, ubicaciones, contactos y citas**: ver
  [Lo que entiende](#lo-que-entiende-fotos-audios-ubicaciones).
- **No pisa al equipo:** justo antes de pensar la respuesta, y otra vez antes
  de mandarla, mira si alguien le puso `humano` o la resolvió mientras tanto.
- **Contesta como una persona:** pausa entre globos, y el visto azul y los
  puntitos en el celular si cargás los datos de Meta (ver
  [Que parezca una persona](#que-parezca-una-persona)).
- **Tope de mensajes por conversación y por día** (`TOPE_MENSAJES_POR_DIA`),
  para el que se queda charlando de cualquier cosa.
- **Un texto pegado enorme se recorta** a 2.000 caracteres antes de llegar al
  modelo (`LARGO_MAXIMO_DE_ENTRADA`): si no, se pagaría en ese mensaje y en
  todos los que siguen, porque queda en la memoria.
- **La clave del webhook no queda en los registros** (se ve `/chatwoot/***`),
  y si falta, es corta o es la del ejemplo, el agente no arranca. Un pedido de
  más de medio mega se descarta sin terminar de leerlo.
- **Ningún mensaje pasa los 4.096 caracteres**, el tope de WhatsApp: uno más
  largo, Meta no lo entrega.

---

## Dejarlo corriendo en un servidor

Hasta acá el agente vivía mientras tu computadora estuviera prendida. Para que
conteste siempre —desde el gimnasio, de viaje, a las 3 de la mañana— tiene que
correr en un servidor.

**Antes que nada: hay dos formas de desplegar este repo y son opuestas.** Es
lo que más confunde, así que va en una tabla:

|  | WhatsApp (`webhook_chatwoot.py`) | Telegram (`bot_telegram.py`) |
|---|---|---|
| Cómo llegan los mensajes | Chatwoot le pega a tu URL | El bot sale a buscarlos |
| ¿Dominio? | **Sí, obligatorio** | **No, y si te asignan uno, borralo** |
| ¿Puerto? | El 8000 | Ninguno |
| Chequeo de salud (*Health check*) | Prendido, en `/salud` | **Apagado** |

**El `Dockerfile` del repo corre el webhook de WhatsApp**, que es el caso que
necesita servidor de verdad. Si querés desplegar el bot de Telegram, cambiale
la última línea a `CMD ["python", "bot_telegram.py"]` y seguí la columna de la
derecha. En los dos casos: **no levanta la plataforma de pruebas.**

```bash
docker build -t agente .
docker run -d --env-file .env -p 8000:8000 --name agente agente
```

### Con Coolify (o cualquier PaaS que lea un Dockerfile)

1. Subí el código a un repositorio (privado está bien).
2. Creá una aplicación de tipo **Dockerfile** apuntando a ese repo.
3. **Ponele el dominio** que va a usar el webhook, y dejá el puerto en `8000`.
   (Si desplegás el bot de Telegram, este paso es al revés: sacale el dominio.)
4. **El chequeo de salud (*Health check*) en `/salud`**, con el puerto 8000.
5. Cargá las variables en el panel — **el `.env` no se sube al repo**:

   ```
   PROVEEDOR · OPENAI_API_KEY · MODELO_OPENAI
   MODO=produccion · POSTGRES_DSN
   CACHE · MAX_TOKENS · MEMORIA_MENSAJES · PROMPT_SISTEMA
   CHATWOOT_URL · CHATWOOT_TOKEN · CHATWOOT_CUENTA_ID
   CHATWOOT_WEBHOOK_TOKEN · CHATWOOT_ETIQUETA_HUMANO · BUFFER_SEGUNDOS
   MENSAJES_POR_RESPUESTA · TOPE_MENSAJES_POR_DIA · LARGO_MAXIMO_DE_ENTRADA
   RESPETAR_RESUELTAS · SOLO_EL_PRIMER_MENSAJE
   AVISOS_EMAIL · GMAIL_CLIENT_ID · GMAIL_CLIENT_SECRET · GMAIL_REFRESH_TOKEN
   ```

   Los tres últimos renglones son las seis decisiones: si falta
   `TOPE_MENSAJES_POR_DIA`, el agente queda sin tope; si falta
   `RESPETAR_RESUELTAS`, resolver no cambia nada, y si falta
   `AVISOS_EMAIL`, no te llega ningún mail. Las tres `GMAIL_*` las copiás
   de tu `.env` (las dejó ahí `conectar_gmail.py`). Si tu mail no es de
   Google, en su lugar van `SMTP_SERVIDOR · SMTP_PUERTO · SMTP_USUARIO ·
   SMTP_CLAVE`.

   Para que entienda audios va también `OPENAI_API_KEY` (aunque el agente use
   otro proveedor), y para el visto azul, `WHATSAPP_TOKEN` y
   `WHATSAPP_PHONE_NUMBER_ID`.

6. Desplegá, y entrá a `https://tu-dominio.com/salud` para confirmar.

**Si la base de datos está en el mismo servidor**, usá el nombre interno del
contenedor en el `POSTGRES_DSN` en vez de la IP pública: es más rápido y no
sale a internet para volver a entrar.

### Tres cosas para no comerte

**`MODO=produccion`, o vas a perder las conversaciones.** En un contenedor,
SQLite vive en el disco del contenedor, y ese disco se borra en cada despliegue.
Con Postgres la memoria sobrevive a los despliegues.

**Si el panel te dice que el contenedor está *unhealthy* pero arranca bien,
es `curl`.** El chequeo de salud de un PaaS le pega a la URL **desde adentro** del
contenedor, con `curl` o `wget`, y las imágenes `slim` de Python no traen
ninguno de los dos. El contenedor levanta, atiende perfecto, y el panel lo da
de baja igual con un *"New container is not healthy, rolling back"* que no
menciona a `curl` por ningún lado. El `Dockerfile` de este repo ya lo instala;
lo aclaramos porque se pierde un rato largo buscando el error en otro lado.

**Una sola instancia a la vez, si usás Telegram.** Si el bot queda corriendo
en el servidor *y* en tu computadora, los dos le van a preguntar a Telegram
por los mismos mensajes y se los van a repartir al azar: la mitad de las
respuestas van a salir de una máquina y la otra mitad de la otra. Apagá el
local antes. (Con WhatsApp esto no pasa: los mensajes llegan a una URL, y esa
URL es una sola.)

### Cómo actualizarlo después

```bash
git push
```

Y redesplegás desde el panel. El código nuevo entra en el próximo despliegue; la
conversación de cada persona sigue intacta, porque vive en Postgres y no en
el contenedor.

---

## Cambiar la personalidad

Editá **`prompts/sistema.md`**, guardá, y el próximo mensaje ya sale distinto.
**No hay que reiniciar nada**: el archivo se lee en cada mensaje.

Desde la web lo tenés al costado, con un botón de guardar.

Es la forma más rápida de ver qué cambia: escribí algo, cambiá el prompt,
volvé a escribir lo mismo.

---

## Usarlo desde tu código

El agente recibe texto y devuelve texto. Nada más. Eso es lo que después
permite enchufarlo a cualquier canal:

```python
import sys; sys.path.insert(0, "src")
from agente import Agente

a = Agente()

# Respuesta completa
respuesta = a.responder("Hola", conversacion="usuario-123")
print(respuesta.texto)
print(respuesta.tokens_entrada, respuesta.tokens_salida)
print(respuesta.tokens_cache_leidos)   # cuánto salió del caché

# Respuesta en vivo, mientras se escribe
transmision = a.responder_en_vivo("Contame un chiste", conversacion="usuario-123")
for pedazo in transmision:
    print(pedazo, end="", flush=True)
print(transmision.resumen.tokens_salida)

# Ya partida en varios mensajes (para mensajería)
for mensaje in a.responder_partido("Explicame cómo funciona", conversacion="usuario-123"):
    print("─", mensaje)
```

Conectarlo a Telegram o WhatsApp es escribir el pegamento que traduce
"mensaje que llega" → `a.responder(texto, conversacion=<id del chat>)` →
"mensaje que sale". **El agente no cambia.**

Un detalle que importa cuando haya muchas conversaciones a la vez: el
resumen (tokens, modelo) vive en cada `Transmision`, **no** en el agente.
Si viviera en el agente, dos personas escribiendo al mismo tiempo se
pisarían los datos.

### Agregar herramientas

Las herramientas viven en **`src/agente/herramientas.py`**. Agregar una es
escribir una función y sumarla a la lista `HERRAMIENTAS`: el grafo ya está
armado para usarlas, así que no se toca nada más.

```python
@tool
def clima(lugar: str) -> str:
    """Dice el clima que hace ahora mismo en una ciudad."""
    ...

HERRAMIENTAS = [clima]
```

**Ese docstring no es un comentario: es lo que lee el modelo** para decidir si
la herramienta le sirve. Si está mal escrito, la herramienta no se usa nunca.

---

## Todas las variables del `.env`

| Variable | Por defecto | Qué hace |
|---|---|---|
| `PROVEEDOR` | `claude` | `claude`, `openai` o `gemini` |
| `ANTHROPIC_API_KEY` | — | Tu clave de Claude |
| `OPENAI_API_KEY` | — | Tu clave de OpenAI |
| `GOOGLE_API_KEY` | — | Tu clave de Gemini |
| `MODELO_CLAUDE` | `claude-opus-5` | Qué modelo de Claude usar (el `.env.example` trae `claude-haiku-4-5`, el más barato para probar) |
| `MODELO_OPENAI` | `gpt-5` | Qué modelo de OpenAI usar |
| `MODELO_GEMINI` | `gemini-2.5-pro` | Qué modelo de Gemini usar |
| `MODO` | `test` | `test` (SQLite) o `produccion` (Postgres) |
| `SQLITE_RUTA` | `datos/conversaciones.db` | Dónde va el archivo, en modo test |
| `POSTGRES_DSN` | — | La conexión, en modo producción |
| `CACHE` | `true` | Cachear el prompt del sistema |
| `MAX_TOKENS` | `4096` | Cuánto puede escribir el agente por respuesta |
| `MEMORIA_MENSAJES` | `20` | Cuántos mensajes recuerda |
| `PROMPT_SISTEMA` | `prompts/sistema.md` | Qué archivo usar de personalidad |
| `TELEGRAM_TOKEN` | — | El token de @BotFather, para `bot_telegram.py` |

Y estas, solo si vas a atender WhatsApp con `webhook_chatwoot.py`:

| Variable | Por defecto | Qué hace |
|---|---|---|
| `CHATWOOT_URL` | — | La dirección de tu Chatwoot, con `https://` |
| `CHATWOOT_TOKEN` | — | El token de tu perfil de Chatwoot |
| `CHATWOOT_CUENTA_ID` | `1` | El número que ves en la URL de Chatwoot |
| `CHATWOOT_WEBHOOK_TOKEN` | — | El secreto que va en la URL del webhook |
| `CHATWOOT_ETIQUETA_HUMANO` | `humano` | La etiqueta que apaga al bot en una conversación |
| `BUFFER_SEGUNDOS` | `8` | Cuánto espera juntando la ráfaga antes de contestar |
| `MENSAJES_POR_RESPUESTA` | `3` | De `1` (todo en un mensaje) a `5`. `3` = como una persona, en varios globos. Meta cobra por mensaje |
| `TOPE_MENSAJES_POR_DIA` | `0` (el `.env.example` trae `50`) | Cuántos mensajes de una misma conversación atiende en 24 h antes de pasarla a `humano` (cuentan los que manda la persona, no las respuestas). `0` = sin tope |
| `LARGO_MAXIMO_DE_ENTRADA` | `2000` | Lo que entra se recorta a este largo antes de llegar al modelo |
| `RESPETAR_RESUELTAS` | `0` (el `.env.example` trae `1`) | `1` = si resolvés una conversación, el agente no le vuelve a hablar a esa persona |
| `SOLO_EL_PRIMER_MENSAJE` | `0` | `1` = contesta el primer mensaje y la conversación pasa a `humano` |
| `DESCRIBIR_IMAGENES` | `1` | Las fotos las describe el modelo del agente. `0` = no se leen: pregunta qué son |
| `MODELO_IMAGENES` | — (el del agente) | Otro modelo del mismo proveedor para describir fotos, por ejemplo uno más barato |
| `TRANSCRIBIR_AUDIOS` | `1` | Los audios los transcribe OpenAI (pide `OPENAI_API_KEY`). Sin clave o con `0`, pasan a `humano` |
| `MODELO_TRANSCRIPCION` | `gpt-4o-mini-transcribe` | El modelo de OpenAI que transcribe |
| `PAUSA_ENTRE_GLOBOS` | `1` | Entre globo y globo, lo que tardaría alguien en tipearlo |
| `ESPERA_SEGUNDOS` | `0` | Una espera antes de contestar (de 0 a 600). `0` = contesta apenas junta la ráfaga |
| `SILENCIO_SEGUNDOS` | `25` | Cuánto de esa espera va sin puntitos |
| `WHATSAPP_TOKEN` | — | El token de tu cuenta de WhatsApp Business en Meta: para el visto azul y los puntitos |
| `WHATSAPP_PHONE_NUMBER_ID` | — | El id del número en Meta (solo dígitos: no es el teléfono) |
| `AVISOS_EMAIL` | — | A quién le llega el mail cuando algo se rompe |
| `GMAIL_CLIENT_ID` | — | El cliente de Google Cloud («App de escritorio»). Lo deja `conectar_gmail.py` |
| `GMAIL_CLIENT_SECRET` | — | Su clave. Lo deja `conectar_gmail.py` |
| `GMAIL_REFRESH_TOKEN` | — | El permiso de la cuenta para mandar mails (solo mandar). Lo deja `conectar_gmail.py` |
| `SMTP_SERVIDOR` | — | Solo si tu mail no es de Google: el servidor de tu proveedor |
| `SMTP_PUERTO` | `587` | `587` (STARTTLS) o `465` (cifrado desde el arranque) |
| `SMTP_USUARIO` | — | La cuenta que manda el mail |
| `SMTP_CLAVE` | — | Su clave (los espacios no importan) |
| `PUERTO` | `8000` | Dónde escucha el webhook |

**Para atender WhatsApp no hace falta ninguna variable de Meta:** el agente le
habla a Chatwoot, y Chatwoot es el que le habla a Meta. Las dos de Meta de la
tabla (`WHATSAPP_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID`) son solo para el visto
azul y los puntitos en el celular de la persona, y son opcionales.

---

## Preguntas que aparecen siempre

**¿Necesito pagar un servidor?**
Para probarlo o para Telegram, no: corre en tu computadora y pagás solo el
consumo del modelo (Gemini tiene un plan gratis para empezar). Para WhatsApp,
sí: Chatwoot tiene que poder llegar a tu agente por internet, así que va en un
servidor con dominio y HTTPS.

**¿Funciona sin internet?**
Con estos tres proveedores no, porque el modelo corre en la nube de ellos.
Si querés 100% local, hay que cambiar `modelos.py` para que apunte a Ollama.

**¿Por qué se olvida de todo cuando cierro el programa?**
No debería: en `MODO=test` guarda en un archivo y sobrevive al reinicio.
Si estás usando `ram()` a mano, eso sí se borra.

**¿Cuánto sale?**
Depende del modelo y de cuánto hables. La web te muestra los tokens de cada
mensaje. Tres formas de gastar menos, de mayor a menor impacto:
1. Usar un modelo más chico (los "mini" / "haiku" salen mucho menos)
2. Bajar `MEMORIA_MENSAJES`
3. Dejar `CACHE=true` (ya viene así)

En WhatsApp se suma lo de Meta: pasados los 1.000 mensajes gratis del mes,
cada mensaje que manda el agente se paga. Ahí las palancas son
`MENSAJES_POR_RESPUESTA=1` y el tope por conversación (`TOPE_MENSAJES_POR_DIA`).
Para WhatsApp alcanza con `MAX_TOKENS=1024`: una respuesta de chat no necesita
más, y lo que escribe el agente también queda en la memoria. Y poné un tope
de gasto en la consola del proveedor del modelo: es el único freno que no
depende del agente.

**Me tira un error y no entiendo.**
La web muestra el error tal cual viene del proveedor, sin esconderlo. Los tres
motivos habituales:
- La clave está mal pegada (le sobra un espacio o le falta un pedazo)
- El nombre del modelo en el `.env` no existe → elegilo de la lista
- No tenés saldo en la cuenta del proveedor

**¿Por qué el mail va con Google Cloud y no con una contraseña de aplicación?**
Por lo que queda en el servidor. Una contraseña de aplicación abre la casilla
entera: quien la tenga puede leer todo tu mail. El permiso de Google Cloud
sirve solo para mandar (`gmail.send`): si alguien se lleva las variables del
servidor, no puede leer ni un mail. Y se revoca desde tu cuenta de Google sin
cambiar ninguna contraseña.

**¿Puedo usarlo con Claude Code?**
Sí, y con Codex y Cursor también. El archivo **`AGENTS.md`** lo leen solos:
les explica la arquitectura, dónde tocar cada cosa, las convenciones y las
trampas del código. Abrí el agente que uses en la carpeta y pedile lo que
quieras.

---

## Con qué está hecho

[LangChain](https://python.langchain.com) + [LangGraph](https://langchain-ai.github.io/langgraph/)
para el agente y la memoria · [FastAPI](https://fastapi.tiangolo.com) para la
plataforma de pruebas · Python 3.10 o más nuevo.

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/img/logo-blanco.png">
    <img src="docs/img/logo-negro.png" alt="Basdonax AI" width="72">
  </picture>
  <br>
  Hecho por <a href="https://basdonax.com">Basdonax AI</a>
</p>

---
name: actualizar-agente-whatsapp
description: Adapta el agente de IA de WhatsApp al cobro por mensaje que Meta aplica desde el 1 de octubre de 2026, esté donde esté — armado en n8n con un nodo «Format Chain», en código con el Agent Kit, o todavía sin agente. Explica qué cambia, pregunta cómo querés que responda (como una persona en varios mensajes o todo en uno), guía para cargar la tarjeta en Meta y hace el cambio en n8n por su API, o te guía para hacerlo a mano. Usar cuando digan "actualizá mi agente", "actualizá mi agente de WhatsApp", "lo del cobro de Meta", "Meta cobra por mensaje", "la Format Chain nueva", "cómo cargo la tarjeta en Meta", "mi agente manda muchos mensajes".
---

# Actualizar el agente de WhatsApp al cobro de Meta

Cada persona que usa esta skill está en un punto distinto: unos tienen el agente en n8n, otros en código, otros todavía no lo armaron. **No asumas: preguntá dónde está y seguí el camino que corresponde.**

**Las rutas de esta skill** (`scripts/…`, `referencias/…`) son relativas a la carpeta de la skill: Claude Code te la muestra al cargarla («Base directory for this skill»). Los comandos se corren **desde la carpeta del proyecto** (ahí se busca el archivo de acceso a n8n), con la ruta completa al script:

```bash
python "<carpeta de la skill>/scripts/n8n_format_chain.py" buscar
```

En Mac puede ser `python3` en vez de `python`.

## Paso 0 · Qué cambia (contáselo así, antes de tocar nada)

> Desde el **1 de octubre de 2026, Meta cobra los mensajes que manda tu agente** por WhatsApp. Cada número tiene **1.000 mensajes gratis por mes** para contestar; después se paga cada uno.
>
> Si tu agente contesta en tres mensajes cortos para parecer una persona, son **hasta tres mensajes cobrados**. Lo que entra por un **anuncio de clic a WhatsApp**, si la persona escribe desde el celular, es gratis durante 72 horas desde la primera respuesta, se manden los mensajes que se manden.
>
> Y lo más importante: **sin una tarjeta cargada en Meta, pasados los 1.000 del mes los mensajes del agente dejan de llegar, y el agente no se entera.**

## Reglas que no se rompen

- **La clave de API de n8n no pasa por el chat.** La escribe la persona en su archivo (Paso 4). No la pidas, no la leas, no la muestres y no la pongas en una línea de comando: queda guardada en la conversación y en el historial. Si la persona la pega igual en el chat, decile que la borre en n8n y cree otra.
- **Antes de cambiar un flujo, respaldo.** El script lo hace solo, en la carpeta `respaldos-n8n` del usuario (fuera del proyecto); si algo sale mal, `restaurar` lo deja como estaba.
- **No prendas ni apagues flujos, y no toques otros nodos.** Solo cambia el código del nodo «Format Chain».
- **Una Format Chain con cambios propios no se reemplaza entera:** se le agrega solo la elección, sin tocar sus filtros.
- **Las decisiones son de la persona.** Preguntá y explicá; no elijas vos por ella.

## Paso 1 · Dónde está el agente

**Preguntá siempre primero, aunque la carpeta parezca decirlo:**

> *«¿Tu agente de WhatsApp está armado en n8n, en código (el Agent Kit) o todavía no lo tenés?»*

Esta carpeta puede ser el Agent Kit recién bajado solo para usar esta skill, así que su contenido no alcanza para saber dónde está el agente.

1. **En n8n** → Paso 2, 3, 4 y 5A.
2. **En el Agent Kit** (su propia carpeta, con `AGENTS.md`, `src/agente/` y su `.env`) → Paso 2, 3 y **5B**.
3. **Todavía no tiene agente** → solo el Paso 0 y el Paso 3 (la tarjeta). Que arranque ya con la elección hecha.

## Paso 2 · Cómo querés que responda

Preguntá, con esta explicación:

> **¿Querés que tu agente responda como una persona, en varios mensajes cortos, o todo en un solo mensaje?**
>
> Varios mensajes cortos se leen más humanos, pero cada uno se cobra. Uno solo cuesta menos y se lee más como un bot. Si casi toda tu gente te llega por anuncios de clic a WhatsApp, la diferencia de plata es chica: elegí lo que mejor se lea.

- **Como una persona** → `FORMA_DE_RESPONDER = 'humano'`. Preguntá el máximo de mensajes por respuesta (de 1 a 5; si no sabe, **3**).
- **Un solo mensaje** → `FORMA_DE_RESPONDER = 'un_mensaje'`. El máximo no cuenta.

En los dos casos ningún mensaje pasa los 4.096 caracteres (el tope de WhatsApp): uno más largo Meta no lo entrega.

## Paso 3 · La tarjeta en Meta

Preguntá: *«¿Tenés una tarjeta cargada en tu cuenta de WhatsApp Business de Meta?»*

Si no sabe, que se fije con los pasos 1 a 3 de abajo: si en la pestaña **Configuración** ya aparece una tarjeta, está. Si no la tiene, guialo **paso por paso, esperando que confirme cada uno** (son los pasos de la ayuda oficial de Meta):

1. Entrá al **Administrador de WhatsApp**: https://business.facebook.com/wa/manage/home/
2. En la **información general**, buscá tu cuenta y hacé clic en los **tres puntos**.
3. **Administrar la configuración de la cuenta** → pestaña **Configuración** → **Configuración de pago**.
4. **Añadir método de pago** → completá la información de pago → **Siguiente**.
5. Poné los datos de la tarjeta → **Guardar** → completá los datos de la empresa → **Guardar**.

Si no le aparece «Configuración de pago», probá primero el camino nuevo: Meta está cambiando esta parte y la versión en inglés de la ayuda ya dice **Meta Business Suite → Configuración → la sección de pagos (*Billing & payments*) → cuentas de mensajería (*Messaging accounts*) → Añadir método de pago**. Si tampoco está ahí, le falta el permiso: tiene que pedírselo al dueño del portfolio comercial.

Lo que hace falta: permiso para administrar los pagos de esa cuenta (el dueño ya lo tiene) y una tarjeta de crédito **Visa o Mastercard** (no aceptan American Express ni PayPal). Puede que pidan los datos fiscales de la empresa.

**Al final, verificá con la persona que la tarjeta aparece en la pestaña Configuración.**

## Paso 4 · Conectar con n8n (solo si el agente está en n8n)

**¿Ya está conectado?** Probá, desde la carpeta del proyecto:

```bash
python "<carpeta de la skill>/scripts/n8n_format_chain.py" buscar
```

El script busca la conexión solo: en el entorno (`N8N_API_URL` y `N8N_API_KEY`), en el archivo `n8n-acceso.env` de la carpeta del proyecto, o en el `.mcp.json` si hay un MCP de n8n configurado. **No abras ni muestres esos archivos**: el script los lee por su cuenta. Si contesta con la lista (o con «no encontré»), ya está: Paso 5A.

**Si no está conectado, ofrecé las dos formas:**

**A. Con una clave de API de n8n** (lo más rápido). Explicale cómo crearla:

1. En n8n, abajo a la izquierda: tu usuario → **Settings** (Configuración) → **n8n API**.
2. **Create an API key**. Nombre: `actualizar agente`. En *Expiration*, **el plazo más corto que te ofrezca**: la usás hoy. Esta clave abre todo tu n8n, así que al terminar la borramos desde la misma pantalla.
3. Copiala: **se ve una sola vez**. No me la pegues acá.

Después creá vos el archivo `n8n-acceso.env` en la carpeta del proyecto, con la dirección (si la persona te la dice, podés dejarla escrita) y un lugar para la clave:

```
N8N_API_URL=https://n8n.tuempresa.com
N8N_API_KEY=pegá-acá-tu-clave
```

Pedile que lo abra en su editor, pegue la clave en lugar de `pegá-acá-tu-clave` y guarde. **No vuelvas a leer ese archivo.** Si el proyecto tiene `.gitignore`, sumale la línea `n8n-acceso.env` antes de seguir (en el Agent Kit ya está), para que la clave no se suba nunca.

La dirección tiene que empezar con **`https://`**: el script no manda la clave sin cifrar (solo acepta `http` si n8n corre en la misma máquina). Si su n8n está en `http://una-ip:5678`, primero hay que ponerle un dominio con HTTPS; mientras tanto, usá la forma B.

Si en Settings no aparece «n8n API» (pasa en la prueba gratis de n8n Cloud), se hace a mano: **Paso 6**.

**B. Si prefiere no crear una clave** → **Paso 6**, a mano, guiado.

## Paso 5A · El cambio en n8n, con la API

1. **Buscá** los flujos con Format Chain y mostrale la lista a la persona:
   ```bash
   python "<carpeta de la skill>/scripts/n8n_format_chain.py" buscar
   ```
   Confirmá con ella cuáles son: el del agente y, si tiene, el del **agente paralelo** (otro flujo con su propia Format Chain). Los dos llevan el mismo cambio.

   **Si no encuentra ninguno**, su agente no usa ese nodo. Preguntale cuál es el nodo que parte la respuesta antes de mandarla a Chatwoot o a WhatsApp (suele ser un nodo de código antes del envío) y, con el código que te pegue, seguí como si fuera una Format Chain con cambios propios (punto 2, segundo caso). Si no tiene ninguno que parta la respuesta, ya manda un solo mensaje: no hay nada que cambiar, solo la tarjeta.

2. **Según lo que diga `buscar` de cada nodo:**

   - **`v3.2 genérica` o `ya es la v4`** → se aplica directo (respalda solo antes):
     ```bash
     python "<carpeta de la skill>/scripts/n8n_format_chain.py" aplicar --flujo ID --forma humano --maximo 3
     python "<carpeta de la skill>/scripts/n8n_format_chain.py" aplicar --flujo ID --forma un_mensaje
     ```
   - **`tiene cambios propios`** → no se reemplaza entera:
     1. `respaldar --flujo ID` (dice dónde lo guardó).
     2. Del respaldo, sacá el código del nodo (`nodes` → el nodo Format Chain → `parameters.jsCode`) a `format_chain_propia.js`, en la carpeta del proyecto (sumá esa línea al `.gitignore` si el proyecto tiene uno: es código del negocio).
     3. **Agregale solo la elección**, sin tocar sus filtros ni cómo lee el texto. Tomá como modelo `referencias/format_chain_v4.js`: las dos constantes de arriba con su comentario, el tope de mensajes en `clampToCap`, `partirPorTope` y `dentroDelTope` para los 4.096 caracteres, y el camino de `un_mensaje` (todo en `part_1`). La salida tiene que seguir siendo `response.part_1` a `part_5`.
     4. Probala: `node "<carpeta de la skill>/scripts/probar_format_chain.js" format_chain_propia.js` tiene que terminar en **«Todo bien»**. Corre el código encerrado: no puede tocar archivos ni lanzar programas. Si no hay `node` (o es más viejo que el 20), decilo y revisá el código dos veces con la persona antes de subir.
     5. `subir --flujo ID --archivo format_chain_propia.js`

   El script no prende ni apaga flujos. Si el flujo **estaba prendido**, además lo publica (en los n8n nuevos guardar deja un borrador y el agente seguiría con el código viejo). Si no lo puede publicar, lo dice: ahí la persona toca «Publish» en n8n.

3. **Verificá:** `verificar --flujo ID`

4. **Si algo sale mal:** `restaurar --flujo ID --archivo <el respaldo>.json`. Tiene que ser el mismo flujo del respaldo; antes de pisar, respalda lo que haya.

## Paso 5B · El Agent Kit (el agente en código)

1. **¿Ya está al día?** Si `src/agente/__init__.py` dice `__version__ = "1.1.0"` o más, y el `AGENTS.md` tiene la sección «Al instalar», ya tiene la versión nueva: seguí directo al punto 5.
2. **Cuidá lo suyo antes de traer nada:** el `.env` (no se sube, pero no lo pises) y **`prompts/sistema.md`** (la personalidad de su agente): copialo a un lugar seguro fuera de la carpeta.
3. **Traé la versión nueva del mismo lugar de donde la sacó** (`git remote -v` dice cuál). Con git: guardá sus cambios, `git pull`, y si hay conflicto en `prompts/sistema.md` quedate con **el suyo**. Sin git: bajá la versión nueva y copiá todo **menos** `.env`, `prompts/sistema.md` y la carpeta `datos/`.
4. `pip install -r requirements.txt` y, si tiene pytest, `pytest`.
5. **Seguí la sección «Al instalar» de su `AGENTS.md`**: ahí están las preguntas (cómo responde, la tarjeta, el tope de mensajes por día, el mail de avisos) y la prueba del mail (`python probar_mail.py`), que se hace donde corre el agente.
6. **En el servidor:** sumá las variables nuevas a las de la aplicación (en Coolify: la app → *Environment Variables*; la lista completa está en el README, «Con Coolify»), desplegá de nuevo y confirmá que `https://su-dominio/salud` contesta. Ojo: si su `CHATWOOT_WEBHOOK_TOKEN` es corto (menos de 32 caracteres), la versión nueva no arranca: generá uno nuevo y cambiá la dirección del webhook en Chatwoot.
7. **Si el código es propio, no el Agent Kit:** buscá dónde se parte la respuesta antes de mandarla y agregá la misma elección (varios mensajes con un máximo, o uno solo, y nunca más de 4.096 caracteres por mensaje).

## Paso 6 · A mano dentro de n8n (sin clave de API)

Guialo esperando que confirme cada paso:

1. Abrí n8n y entrá al flujo de tu agente de WhatsApp.
2. **Duplicalo primero:** los tres puntos arriba a la derecha → *Duplicate*. Ese duplicado es tu respaldo; dejalo apagado.
3. Volvé al flujo original y hacé doble clic en el nodo **«Format Chain»**.
4. Mirá la primera línea del código:
   - Si dice **`Format Chain v3.2`** y nunca lo tocaste: borrá todo el código y pegá el de `referencias/format_chain_v4.js`. Copiáselo al portapapeles: en Windows `Get-Content "<carpeta de la skill>/referencias/format_chain_v4.js" -Raw -Encoding UTF8 | Set-Clipboard` (sin `-Encoding UTF8`, PowerShell desfigura las tildes de los comentarios); en Mac `pbcopy < "<carpeta de la skill>/referencias/format_chain_v4.js"`.
   - Si **le hiciste cambios**: no lo borres. Pegame acá tu código, te lo devuelvo con la elección agregada y probado (Paso 5A, punto 2), y lo pegás.
5. Arriba de todo, elegí: `FORMA_DE_RESPONDER` (`'humano'` o `'un_mensaje'`) y `MAXIMO_DE_MENSAJES`.
6. Cerrá el nodo y **guardá** el flujo (*Save* o Ctrl+S).
7. **Si tu n8n tiene el botón «Publish»** arriba (las versiones nuevas), tocalo: guardar solo deja un borrador, y hasta que publicás el agente sigue con el código viejo. En las versiones anteriores no hace falta: con guardar alcanza.
8. Si tenés el **agente paralelo** (otro flujo con su propia Format Chain), repetí ahí.

## Paso 7 · El cierre

1. **La prueba de verdad:** que se mande un WhatsApp a su propio número preguntando algo que tenga una respuesta larga. ¿Llegó como eligió?
2. **Si no llega nada:** en n8n, *Executions* del flujo muestra el error. Si hace falta, volvé atrás (`restaurar`, o el duplicado del Paso 6).
3. **La tarjeta:** si no quedó cargada, recordale que sin ella, pasados los 1.000 del mes, los mensajes del agente dejan de llegar.
4. **La clave de n8n:** si creó una para esto, que la borre (Settings → n8n API) y que borre el archivo `n8n-acceso.env`.
5. **El resumen para la persona:** qué eligió, qué flujos se cambiaron, dónde quedó el respaldo y cómo se vuelve atrás.

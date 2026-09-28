# Actualizar el agente de WhatsApp al cobro de Meta

Desde el **1 de octubre de 2026, Meta cobra los mensajes que manda tu agente** de WhatsApp, pasados los 1.000 gratis de cada mes (por número). Esta skill le enseña a Claude Code a adaptar tu agente, esté donde esté:

- **En n8n**, con el nodo «Format Chain»: lo cambia por su API, o te guía para hacerlo a mano.
- **En código**, con el Agent Kit: trae la versión nueva sin pisar tu configuración.
- **Si todavía no tenés agente:** te explica qué cambia y te ayuda a dejar la tarjeta cargada.

Te pregunta cómo querés que responda (como una persona, en varios mensajes cortos, o todo en uno solo) y te guía para cargar la tarjeta en Meta: **sin tarjeta, pasados los 1.000 mensajes del mes, los mensajes del agente dejan de llegar, y el agente no se entera.**

## Cómo se usa

**Desde este repo:** abrí la carpeta del repo con Claude Code y decile:

> **actualizá mi agente de WhatsApp**

**Desde tu propio proyecto:** copiá esta carpeta entera adentro de `.claude/skills/` de tu proyecto. Tiene que quedar así:

```
tu-proyecto/
└── .claude/
    └── skills/
        └── actualizar-agente-whatsapp/
            ├── SKILL.md
            ├── LEEME.md
            ├── referencias/
            └── scripts/
```

Y abrí Claude Code en la carpeta de tu proyecto con el mismo pedido. Te va preguntando y explicando cada paso.

## Qué necesitás

- **Claude Code.**
- **Python 3** para el cambio por la API de n8n (en Mac puede llamarse `python3`). No hay que instalar nada más.
- **Node 20 o más nuevo** es opcional: sirve para probar el código antes de subirlo, encerrado, sin que pueda tocar tus archivos.
- Si tu agente está en n8n y querés que lo haga Claude Code: la dirección de tu n8n (con `https://`) y una clave de su API. **La clave la cargás vos** en un archivo que no se sube a ningún lado; Claude Code no la ve. Si preferís no crear una clave, te guía para hacerlo a mano.

## Qué hay adentro

| | |
|---|---|
| `SKILL.md` | Lo que sigue Claude Code, paso a paso |
| `referencias/format_chain_v4.js` | La Format Chain nueva, con la elección arriba de todo |
| `referencias/format_chain_v3_2.js` | La anterior: sirve para reconocer si la tuya está sin cambios |
| `scripts/n8n_format_chain.py` | Busca, respalda, cambia y verifica el nodo en n8n. Con `--help` te muestra cómo |
| `scripts/probar_format_chain.js` | Prueba el código del nodo antes de subirlo |

Antes de cambiar un flujo, siempre queda un respaldo en la carpeta `respaldos-n8n` de tu usuario (fuera de tu proyecto: son flujos enteros y no se tienen que subir a ningún lado). Si algo sale mal, se vuelve atrás con `restaurar`.

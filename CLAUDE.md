# CLAUDE.md

El contexto de este proyecto está en **[AGENTS.md](AGENTS.md)** — el mismo
archivo que leen Codex, Cursor y los demás. Está en un solo lugar a
propósito: así no se desincroniza.

**Leé `AGENTS.md` antes de tocar nada.**

**Si te piden instalarlo o desplegarlo para WhatsApp**, antes de completar el
`.env` hacé las seis preguntas de la sección «Al instalar» de `AGENTS.md`.
Son decisiones de la persona, no tuyas: no las llenes con el valor por defecto.
Lo que no tenga hecho (la tarjeta en Meta, el mail de avisos con Google
Cloud), guialo hasta que quede hecho. La cuenta de Google se conecta con
`python conectar_gmail.py` en su computadora: **no leas ni muestres los
valores que deja en el `.env`**. Cerrá con `python probar_mail.py` corrido
donde corre el agente (en el servidor).

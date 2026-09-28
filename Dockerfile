# El agente atendiendo WhatsApp, en un servidor.
#
# Corre `webhook_chatwoot.py`: un servidor que espera a que Chatwoot le pegue
# cuando llega un mensaje. A diferencia del bot de Telegram (que sale a buscar
# los mensajes y no abre ningún puerto), este SÍ escucha en un puerto y
# necesita dominio con HTTPS, porque acá entra alguien de afuera.
#
# El bot de Telegram también queda adentro de la imagen: si algún día querés
# correr ese en vez de este, se cambia el CMD y nada más.
#
# Toda la configuración entra por variables de entorno. El .env no se copia
# acá adentro: en el servidor las variables las pone Coolify.

FROM python:3.13-slim

# Sin esto, Python se guarda los logs en un buffer y en el panel del servidor
# no ves nada hasta que el proceso muere. Con un servidor que corre para
# siempre, eso es no ver nunca nada.
ENV PYTHONUNBUFFERED=1

# Que las tildes no rompan cuando se imprime un mensaje.
ENV PYTHONIOENCODING=utf-8

WORKDIR /app

# curl es para el health check del panel, no para la app.
#
# Coolify (y casi cualquier PaaS) revisa que el contenedor esté vivo pegándole
# a una URL con curl o wget DESDE ADENTRO del contenedor. La imagen `slim` no
# trae ninguno de los dos, así que sin esta línea el contenedor arranca bien,
# atiende bien, y el panel igual lo marca *unhealthy* y lo da de baja. El log
# que deja es "New container is not healthy, rolling back": no dice que falte
# curl, y se pierde un rato largo buscando el error en otro lado.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias primero y el código después: así, mientras no toques los
# requirements, Docker reusa la capa ya instalada y el deploy tarda segundos
# en vez de minutos.
COPY requirements.txt requirements-produccion.txt ./
RUN pip install --no-cache-dir -r requirements-produccion.txt

COPY src/ ./src/
COPY prompts/ ./prompts/
COPY webhook_chatwoot.py bot_telegram.py probar_mail.py ./

# Sin esto corre como root sin necesidad. Y el usuario es dueño solo de
# datos/ (el SQLite, si alguien lo corre en modo test): el código y el
# prompt quedan de solo lectura para el proceso, así que ni él ni alguien
# que lo engañe puede reescribirlos.
RUN useradd --create-home agente && mkdir -p /app/datos && chown -R agente:agente /app/datos
USER agente

# El puerto donde escucha. Coolify lee este número para saber a dónde
# mandarle el tráfico del dominio.
ENV PUERTO=8000
EXPOSE 8000

CMD ["python", "webhook_chatwoot.py"]

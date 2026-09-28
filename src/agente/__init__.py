"""Un agente de IA en local, sin servidor y sin humo."""

from __future__ import annotations

from .agente import Agente, Respuesta, Transmision
from .canales import Canal, MensajeEntrante
from .config import Config, ErrorDeConfiguracion, proveedores_disponibles
from .modelos import crear_modelo
from .respuesta import partir_respuesta

__version__ = "1.1.0"

__all__ = [
    "Agente",
    "Canal",
    "Config",
    "ErrorDeConfiguracion",
    "MensajeEntrante",
    "Respuesta",
    "Transmision",
    "crear_modelo",
    "partir_respuesta",
    "proveedores_disponibles",
]

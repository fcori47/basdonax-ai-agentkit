"""Pruebas del actualizador de agentes en n8n (.claude/skills/actualizar-agente-whatsapp).

Corre las pruebas de la skill contra un n8n de MENTIRA que levanta en un
hilo: estricto como el real (un PUT con un campo de más da 400, la lista de
flujos pagina). No toca ningún n8n de verdad, no gasta tokens.

    pytest tests/test_actualizador_n8n.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests" / "actualizador"))

import probar_todo  # noqa: E402


def test_el_actualizador_pasa_todas_sus_pruebas():
    """Buscar, respaldar, aplicar, subir, verificar y restaurar, contra el n8n de mentira."""
    assert probar_todo.main() == 0, "hay pruebas del actualizador que fallan: mirá la salida"


def test_la_format_chain_suelta_es_la_misma_que_usa_el_actualizador():
    """Son dos copias a propósito (una para pegar a mano, otra para la skill).

    Si alguien toca una y no la otra, el que la pega a mano y el que usa
    Claude Code terminan con agentes distintos.
    """
    suelta = (RAIZ / "n8n" / "format_chain_v4.js").read_bytes()
    de_la_skill = (
        RAIZ / ".claude" / "skills" / "actualizar-agente-whatsapp" / "referencias" / "format_chain_v4.js"
    ).read_bytes()
    assert suelta == de_la_skill

"""Pruebas de cómo se lee y se guarda el prompt del sistema."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agente.prompts import PROMPT_DE_EMERGENCIA, guardar_prompt, leer_prompt  # noqa: E402


def test_lee_el_prompt_del_archivo(tmp_path):
    ruta = tmp_path / "sistema.md"
    ruta.write_text("Sos un asistente de pruebas.", encoding="utf-8")

    assert leer_prompt(ruta) == "Sos un asistente de pruebas."


def test_si_no_existe_el_archivo_usa_el_de_emergencia(tmp_path):
    assert leer_prompt(tmp_path / "no-existe.md") == PROMPT_DE_EMERGENCIA


def test_si_el_archivo_esta_vacio_usa_el_de_emergencia(tmp_path):
    ruta = tmp_path / "vacio.md"
    ruta.write_text("   \n  ", encoding="utf-8")

    assert leer_prompt(ruta) == PROMPT_DE_EMERGENCIA


def test_guardar_crea_las_carpetas_que_falten(tmp_path):
    ruta = tmp_path / "una" / "carpeta" / "que" / "no" / "existe" / "sistema.md"

    guardar_prompt(ruta, "Personalidad nueva")

    assert leer_prompt(ruta) == "Personalidad nueva"


def test_guardar_le_saca_los_espacios_de_mas(tmp_path):
    ruta = tmp_path / "sistema.md"

    guardar_prompt(ruta, "  con espacios de sobra  \n\n")

    assert ruta.read_text(encoding="utf-8") == "con espacios de sobra\n"

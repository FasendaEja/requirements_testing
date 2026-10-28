# -*- coding: utf-8 -*-
"""Конфигурация утилиты (значения по умолчанию согласно техническому заданию)."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MODEL = "qwen3.8"        # модель согласно заданию
DEFAULT_TEMPERATURE = 0.1        # согласно заданию
DEFAULT_MAX_TOKENS = 200000      # согласно заданию

# Корень проекта: .../src/req_tester/config.py -> parents[2] == корень
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_PROMPT_FILE = PROJECT_ROOT / "prompt.txt"

# Поддерживаемые форматы файлов требований
SUPPORTED_EXTS = {".doc", ".docx", ".md", ".pdf", ".txt", ".xlsx", ".xml", ".json"}

# Лимит на объём текста одного файла, отправляемый в модель (символов).
MAX_CHARS_PER_FILE = 400_000

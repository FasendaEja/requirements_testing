# -*- coding: utf-8 -*-
"""Общие фикстуры для тестов."""

import sys
from pathlib import Path

# Делаем пакет src/req_tester импортируемым без установки проекта
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

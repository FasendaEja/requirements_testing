#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точка входа для запуска утилиты без установки пакета: python run.py [опции]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from req_tester.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Рекурсивное сканирование входной папки и сбор файлов требований."""

from __future__ import annotations

from pathlib import Path

from .config import SUPPORTED_EXTS
from .extractors import extract_text


def collect_files(input_dir: Path) -> list[Path]:
    """Рекурсивный сбор файлов поддерживаемых форматов из input_dir."""
    return sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def collect_files_with_text(input_dir: Path,
                            verbose: bool = True) -> list[tuple[Path, str]]:
    """Собирает файлы и извлекает их текстовое содержимое.

    Возвращает список пар (относительный_путь, текст).
    """
    results: list[tuple[Path, str]] = []
    for f in collect_files(input_dir):
        rel = f.relative_to(input_dir)
        text = extract_text(f)
        if verbose:
            chars = len(text.strip())
            status = f"{chars} симв." if chars else "ПУСТО/без текста"
            print(f"  • {rel} [{f.suffix.lower()}] — {status}")
        results.append((rel, text))
    return results

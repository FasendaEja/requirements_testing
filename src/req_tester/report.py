# -*- coding: utf-8 -*-
"""Формирование и сохранение файла результатов тестирования требований."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

REPORT_NAME_TEMPLATE = "тестирование требований_{timestamp}.md"


def make_output_path(output_dir: Path, now: datetime | None = None) -> Path:
    """Путь отчёта вида «тестирование требований_<дата_время>.md»."""
    now = now or datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / REPORT_NAME_TEMPLATE.format(timestamp=timestamp)


def build_report(*, files_texts: list[tuple[Path, str]], sections: list[str],
                 errors: list[str], model: str, temperature: float,
                 max_tokens: int, prompt_file: Path, input_dir: Path) -> str:
    """Собирает итоговый текст отчёта (шапка + ответы ИИ + ошибки)."""
    parts = [
        "# Тестирование требований — результаты",
        "",
        f"- Дата/время выполнения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Модель: {model} (temperature={temperature}, max_tokens={max_tokens})",
        f"- Файл промпта: {prompt_file}",
        f"- Входная папка: {input_dir}",
        f"- Обработано файлов: {len(files_texts)}",
        "",
        "## Список исходных файлов",
        *[f"- {rel}" for rel, _ in files_texts],
        "",
        "---",
        "",
    ]
    parts.extend(sections)
    if errors:
        parts += ["", "## Ошибки выполнения", *[f"- {err}" for err in errors]]
    return "\n".join(parts)


def save_report(path: Path, content: str) -> Path:
    """Записывает отчёт в файл (UTF-8) и возвращает путь."""
    path.write_text(content, encoding="utf-8")
    return path

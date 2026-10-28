# -*- coding: utf-8 -*-
"""Тесты формирования имени и содержимого файла результатов."""

from datetime import datetime
from pathlib import Path

from req_tester.report import build_report, make_output_path, save_report


def test_output_name_has_date_and_time(tmp_path: Path):
    now = datetime(2026, 10, 28, 15, 30, 0)
    out = make_output_path(tmp_path / "out", now)
    assert out.name == "тестирование требований_2026-10-28_15-30-00.md"
    assert out.parent.exists()


def test_build_report_sections(tmp_path: Path):
    report = build_report(
        files_texts=[(Path("a.md"), "текст")],
        sections=["ОТВЕТ ИИ"],
        errors=["RuntimeError: boom"],
        model="qwen3.8", temperature=0.1, max_tokens=200000,
        prompt_file=tmp_path / "prompt.txt", input_dir=tmp_path,
    )
    assert "ОТВЕТ ИИ" in report
    assert "qwen3.8" in report and "temperature=0.1" in report and "max_tokens=200000" in report
    assert "- a.md" in report and "boom" in report


def test_save_report(tmp_path: Path):
    p = tmp_path / "r.md"
    save_report(p, "содержимое")
    assert p.read_text(encoding="utf-8") == "содержимое"

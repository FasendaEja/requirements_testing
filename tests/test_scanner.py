# -*- coding: utf-8 -*-
"""Тесты рекурсивного сканирования папки input."""

from pathlib import Path

from req_tester.scanner import collect_files, collect_files_with_text


def test_collect_recursive(tmp_path: Path):
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "a.md").write_text("REQ-1", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("REQ-2", encoding="utf-8")
    (tmp_path / "sub" / "deep" / "c.json").write_text('{"t": "REQ-3"}', encoding="utf-8")
    (tmp_path / "ignore.exe").write_text("no", encoding="utf-8")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert names == {"a.md", "b.txt", "c.json"}


def test_collect_files_with_text(tmp_path: Path):
    (tmp_path / "x.md").write_text("# Требование X", encoding="utf-8")
    pairs = collect_files_with_text(tmp_path, verbose=False)
    assert len(pairs) == 1
    rel, text = pairs[0]
    assert str(rel) == "x.md" and "Требование X" in text

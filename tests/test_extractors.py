# -*- coding: utf-8 -*-
"""Тесты извлечения текста из файлов поддерживаемых форматов."""

import json
from pathlib import Path

import pytest

from req_tester.extractors import (extract_json, extract_plain, extract_text,
                                   extract_xml)

SAMPLES = Path(__file__).resolve().parents[1] / "input"


def test_extract_md_sample():
    text = extract_plain(SAMPLES / "example" / "requirements_sample.md")
    assert "FR-001" in text


def test_extract_json(tmp_path: Path):
    p = tmp_path / "req.json"
    p.write_text(json.dumps({"req": [{"id": "FR-1", "text": "Система должна логировать"}]},
                            ensure_ascii=False), encoding="utf-8")
    out = extract_json(p)
    assert "Система должна логировать" in out


def test_extract_json_invalid_returns_raw(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert extract_json(p) == "{not valid json"


def test_extract_xml(tmp_path: Path):
    p = tmp_path / "req.xml"
    p.write_text("<requirements><req id='FR-1'>Требование один</req></requirements>",
                 encoding="utf-8")
    out = extract_xml(p)
    assert "Требование один" in out and "FR-1" in out


def test_extract_plain_cp1251(tmp_path: Path):
    p = tmp_path / "req.txt"
    p.write_bytes("Требование: система должна отвечать".encode("cp1251"))
    assert "Требование" in extract_plain(p)


def test_extract_text_unknown_ext_does_not_crash(tmp_path: Path):
    p = tmp_path / "file.unknown"
    p.write_text("x", encoding="utf-8")
    assert "не распознан" in extract_text(p)


@pytest.mark.parametrize("ext", [".docx", ".pdf", ".xlsx"])
def test_registered_exts(ext):
    from req_tester.config import SUPPORTED_EXTS
    from req_tester.extractors import EXTRACTORS
    assert ext in SUPPORTED_EXTS and ext in EXTRACTORS

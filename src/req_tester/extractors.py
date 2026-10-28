# -*- coding: utf-8 -*-
"""Извлечение текстового содержимого из файлов требований поддерживаемых форматов.

Форматы: doc, docx, md, pdf, txt, xlsx, xml, json.
"""

from __future__ import annotations

import json
import re
import xml.dom.minidom
from pathlib import Path


def extract_docx(path: Path) -> str:
    """Извлечение текста из .docx (python-docx): абзацы + таблицы."""
    from docx import Document

    doc = Document(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for i, table in enumerate(doc.tables, start=1):
        parts.append(f"\n[Таблица {i}]")
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_doc(path: Path) -> str:
    """
    Извлечение текста из старого бинарного .doc.
    Сначала пробуем LibreOffice (soffice --convert-to txt), затем — грубый
    fallback: читаем 'WordDocument' поток через olefile и оставляем печатные
    символы (качество ниже, но файл не будет пропущен).
    """
    import shutil
    import subprocess
    import tempfile

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(
                    [soffice, "--headless", "--convert-to", "txt",
                     "--outdir", tmp, str(path)],
                    check=True, capture_output=True, timeout=120,
                )
                txt = Path(tmp) / (path.stem + ".txt")
                if txt.exists():
                    return txt.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass  # fallback ниже

    # Fallback: сырое извлечение строк из OLE-потока WordDocument
    try:
        import olefile

        if olefile.isOleFile(str(path)):
            with olefile.OleFileIO(str(path)) as ole:
                stream_name = ("WordDocument"
                               if ole.exists("WordDocument") else ole.listdir()[0])
                data = ole.openstream(stream_name).read()
            text = data.decode("utf-16-le", errors="ignore")
            text = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in text)
            text = re.sub(r"[ \t]{2,}", " ", text)
            return text.strip()
    except Exception:
        pass
    return "[Не удалось извлечь текст из .doc файла]"


def extract_pdf(path: Path) -> str:
    """Извлечение текста из PDF (pypdf)."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            pages.append(f"\n--- Страница {i} ---\n{page.extract_text() or ''}")
        except Exception as e:
            pages.append(f"\n--- Страница {i}: ошибка извлечения ({e}) ---")
    return "\n".join(pages)


def extract_xlsx(path: Path) -> str:
    """Извлечение текста из .xlsx (openpyxl): все листы, все непустые ячейки."""
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"\n=== Лист: {ws.title} ===")
        for row in ws.iter_rows(values_only=True):
            values = [str(v) for v in row if v is not None and str(v).strip()]
            if values:
                parts.append(" | ".join(values))
    wb.close()
    return "\n".join(parts)


def extract_xml(path: Path) -> str:
    """Извлечение текста из XML: pretty-print + значения атрибутов/тегов."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        dom = xml.dom.minidom.parseString(raw)
        lines = []
        for node in dom.getElementsByTagName("*"):
            for text in node.childNodes:
                if text.nodeType == text.TEXT_NODE and text.data.strip():
                    lines.append(f"<{node.tagName}> {text.data.strip()}")
            for k, v in node.attributes.items():
                if str(v).strip():
                    lines.append(f"{node.tagName}@{k} = {v}")
        pretty = "\n".join(dict.fromkeys(lines))  # дедупликация с сохранением порядка
        return pretty if pretty.strip() else raw
    except Exception:
        return raw


def extract_json(path: Path) -> str:
    """Извлечение текста из JSON: рекурсивный обход всех строковых значений."""
    raw = path.read_text(encoding="utf-8", errors="replace")

    def walk(obj, prefix=""):
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.extend(walk(v, f"{prefix}/{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                out.extend(walk(v, f"{prefix}[{i}]"))
        elif isinstance(obj, str):
            if obj.strip():
                out.append(f"{prefix}: {obj}")
        else:
            out.append(f"{prefix}: {obj}")
        return out

    try:
        data = json.loads(raw)
        text = "\n".join(walk(data))
        return text if text.strip() else raw
    except json.JSONDecodeError:
        return raw


def extract_plain(path: Path) -> str:
    """Чтение простых текстовых файлов (.txt, .md) с определением кодировки."""
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


EXTRACTORS = {
    ".docx": extract_docx,
    ".doc": extract_doc,
    ".pdf": extract_pdf,
    ".xlsx": extract_xlsx,
    ".xml": extract_xml,
    ".json": extract_json,
    ".txt": extract_plain,
    ".md": extract_plain,
}


def extract_text(path: Path) -> str:
    """Точка входа: извлекает текст из файла по его расширению.

    Ошибки извлечения не прерывают работу утилиты — вместо текста возвращается
    пометка об ошибке, которая попадёт в запрос к ИИ и в отчёт.
    """
    ext = path.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        return f"[Поддерживаемый формат '{ext}' не распознан извлекателем]"
    try:
        return extractor(path)
    except Exception as e:
        return f"[Ошибка извлечения текста из {path.name}: {e}]"

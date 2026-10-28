#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилита автоматизированного тестирования требований с помощью LLM.

Логика работы:
1. Рекурсивно сканирует папку ./input (или иную, заданную через --input-dir)
   и собирает файлы требований форматов: doc, docx, md, pdf, txt, xlsx, xml, json.
2. Извлекает текстовое содержимое каждого файла.
3. Отправляет содержимое в OpenAI-совместимый API (модель qwen3.8),
   используя промпт из файла prompt.txt (параметры: temperature=0.1, max_tokens=200000).
   ВАЖНО: обработка ответа ИИ начинается ТОЛЬКО после полного получения ответа
   (запрос синхронный, без stream=True; ответ собирается целиком, только затем
   разбирается и сохраняется).
4. Сохраняет результат в файл "тестирование требований_<ГГГГ-ММ-ДД_ЧЧ-ММ-СС>.md".

Запуск:
    export OPENAI_API_KEY="sk-..."
    python req_tester.py [--model qwen3.8] [--input-dir input] [--output-dir output]

Если используется не официальный OpenAI, а совместимый шлюз (DashScope/Aliyun,
vLLM, OpenRouter и т.п.), задайте переменную окружения OPENAI_BASE_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
import xml.dom.minidom
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Конфигурация по умолчанию (можно переопределить аргументами командной строки
# или переменными окружения)
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "qwen3.8"          # модель согласно заданию
DEFAULT_TEMPERATURE = 0.1          # согласно заданию
DEFAULT_MAX_TOKENS = 200000        # согласно заданию
PROMPT_FILE = Path(__file__).parent / "prompt.txt"
SUPPORTED_EXTS = {".doc", ".docx", ".md", ".pdf", ".txt", ".xlsx", ".xml", ".json"}
# Лимит на объём текста одного файла, отправляемый в модель (символов).
# Нужен, чтобы не превысить контекст модели; при необходимости измените.
MAX_CHARS_PER_FILE = 400_000


# ──────────────────────────────────────────────────────────────────────────────
# Извлечение текста из файлов
# ──────────────────────────────────────────────────────────────────────────────
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
    ext = path.suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        return f"[Поддерживаемый формат '{ext}' не распознан извлекателем]"
    try:
        return extractor(path)
    except Exception as e:
        return f"[Ошибка извлечения текста из {path.name}: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# Сканирование входной папки
# ──────────────────────────────────────────────────────────────────────────────
def collect_files(input_dir: Path) -> list[Path]:
    """Рекурсивный сбор файлов поддерживаемых форматов."""
    files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )
    return files


# ──────────────────────────────────────────────────────────────────────────────
# Запрос к ИИ
# ──────────────────────────────────────────────────────────────────────────────
def ask_ai(client, model: str, system_prompt: str, user_content: str,
           temperature: float, max_tokens: int) -> str:
    """
    Синхронный запрос к chat completions.

    КЛЮЧЕВОЕ ТРЕБОВАНИЕ ЗАДАНИЯ: функция НЕ возвращает управление и ничего
    не обрабатывает, пока модель не отдаст ПОЛНЫЙ ответ. Используется обычный
    (не streaming) вызов.chat.completions.create — блокируется до завершения
    генерации; разбор response.choices[*].message.content выполняется строго
    после получения всего ответа.
    """
    completion = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,  # ответ обрабатывается только после полной отдачи ИИ
    )

    # ── Обработка начинается ЗДЕСЬ — то есть уже ПОСЛЕ того, как ИИ отдал ответ
    if not getattr(completion, "choices", None):
        raise RuntimeError("Пустой ответ от модели (нет choices)")
    answer = completion.choices[0].message.content or ""
    finish_reason = getattr(completion.choices[0], "finish_reason", None)
    usage = getattr(completion, "usage", None)
    if usage:
        print(f"    токены: prompt={usage.prompt_tokens}, "
              f"completion={usage.completion_tokens}, total={usage.total_tokens}"
              + (f", finish_reason={finish_reason}" if finish_reason else ""))
    return answer.strip()


def build_user_content(files_texts: list[tuple[Path, str]]) -> str:
    """Формирует единый пользовательский запрос со всеми файлами."""
    blocks = []
    for path, text in files_texts:
        trimmed = text[:MAX_CHARS_PER_FILE]
        note = ("\n[ВНИМАНИЕ: содержимое обрезано по лимиту]"
                if len(text) > MAX_CHARS_PER_FILE else "")
        blocks.append(
            f"########## ФАЙЛ: {path} ##########\n{trimmed}{note}\n"
        )
    header = (
        "Ниже приведены документы с требованиями, считанные из файлов. "
        "Проведи их тестирование согласно инструкциям.\n\n"
    )
    return header + "\n".join(blocks)


# ──────────────────────────────────────────────────────────────────────────────
# Основной сценарий
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Тестирование требований с помощью ИИ")
    parser.add_argument("--input-dir", default="input",
                        help="Папка с файлами требований (по умолчанию ./input)")
    parser.add_argument("--output-dir", default="output",
                        help="Папка для результатов (по умолчанию ./output)")
    parser.add_argument("--prompt-file", default=str(PROMPT_FILE),
                        help="Файл с промптом для ИИ (по умолчанию ./prompt.txt)")
    parser.add_argument("--model", default=os.environ.get("QWEN_MODEL", DEFAULT_MODEL),
                        help=f"Модель (по умолчанию {DEFAULT_MODEL})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--per-file", action="store_true",
                        help="Отправлять каждый файл отдельным запросом "
                             "(по умолчанию все файлы — один запрос)")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    prompt_file = Path(args.prompt_file).resolve()

    # ── Проверки окружения
    if not input_dir.is_dir():
        print(f"ОШИБКА: входная папка не найдена: {input_dir}", file=sys.stderr)
        return 1
    if not prompt_file.is_file():
        print(f"ОШИБКА: файл промпта не найден: {prompt_file}", file=sys.stderr)
        return 1

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ОШИБКА: не задана переменная окружения OPENAI_API_KEY.", file=sys.stderr)
        print('Пример: export OPENAI_API_KEY="sk-..."', file=sys.stderr)
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("ОШИБКА: отсутствует библиотека openai. Выполните: pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    system_prompt = prompt_file.read_text(encoding="utf-8").strip()

    base_url = os.environ.get("OPENAI_BASE_URL") or None
    client = OpenAI(api_key=api_key, base_url=base_url)

    # ── 1) Сбор файлов
    print(f"Сканирую папку: {input_dir}")
    files = collect_files(input_dir)
    if not files:
        print("В папке input нет файлов поддерживаемых форматов "
              f"({', '.join(sorted(SUPPORTED_EXTS))}).")
        return 0
    print(f"Найдено файлов: {len(files)}")

    # ── 2) Извлечение содержимого
    files_texts: list[tuple[Path, str]] = []
    for f in files:
        rel = f.relative_to(input_dir)
        text = extract_text(f)
        chars = len(text.strip())
        status = f"{chars} симв." if chars else "ПУСТО/без текста"
        print(f"  • {rel} [{f.suffix.lower()}] — {status}")
        files_texts.append((rel, text))

    # ── 3) Отправка в ИИ и ожидание ПОЛНОГО ответа
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"тестирование требований_{timestamp}.md"

    print(f"\nМодель: {args.model} | temperature={args.temperature} | "
          f"max_tokens={args.max_tokens}")
    print("Отправляю содержимое в ИИ... (обработка начнётся только после "
          "получения полного ответа)")

    sections: list[str] = []
    errors: list[str] = []

    try:
        if args.per_file:
            # Каждый файл — отдельный синхронный запрос; ответ каждого файла
            # обрабатывается строго после его полного получения.
            for (rel, _orig), (_, text) in zip(files_texts, files_texts):
                print(f"  → запрос по файлу: {rel}")
                answer = ask_ai(client, args.model, system_prompt, text,
                                args.temperature, args.max_tokens)
                sections.append(f"# Результат тестирования файла: {rel}\n\n{answer}")
        else:
            user_content = build_user_content(files_texts)
            print(f"  размер запроса: {len(user_content):,} символов")
            answer = ask_ai(client, args.model, system_prompt, user_content,
                            args.temperature, args.max_tokens)
            sections.append(answer)
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ── 4) Сохранение результата
    report_parts = [
        "# Тестирование требований — результаты",
        "",
        f"- Дата/время выполнения: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Модель: {args.model} (temperature={args.temperature}, "
        f"max_tokens={args.max_tokens})",
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
    report_parts.extend(sections)
    if errors:
        report_parts += ["", "## Ошибки выполнения", *[f"- {err}" for err in errors]]

    out_path.write_text("\n".join(report_parts), encoding="utf-8")

    if errors:
        print(f"\nВыполнено с ошибками. Частичный результат сохранён: {out_path}")
        return 2
    print(f"\nГотово. Результат сохранён: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

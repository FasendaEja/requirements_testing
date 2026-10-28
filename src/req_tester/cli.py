# -*- coding: utf-8 -*-
"""CLI утилиты тестирования требований с помощью ИИ.

Точка входа: ``req-tester`` (см. pyproject.tomл -> [project.scripts]) или
``python -m req_tester``.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from .ai_client import ask_ai, build_user_content, create_client
from .config import (DEFAULT_INPUT_DIR, DEFAULT_MAX_TOKENS, DEFAULT_MODEL,
                     DEFAULT_OUTPUT_DIR, DEFAULT_PROMPT_FILE,
                     DEFAULT_TEMPERATURE, SUPPORTED_EXTS)
from .report import build_report, make_output_path, save_report
from .scanner import collect_files_with_text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="req-tester",
        description="Тестирование требований с помощью ИИ (OpenAI-совместимый API)",
    )
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR),
                        help="Папка с файлами требований (по умолчанию ./input)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Папка для результатов (по умолчанию ./output)")
    parser.add_argument("--prompt-file", default=str(DEFAULT_PROMPT_FILE),
                        help="Файл с промптом для ИИ (по умолчанию ./prompt.txt)")
    parser.add_argument("--model", default=os.environ.get("QWEN_MODEL", DEFAULT_MODEL),
                        help=f"Модель (по умолчанию {DEFAULT_MODEL})")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--per-file", action="store_true",
                        help="Отправлять каждый файл отдельным запросом "
                             "(по умолчанию все файлы — один запрос)")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
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
        client = create_client(api_key, os.environ.get("OPENAI_BASE_URL"))
    except ImportError:
        print("ОШИБКА: отсутствует библиотека openai. "
              "Выполните: pip install -r requirements.txt", file=sys.stderr)
        return 1

    system_prompt = prompt_file.read_text(encoding="utf-8").strip()

    # ── 1–2) Сбор файлов и извлечение содержимого
    print(f"Сканирую папку: {input_dir}")
    files_texts = collect_files_with_text(input_dir)
    if not files_texts:
        print("В папке input нет файлов поддерживаемых форматов "
              f"({', '.join(sorted(SUPPORTED_EXTS))}).")
        return 0
    print(f"Найдено файлов: {len(files_texts)}")

    # ── 3) Отправка в ИИ и ожидание ПОЛНОГО ответа
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = make_output_path(output_dir, datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S"))

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
            for rel, text in files_texts:
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
    report = build_report(files_texts=files_texts, sections=sections, errors=errors,
                          model=args.model, temperature=args.temperature,
                          max_tokens=args.max_tokens, prompt_file=prompt_file,
                          input_dir=input_dir)
    save_report(out_path, report)

    if errors:
        print(f"\nВыполнено с ошибками. Частичный результат сохранён: {out_path}")
        return 2
    print(f"\nГотово. Результат сохранён: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

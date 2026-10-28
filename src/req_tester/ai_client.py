# -*- coding: utf-8 -*-
"""Клиент LLM (OpenAI-совместимый API) и формирование запросов.

КЛЮЧЕВОЕ ТРЕБОВАНИЕ: содержимое ответа модели обрабатывается ТОЛЬКО после
того, как модель полностью отдаст ответ (синхронный вызов без streaming).
"""

from __future__ import annotations

from pathlib import Path

from .config import MAX_CHARS_PER_FILE


def create_client(api_key: str, base_url: str | None = None):
    """Создаёт OpenAI-совместимый клиент.

    base_url можно задать переменной окружения OPENAI_BASE_URL, если
    используется совместимый шлюз (DashScope, OpenRouter, vLLM и т.п.).
    """
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url or None)


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


def ask_ai(client, model: str, system_prompt: str, user_content: str,
           temperature: float, max_tokens: int) -> str:
    """
    Синхронный запрос к chat completions.

    КЛЮЧЕВОЕ ТРЕБОВАНИЕ ЗАДАНИЯ: функция НЕ возвращает управление и ничего
    не обрабатывает, пока модель не отдаст ПОЛНЫЙ ответ. Используется обычный
    (не streaming) вызов client.chat.completions.create — он блокируется до
    завершения генерации; разбор response.choices[*].message.content
    выполняется строго после получения всего ответа.
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

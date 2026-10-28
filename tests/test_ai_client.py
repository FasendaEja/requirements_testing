# -*- coding: utf-8 -*-
"""Тесты клиента ИИ: ответ обрабатывается только после полной отдачи ответа."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from req_tester.ai_client import ask_ai, build_user_content


class FakeCompletions:
    def __init__(self, answer="Готовый ответ модели"):
        self.answer = answer
        self.call_kwargs = None

    def create(self, **kwargs):
        self.call_kwargs = kwargs

        def _gen():
            # имитация «полной отдачи»: весь текст доступен только после
            # завершения вызова (сгенерирован целиком до возврата)
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=self.answer),
                    finish_reason="stop")],
                usage=None,
            )
        return list(_gen())[0]


class FakeClient:
    def __init__(self, answer="Готовый ответ модели"):
        self.chat = SimpleNamespace(completions=FakeCompletions(answer))


def test_ask_ai_sync_no_stream():
    client = FakeClient()
    result = ask_ai(client, model="qwen3.8", system_prompt="s", user_content="u",
                    temperature=0.1, max_tokens=200000)
    assert result == "Готовый ответ модели"
    kw = client.chat.completions.call_kwargs
    assert kw["stream"] is False          # обработка — только после полного ответа
    assert kw["model"] == "qwen3.8"
    assert kw["temperature"] == 0.1
    assert kw["max_tokens"] == 200000


def test_ask_ai_empty_choices_raises():
    class NoChoices:
        def create(self, **kw):
            return SimpleNamespace(choices=[], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=NoChoices()))
    with pytest.raises(RuntimeError):
        ask_ai(client, "m", "s", "u", 0.1, 100)


def test_build_user_content_contains_all_files():
    pairs = [(Path("a.md"), "текст А"), (Path("sub/b.txt"), "текст Б")]
    content = build_user_content(pairs)
    assert "ФАЙЛ: a.md" in content and "текст А" in content
    assert "ФАЙЛ: sub/b.txt" in content and "текст Б" in content

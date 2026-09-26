"""LLM の呼び出し。本物の Gemini と、鍵がなくても動く偽物を同じ形で扱う。"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from .knowledge import KnowledgeBase


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


class LLMProvider(Protocol):
    name: str

    def stream(self, system: str, contents: list[dict[str, Any]], usage: Usage) -> AsyncIterator[str]:
        """本文の断片を順に返す。終わった時点で usage を埋める。"""
        ...


class GeminiDeveloperLLM:
    """Gemini Developer API。見本の無料版で使う。"""

    name = "gemini-developer"

    def __init__(self, api_key: str, model: str, temperature: float, max_output_tokens: int):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    async def stream(self, system: str, contents: list[dict[str, Any]], usage: Usage) -> AsyncIterator[str]:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        stream = await self._client.aio.models.generate_content_stream(
            model=self.model, contents=contents, config=config)
        async for chunk in stream:
            meta = getattr(chunk, "usage_metadata", None)
            if meta:
                usage.input_tokens = meta.prompt_token_count or usage.input_tokens
                usage.cached_tokens = meta.cached_content_token_count or usage.cached_tokens
                usage.output_tokens = meta.candidates_token_count or usage.output_tokens
                usage.thinking_tokens = meta.thoughts_token_count or usage.thinking_tokens
            if chunk.text:
                yield chunk.text


class FakeLLM:
    """鍵がないときの偽物。質問と知識の文字の重なりで答えを選ぶ。"""

    name = "fake"
    model = "fake"

    def __init__(self, kb_getter, delay: float = 0.02):
        self._kb_getter = kb_getter
        self._delay = delay

    async def stream(self, system: str, contents: list[dict[str, Any]], usage: Usage) -> AsyncIterator[str]:
        raw = contents[-1]["parts"][0]["text"]
        m = re.search(r"<customer_message[^>]*>\n(.*)\n</customer_message>", raw, re.S)
        question = m.group(1) if m else raw
        kb: KnowledgeBase = self._kb_getter()
        best, score = None, 0
        for short, kid in kb.short_ids.items():
            item = kb.by_id[kid]
            s = len(set(item.question) & set(question))
            if s > score:
                best, score = (short, item), s
        if best and score >= 4:
            short, item = best
            meta = {"e": "smile", "r": [short], "o": False, "s": ""}
            body = f"見本の偽物の答えだ。店の知識にはこうある。{item.answer}"
        else:
            meta = {"e": "sorry", "r": [], "o": True, "s": ""}
            body = "すまん、それは俺の手元の知識にないんだ。公式 LINE のヘルプから店に聞けるが、返事には時間がかかることがあるぞ。"
        text = "#meta " + json.dumps(meta, ensure_ascii=False) + "\n" + body
        usage.input_tokens = len(system) + len(question)
        usage.output_tokens = len(text)
        for i in range(0, len(text), 6):
            await asyncio.sleep(self._delay)
            yield text[i:i + 6]

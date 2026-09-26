"""緊急時の質問を見分け、確認済みの定型文を返す。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Tenant


@dataclass
class SafetyAnswer:
    template_id: str
    title: str
    text: str
    note: str


class SafetyRouter:
    def __init__(self, tenant: Tenant):
        self.templates = tenant.safety.get("templates", {})
        self.note = tenant.safety.get("note", {})
        self.default_language = tenant.config.get("default_language", "ja")

    def detect(self, text: str) -> str | None:
        """キーワードで緊急の種類を探す。見つからなければ None を返す。"""
        lowered = text.lower()
        for tid, t in self.templates.items():
            for kw in t.get("keywords", []):
                if kw.lower() in lowered:
                    return tid
        return None

    def answer(self, template_id: str, language: str) -> SafetyAnswer:
        t = self.templates[template_id]

        def pick(d: dict[str, str]) -> str:
            return d.get(language) or d.get(self.default_language) or next(iter(d.values()))

        return SafetyAnswer(template_id, pick(t["title"]), pick(t["text"]), pick(self.note))


PHONE = re.compile(r"(?<!\d)0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CARD = re.compile(r"(?<!\d)(?:\d[\s-]?){13,16}(?!\d)")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask_pii(text: str) -> str:
    """電話番号、メールアドレス、カード番号を伏せ字にする。注文番号のような短い数字は残す。"""
    text = EMAIL.sub("[メール]", text)
    text = CARD.sub("[番号]", text)
    text = PHONE.sub("[電話番号]", text)
    return text


def clean_input(text: str, max_chars: int) -> str:
    return CONTROL.sub("", text).strip()[:max_chars]

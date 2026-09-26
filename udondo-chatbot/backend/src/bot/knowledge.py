"""店の知識を読み込み、全件をプロンプトに入れる形に整える。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from .config import TENANTS_DIR

VIDEO_HOSTS = ("youtu.be", "youtube.com")


@dataclass
class KnowledgeItem:
    id: str
    question: str
    answer: str
    category: str = ""
    step_no: int | None = None
    video_url: str | None = None
    link_url: str | None = None
    priority: str | None = None

    def attachments(self) -> list[dict[str, str]]:
        out = []
        if self.video_url:
            out.append({"kind": "video", "url": self.video_url, "label": self.question})
        if self.link_url:
            out.append({"kind": "link", "url": self.link_url, "label": self.question})
        return out


def from_supabase_row(row: dict[str, Any]) -> KnowledgeItem:
    """Supabase の knowledge_base の1行を標準の形に変える。"""
    meta = row.get("metadata") or {}
    video = link = None
    url = meta.get("youtube_url")
    if url:
        # 漫画のページの URL が youtube_url に入った行があるので、動画以外はリンクに回す
        if any(h in url for h in VIDEO_HOSTS):
            video = url
        else:
            link = url
    link = link or meta.get("line_url") or meta.get("google_maps_url")
    return KnowledgeItem(
        id=str(row["id"]),
        question=row.get("title") or "",
        answer=row.get("content") or "",
        category=row.get("category") or "",
        video_url=video,
        link_url=link,
        priority=meta.get("priority"),
    )


def load_sample(tenant_id: str) -> list[KnowledgeItem]:
    path = TENANTS_DIR / tenant_id / "knowledge_sample.yaml"
    rows = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [KnowledgeItem(**r) for r in rows]


@dataclass
class KnowledgeBase:
    items: list[KnowledgeItem]
    version: str
    by_id: dict[str, KnowledgeItem] = field(init=False)
    short_ids: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.items = sorted(
            self.items,
            key=lambda k: (k.step_no if k.step_no is not None else 99, k.category, k.id),
        )
        # プロンプトでは長い UUID の代わりに K1、K2 の短い ID を使う
        self.short_ids = {f"K{i + 1}": k.id for i, k in enumerate(self.items)}
        self.by_id = {k.id: k for k in self.items}

    def prompt_block(self) -> str:
        lines = [f'<knowledge version="{self.version}">']
        for short, kid in self.short_ids.items():
            k = self.by_id[kid]
            head = f"[{short}] category={k.category}"
            if k.step_no is not None:
                head += f" step={k.step_no}"
            lines += [head, f"Q: {k.question}", f"A: {k.answer}"]
        lines.append("</knowledge>")
        return "\n".join(lines)

    def resolve(self, refs: list[str]) -> list[KnowledgeItem]:
        out = []
        for r in refs:
            kid = self.short_ids.get(r)
            if kid and kid in self.by_id:
                out.append(self.by_id[kid])
        return out


class KnowledgeCache:
    """知識を数分だけ手元に持ち、毎回の読み込みを避ける。"""

    def __init__(self, loader: Callable[[], KnowledgeBase], ttl_seconds: int = 300):
        self._loader = loader
        self._ttl = ttl_seconds
        self._value: KnowledgeBase | None = None
        self._at = 0.0

    def get(self) -> KnowledgeBase:
        if self._value is None or time.monotonic() - self._at > self._ttl:
            self._value = self._loader()
            self._at = time.monotonic()
        return self._value

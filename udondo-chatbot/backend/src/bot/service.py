"""1ターンの処理。上限の確認、緊急時の判定、生成、記録をまとめる。"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from .config import Tenant
from .knowledge import KnowledgeCache
from .llm import LLMProvider, Usage
from .meta import MetaSplitter
from .prompt import answer_language, build_contents, build_system_prompt, looks_leaked
from .safety import SafetyRouter, clean_input, mask_pii
from .store import Store

JST = timezone(timedelta(hours=9))

# 有料枠で呼んだ場合の単価。無料枠でも、費用上限の判定と見積もりとの突き合わせに使う
# 出典 https://ai.google.dev/gemini-api/docs/pricing 確認日 2026-09-25
PRICES_USD_PER_1M = {
    "gemini-3.5-flash-lite": {"input": 0.30, "cached": 0.03, "output": 2.50},
    "fake": {"input": 0.0, "cached": 0.0, "output": 0.0},
}


def cost_usd(u: Usage) -> float:
    p = PRICES_USD_PER_1M.get(u.model, PRICES_USD_PER_1M["gemini-3.5-flash-lite"])
    fresh = max(u.input_tokens - u.cached_tokens, 0)
    return (fresh * p["input"] + u.cached_tokens * p["cached"] + (u.output_tokens + u.thinking_tokens) * p["output"]) / 1e6


def now() -> datetime:
    return datetime.now(JST)


def today() -> str:
    return now().date().isoformat()


class GuardError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


@dataclass
class Event:
    name: str
    data: dict[str, Any]


class DialogueService:
    def __init__(self, tenant: Tenant, store: Store, llm: LLMProvider, knowledge: KnowledgeCache, salt: str,
                 llm_timeout: float = 20.0):
        self.tenant = tenant
        self.store = store
        self.llm = llm
        self.knowledge = knowledge
        self.safety = SafetyRouter(tenant)
        self.salt = salt
        self.llm_timeout = llm_timeout
        self.usd_jpy = float(tenant.config.get("usd_jpy", 158.73))

    def ip_hash(self, ip: str) -> str:
        return hashlib.sha256((self.salt + ip).encode()).hexdigest()[:24]

    async def create_session(self, ip: str, language: str | None) -> dict[str, Any]:
        await self._rate_limit(ip)
        lang = language if language in self.tenant.languages else self.tenant.config.get("default_language", "ja")
        sid = secrets.token_urlsafe(18)
        t = now()
        await self.store.create_session({"id": sid, "tenant_id": self.tenant.id, "created_at": t, "last_active_at": t,
                                         "language": lang, "turn_count": 0, "ip_hash": self.ip_hash(ip)})
        idle = self.tenant.limits["session_idle_minutes"]
        return {"session_id": sid, "expires_at": (t + timedelta(minutes=idle)).isoformat(),
                "remaining_turns": self.tenant.limits["session_turns"], "language": lang}

    async def _rate_limit(self, ip: str) -> None:
        key = f"ip:{self.ip_hash(ip)}:{now().strftime('%Y%m%d%H%M')}"
        if await self.store.hit(self.tenant.id, key) > self.tenant.limits["ip_per_minute"]:
            raise GuardError(429, "rate_limited", "少し時間をおいてからもう一度試してください")

    async def _load_session(self, session_id: str) -> dict[str, Any]:
        s = await self.store.get_session(self.tenant.id, session_id)
        if not s:
            raise GuardError(401, "unauthorized", "セッションがありません")
        last = s["last_active_at"]
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        if now() - last > timedelta(minutes=self.tenant.limits["session_idle_minutes"]):
            raise GuardError(401, "unauthorized", "セッションの期限が切れました")
        return s

    async def precheck(self, session_id: str, ip: str, message: str) -> dict[str, Any]:
        """SSE を始める前に確かめる。失敗は状態コードで返す。"""
        if not message.strip():
            raise GuardError(400, "invalid_input", "質問が空です")
        if len(message) > self.tenant.limits["question_chars"]:
            raise GuardError(400, "invalid_input", "質問が長すぎます")
        await self._rate_limit(ip)
        session = await self._load_session(session_id)
        if await self.store.daily_cost(self.tenant.id, today()) >= self.tenant.limits["daily_cost_jpy"]:
            raise GuardError(503, "daily_cap", "本日の上限に達しました")
        return session

    async def chat(self, session: dict[str, Any], message: str, language: str | None) -> AsyncIterator[Event]:
        limits = self.tenant.limits
        ui_lang = language if language in self.tenant.languages else session["language"]
        lang = answer_language(message, ui_lang)
        seq = session["turn_count"] + 1
        remaining = limits["session_turns"] - seq
        turn_id = f"{session['id']}-{seq}"
        if seq > limits["session_turns"]:
            yield Event("degraded", {"reason": "session_limit"})
            return
        text = mask_pii(clean_input(message, limits["question_chars"]))
        started = time.monotonic()
        base = {"id": turn_id, "tenant_id": self.tenant.id, "session_id": session["id"], "seq": seq,
                "created_at": now(), "mode": "text", "language": lang, "user_text_masked": text}

        kind = self.safety.detect(text)
        if kind:
            yield Event("meta", {"turn_id": turn_id, "language": lang, "emotion": "serious", "refs": [],
                                 "out_of_knowledge": False, "attachments": []})
            ans = self.safety.answer(kind, lang)
            yield Event("safety", {"template_id": ans.template_id, "title": ans.title, "text": ans.text, "note": ans.note})
            await self._finish(session, base | {"bot_text": ans.text, "emotion": "serious", "safety_id": kind,
                                                "latency_first_ms": _ms(started), "latency_total_ms": _ms(started)}, None)
            yield Event("done", {"turn_id": turn_id, "remaining_turns": remaining, "usage": {"cost_usd": 0}})
            return

        kb = self.knowledge.get()
        system = build_system_prompt(self.tenant, kb)
        # 言語が変わったときは、違う言語の履歴を渡さない。履歴の言語に答えが引きずられるため
        history = [(t["user_text_masked"], t["bot_text"])
                   for t in await self.store.recent_turns(session["id"], self.tenant.config["llm"]["history_turns"])
                   if answer_language(t["user_text_masked"], ui_lang) == lang]
        contents = build_contents(history, ui_lang, text)

        splitter = MetaSplitter()
        body: list[str] = []
        usage = Usage(model=getattr(self.llm, "model", self.llm.name))
        first_ms = None
        meta_sent = False
        try:
            async for piece in self._generate(system, contents, usage):
                out = splitter.feed(piece)
                if splitter.meta is None:
                    continue
                if not meta_sent:
                    meta_sent = True
                    if splitter.meta.safety:
                        break
                    yield self._meta_event(turn_id, lang, splitter, kb)
                if out:
                    body.append(out)
                    first_ms = first_ms or _ms(started)
                    yield Event("delta", {"text": out})
            tail = splitter.finish()
            if tail:
                body.append(tail)
            if not meta_sent and not (splitter.meta and splitter.meta.safety):
                yield self._meta_event(turn_id, lang, splitter, kb)
                if tail:
                    yield Event("delta", {"text": tail})
        except Exception as e:  # noqa: BLE001 LLM の失敗はすべて縮退として扱う
            await self._finish(session, base | {"bot_text": "".join(body), "error": type(e).__name__,
                                                "latency_total_ms": _ms(started)}, usage)
            yield Event("degraded", {"reason": "llm_error"})
            return

        meta = splitter.meta
        if meta and meta.safety:
            ans = self.safety.answer(meta.safety, lang)
            yield Event("meta", {"turn_id": turn_id, "language": lang, "emotion": "serious", "refs": [],
                                 "out_of_knowledge": False, "attachments": []})
            yield Event("safety", {"template_id": ans.template_id, "title": ans.title, "text": ans.text, "note": ans.note})
            bot_text, safety_id = ans.text, meta.safety
        else:
            bot_text, safety_id = "".join(body).strip(), None
            if looks_leaked(bot_text):
                bot_text = "すまん、それには答えられないんだ。店の使い方なら何でも聞いてくれ。"
                yield Event("delta", {"text": "\n" + bot_text})

        row = base | {"bot_text": bot_text, "emotion": meta.emotion if meta else "neutral",
                      "refs": [k.id for k in kb.resolve(meta.refs)] if meta else [],
                      "out_of_knowledge": bool(meta and meta.out_of_knowledge), "safety_id": safety_id,
                      "latency_first_ms": first_ms, "latency_total_ms": _ms(started)}
        cost = await self._finish(session, row, usage)
        if row["out_of_knowledge"]:
            await self.store.add_unanswered({"id": f"{turn_id}-ook", "tenant_id": self.tenant.id,
                                             "session_id": session["id"], "turn_id": turn_id,
                                             "question_masked": text, "language": lang, "reason": "out_of_knowledge",
                                             "created_at": now()})
        yield Event("done", {"turn_id": turn_id, "remaining_turns": remaining, "usage": {"cost_usd": round(cost, 6)}})

    async def _generate(self, system: str, contents: list[dict[str, Any]], usage: Usage) -> AsyncIterator[str]:
        """時間切れか失敗のとき、何も送っていなければ1回だけ再試行する。"""
        for attempt in range(2):
            sent = False
            try:
                agen = self.llm.stream(system, contents, usage).__aiter__()
                deadline = time.monotonic() + self.llm_timeout
                while True:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError
                    try:
                        piece = await asyncio.wait_for(agen.__anext__(), timeout=left)
                    except StopAsyncIteration:
                        return
                    sent = True
                    yield piece
            except Exception:
                if sent or attempt == 1:
                    raise
                await asyncio.sleep(0.5)

    def _meta_event(self, turn_id: str, lang: str, splitter: MetaSplitter, kb) -> Event:
        m = splitter.meta
        items = kb.resolve(m.refs) if m else []
        attachments = [a for k in items for a in k.attachments()]
        return Event("meta", {"turn_id": turn_id, "language": lang, "emotion": m.emotion if m else "neutral",
                              "refs": m.refs if m else [], "out_of_knowledge": bool(m and m.out_of_knowledge),
                              "attachments": attachments})

    async def _finish(self, session: dict[str, Any], row: dict[str, Any], usage: Usage | None) -> float:
        await self.store.add_turn(row)
        await self.store.update_session(session["id"], {"turn_count": row["seq"], "last_active_at": now()})
        cost = 0.0
        if usage:
            cost = cost_usd(usage)
            await self.store.add_usage({"tenant_id": self.tenant.id, "session_id": session["id"], "turn_id": row["id"],
                                        "kind": "llm", "provider": self.llm.name, "model": usage.model,
                                        "input_tokens": usage.input_tokens, "cached_tokens": usage.cached_tokens,
                                        "output_tokens": usage.output_tokens, "thinking_tokens": usage.thinking_tokens,
                                        "cost_usd": round(cost, 6), "cost_jpy": round(cost * self.usd_jpy, 4)})
        await self.store.add_daily_cost(self.tenant.id, today(), cost * self.usd_jpy, 1 if row["seq"] == 1 else 0, 1)
        return cost

    async def feedback(self, session_id: str, turn_id: str, resolved: bool) -> None:
        await self._load_session(session_id)
        if not await self.store.set_resolved(self.tenant.id, session_id, turn_id, resolved):
            raise GuardError(404, "not_found", "ターンがありません")
        if not resolved:
            turns = [t for t in await self.store.recent_turns(session_id, 50) if t.get("id", turn_id) == turn_id]
            question = turns[0]["user_text_masked"] if turns else ""
            await self.store.add_unanswered({"id": f"{turn_id}-nr", "tenant_id": self.tenant.id, "session_id": session_id,
                                             "turn_id": turn_id, "question_masked": question, "language": "",
                                             "reason": "not_resolved", "created_at": now()})


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

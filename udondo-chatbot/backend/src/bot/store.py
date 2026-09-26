"""セッション、会話、使用量、費用、未回答質問、レート制限の保存先。"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Protocol


class Store(Protocol):
    async def create_session(self, row: dict[str, Any]) -> None: ...
    async def get_session(self, tenant_id: str, session_id: str) -> dict[str, Any] | None: ...
    async def update_session(self, session_id: str, fields: dict[str, Any]) -> None: ...
    async def add_turn(self, row: dict[str, Any]) -> None: ...
    async def recent_turns(self, session_id: str, n: int) -> list[dict[str, Any]]: ...
    async def set_resolved(self, tenant_id: str, session_id: str, turn_id: str, resolved: bool) -> bool: ...
    async def add_usage(self, row: dict[str, Any]) -> None: ...
    async def add_daily_cost(self, tenant_id: str, day: str, jpy: float, conversations: int, turns: int) -> None: ...
    async def daily_cost(self, tenant_id: str, day: str) -> float: ...
    async def add_unanswered(self, row: dict[str, Any]) -> None: ...
    async def hit(self, tenant_id: str, key: str) -> int: ...


class MemoryStore:
    """手元とテスト用。プロセスが止まると消える。"""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.turns: list[dict[str, Any]] = []
        self.usage: list[dict[str, Any]] = []
        self.costs: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"jpy": 0.0, "conversations": 0, "turns": 0})
        self.unanswered: list[dict[str, Any]] = []
        self.hits: dict[tuple[str, str], int] = defaultdict(int)

    async def create_session(self, row):
        self.sessions[row["id"]] = dict(row)

    async def get_session(self, tenant_id, session_id):
        s = self.sessions.get(session_id)
        return dict(s) if s and s["tenant_id"] == tenant_id else None

    async def update_session(self, session_id, fields):
        self.sessions[session_id].update(fields)

    async def add_turn(self, row):
        self.turns.append(dict(row))

    async def recent_turns(self, session_id, n):
        rows = [t for t in self.turns if t["session_id"] == session_id]
        return rows[-n:]

    async def set_resolved(self, tenant_id, session_id, turn_id, resolved):
        for t in self.turns:
            if t["id"] == turn_id and t["session_id"] == session_id and t["tenant_id"] == tenant_id:
                t["resolved"] = resolved
                return True
        return False

    async def add_usage(self, row):
        self.usage.append(dict(row))

    async def add_daily_cost(self, tenant_id, day, jpy, conversations, turns):
        c = self.costs[(tenant_id, day)]
        c["jpy"] += jpy
        c["conversations"] += conversations
        c["turns"] += turns

    async def daily_cost(self, tenant_id, day):
        return self.costs[(tenant_id, day)]["jpy"]

    async def add_unanswered(self, row):
        self.unanswered.append(dict(row))

    async def hit(self, tenant_id, key):
        self.hits[(tenant_id, key)] += 1
        return self.hits[(tenant_id, key)]


class SupabaseStore:
    """Supabase の bot_ で始まるテーブルに書く。サービスロールの鍵で接続する。"""

    def __init__(self, url: str, key: str):
        from supabase import create_client

        self._db = create_client(url, key)

    async def _run(self, fn):
        return await asyncio.to_thread(fn)

    async def create_session(self, row):
        await self._run(lambda: self._db.table("bot_sessions").insert(_jsonable(row)).execute())

    async def get_session(self, tenant_id, session_id):
        res = await self._run(lambda: self._db.table("bot_sessions").select("*")
                              .eq("id", session_id).eq("tenant_id", tenant_id).limit(1).execute())
        return res.data[0] if res.data else None

    async def update_session(self, session_id, fields):
        await self._run(lambda: self._db.table("bot_sessions").update(_jsonable(fields)).eq("id", session_id).execute())

    async def add_turn(self, row):
        await self._run(lambda: self._db.table("bot_turns").insert(_jsonable(row)).execute())

    async def recent_turns(self, session_id, n):
        res = await self._run(lambda: self._db.table("bot_turns").select("id,user_text_masked,bot_text,seq")
                              .eq("session_id", session_id).order("seq", desc=True).limit(n).execute())
        return list(reversed(res.data or []))

    async def set_resolved(self, tenant_id, session_id, turn_id, resolved):
        res = await self._run(lambda: self._db.table("bot_turns").update({"resolved": resolved})
                              .eq("id", turn_id).eq("session_id", session_id).eq("tenant_id", tenant_id).execute())
        return bool(res.data)

    async def add_usage(self, row):
        await self._run(lambda: self._db.table("bot_usage").insert(_jsonable(row)).execute())

    async def add_daily_cost(self, tenant_id, day, jpy, conversations, turns):
        await self._run(lambda: self._db.rpc("bot_add_daily_cost", {
            "p_tenant_id": tenant_id, "p_day": day, "p_jpy": jpy,
            "p_conversations": conversations, "p_turns": turns}).execute())

    async def daily_cost(self, tenant_id, day):
        res = await self._run(lambda: self._db.table("bot_daily_costs").select("cost_jpy")
                              .eq("tenant_id", tenant_id).eq("day", day).limit(1).execute())
        return float(res.data[0]["cost_jpy"]) if res.data else 0.0

    async def add_unanswered(self, row):
        await self._run(lambda: self._db.table("bot_unanswered").insert(_jsonable(row)).execute())

    async def hit(self, tenant_id, key):
        res = await self._run(lambda: self._db.rpc("bot_hit", {"p_tenant_id": tenant_id, "p_key": key}).execute())
        return int(res.data)


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()}

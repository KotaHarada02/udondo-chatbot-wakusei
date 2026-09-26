"""客向けの API。docs の openapi.yaml と同じ形にする。"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .config import Tenant, get_settings, get_tenant
from .knowledge import KnowledgeBase, KnowledgeCache, from_supabase_row, load_sample
from .llm import FakeLLM, GeminiDeveloperLLM
from .service import DialogueService, GuardError
from .store import MemoryStore, SupabaseStore

router = APIRouter(prefix="/api/v1")


class SessionRequest(BaseModel):
    language: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: str | None = None


class FeedbackRequest(BaseModel):
    turn_id: str
    resolved: bool


@lru_cache
def _store():
    s = get_settings()
    return SupabaseStore(s.supabase_url, s.supabase_service_role_key) if s.use_supabase else MemoryStore()


_services: dict[str, DialogueService] = {}


def _knowledge_loader(tenant_id: str):
    s = get_settings()

    def load() -> KnowledgeBase:
        if s.use_supabase:
            from supabase import create_client

            db = create_client(s.supabase_url, s.supabase_service_role_key)
            rows = (db.table("knowledge_base").select("id,title,content,category,metadata,is_active,updated_at")
                    .eq("is_active", True).execute().data or [])
            version = max((r.get("updated_at") or "" for r in rows), default="0")
            return KnowledgeBase([from_supabase_row(r) for r in rows], version=version[:19])
        return KnowledgeBase(load_sample(tenant_id), version="sample")

    return load


def service_for(tenant_id: str) -> DialogueService:
    if tenant_id not in _services:
        try:
            tenant = get_tenant(tenant_id)
        except KeyError:
            raise HTTPException(404, detail={"code": "not_found", "message": "店がありません"})
        s = get_settings()
        cache = KnowledgeCache(_knowledge_loader(tenant_id))
        llm_cfg = tenant.config["llm"]
        llm = (GeminiDeveloperLLM(s.gemini_api_key, llm_cfg["model"], llm_cfg["temperature"], llm_cfg["max_output_tokens"])
               if s.use_real_llm else FakeLLM(cache.get))
        _services[tenant_id] = DialogueService(tenant, _store(), llm, cache, s.ip_hash_salt)
    return _services[tenant_id]


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def error(e: GuardError) -> JSONResponse:
    return JSONResponse({"code": e.code, "message": e.message}, status_code=e.status)


def screen_config(t: Tenant, mode: str) -> dict[str, Any]:
    c = t.copy
    return {
        "shop_name": t.config["shop_name"],
        "character_name": t.persona["character_name"],
        "languages": t.languages,
        "features": t.config["features"],
        "greeting_title": c.get("greeting_title", {}),
        "greeting": c.get("greeting", {}),
        "quick_questions": c.get("quick_questions", {}),
        "sfx": c.get("sfx", {}),
        "fallback_intro": c.get("fallback_intro", {}),
        "fallback_steps": c.get("fallback_steps", {}),
        "links": t.config.get("links", {}),
        "theme": t.theme,
        "mode": mode,
    }


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/t/{tenant_id}/config")
async def tenant_config(tenant_id: str):
    """画面の設定だけを返す。セッションを作る前と、縮退画面で使う。"""
    svc = service_for(tenant_id)
    return screen_config(svc.tenant, svc.llm.name)


@router.post("/t/{tenant_id}/sessions")
async def create_session(tenant_id: str, body: SessionRequest, request: Request):
    svc = service_for(tenant_id)
    try:
        s = await svc.create_session(client_ip(request), body.language)
    except GuardError as e:
        return error(e)
    return s | {"tenant": screen_config(svc.tenant, svc.llm.name)}


@router.post("/t/{tenant_id}/chat")
async def chat(tenant_id: str, body: ChatRequest, request: Request, x_session_id: str = Header(...)):
    svc = service_for(tenant_id)
    try:
        session = await svc.precheck(x_session_id, client_ip(request), body.message)
    except GuardError as e:
        return error(e)

    async def events():
        async for ev in svc.chat(session, body.message, body.language):
            yield f"event: {ev.name}\ndata: {json.dumps(ev.data, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/t/{tenant_id}/feedback", status_code=204)
async def feedback(tenant_id: str, body: FeedbackRequest, x_session_id: str = Header(...)):
    svc = service_for(tenant_id)
    try:
        await svc.feedback(x_session_id, body.turn_id, body.resolved)
    except GuardError as e:
        return error(e)
    return Response(status_code=204)

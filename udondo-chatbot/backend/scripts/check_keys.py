""".env.local の鍵が正しいかを確かめる。鍵の値は表示しない。

    .venv/bin/python scripts/check_keys.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bot.config import get_settings  # noqa: E402

BOT_TABLES = ["bot_sessions", "bot_turns", "bot_usage", "bot_daily_costs", "bot_unanswered", "bot_rate_limits"]


def check_gemini(key: str, model: str) -> str:
    if not key:
        return "未設定"
    from google import genai
    from google.genai import types

    try:
        client = genai.Client(api_key=key)
        r = client.models.generate_content(
            model=model, contents="「はい」とだけ答えて",
            config=types.GenerateContentConfig(max_output_tokens=10,
                                               thinking_config=types.ThinkingConfig(thinking_level="minimal")))
        return f"OK。{model} が応答した: {(r.text or '').strip()[:20]}"
    except Exception as e:  # noqa: BLE001
        return f"NG。{type(e).__name__}: {str(e)[:160]}"


def check_supabase(url: str, key: str) -> list[str]:
    if not url or not key:
        return ["未設定"]
    from supabase import create_client

    out = []
    try:
        db = create_client(url, key)
        n = db.table("knowledge_base").select("id", count="exact").eq("is_active", True).execute().count
        out.append(f"OK。knowledge_base の有効な行 {n} 件")
    except Exception as e:  # noqa: BLE001
        return [f"NG。{type(e).__name__}: {str(e)[:160]}"]
    for t in BOT_TABLES:
        try:
            db.table(t).select("*", count="exact").limit(1).execute()
            out.append(f"OK。{t} がある")
        except Exception:  # noqa: BLE001
            out.append(f"NG。{t} がない。001_bot_tables.sql を流す")
    return out


def main() -> None:
    s = get_settings()
    import yaml

    model = yaml.safe_load((Path(__file__).resolve().parents[1] / "tenants/udondo/tenant.yaml").read_text())["llm"]["model"]
    print("Gemini:", check_gemini(s.gemini_api_key, model))
    for line in check_supabase(s.supabase_url, s.supabase_service_role_key):
        print("Supabase:", line)
    print("IP_HASH_SALT:", "OK" if len(s.ip_hash_salt) >= 20 and s.ip_hash_salt != "demo-salt" else "未設定")


if __name__ == "__main__":
    main()

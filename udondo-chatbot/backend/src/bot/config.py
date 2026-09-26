"""環境変数と店の設定を読み込む。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[2]
TENANTS_DIR = BACKEND_DIR / "tenants"
_ENV_FILE = BACKEND_DIR.parent / ".env.local"


class Settings(BaseSettings):
    """鍵と接続先。値は .env.local か Vercel の環境変数から読む。"""

    gemini_api_key: str = ""
    supabase_url: str = Field(default="", alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_service_role_key: str = ""
    # auto は鍵があれば本物、なければ偽物を使う。fake は常に偽物を使う
    bot_mode: str = "auto"
    ip_hash_salt: str = "demo-salt"

    model_config = {
        "env_file": str(_ENV_FILE) if _ENV_FILE.exists() else None,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }

    @property
    def use_real_llm(self) -> bool:
        return self.bot_mode != "fake" and bool(self.gemini_api_key)

    @property
    def use_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


class Tenant:
    """tenants/<tenant_id>/ の設定ファイルをまとめて持つ。"""

    def __init__(self, tenant_id: str, root: Path = TENANTS_DIR):
        base = root / tenant_id
        if not base.is_dir():
            raise KeyError(tenant_id)
        self.id = tenant_id
        self.config: dict[str, Any] = self._load(base / "tenant.yaml")
        self.persona: dict[str, Any] = self._load(base / "persona.yaml")
        self.safety: dict[str, Any] = self._load(base / "safety_templates.yaml")
        self.copy: dict[str, Any] = self._load(base / "copy.yaml")
        self.theme: dict[str, Any] = self._load(base / "theme.yaml")

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    @property
    def limits(self) -> dict[str, Any]:
        return self.config["limits"]

    @property
    def languages(self) -> list[str]:
        return self.config["languages"]


@lru_cache
def get_tenant(tenant_id: str) -> Tenant:
    return Tenant(tenant_id)

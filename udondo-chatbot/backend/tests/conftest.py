import os

import pytest

# テストは常に偽の LLM とメモリの保存先で動かし、外部の API を呼ばない
os.environ["BOT_MODE"] = "fake"
os.environ["GEMINI_API_KEY"] = ""
os.environ["NEXT_PUBLIC_SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""


@pytest.fixture(autouse=True)
def fresh_app():
    from src.bot import api, config

    config.get_settings.cache_clear()
    config.get_tenant.cache_clear()
    api._store.cache_clear()
    api._services.clear()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.main import create_app

    return TestClient(create_app())

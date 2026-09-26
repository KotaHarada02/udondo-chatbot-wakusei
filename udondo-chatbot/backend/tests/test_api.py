import json


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        events.append((name, data))
    return events


def start(client, lang="ja"):
    r = client.post("/api/v1/t/udondo/sessions", json={"language": lang})
    assert r.status_code == 200
    return r.json()


def ask(client, sid, message):
    r = client.post("/api/v1/t/udondo/chat", json={"message": message}, headers={"X-Session-Id": sid})
    return r


def test_healthz(client):
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}


def test_session_returns_screen_config(client):
    s = start(client)
    assert s["remaining_turns"] == 20
    assert s["tenant"]["theme"]["variants"]["bot_message"] == "manga"
    assert s["tenant"]["mode"] == "fake"


def test_unknown_tenant(client):
    assert client.post("/api/v1/t/nope/sessions", json={}).status_code == 404


def test_chat_streams_meta_delta_done(client):
    s = start(client)
    r = ask(client, s["session_id"], "麺の茹で方と茹で時間を教えて")
    assert r.status_code == 200
    names = [n for n, _ in parse_sse(r.text)]
    assert names[0] == "meta" and names[-1] == "done" and "delta" in names
    meta = parse_sse(r.text)[0][1]
    assert meta["out_of_knowledge"] is False and meta["refs"]


def test_out_of_knowledge_is_flagged(client):
    s = start(client)
    events = parse_sse(ask(client, s["session_id"], "今日の天気は？").text)
    assert events[0][1]["out_of_knowledge"] is True


def test_safety_skips_llm(client):
    s = start(client)
    events = parse_sse(ask(client, s["session_id"], "熱湯でやけどした").text)
    names = [n for n, _ in events]
    assert names == ["meta", "safety", "done"]
    assert events[1][1]["template_id"] == "burn"


def test_requires_session(client):
    assert ask(client, "missing", "こんにちは").status_code == 401


def test_session_turn_limit(client):
    from src.bot.api import service_for

    svc = service_for("udondo")
    svc.tenant.limits["session_turns"] = 1
    svc.tenant.limits["ip_per_minute"] = 100
    s = start(client)
    ask(client, s["session_id"], "麺の茹で方")
    events = parse_sse(ask(client, s["session_id"], "麺の茹で方").text)
    assert events == [("degraded", {"reason": "session_limit"})]


def test_rate_limit(client):
    from src.bot.api import service_for

    service_for("udondo").tenant.limits["ip_per_minute"] = 2
    s = start(client)
    ask(client, s["session_id"], "麺の茹で方")
    assert ask(client, s["session_id"], "麺の茹で方").status_code == 429


def test_daily_cap(client):
    import asyncio

    from src.bot.api import service_for
    from src.bot.service import today

    svc = service_for("udondo")
    s = start(client)
    asyncio.run(svc.store.add_daily_cost("udondo", today(), 60.0, 0, 0))
    r = ask(client, s["session_id"], "麺の茹で方")
    assert r.status_code == 503 and r.json()["code"] == "daily_cap"


def test_feedback(client):
    s = start(client)
    done = parse_sse(ask(client, s["session_id"], "麺の茹で方と茹で時間").text)[-1][1]
    h = {"X-Session-Id": s["session_id"]}
    assert client.post("/api/v1/t/udondo/feedback", json={"turn_id": done["turn_id"], "resolved": False}, headers=h).status_code == 204
    assert client.post("/api/v1/t/udondo/feedback", json={"turn_id": "x", "resolved": True}, headers=h).status_code == 404

from src.bot.config import get_tenant
from src.bot.knowledge import KnowledgeBase, KnowledgeItem, from_supabase_row, load_sample
from src.bot.prompt import build_contents, build_system_prompt, looks_leaked


def test_from_supabase_row_routes_non_video_urls_to_link():
    manga = from_supabase_row({"id": 1, "title": "名前の由来", "content": "c", "category": "about",
                               "metadata": {"youtube_url": "https://www.udondo.com/マンガnew"}})
    video = from_supabase_row({"id": 2, "title": "t", "content": "c", "metadata": {"youtube_url": "https://youtu.be/x"}})
    line = from_supabase_row({"id": 3, "title": "t", "content": "c", "metadata": {"line_url": "https://line.me/x"}})
    assert (manga.video_url, manga.link_url) == (None, "https://www.udondo.com/マンガnew")
    assert video.video_url == "https://youtu.be/x"
    assert line.link_url == "https://line.me/x"


def test_knowledge_sorted_and_resolved():
    kb = KnowledgeBase([KnowledgeItem("b", "q2", "a2", "rule"), KnowledgeItem("a", "q1", "a1", "rule", step_no=1)], "v1")
    assert kb.items[0].id == "a"
    assert [k.id for k in kb.resolve(["K1", "K9"])] == ["a"]
    assert '<knowledge version="v1">' in kb.prompt_block() and "[K2] category=rule" in kb.prompt_block()


def test_system_prompt_has_persona_rules_and_knowledge():
    t = get_tenant("udondo")
    kb = KnowledgeBase(load_sample("udondo"), "sample")
    p = build_system_prompt(t, kb)
    assert "ウドンド" in p and "一人称は「俺」" in p and "<knowledge" in p and "#meta" in p
    # 固定部分は毎回同じ文字列になる
    assert p == build_system_prompt(t, kb)


def test_contents_wraps_customer_text_and_trims_history():
    c = build_contents([("前の質問", "あ" * 500)], "ja", "今の質問")
    assert c[-1]["parts"][0]["text"] == '<customer_message lang="ja">\n今の質問\n</customer_message>'
    assert len(c[1]["parts"][0]["text"]) == 200


def test_leak_detection():
    assert looks_leaked("# 答え方の規則 1. ...")
    assert not looks_leaked("標準は10分だ。")

import pytest

from src.bot.config import get_tenant
from src.bot.safety import SafetyRouter, clean_input, mask_pii


@pytest.fixture
def router():
    return SafetyRouter(get_tenant("udondo"))


@pytest.mark.parametrize("text,kind", [
    ("熱湯がかかってやけどした", "burn"),
    ("I got burned by hot water", "burn"),
    ("被烫伤了", "burn"),
    ("화상을 입었어요", "burn"),
    ("煙が出ている", "fire"),
    ("不審な人がいて怖い", "suspicious"),
    ("友達が倒れた", "sick"),
])
def test_detect(router, text, kind):
    assert router.detect(text) == kind


@pytest.mark.parametrize("text", ["スープが熱い", "麺が硬くて顎が痛い", "何分茹でる？"])
def test_no_false_positive(router, text):
    assert router.detect(text) is None


def test_answer_language_and_fallback(router):
    assert router.answer("burn", "en").text.startswith("If you get burned")
    assert router.answer("burn", "xx").text.startswith("やけどしたら")


def test_mask_pii():
    assert mask_pii("電話は090-1234-5678です") == "電話は[電話番号]です"
    assert mask_pii("mail me a@b.co") == "mail me [メール]"
    assert mask_pii("カード 4111 1111 1111 1111") == "カード [番号]"
    assert mask_pii("注文番号は1234です") == "注文番号は1234です"


def test_clean_input():
    assert clean_input("  a\x00b  ", 10) == "ab"
    assert len(clean_input("あ" * 500, 300)) == 300

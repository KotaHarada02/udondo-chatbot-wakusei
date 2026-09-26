from src.bot.meta import MetaSplitter, parse_meta_line


def test_parse_valid():
    m = parse_meta_line('#meta {"e":"smile","r":["K3"],"o":false,"s":""}')
    assert (m.emotion, m.refs, m.out_of_knowledge, m.safety, m.broken) == ("smile", ["K3"], False, "", False)


def test_parse_unknown_values_fall_back():
    m = parse_meta_line('#meta {"e":"angry","r":[],"o":true,"s":"flood"}')
    assert m.emotion == "neutral" and m.safety == "" and m.out_of_knowledge is True


def test_parse_broken():
    assert parse_meta_line("こんにちは").broken
    assert parse_meta_line("#meta {oops").broken


def test_splitter_holds_until_newline():
    s = MetaSplitter()
    assert s.feed('#meta {"e":"smile",') == ""
    assert s.feed('"r":[],"o":false,"s":""}\n標準は') == "標準は"
    assert s.feed("10分だ。") == "10分だ。"
    assert s.meta.emotion == "smile"


def test_splitter_without_meta_passes_text():
    s = MetaSplitter()
    assert s.feed("メタ行がない答え\n続き") == "メタ行がない答え\n続き"
    assert s.meta.broken


def test_splitter_finish_without_newline():
    s = MetaSplitter()
    assert s.feed("改行のない答え") == ""
    assert s.finish() == "改行のない答え"

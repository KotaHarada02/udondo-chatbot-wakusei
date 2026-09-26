from src.bot.meta import MetaSplitter, parse_meta_line


def test_parse_valid():
    m = parse_meta_line('#meta {"e":"smile","r":["K3"],"o":false,"s":""}')
    assert (m.emotion, m.refs, m.out_of_knowledge, m.safety, m.broken) == ("smile", ["K3"], False, "", False)


def test_parse_unknown_values_fall_back():
    m = parse_meta_line('#meta {"e":"angry","r":[],"o":true,"s":"flood"}')
    assert m.emotion == "neutral" and m.safety == "" and m.out_of_knowledge is True


def test_parse_broken():
    assert parse_meta_line("こんにちは").broken
    # #meta で始まる行は読めなくても本文に回さない
    m = parse_meta_line("#meta {oops")
    assert not m.broken and m.emotion == "neutral"


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


def test_parse_repairs_double_colon():
    m = parse_meta_line('#meta {"e":"neutral","r":["K16"],"o":false,"s"::""}')
    assert (m.refs, m.out_of_knowledge, m.broken) == (["K16"], False, False)


def test_parse_extracts_fields_from_mangled_json():
    m = parse_meta_line('#meta {e:"sorry", "r": ["K1" "K2"], "o": true, "s": "burn"')
    assert m.out_of_knowledge is True and m.safety == "burn" and not m.broken


def test_unreadable_meta_line_is_never_shown():
    s = MetaSplitter()
    assert s.feed("#meta {{{\n本文") == "本文"
    assert not s.meta.broken

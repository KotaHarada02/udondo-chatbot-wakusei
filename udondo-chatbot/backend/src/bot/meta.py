"""回答の1行目のメタ行を、ストリーミングの途中で読み取る。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

EMOTIONS = {"neutral", "smile", "think", "surprise", "sorry", "serious"}
SAFETY_KINDS = {"burn", "injury", "fire", "sick", "suspicious"}
PREFIX = "#meta"


@dataclass
class Meta:
    emotion: str = "neutral"
    refs: list[str] = field(default_factory=list)
    out_of_knowledge: bool = False
    safety: str = ""
    broken: bool = False


def _loads_lenient(raw: str) -> dict | None:
    """LLM が少し崩した JSON も読む。読めなければ項目ごとに拾う。"""
    for candidate in (raw, re.sub(r":\s*:", ":", raw).replace("'", '"')):
        try:
            d = json.loads(candidate)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            pass
    d: dict = {}
    if m := re.search(r'"e"\W*"(\w+)"', raw):
        d["e"] = m.group(1)
    if m := re.search(r'"r"\W*\[([^\]]*)\]', raw):
        d["r"] = re.findall(r'"([^"]+)"', m.group(1))
    if m := re.search(r'"o"\W*(true|false)', raw):
        d["o"] = m.group(1) == "true"
    if m := re.search(r'"s"\W*"(\w*)"', raw):
        d["s"] = m.group(1)
    return d or None


def parse_meta_line(line: str) -> Meta:
    """メタ行を読む。#meta で始まらない行だけを broken とし、本文として扱わせる。"""
    line = line.strip()
    if not line.startswith(PREFIX):
        return Meta(broken=True)
    d = _loads_lenient(line[len(PREFIX):].strip())
    if d is None:
        # #meta で始まる行は、読めなくても客には出さない
        return Meta()
    emotion = d.get("e") if d.get("e") in EMOTIONS else "neutral"
    refs = [str(r) for r in d.get("r", []) if isinstance(r, (str, int))]
    safety = d.get("s") if d.get("s") in SAFETY_KINDS else ""
    return Meta(emotion=emotion, refs=refs, out_of_knowledge=d.get("o") is True, safety=safety)


class MetaSplitter:
    """断片を受け取り、最初の改行までをメタ行として切り分ける。"""

    def __init__(self) -> None:
        self._buf = ""
        self.meta: Meta | None = None

    def feed(self, chunk: str) -> str:
        """本文として客に送ってよい文字列を返す。メタ行を読み終えるまでは空文字を返す。"""
        if self.meta is not None:
            return chunk
        self._buf += chunk
        if "\n" not in self._buf:
            return ""
        head, rest = self._buf.split("\n", 1)
        self.meta = parse_meta_line(head)
        if self.meta.broken:
            # メタ行がなければ、受け取った文字をすべて本文として扱う
            return self._buf
        return rest.lstrip("\n")

    def finish(self) -> str:
        """改行が来ないまま終わったときの残りを返す。"""
        if self.meta is not None:
            return ""
        self.meta = parse_meta_line(self._buf)
        return "" if not self.meta.broken else self._buf

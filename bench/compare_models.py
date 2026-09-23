"""Goal C1: MARCO and other models on the same frozen exams, scored from the reply text alone.

Every frozen dialogue (``data/benchmarks/dialogues_v1/``) and every frozen
reasoning problem (``data/benchmarks/reasoning_v1/``, setup statements and
questions in the gate's play order) is played turn by turn through an
*answerer* (``bench/answerers/``): ``answer(history, utterance) -> str``, with
the whole conversation so far as history.  The reply text is the only thing
scored, by one extractor applied identically to every model, MARCO included:

* the value: digits, English number words, Korean native numerals with or
  without a counter; quoted, bracketed and parenthesised spans are removed
  first (they cite, they do not assert: ``dialogue_gate.asserted``);
* the holder: which of the conversation's names a value, a comparison or a
  place belongs to (``than X`` / ``X보다`` is the other side; ``from X`` /
  ``X에서`` is where it was);
* a hold: a clause that declines or says the information is missing
  (``DECLINE_EN`` / ``DECLINE_KO``), or a reply that only asks back.

Buckets and denominators follow the two gates.  Dialogues
(``bench/dialogue_gate.py``): the 108 answerable turns are correct / wrong /
hold / unverifiable / execution_error; missing-premise, ambiguous and
unsupported turns are scored as the gate scores them, with "the reply holds"
read from the text instead of from the engine's verdict.  Statement,
correction and "why" turns are not scored: the gate checks them against the
engine's recorded state and evidence rows, which a reply text cannot show.
Reasoning (``bench/reasoning_gate.py``): every question is correct / wrong /
hold / execution_error, a problem is correct when every question is, wrong
when any is; there is no "unparsed" bucket, because a text reply cannot show
whether a setup statement was recorded, so every model is scored over all
114 problems and 156 questions.

Two more columns per model: **invented answers**, value-bearing replies on
turns whose premise is missing or whose request is unsupported (gate
condition 3), and **cost**: wall-clock latency and the process's physical
memory footprint (macOS ``phys_footprint``, which counts GPU buffers) per turn.

Commands (``python bench/compare_models.py <command>``):

  run <answerer>   play both sets through one answerer, save the replies to
                   the answers folder (outside the repository: models echo exam
                   sentences), score them and write the report JSON
  score <answers>  score a saved answers file again
  table            print the comparison table from the report JSONs

Reports hold aggregates and per-turn buckets by id only: no exam sentence and
no reply text.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "bench") not in sys.path:
    sys.path.insert(0, str(ROOT / "bench"))
import dialogue_gate as gate  # noqa: E402
import reasoning_gate as rgate  # noqa: E402

SCHEMA = "marco1-model-comparison-v1"
REPORT_DIR = ROOT / "docs/ko/model-comparison-2026-09-24"
ANSWERS_DIR = Path(os.environ.get("NAI_COMPARE_ANSWERS",
                                  Path.home() / ".cache" / "nai-model-comparison-2026-09-24"))
SETS = ("dialogues", "reasoning")
GATE_REPORTS = {"dialogues": ROOT / "docs/ko/dialogue-gate-2026-09-22/round2.json",
                "reasoning": ROOT / "docs/ko/reasoning-gate-2026-09-24/round2.json"}
D_BUCKETS = ("correct", "wrong", "hold", "unverifiable", "execution_error")
R_BUCKETS = ("correct", "wrong", "hold", "execution_error")
QUANTITY_RELATIONS = {"count", "total", "initial_quantity"}


# ---------------------------------------------------------------------------
# memory: the process's physical footprint (what Activity Monitor calls Memory)
# ---------------------------------------------------------------------------
_RUSAGE_INFO_V4 = 4
_UUID_WORDS = 2       # ri_uuid is 16 bytes, then uint64 fields
_RESIDENT, _FOOTPRINT, _LIFETIME_MAX = 6, 7, 28
_LIBPROC = None


def memory():
    """``{"footprint_mb", "resident_mb", "peak_footprint_mb"}`` for this process, or ``{}`` off macOS."""
    if platform.system() != "Darwin":
        try:
            import resource
            return {"peak_resident_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 10, 1)}
        except Exception:  # pragma: no cover
            return {}
    global _LIBPROC
    try:
        _LIBPROC = _LIBPROC or ctypes.CDLL("/usr/lib/libproc.dylib")
        buf = (ctypes.c_uint64 * 64)()
        if _LIBPROC.proc_pid_rusage(os.getpid(), _RUSAGE_INFO_V4, ctypes.byref(buf)) != 0:
            return {}
    except OSError:  # pragma: no cover
        return {}
    mb = lambda i: round(buf[_UUID_WORDS + i] / 2 ** 20, 1)  # noqa: E731
    return {"footprint_mb": mb(_FOOTPRINT), "resident_mb": mb(_RESIDENT), "peak_footprint_mb": mb(_LIFETIME_MAX)}


# ---------------------------------------------------------------------------
# the extractor: reply text -> value, holder, hold
# ---------------------------------------------------------------------------
DECLINE_EN = [re.compile(p, re.I) for p in (
    r"\b(?:i|we)\s+(?:do\s+not|don't|dont|did\s+not|didn't)\s+(?:know|have|see|find|remember)\b",
    r"\b(?:i|we)\s+(?:cannot|can't|can\s+not|could\s+not|couldn't|am\s+unable|'m\s+unable|am\s+not\s+able|"
    r"'m\s+not\s+able|was\s+not\s+able|wasn't\s+able|have\s+no)\b",
    r"\b(?:don't|do\s+not|doesn't|does\s+not|didn't|did\s+not)\s+(?:say|mention|specify|tell|state|give|include|"
    r"provide|indicate|know)\b",
    r"\b(?:not|never|wasn't|weren't|isn't|aren't|hasn't|haven't|hadn't)\s+(?:been\s+|yet\s+)?(?:mentioned|given|"
    r"stated|specified|provided|said|told|known|included|recorded|shared|indicated|available|determinable|"
    r"derivable)\b",
    r"\bno\s+(?:information|info|data|mention|records?|details?|indication|way\s+to\s+(?:know|tell|determine))\b",
    r"\b(?:not|insufficient|isn't|is\s+not)\s+(?:enough|sufficient)\s+(?:information|info|data|details?)\b",
    r"\binsufficient\s+(?:information|info|data)\b",
    r"\b(?:can't|cannot|can\s+not|couldn't|could\s+not|unable\s+to|impossible\s+to|not\s+possible\s+to)\s+"
    r"(?:be\s+)?(?:know|known|tell|say|determine|determined|answer|answered|conclude|concluded|sure|certain|"
    r"infer|inferred|deduce|deduced|find|read|help|provide|predict|access|check|summari[sz]e|write|compose|do|"
    r"give|confirm|verify)\b",
    r"\b(?:unknown|unclear|uncertain|unspecified|unanswerable|undetermined|indeterminate)\b",
    r"\bnot\s+(?:sure|certain)\b", r"\bno\s+idea\b", r"\bsorry\b", r"\bnot\s+necessarily\b", r"\bnot\s+able\s+to\b",
    r"\bcould\s+not\b", r"\bcouldn't\b",
    r"\b(?:please|could\s+you|can\s+you|would\s+you)\s+(?:tell|say|let\s+me\s+know|give|specify|clarify|check|"
    r"confirm|rephrase|provide)\b",
    r"\blet\s+me\s+know\b",
    r"\b(?:not|isn't|wasn't|aren't|weren't)\s+(?:in|part\s+of)\s+(?:the|our|this|what)\s+(?:conversation|dialogue|"
    r"information|facts|you\s+(?:said|told|gave))\b")]
DECLINE_KO_PATTERN = re.compile(r"(?:정보|언급|내용|기록|말씀)[은는이가도]?\s*(?:\S+\s+){0,2}없")
DECLINE_KO = (
    "모르", "모릅", "알 수 없", "알 수가 없", "알 수는 없", "알지 못", "알려지지 않", "말씀하지 않", "말씀하시지 않",
    "말하지 않", "말씀 안", "말한 적", "말씀하신 적", "언급되지 않", "언급하지 않", "언급이 없", "언급은 없", "언급된 적",
    "언급된 바", "언급하신 적", "나와 있지 않", "나와있지 않", "나오지 않", "주어지지 않", "주어지지않", "제공되지 않",
    "명시되지 않", "명시하지 않", "밝히지 않", "정보가 없", "정보는 없", "정보도 없", "정보가 부족", "정보가 충분하지",
    "정보를 찾을 수 없", "기록이 없", "기록되지 않", "기록에 없", "근거가 없", "근거는 없", "확인하지 못", "확인이 어렵",
    "확인되지 않", "판단하기 어렵", "단정하기 어렵", "수 없", "수가 없", "수는 없", "지 못했", "지 못합", "지 못해",
    "지 못하", "못 했", "불가", "죄송", "어렵습니다", "어려워요", "어렵네요", "지원하지 않", "지원되지 않",
    "확실하지 않", "확실하지는 않", "확실치는 않",
    "확실치 않", "불확실", "알려 주세요", "알려주세요", "알려 주시면", "알려주시면", "말씀해 주세요", "말씀해주세요",
    "말씀해 주시면", "말해 주세요", "말해주세요", "알려주지 않", "알려 주지 않", "알려주시지 않", "알려 주시지 않",
    "확인해 주세요", "확인해주세요")
HEDGE = re.compile(r"\b(?:probably|maybe|perhaps|likely|i\s+think|i\s+believe|i\s+guess|roughly|"
                   r"approximately|possibly|might)\b|아마|것 같|듯|쯤|정도|추정|일지도|일 수도|수도 있", re.I)
ASK_WHICH = re.compile(r"\b(?:which|who\s+do\s+you\s+mean|do\s+you\s+mean|are\s+you\s+asking|clarify)\b|"
                       r"어느|누구|누굴|어떤 분|어떤 사람|말씀하시는|말하는 건|말씀인가", re.I)
_SENTENCES = re.compile(r"(?<=[.!?。])\s+|\n+|;\s*")
_CONTRAST = re.compile(r",?\s*\b(?:but|however|although|though|whereas)\b\s*|(?<=지만)\s*|(?<=는데)\s*,?\s*|"
                       r"\s*(?:하지만|그러나|그런데|다만)\s*", re.I)
_SEGMENT = re.compile(r",\s*|\s+(?=(?:and|so|therefore|thus|hence|which|leaving|making)\b)|(?<=[고서며])\s+|"
                      r"(?<=면서)\s*|(?<=니까)\s*|(?<=므로)\s*|\s*(?=그리고|그래서|따라서|그러므로|결국)", re.I)
PAST = re.compile(r"\b(?:had|was|were|used\s+to|originally|at\s+first|initially|before|earlier|previously|"
                  r"started\s+with|began\s+with)\b|원래|처음|전에|이전|있었|였|이었", re.I)
CONCLUSION = re.compile(r"\b(?:so|therefore|thus|hence|now|in\s+total|altogether|total|overall|in\s+all|makes|"
                        r"leaving|leaves|left\s+with|ends?\s+up)\b|=|→|따라서|그래서|그러므로|결국|이제|지금|합쳐|합하면|"
                        r"합치면|모두|총|전부|남아|남았|남은|됩니다|돼요|됐|된다", re.I)
TOTAL = re.compile(r"\b(?:together|total|altogether|combined|in\s+all|both|sum|all)\b|합|모두|총|전부|둘 다|두 사람|"
                   r"함께|다 해서", re.I)
MORE = re.compile(r"\b(?:more|most|greater|larger|bigger|taller|higher|longer)\b|많|크|커|높|길", re.I)
NOW = re.compile(r"\b(?:now|currently|at\s+the\s+moment|at\s+present|still)\b|지금|현재|이제|여전히", re.I)
LESS = re.compile(r"\b(?:fewer|less|least|smaller|shorter|lower)\b|적|작|짧|낮|덜", re.I)
YES = re.compile(r"^\W*(?:yes|yeah|yep|correct|right|true|indeed|certainly|definitely)\b|"
                 r"^\W*(?:네|예|응|맞아|맞습니다|맞아요|그렇습니다|그래요|그렇다)", re.I)
NO = re.compile(r"^\W*(?:no|nope|false)\b|^\W*(?:아니|아뇨)", re.I)
NEGATION = re.compile(r"\b(?:not|isn't|aren't|doesn't|don't|cannot|can't|never|no)\b|아니|않|없|못", re.I)
_KO_STANDALONE = re.compile(
    r"(?<![가-힣])(열|스물|서른|마흔|쉰)?(하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉)?"
    r"(?=(?:이에요|예요|이야|야|입니다|이다|이고|이며|이네요|네요|이지|입니까|이요|요)(?![가-힣])|"
    r"(?:\s*(?:$|[.,!?~]))|\s(?!\s*다(?:[\s.,!?]|$)))")
_ZERO = re.compile(r"\bnone\b|하나도 없|한 개도 없|아무것도 없", re.I)
_UNITS = {"하나": 1, "둘": 2, "셋": 3, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_TENS = {"열": 10, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50}
_COPULA = re.compile(r"^(?:이에요|예요|이야|야|입니다|이다|이고|이며|이네요|네요|이지|입니까|이요|요)")


def asserted(text):
    """The reply without quoted, bracketed and parenthesised spans (the gate's rule)."""
    return gate.asserted(text or "")


def quantities(text):
    """Every quantity ``text`` states: the gate's digits and number words, plus Korean native
    numerals standing without a counter (``다섯이에요``, ``하나 남았어요``) and "none"."""
    values = set(gate.quantities(text))
    for m in _KO_STANDALONE.finditer(text):
        tens, unit = m.group(1), m.group(2)
        if not (tens or unit):
            continue
        if tens and not unit and not _COPULA.match(text[m.end():]):
            continue          # a bare 열 before a space is as often the verb "open"
        values.add(_TENS.get(tens, 0) + _UNITS.get(unit, 0))
    if _ZERO.search(text):
        values.add(0)
    return values


def declines(text):
    lower = (text or "").lower()
    return (any(p.search(lower) for p in DECLINE_EN) or any(m in text for m in DECLINE_KO)
            or bool(DECLINE_KO_PATTERN.search(text)))


def clauses(text):
    """Sentences, then contrastive clauses ("but", "하지만", "-지만", "-는데")."""
    out = []
    for sentence in _SENTENCES.split(text or ""):
        out += [c.strip() for c in _CONTRAST.split(sentence) if c and c.strip()]
    return out


def segments(text):
    """Clauses cut finer at commas, "and"/"so", and Korean connectives, for attributing values."""
    out = []
    for clause in clauses(text):
        out += [s.strip() for s in _SEGMENT.split(clause) if s and s.strip()]
    return out


def mentions(text, name):
    return bool(name) and gate._mentions(text, name)


def read(reply):
    """What a reply says, before any expectation is consulted."""
    raw = reply or ""
    text = asserted(raw)
    parts = clauses(text)
    declined_parts = [c for c in parts if declines(c)]
    assertive = " . ".join(c for c in parts if not declines(c))
    stripped = text.strip()
    return {"text": text, "assertive": assertive, "declined": bool(declined_parts),
            "question_only": stripped.endswith(("?", "？")) and not quantities(assertive),
            "empty": not re.search(r"[0-9A-Za-z가-힣]", raw), "hedged": bool(HEDGE.search(text)),
            "values": quantities(assertive)}


def _tier_value(rows):
    """One value from segments ``[(segment, values)]``: the single distinct value, else the last
    segment that concludes ("so", "now", "=", "따라서", "이제" ...), else the value after "="."""
    values = {v for _s, vs in rows for v in vs}
    if len(values) == 1:
        return next(iter(values)), None
    if not values:
        return None, None
    concluding = [(s, vs) for s, vs in rows if CONCLUSION.search(s)]
    if concluding:
        segment, vs = concluding[-1]
        for mark in ("=", "→"):
            if mark in segment:
                after = quantities(segment.rsplit(mark, 1)[1])
                if len(after) == 1:
                    return next(iter(after)), None
        tail = CONCLUSION.split(segment)[-1]
        after = quantities(tail)
        if len(after) == 1:
            return next(iter(after)), None
        if len(vs) == 1:
            return next(iter(vs)), None
    return None, sorted(values)


def value_for(reply_text, entity, holders):
    """The value a reply states for ``entity`` (a name, or a list of names for a total).

    Returns ``(value, reason)``: ``value`` is None when no value is stated
    (reason ``no_value``), when only other holders' values are stated
    (``other_holder``) or when several values remain (``several:[...]``).
    """
    total = isinstance(entity, list)
    members = set(entity) if total else {entity}
    others = [h for h in holders if h not in members and not any(mentions(h, m) for m in members)]
    rows = []
    for segment in segments(reply_text):
        vs = quantities(segment)
        if not vs:
            continue
        own = any(mentions(segment, m) for m in members)
        other = any(mentions(segment, h) for h in others)
        kind = "mixed" if own and other else "own" if own else "other" if other else "neutral"
        rows.append({"segment": segment, "values": vs, "kind": kind, "past": bool(PAST.search(segment)),
                     "total": bool(TOTAL.search(segment))})
    if not rows:
        return None, "no_value"
    usable = [r for r in rows if r["kind"] != "other"]
    if not usable:
        return None, "other_holder"
    if any(not r["past"] for r in usable):
        usable = [r for r in usable if not r["past"]]
    concluding = [r for r in usable if r["kind"] in ("own", "neutral") and CONCLUSION.search(r["segment"])]
    last = [concluding[-1]] if concluding else []
    tiers = ([[r for r in usable if r["total"]], last, usable] if total else
             [last, [r for r in usable if r["kind"] == "own"], [r for r in usable if r["kind"] == "neutral"],
              [r for r in usable if r["kind"] == "mixed"]])
    for tier in tiers:
        if tier:
            value, several = _tier_value([(r["segment"], r["values"]) for r in tier])
            if value is not None:
                return value, "value"
            if several:
                return None, "several:%s" % several
    return None, "no_value"


def _than_side(segment, name):
    """True when ``name`` is the other side of a comparison in ``segment``: "than X", "X보다"."""
    lower = segment.lower()
    if re.fullmatch(r"[a-z .'-]+", name.lower()):
        return re.search(r"\bthan\s+(?:the\s+)?%s(?![a-z])" % re.escape(name.lower()), lower) is not None
    return re.search(re.escape(name) + r"(?:이|이가|가|는|은)?\s*보다", segment) is not None


def _without_restated_pair(segment, candidates):
    """Drop a restated question pair: "X와 Y 중 ...", "Between X and Y, ...", "Of X and Y, ..."."""
    for pattern in (r"^.*?(?:중에서|중에|중)\s+", r"^\s*(?:between|of|out\s+of)\s+[^,]+,\s*"):
        m = re.match(pattern, segment, re.I)
        if m and all(mentions(m.group(0), c) for c in candidates):
            return segment[m.end():]
    return segment


def claimed_candidate(reply_text, candidates):
    """Which candidate a comparison reply picks: ``(name, reason)``; name None with reason
    ``none`` or ``several``."""
    segs = segments(reply_text)
    comparative = [s for s in segs if MORE.search(s) or LESS.search(s)]
    scopes = [comparative[-1]] if comparative else [reply_text]
    for scope in scopes:
        scope = _without_restated_pair(scope, candidates)
        named = [c for c in candidates if mentions(scope, c)]
        if len(named) > 1:
            named = [c for c in named if not _than_side(scope, c)] or named
        if len(named) == 1:
            if LESS.search(scope) and not MORE.search(scope) and len(candidates) == 2:
                return next(c for c in candidates if c != named[0]), "inverted"
            return named[0], "named"
        if len(named) > 1:
            return None, "several"
    named = [c for c in candidates if mentions(reply_text, c)]
    return (named[0], "named") if len(named) == 1 else (None, "several" if named else "none")


_FROM_EN = (r"(?:from|not(?:\s+(?:in|on|at))?|no\s+longer\s+(?:in|on|at)|instead\s+of|rather\s+than|out\s+of|"
            r"left)\s+(?:the\s+)?")
_FROM_KO = r"\s*(?:에서|이\s*아니|가\s*아니|말고|대신)"


def claimed_place(reply_text, places):
    """Which of ``places`` the reply puts the item in now: ``(place, reason)``."""
    segs = segments(reply_text) or [reply_text]
    current = [s for s in segs if not PAST.search(s)] or segs
    now = [s for s in current if NOW.search(s) and any(mentions(s, p) for p in places)]
    named = [p for p in places if any(mentions(s, p) for s in (now or current))]
    if len(named) > 1:
        kept = []
        for p in named:
            if re.fullmatch(r"[a-z .'-]+", p.lower()):
                away = re.search(_FROM_EN + re.escape(p.lower()) + r"(?![a-z])", reply_text.lower())
            else:
                away = re.search(re.escape(p) + _FROM_KO, reply_text)
            if not away:
                kept.append(p)
        named = kept or named
    if len(named) == 1:
        return named[0], "named"
    return None, "several" if named else "none"


def yes_no(reply_text, obj):
    """``yes`` / ``no`` / ``undetermined`` / None for a membership question."""
    text = reply_text.strip()
    if YES.search(text):
        return "yes"
    if NO.search(text):
        return "no"
    if declines(text):
        return "undetermined"
    if NEGATION.search(text):
        return "no"
    if obj and mentions(text, obj):
        return "yes"
    return None


# ---------------------------------------------------------------------------
# scoring one turn: the gates' buckets, read from the text
# ---------------------------------------------------------------------------
def dialogue_holders(dialogue):
    names = set()
    for t in dialogue["turns"]:
        e = t["expect"]
        for ev in (e.get("events") or []) + (e.get("with") or []) + (e.get("replaces") or []):
            names.update(ev[k] for k in ("holder", "from", "to") if ev.get(k))
        names.update(row["entity"] for row in e.get("state") or [] if row.get("entity"))
        entity = e.get("entity")
        names.update(entity if isinstance(entity, list) else [entity] if entity else [])
        names.update(e.get("candidates") or [])
    return sorted(names, key=len, reverse=True)


def problem_holders(problem):
    names = set()
    for s in problem["setup"]:
        for ev in s["events"]:
            names.update(ev[k] for k in ("holder", "from", "to", "member", "a", "b") if ev.get(k))
    for q in problem["questions"]:
        e = q["expect"]
        names.update(x for x in [e.get("entity"), e.get("subject")] + list(e.get("members") or [])
                     + list(e.get("candidates") or []) if x)
    return sorted(names, key=len, reverse=True)


def _result(bucket, reason, r, **extra):
    out = {"bucket": bucket, "reason": reason, "declined": r["declined"], "hedged": r["hedged"]}
    out.update(extra)
    return out


def score_dialogue_turn(dialogue, turn, row, holders=None):
    """Bucket for one dialogue turn from its reply text, mirroring ``dialogue_gate.score_turn``."""
    e, label = turn["expect"], turn["label"]
    if row.get("error"):
        return {"bucket": "execution_error", "reason": "error", "declined": False, "hedged": False}
    r = read(row.get("reply"))
    holders = holders if holders is not None else dialogue_holders(dialogue)
    if label == "answerable":
        if r["empty"]:
            return _result("hold", "empty_reply", r)
        if e["relation"] == "more":
            name, how = claimed_candidate(r["assertive"], e["candidates"])
            if name is None and (r["declined"] or r["question_only"]):
                return _result("hold", "declined", r)
            if name == e["entity"]:
                return _result("correct", "entity", r)
            if name is not None:
                return _result("wrong", "other_entity", r)
            return _result("unverifiable", "several_candidates_named" if how == "several" else
                           "no_candidate_named", r)
        value, how = value_for(r["assertive"], e["entity"], holders)
        if value is None:
            if r["declined"] or r["question_only"]:
                return _result("hold", "declined", r)
            if how == "other_holder":
                return _result("wrong", "other_holder", r)
            if how.startswith("several"):
                return _result("unverifiable", "several_quantities", r, values=json.loads(how.split(":", 1)[1]))
            return _result("unverifiable", "no_quantity_in_answer", r)
        if value != e["quantity"]:
            if value == e.get("retracted_quantity"):
                return _result("wrong", "retracted_value", r, value=value)
            if value == e.get("reexecuted_quantity"):
                return _result("wrong", "correction_reexecuted", r, value=value)
            return _result("wrong", "value", r, value=value)
        return _result("correct", "value", r, value=value)
    if label in ("hold", "ambiguous", "unsupported") and e["act"] in ("hold", "clarify", "decline"):
        quantity = e.get("relation") in QUANTITY_RELATIONS
        bearing = bool(r["values"]) if quantity or label == "ambiguous" else bool(r["assertive"].strip())
        if r["empty"]:
            return _result("hold", "empty_reply", r, invented=False)
        if label == "ambiguous":
            asks = r["question_only"] or bool(ASK_WHICH.search(r["text"]))
            both = all(mentions(r["text"], c) for c in e["candidates"])
            if both and (asks or r["declined"]):
                return _result("correct", "asked_which", r, invented=False)
            if r["values"] and not r["declined"]:
                return _result("wrong", "confident_answer", r, invented=True)
            if r["declined"] or asks:
                return _result("hold", "vague_hold", r, invented=False)
            return _result("wrong", "confident_answer", r, invented=bearing)
        held = r["declined"] or r["question_only"]
        if label == "unsupported":
            return (_result("correct", "declined", r, invented=False) if held else
                    _result("wrong", "confident_answer", r, invented=bearing))
        if held:
            return (_result("correct", "held_and_named", r, invented=False) if mentions(r["text"], e["entity"])
                    else _result("hold", "vague_hold", r, invented=False))
        return _result("wrong", "confident_answer", r, invented=bearing)
    return {"bucket": "not_scored", "reason": "%s: needs the engine's recorded state or evidence rows" % label,
            "declined": r["declined"], "hedged": r["hedged"]}


def score_question(problem, question, row, holders=None):
    """Bucket for one reasoning question from its reply text, mirroring ``reasoning_gate.score_question``."""
    e = question["expect"]
    if row.get("error"):
        return {"bucket": "execution_error", "reason": "error", "declined": False, "hedged": False}
    r = read(row.get("reply"))
    holders = holders if holders is not None else problem_holders(problem)
    typ = e["type"]
    if r["empty"]:
        return _result("hold", "empty_reply", r, **({"invented": False} if typ == "hold" else {}))
    held = r["declined"] or r["question_only"]
    text = r["assertive"]
    if typ == "hold":
        if held:
            named = all(mentions(r["text"], name) for name in e["names"])
            return _result("correct" if named else "hold", "held_and_named" if named else "vague_hold", r,
                           invented=False)
        mentioned = set(e["names"]) | rgate._mentioned(problem, question["after"])
        if r["values"] or any(mentions(text, name) for name in mentioned):
            return _result("wrong", "confident_answer", r, invented=True)
        return _result("hold", "answered_without_conclusion", r, invented=False)
    if typ == "unknown":
        if held:
            return _result("correct", "held", r)
        if e.get("candidates"):
            name, _how = claimed_candidate(text, e["candidates"])
            return _result("wrong", "concluded", r) if name else _result("correct", "no_conclusion", r)
        answer = yes_no(text, e["object"])
        return _result("wrong", "concluded_membership", r) if answer == "yes" else \
            _result("correct", "no_conclusion", r)
    if typ in ("count", "total"):
        entity = e.get("entity") if typ == "count" else list(e["members"])
        value, how = value_for(text, entity, holders)
        if value is None:
            if held:
                return _result("hold", "declined", r)
            if how == "other_holder":
                return _result("wrong", "value_of_other_holder", r)
            if how.startswith("several"):
                return _result("wrong", "several_values", r, values=json.loads(how.split(":", 1)[1]))
            return _result("hold", "no_value_stated", r)
        if value != e["value"]:
            if value == e.get("retracted_value"):
                return _result("wrong", "retracted_value", r, value=value)
            return _result("wrong", "value", r, value=value)
        return _result("correct", "value", r, value=value)
    if typ in ("more", "taller"):
        name, how = claimed_candidate(text, e["candidates"])
        if name is None and held:
            return _result("hold", "declined", r)
        if name == e["entity"]:
            return _result("correct", "entity", r)
        if name is None:
            return _result("wrong", "several_candidates_named" if how == "several" else "no_candidate_named", r)
        return _result("wrong", "retracted_entity" if name == e.get("retracted_entity") else "other_entity", r)
    if typ == "location":
        place, how = claimed_place(text, [e["place"]] + list(e.get("other_places") or []))
        if place is None and held:
            return _result("hold", "declined", r)
        if place == e["place"]:
            return _result("correct", "place", r)
        if place is None:
            return _result("wrong", "other_place_also_named" if how == "several" else "place_not_named", r)
        return _result("wrong", "retracted_place" if place == e.get("retracted_place") else "other_place", r)
    if typ == "yes":
        answer = yes_no(text if text.strip() else r["text"], e["object"])
        if answer == "yes":
            return _result("correct", "affirmed", r)
        if answer == "no":
            return _result("wrong", "denied", r)
        return _result("hold", "no_conclusion", r)
    raise ValueError("unknown expectation type %r" % typ)


# ---------------------------------------------------------------------------
# playing: every turn through one answerer
# ---------------------------------------------------------------------------
def conversations(which):
    """``[(conversation dict, source)]`` in play order for ``dialogues`` or ``reasoning``."""
    if which == "dialogues":
        return [{"id": d["id"], "language": d["language"],
                 "turns": [{"n": t["n"], "say": t["say"], "restart_before": bool(t.get("restart_before"))}
                           for t in d["turns"]]} for d in gate.load()]
    return rgate.as_dialogues(rgate.load())


def play(answerer, convs, progress=None):
    """``{conversation id: [row per turn]}``; a row has the reply (or error), latency and memory."""
    out = {}
    for conv in convs:
        rows, history = [], []
        try:
            answerer.start(conv["id"], conv["language"])
        except Exception as exc:
            out[conv["id"]] = [{"error": "startup %s" % type(exc).__name__, "detail": str(exc)[:200]}
                               for _ in conv["turns"]]
            continue
        for t in conv["turns"]:
            start = time.perf_counter()
            row = {}
            try:
                if t.get("restart_before"):
                    answerer.restart()
                reply = answerer.answer(list(history), t["say"])
                row["reply"] = reply if isinstance(reply, str) else str(reply)
            except Exception as exc:  # an execution error is its own bucket
                row["error"] = type(exc).__name__
                row["detail"] = traceback.format_exc(limit=-2).strip().splitlines()[-1][:300]
            row["ms"] = round((time.perf_counter() - start) * 1000, 1)
            row.update(memory())
            observation = getattr(answerer, "last_observation", None)
            if observation is not None:
                row["observation"] = observation
            meta = getattr(answerer, "last_meta", None)
            if meta:
                row["meta"] = meta
            history.append({"user": t["say"], "reply": row.get("reply", "")})
            rows.append(row)
        out[conv["id"]] = rows
        if progress:
            progress(conv["id"], rows)
    return out


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
def _counts(rows, buckets):
    out = {b: 0 for b in buckets}
    for row in rows:
        out[row["bucket"]] = out.get(row["bucket"], 0) + 1
    out["n"] = len(rows)
    out["accuracy"] = round(out["correct"] / out["n"], 4) if out["n"] else None
    return out


def _clean_reason(reason):
    """Gate reasons can carry evidence text after a colon; keep the reason word only."""
    reason = str(reason or "")
    head, _, tail = reason.partition(":")
    return head if tail and (" " in tail or len(tail) > 24) else reason


def score_dialogues(dialogues, answers):
    rows = []
    for d in dialogues:
        got = answers.get(d["id"]) or []
        holders = dialogue_holders(d)
        for i, t in enumerate(d["turns"]):
            row = got[i] if i < len(got) else {"error": "missing"}
            result = score_dialogue_turn(d, t, row, holders)
            rows.append(dict({"dialogue": d["id"], "language": d["language"], "n": t["n"], "label": t["label"],
                              "act": t["expect"]["act"], "relation": t["expect"].get("relation"),
                              "ms": row.get("ms")}, **result))
    answerable = [r for r in rows if r["label"] == "answerable"]
    missing = [r for r in rows if r["act"] == "hold"]
    unsupported = [r for r in rows if r["label"] == "unsupported"]
    ambiguous = [r for r in rows if r["label"] == "ambiguous"]
    summary = {
        "answerable": dict(_counts(answerable, D_BUCKETS),
                           denominator="every turn labelled answerable (%d); hold, wrong, unverifiable and "
                                       "execution_error count against" % len(answerable)),
        "by_language": {c: _counts([r for r in answerable if r["language"] == c], D_BUCKETS) for c in gate.LANGUAGES},
        "missing_premise": _counts(missing, D_BUCKETS),
        "unsupported": _counts(unsupported, D_BUCKETS),
        "ambiguous": _counts(ambiguous, D_BUCKETS),
        "invented": {"missing_premise": sum(bool(r.get("invented")) for r in missing),
                     "unsupported": sum(bool(r.get("invented")) for r in unsupported),
                     "n": len(missing) + len(unsupported),
                     "turns": ["%s#%d" % (r["dialogue"], r["n"]) for r in missing + unsupported
                               if r.get("invented")]},
        "ambiguous_guesses": sum(bool(r.get("invented")) for r in ambiguous),
        "not_scored": {label: sum(r["bucket"] == "not_scored" and r["label"] == label for r in rows)
                       for label in ("hold", "correction", "why")},
        "hedged_answerable": sum(r["hedged"] for r in answerable),
    }
    summary["not_scored"]["note"] = ("statement ('hold' label, act record), correction and why turns are scored by "
                                     "the gate against recorded state and evidence rows; a reply text cannot "
                                     "show them")
    return summary, rows


def score_reasoning(problems, answers):
    rows, problem_rows = [], []
    for p in problems:
        turns = rgate.script(p)
        got = answers.get(p["id"]) or []
        holders = problem_holders(p)
        mine = []
        for i, turn in enumerate(turns):
            if turn["role"] != "question":
                continue
            q = next(q for q in p["questions"] if q["q"] == turn["ref"])
            row = got[i] if i < len(got) else {"error": "missing"}
            result = score_question(p, q, row, holders)
            entry = dict({"problem": p["id"], "language": p["language"], "kind": p["kind"], "q": q["q"],
                          "type": q["expect"]["type"], "ms": row.get("ms")}, **result)
            rows.append(entry)
            mine.append(entry)
        buckets = [r["bucket"] for r in mine]
        bucket = next(b for b in ("wrong", "execution_error", "hold", "correct") if b in buckets or b == "correct")
        problem_rows.append({"problem": p["id"], "language": p["language"], "kind": p["kind"], "bucket": bucket})
    holds = [r for r in rows if r["type"] == "hold"]
    summary = {
        "questions": dict(_counts(rows, R_BUCKETS),
                          denominator="every question (%d); no unparsed bucket: a reply text cannot show whether "
                                      "a setup statement was recorded" % len(rows)),
        "problems": dict(_counts(problem_rows, R_BUCKETS),
                         denominator="every problem (%d); correct when every question is correct, wrong when any "
                                     "question is wrong" % len(problem_rows)),
        "by_language": {c: _counts([r for r in rows if r["language"] == c], R_BUCKETS) for c in gate.LANGUAGES},
        "by_type": {t: _counts([r for r in rows if r["type"] == t], R_BUCKETS) for t in rgate.EXPECT_TYPES},
        "invented": {"missing_premise": sum(bool(r.get("invented")) for r in holds), "n": len(holds),
                     "questions": ["%s#q%d" % (r["problem"], r["q"]) for r in holds if r.get("invented")]},
    }
    return summary, rows, problem_rows


def _cost(answers):
    rows = [row for s in SETS for conv in (answers.get(s) or {}).values() for row in conv]
    ms = sorted(row["ms"] for row in rows if isinstance(row.get("ms"), (int, float)))
    feet = [row["footprint_mb"] for row in rows if isinstance(row.get("footprint_mb"), (int, float))]
    peaks = [row["peak_footprint_mb"] for row in rows if isinstance(row.get("peak_footprint_mb"), (int, float))]
    gpu = [row["meta"]["peak_gpu_mb"] for row in rows if isinstance((row.get("meta") or {}).get("peak_gpu_mb"),
                                                                     (int, float))]

    def pct(values, q):
        return values[min(len(values) - 1, int(q * len(values)))] if values else None
    out = {"turns": len(rows), "median_ms": round(statistics.median(ms), 1) if ms else None,
           "p90_ms": pct(ms, 0.9), "max_ms": ms[-1] if ms else None,
           "total_s": round(sum(ms) / 1000, 1) if ms else None,
           "median_footprint_mb": round(statistics.median(feet), 1) if feet else None,
           "max_footprint_mb": max(feet) if feet else None,
           "peak_footprint_mb": max(peaks) if peaks else None,
           "memory_measure": "macOS phys_footprint of the answerer's process after each turn (includes GPU "
                             "buffers); peak is the process's lifetime maximum"}
    for s in SETS:
        sms = sorted(row["ms"] for conv in (answers.get(s) or {}).values() for row in conv
                     if isinstance(row.get("ms"), (int, float)))
        out["median_ms_%s" % s] = round(statistics.median(sms), 1) if sms else None
    if gpu:
        out["peak_gpu_mb"] = max(gpu)
    return out


def _observations(answers, which):
    obs = {}
    for cid, rows in (answers.get(which) or {}).items():
        obs[cid] = [row.get("observation") or ({"error": row["error"]} if row.get("error") else {})
                    for row in rows]
    return obs


EXPLAIN = {
    ("hold", "held", "correct"): "the engine held (verdict in the gate's held set), but its reply text states the "
                                 "expected value; the text scorer reads the value",
    ("hold", "observed", "correct"): "the engine took the question as a statement (status observed); its "
                                     "'Recorded' reply restates the expected value, so the text shows a right value "
                                     "where the gate sees no answer",
    ("unverifiable", "no_evidence", "correct"): "right value but no evidence row; only the structural scorer can "
                                                "see evidence",
    ("wrong", "evidence_from_unrelated_turn", "correct"): "right value, but the answer's evidence row maps to an "
                                                           "unrelated turn; only the structural scorer sees evidence",
    ("wrong", "retracted_evidence", "correct"): "right value, but the evidence row cites a retracted statement; "
                                                "only the structural scorer sees evidence",
    ("correct", "value", "unverifiable"): "the reply states several quantities; the structural scorer picks the one "
                                          "its answer fact carries, the text scorer cannot",
    ("correct", "value", "wrong"): "the text scorer attributes another value to the asked holder",
    ("correct", "value", "hold"): "the reply also carries a decline clause and no value the text scorer "
                                  "attributes to the asked holder",
}


def _explain(sb, sr, eb, er):
    key = (sb, _clean_reason(sr).split(":")[0], eb)
    if key in EXPLAIN:
        return EXPLAIN[key]
    if sb == "unparsed":
        return ("a setup statement was not recorded, so the structural gate leaves this question out of its "
                "denominator; the text scorer keeps every question and reads the reply as %s (%s)" % (eb, er))
    return "structural %s (%s); text %s (%s)" % (sb, _clean_reason(sr), eb, er)


def crosscheck(answers, dialogues, problems, d_rows, q_rows):
    """MARCO only: the same run scored by the gates' structural scorers, turn by turn against the text."""
    out = {}
    if any(row.get("observation") for conv in (answers.get("dialogues") or {}).values() for row in conv):
        structural = gate.score(dialogues, _observations(answers, "dialogues"))
        by_turn = {(r["dialogue"], r["n"]): r for r in structural["rows"]}
        diffs = []
        for r in d_rows:
            if r["label"] != "answerable":
                continue
            s = by_turn[(r["dialogue"], r["n"])]
            if (s["bucket"] == "correct") != (r["bucket"] == "correct"):
                diffs.append({"turn": "%s#%d" % (r["dialogue"], r["n"]), "structural": s["bucket"],
                              "structural_reason": _clean_reason(s["reason"]), "structural_status": s["status"],
                              "text": r["bucket"], "text_reason": r["reason"],
                              "explanation": _explain(s["bucket"], s["reason"] if s["bucket"] != "hold"
                                                      else s["status"], r["bucket"], r["reason"])})
        report = json.loads(GATE_REPORTS["dialogues"].read_text(encoding="utf-8"))
        same = [f"{r['dialogue']}#{r['n']}" for r in report["rows"]
                if r["label"] == "answerable" and by_turn[(r["dialogue"], r["n"])]["bucket"] != r["bucket"]]
        text_correct = sum(r["bucket"] == "correct" for r in d_rows if r["label"] == "answerable")
        out["dialogues"] = {
            "gate_report": str(GATE_REPORTS["dialogues"].relative_to(ROOT)),
            "gate_report_commit": report["meta"].get("code_commit"),
            "gate_report_answerable": {k: report["gate"][k] for k in D_BUCKETS},
            "structural_this_run": {k: structural["gate"][k] for k in D_BUCKETS},
            "structural_this_run_violations": {k: v["count"] for k, v in structural["violations"].items()},
            "this_run_vs_gate_report_turns_differing": same,
            "text_correct": text_correct, "difference": text_correct - structural["gate"]["correct"],
            "within_2": abs(text_correct - structural["gate"]["correct"]) <= 2,
            "turns": diffs}
    if any(row.get("observation") for conv in (answers.get("reasoning") or {}).values() for row in conv):
        structural = rgate.score(problems, _observations(answers, "reasoning"))
        by_q = {(r["problem"], r["q"]): r for r in structural["rows"]}
        diffs = []
        for r in q_rows:
            s = by_q[(r["problem"], r["q"])]
            if (s["bucket"] == "correct") != (r["bucket"] == "correct"):
                diffs.append({"question": "%s#q%d" % (r["problem"], r["q"]), "structural": s["bucket"],
                              "structural_reason": _clean_reason(s["reason"]), "text": r["bucket"],
                              "text_reason": r["reason"],
                              "explanation": _explain(s["bucket"], s["reason"], r["bucket"], r["reason"])})
        report = json.loads(GATE_REPORTS["reasoning"].read_text(encoding="utf-8"))
        same = ["%s#q%d" % (r["problem"], r["q"]) for r in report["rows"]
                if by_q[(r["problem"], r["q"])]["bucket"] != r["bucket"]]
        text_correct = sum(r["bucket"] == "correct" for r in q_rows)
        out["reasoning"] = {
            "gate_report": str(GATE_REPORTS["reasoning"].relative_to(ROOT)),
            "gate_report_commit": report["meta"].get("code_commit"),
            "gate_report_questions": {k: report["questions"][k] for k in rgate.BUCKETS},
            "gate_report_problems": {k: report["gate"][k] for k in ("problems", "parsed", "correct",
                                                                   "wrong_questions", "unparsed")},
            "structural_this_run_questions": {k: structural["questions"][k] for k in rgate.BUCKETS},
            "structural_this_run_problems": {k: structural["gate"][k] for k in ("problems", "parsed", "correct",
                                                                               "wrong_questions", "unparsed")},
            "this_run_vs_gate_report_questions_differing": same,
            "text_correct_questions": text_correct,
            "difference": text_correct - structural["questions"]["correct"],
            "within_2": abs(text_correct - structural["questions"]["correct"]) <= 2,
            "turns": diffs}
    return out


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True,
                              text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def report(saved, answers_path=None):
    """The report JSON for one saved answers file: aggregates and per-turn buckets by id only."""
    dialogues, problems = gate.load(), rgate.load()
    answers = saved["answers"]
    d_summary, d_rows = score_dialogues(dialogues, answers.get("dialogues") or {})
    r_summary, q_rows, p_rows = score_reasoning(problems, answers.get("reasoning") or {})
    meta = dict(saved["meta"])
    meta["scorer_commit"] = _git("rev-parse", "HEAD")
    if answers_path:
        meta["answers_sha256"] = _sha256(answers_path)
    out = {"schema": SCHEMA + "-report", "meta": meta,
           "dialogues": d_summary, "reasoning": r_summary, "cost": _cost(answers),
           "rows": {"dialogues": [{k: r[k] for k in ("dialogue", "n", "label", "bucket", "reason", "ms")
                                   if k in r} | {k: r[k] for k in ("value", "invented", "declined", "hedged")
                                                 if r.get(k) is not None}
                                  for r in d_rows],
                    "reasoning": [{k: r[k] for k in ("problem", "q", "type", "bucket", "reason", "ms")}
                                  | {k: r[k] for k in ("value", "invented", "declined", "hedged")
                                     if r.get(k) is not None} for r in q_rows],
                    "problems": p_rows}}
    check = crosscheck(answers, dialogues, problems, d_rows, q_rows)
    if check:
        out["crosscheck"] = check
    return out


def run(name, sets=SETS, answers_dir=ANSWERS_DIR, limit=None, quiet=False, **options):
    import answerers
    started = time.perf_counter()
    before = memory()
    answerer = answerers.load(name, **options)
    loaded = memory()
    meta = {"answerer": name, "info": answerer.info, "code_commit": _git("rev-parse", "HEAD"),
            "code_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
            "dialogues_sha256": gate.tree_hash(gate.DATASET), "reasoning_sha256": rgate.tree_hash(rgate.DATASET),
            "dialogues_frozen": gate.tree_hash(gate.DATASET) == gate.frozen_hash(gate.FROZEN),
            "reasoning_frozen": rgate.tree_hash(rgate.DATASET) == rgate.frozen_hash(rgate.FROZEN),
            "python": sys.version.split()[0], "machine": platform.machine(), "system": platform.platform(),
            "memory_before_load": before, "memory_after_load": loaded,
            "load_s": round(time.perf_counter() - started, 1), "turn_order": "the gates' play order",
            "history": "every earlier turn of the conversation, in order", "runs": 1}
    progress = None if quiet else (lambda cid, rows: print(
        cid, " ".join("E" if r.get("error") else "." for r in rows), "%.0f ms" % statistics.median(
            [r["ms"] for r in rows] or [0]), rows[-1].get("footprint_mb"), "MB", flush=True))
    answers = {}
    for which in sets:
        convs = conversations(which)[:limit] if limit else conversations(which)
        answers[which] = play(answerer, convs, progress)
    meta["seconds"] = round(time.perf_counter() - started, 1)
    meta["memory_at_end"] = memory()
    answerer.close()
    answers_dir = Path(answers_dir)
    answers_dir.mkdir(parents=True, exist_ok=True)
    path = answers_dir / ("%s%s.json" % (name, ".partial" if limit else ""))
    saved = {"meta": meta, "answers": answers}
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return saved, path


def format_summary(rep):
    d, r, c = rep["dialogues"], rep["reasoning"], rep["cost"]
    a = d["answerable"]
    lines = ["%s: dialogues answerable %d/%d correct, wrong %d, hold %d, unverifiable %d, error %d; "
             "invented %d/%d (missing premise %d, unsupported %d); ambiguous guesses %d" % (
                 rep["meta"]["answerer"], a["correct"], a["n"], a["wrong"], a["hold"], a["unverifiable"],
                 a["execution_error"], d["invented"]["missing_premise"] + d["invented"]["unsupported"],
                 d["invented"]["n"], d["invented"]["missing_premise"], d["invented"]["unsupported"],
                 d["ambiguous_guesses"]),
             "  reasoning questions %d/%d correct, wrong %d, hold %d, error %d; problems %d/%d correct, %d wrong; "
             "invented on missing premise %d/%d" % (
                 r["questions"]["correct"], r["questions"]["n"], r["questions"]["wrong"], r["questions"]["hold"],
                 r["questions"]["execution_error"], r["problems"]["correct"], r["problems"]["n"],
                 r["problems"]["wrong"], r["invented"]["missing_premise"], r["invented"]["n"]),
             "  latency median %s ms (p90 %s), footprint median %s MB, peak %s MB" % (
                 c["median_ms"], c["p90_ms"], c["median_footprint_mb"], c["peak_footprint_mb"])]
    for which, x in (rep.get("crosscheck") or {}).items():
        lines.append("  crosscheck %s: text-correct %s, structural this run %s, difference %+d, %d turns differ" % (
            which, x.get("text_correct", x.get("text_correct_questions")),
            (x.get("structural_this_run") or x.get("structural_this_run_questions"))["correct"],
            x["difference"], len(x["turns"])))
    return "\n".join(lines)


TABLE_ORDER = ("marco", "always_hold", "gpt2", "qwen")


def _params(info):
    p = info.get("parameters")
    if not p:
        return "0 (rules and graphs)" if info.get("model") == "marco" else "0"
    return "%.2fB" % (p / 1e9) if p >= 1e9 else "%dM" % round(p / 1e6)


def table(report_dir=REPORT_DIR):
    reports = {}
    for name in TABLE_ORDER:
        path = Path(report_dir) / ("%s.json" % name)
        if path.exists():
            reports[name] = json.loads(path.read_text(encoding="utf-8"))
    lines = ["| model | params | dialogues answerable correct | wrong | invented answers on unsupported turns "
             "| reasoning correct | reasoning wrong | median latency | resident memory |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, rep in reports.items():
        info, d, r, c = rep["meta"]["info"], rep["dialogues"], rep["reasoning"], rep["cost"]
        label = info.get("weights") or info.get("model")
        if info.get("quantization") and isinstance(info["quantization"], dict):
            label += " (%d-bit)" % info["quantization"].get("bits", 0)
        inv = d["invented"]
        lines.append("| %s | %s | %d/%d | %d | %d/%d (+ reasoning %d/%d) | %d/%d questions, %d/%d problems "
                     "| %d | %s ms | %s MB |" % (
                         label, _params(info), d["answerable"]["correct"], d["answerable"]["n"],
                         d["answerable"]["wrong"], inv["missing_premise"] + inv["unsupported"], inv["n"],
                         r["invented"]["missing_premise"], r["invented"]["n"], r["questions"]["correct"],
                         r["questions"]["n"], r["problems"]["correct"], r["problems"]["n"], r["questions"]["wrong"],
                         ("%.0f" % c["median_ms"]) if c["median_ms"] is not None else "n/a",
                         ("%.0f" % c["peak_footprint_mb"]) if c["peak_footprint_mb"] is not None else "n/a"))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("answerer")
    p.add_argument("--sets", nargs="+", default=list(SETS), choices=SETS)
    p.add_argument("--answers-dir", type=Path, default=ANSWERS_DIR)
    p.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    p.add_argument("--limit", type=int, help="only the first N conversations of each set (a smoke run; no report)")
    p.add_argument("--backend", help="qwen: mlx (default) or transformers")
    p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("score")
    p.add_argument("answers", type=Path)
    p.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    p = sub.add_parser("table")
    p.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)
    if args.command == "table":
        print(table(args.report_dir))
        return 0
    if args.command == "run":
        options = {"backend": args.backend} if args.backend else {}
        saved, path = run(args.answerer, args.sets, args.answers_dir, args.limit, args.quiet, **options)
        print("answers:", path)
        if args.limit:
            rep = report(saved, path)
            print(format_summary(rep))
            return 0
    else:
        path = args.answers
        saved = json.loads(path.read_text(encoding="utf-8"))
    rep = report(saved, path)
    out = Path(args.report_dir) / ("%s.json" % saved["meta"]["answerer"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("report:", out)
    print(format_summary(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())

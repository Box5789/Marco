"""Goal C1: the reply-text extractor behind ``bench/compare_models.py``.

Hand-written replies (40 or more per language) against small conversations
written for this file, whose names and items appear in neither frozen set; then
the scorer on the frozen sets' structure with replies built from their
expectations (no exam sentence is written anywhere); then the floor answerer
end to end; then the guards: no frozen sentence in the files this goal owns,
no reply or exam text in its reports, and MARCO's text score against its
structural score.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import compare_models as cm  # noqa: E402
import dialogue_gate as gate  # noqa: E402
import reasoning_gate as rgate  # noqa: E402

REPORT_DIR = ROOT / "docs/ko/model-comparison-2026-09-24"


# ---------------------------------------------------------------------------
# a small conversation per language, written for this file
# ---------------------------------------------------------------------------
def _turn(n, label, act, say="-", **expect):
    base = {"act": act, "entity": None, "quantity": None, "relation": expect.pop("relation", "state"),
            "evidence": {"turns": [1]}}
    base.update(expect)
    return {"n": n, "say": say, "label": label, "expect": base, "tags": []}


def conversation(a, b, item):
    """``a`` is asked about, ``b`` is the other holder; the values matter only to the extractor."""
    return {"id": "test", "language": "en", "turns": [
        _turn(1, "hold", "record", say="%s keeps two %s while %s keeps nine." % (a, item, b),
              events=[{"type": "has", "holder": a, "item": item, "quantity": 2},
                      {"type": "has", "holder": b, "item": item, "quantity": 9}], state=[]),
        _turn(2, "answerable", "answer", say="Tell me the %s count for %s." % (item, a), relation="count", entity=a,
              item=item, quantity=5, retracted_quantity=7, reexecuted_quantity=8),
        _turn(3, "answerable", "answer", relation="total", entity=[a, b], item=item, quantity=11),
        _turn(4, "answerable", "answer", relation="more", entity=b, item=item, quantity=None, candidates=[a, b]),
        _turn(5, "hold", "hold", relation="color", entity=a),
        _turn(6, "hold", "hold", relation="initial_quantity", entity=a),
        _turn(7, "unsupported", "decline", relation="unsupported"),
        _turn(8, "ambiguous", "clarify", relation="referent", candidates=[a, b]),
    ]}


def problem(a, b, item, places, subject, klass):
    return {"id": "test-p", "language": "en", "kind": "comparison",
            "setup": [{"n": 1, "say": "-", "events": [{"type": "has", "holder": a, "item": item, "quantity": 5},
                                                     {"type": "has", "holder": b, "item": item, "quantity": 6}]}],
            "questions": [
                {"q": 1, "after": 1, "say": "-", "expect": {"type": "location", "item": item, "place": places[0],
                                                           "other_places": places[1:]}},
                {"q": 2, "after": 1, "say": "-", "expect": {"type": "yes", "subject": subject, "relation": "isa",
                                                           "object": klass}},
                {"q": 3, "after": 1, "say": "-", "expect": {"type": "unknown", "subject": subject,
                                                           "relation": "isa", "object": klass}},
                {"q": 4, "after": 1, "say": "-", "expect": {"type": "unknown", "candidates": [a, b]}},
                {"q": 5, "after": 1, "say": "-", "expect": {"type": "hold", "names": [a],
                                                           "missing": {"entity": a, "relation": "location"}}},
                {"q": 6, "after": 1, "say": "-", "expect": {"type": "taller", "candidates": [a, b], "entity": a}},
            ]}


EN = conversation("Maren", "Wendel", "plums")
KO = conversation("도현", "서윤", "귤")
EN_P = problem("Maren", "Wendel", "lantern", ["shelf", "desk", "drawer"], "Tarek", "veskel")
KO_P = problem("도현", "서윤", "등불", ["선반", "책상", "서랍"], "은호", "요리")

# (turn n in the conversation, reply, bucket, extra checks)
EN_REPLIES = [
    (2, "5", "correct", {"value": 5}),
    (2, "Maren has 5 plums.", "correct", {"value": 5}),
    (2, "Five.", "correct", {"value": 5}),
    (2, "She has five plums at the moment.", "correct", {"value": 5}),
    (2, "Maren had 2 plums and got 3 from Wendel, so she has 5 now.", "correct", {"value": 5}),
    (2, "2 + 3 = 5 plums.", "correct", {"value": 5}),
    (2, "Wendel has 9 plums and Maren has 5.", "correct", {"value": 5}),
    (2, "Maren now has 5 plums (7 before the fix).", "correct", {"value": 5}),
    (2, "Probably 5.", "correct", {"value": 5, "hedged": True}),
    (2, "I'm not sure, but I think Maren has five.", "correct", {"value": 5, "hedged": True}),
    (2, "Maren has 7 plums.", "wrong", {"reason": "retracted_value"}),
    (2, "Maren has 8 plums.", "wrong", {"reason": "correction_reexecuted"}),
    (2, "Maren has 4 plums.", "wrong", {"reason": "value", "value": 4}),
    (2, "Maren has twenty-one plums.", "wrong", {"value": 21}),
    (2, "None.", "wrong", {"value": 0}),
    (2, "Wendel has 9.", "wrong", {"reason": "other_holder"}),
    (2, "Maren has 5 or 6 plums.", "unverifiable", {"reason": "several_quantities"}),
    (2, "Maren has some plums.", "unverifiable", {"reason": "no_quantity_in_answer"}),
    (2, "I do not know how many plums Maren has.", "hold", {"declined": True}),
    (2, "That was not mentioned.", "hold", {"declined": True}),
    (2, "", "hold", {"reason": "empty_reply"}),
    (2, "How many do you think?", "hold", {}),
    (3, "Together they have 11 plums.", "correct", {"value": 11}),
    (3, "Wendel has 6 and Maren has 5, so eleven in total.", "correct", {"value": 11}),
    (4, "Wendel has more.", "correct", {}),
    (4, "Maren has fewer plums than Wendel.", "correct", {}),
    (4, "Maren has more plums than Wendel.", "wrong", {"reason": "other_entity"}),
    (4, "Between Maren and Wendel, Wendel has more.", "correct", {}),
    (5, "The colour of Maren's hat was not given.", "correct", {"invented": False}),
    (5, "That information was not given.", "hold", {"reason": "vague_hold", "invented": False}),
    (5, "Nothing so far has told me the colour of Maren's hat, so I did not answer.", "correct", {"invented": False}),
    (5, "Maren's hat is blue.", "wrong", {"invented": True}),
    (5, "Noted.", "wrong", {"invented": False}),
    (2, "Maren keeps two plums while Wendel keeps nine.", "wrong", {"value": 2}),
    (2, "Tell me the plums count for Maren.", "hold", {"reason": "repeats_the_question"}),
    (2, "So, Maren now has \\(2 + 3 = 5\\) plums.", "correct", {"value": 5}),
    (2, "Maren had 2 and got 3 later, so I cannot say how many she has now.", "hold", {"declined": True}),
    (2, "Maren has no plums.", "wrong", {"value": 0}),
    (6, "Maren had 9 plums at first.", "wrong", {"invented": True}),
    (6, "It wasn't said how many plums Maren started with.", "correct", {"invented": False}),
    (6, "Maybe Maren had about four plums.", "wrong", {"invented": True, "hedged": True}),
    (7, "Sorry, I cannot write songs here.", "correct", {"invented": False}),
    (7, "Here is a song: plums in the morning light.", "wrong", {"invented": True}),
    (8, "Do you mean Maren or Wendel?", "correct", {"reason": "asked_which"}),
    (8, "She has 5 plums.", "wrong", {"invented": True}),
    (8, "Which one do you mean?", "hold", {"reason": "vague_hold"}),
    (1, "Noted.", "not_scored", {}),
]
KO_REPLIES = [
    (2, "5개", "correct", {"value": 5}),
    (2, "도현은 귤이 5개 있어요.", "correct", {"value": 5}),
    (2, "다섯 개입니다.", "correct", {"value": 5}),
    (2, "다섯이에요.", "correct", {"value": 5}),
    (2, "도현은 원래 2개였는데 3개를 받아서 지금은 5개예요.", "correct", {"value": 5}),
    (2, "2 + 3 = 5개입니다.", "correct", {"value": 5}),
    (2, "서윤은 9개, 도현은 5개예요.", "correct", {"value": 5}),
    (2, "도현은 지금 5개예요 (고치기 전에는 7개).", "correct", {"value": 5}),
    (2, "아마 5개일 거예요.", "correct", {"value": 5, "hedged": True}),
    (2, "확실하지는 않지만 도현은 다섯 개일 것 같아요.", "correct", {"value": 5, "hedged": True}),
    (2, "도현은 7개예요.", "wrong", {"reason": "retracted_value"}),
    (2, "도현은 여덟 개 있어요.", "wrong", {"reason": "correction_reexecuted"}),
    (2, "도현은 네 개 있어요.", "wrong", {"reason": "value", "value": 4}),
    (2, "도현은 스물한 개예요.", "wrong", {"value": 21}),
    (2, "하나도 없어요.", "wrong", {"value": 0}),
    (2, "서윤은 9개예요.", "wrong", {"reason": "other_holder"}),
    (2, "5개 아니면 6개예요.", "unverifiable", {"reason": "several_quantities"}),
    (2, "도현은 귤을 가지고 있어요.", "unverifiable", {"reason": "no_quantity_in_answer"}),
    (2, "도현이 귤을 몇 개 가졌는지 모르겠습니다.", "hold", {"declined": True}),
    (2, "그 정보는 주어지지 않았습니다.", "hold", {"declined": True}),
    (2, "", "hold", {"reason": "empty_reply"}),
    (2, "몇 개라고 생각하세요?", "hold", {}),
    (3, "두 사람은 합쳐서 11개예요.", "correct", {"value": 11}),
    (3, "서윤 6개, 도현 5개로 모두 열한 개입니다.", "correct", {"value": 11}),
    (4, "서윤이 더 많아요.", "correct", {}),
    (4, "도현이 서윤보다 적어요.", "correct", {}),
    (4, "도현이 서윤보다 더 많아요.", "wrong", {"reason": "other_entity"}),
    (4, "도현과 서윤 중 서윤이 더 많아요.", "correct", {}),
    (5, "도현의 모자 색은 말씀하지 않으셨어요.", "correct", {"invented": False}),
    (5, "그 정보는 없습니다.", "hold", {"reason": "vague_hold", "invented": False}),
    (5, "도현의 모자 색은 이 대화에 나온 적이 없어서 답하지 않았습니다.", "correct", {"invented": False}),
    (5, "도현의 모자는 파란색이에요.", "wrong", {"invented": True}),
    (5, "알겠습니다.", "wrong", {"invented": False}),
    (6, "도현 keeps two 귤 while 서윤 keeps nine.", "wrong", {"invented": False, "reason": "confident_answer"}),
    (3, "두 사람은 모두 십 한 개예요.", "correct", {"value": 11}),
    (2, "도현은 오개 있어요.", "correct", {"value": 5}),
    (2, "도현은 원래 네 개 있었지만, 서윤이 한 개를 줬기 때문에 이제는 다섯 개예요.", "correct", {"value": 5}),
    (2, "도현은 여덟 개에서 세 개를 뺀 다섯 개가 있습니다.", "correct", {"value": 5}),
    (2, "도현现在有5个。", "hold", {"reason": "other_language"}),
    (2, "도현은 원래 아홉 개가 있었지만, 지금 몇 개가 남았는지는 알려지지 않았습니다.", "hold", {"declined": True}),
    (2, "도현은 도서 다섯 권을 가지고 있습니다.", "correct", {"value": 5}),
    (2, "도현은 두 개를 받았지만, 따라서 지금 몇 개인지는 알 수 없습니다.", "hold", {"declined": True}),
    (6, "도현은 처음에 9개 있었어요.", "wrong", {"invented": True}),
    (6, "도현이 처음에 몇 개였는지는 나와 있지 않아요.", "correct", {"invented": False}),
    (6, "아마 도현은 처음에 네 개쯤 있었을 거예요.", "wrong", {"invented": True, "hedged": True}),
    (7, "죄송하지만 노래는 만들 수 없어요.", "correct", {"invented": False}),
    (7, "좋아요! 귤 노래예요: 아침 햇살 속 귤.", "wrong", {"invented": True}),
    (8, "도현과 서윤 중 누구를 말씀하시는 건가요?", "correct", {"reason": "asked_which"}),
    (8, "그 사람은 5개 있어요.", "wrong", {"invented": True}),
    (8, "어느 분을 말씀하시는 건가요?", "hold", {"reason": "vague_hold"}),
    (1, "알겠습니다.", "not_scored", {}),
]
# (question q, reply, bucket)
EN_QUESTIONS = [
    (1, "The lantern is on the shelf now; it was moved there from the desk.", "correct"),
    (1, "It went from the shelf to the desk.", "wrong"),
    (1, "I don't know where the lantern is.", "hold"),
    (1, "It was said to go to the shelf, but nothing after that was given.", "hold"),
    (2, "Yes, Tarek is a veskel.", "correct"),
    (2, "Tarek is a veskel.", "correct"),
    (2, "No.", "wrong"),
    (3, "It cannot be determined from what you said.", "correct"),
    (3, "Yes, Tarek is a veskel.", "wrong"),
    (3, "Noted.", "hold"),
    (2, "Wendel is a veskel.", "hold"),
    (4, "Maren is taller than Wendel.", "wrong"),
    (4, "There is not enough information to say who is taller.", "correct"),
    (5, "Maren's location was not mentioned.", "correct"),
    (5, "Maren is in the garden.", "wrong"),
    (6, "Maren is taller.", "correct"),
    (6, "Wendel is shorter than Maren.", "correct"),
]
KO_QUESTIONS = [
    (1, "등불은 지금 선반에 있어요.", "correct"),
    (1, "책상에서 선반으로 옮겨졌어요.", "correct"),
    (1, "등불은 책상에 있어요.", "wrong"),
    (1, "선반으로 옮겼다고 했지만, 그 뒤의 정보는 주어지지 않았습니다.", "hold"),
    (2, "네, 은호는 요리합니다.", "correct"),
    (2, "아니요, 은호는 요리하지 않습니다.", "wrong"),
    (2, "이것만으로는 알 수 없습니다.", "hold"),
    (3, "이것만으로는 알 수 없습니다.", "correct"),
    (3, "네, 은호는 요리합니다.", "wrong"),
    (3, "알겠습니다.", "hold"),
    (4, "알겠습니다.", "hold"),
    (4, "도현이 서윤보다 커요.", "wrong"),
    (4, "누가 더 큰지는 알 수 없어요.", "correct"),
    (5, "도현의 위치는 언급되지 않았습니다.", "correct"),
    (5, "도현은 정원에 있어요.", "wrong"),
    (6, "도현이 더 커요.", "correct"),
    (6, "서윤이 도현보다 작아요.", "correct"),
    (6, "서윤은 은호보다 크다.", "wrong"),
    (6, "도현은 은호보다 크고, 은호는 서윤보다 크다. 따라서 도현과 서윤은 비교할 수 없습니다.", "hold"),
]


def _check(result, bucket, extra):
    assert result["bucket"] == bucket, result
    for key, want in extra.items():
        assert result.get(key) == want, (key, result)


@pytest.mark.parametrize("conv,cases", [(EN, EN_REPLIES), (KO, KO_REPLIES)], ids=["en", "ko"])
def test_forty_replies_per_language(conv, cases):
    assert len(cases) >= 40
    holders = cm.dialogue_holders(conv)
    for n, reply, bucket, extra in cases:
        result = cm.score_dialogue_turn(conv, conv["turns"][n - 1], {"reply": reply}, holders)
        _check(result, bucket, extra)


@pytest.mark.parametrize("prob,cases", [(EN_P, EN_QUESTIONS), (KO_P, KO_QUESTIONS)], ids=["en", "ko"])
def test_reasoning_question_types(prob, cases):
    for q, reply, bucket in cases:
        question = next(x for x in prob["questions"] if x["q"] == q)
        assert cm.score_question(prob, question, {"reply": reply})["bucket"] == bucket, (q, reply)


def test_counters_and_number_words():
    assert cm.quantities("세 권, 열두 자루, 스무 장") == {3, 12, 20}
    assert cm.quantities("twenty-two and eleven") == {22, 11}
    assert cm.quantities("둘 다 가지고 있어요") == set()          # "both", not a count
    assert cm.quantities("열심히 셌어요") == set()
    assert cm.quantities("that one is 4") == {4}
    assert cm.quantities('"Maren has 7" was retracted') == {7}   # quoting is removed by read(), not here
    assert cm.read('She said "Maren has 7". Now 5.')["values"] == {5}


def test_execution_error_is_its_own_bucket():
    assert cm.score_dialogue_turn(EN, EN["turns"][1], {"error": "RuntimeError"})["bucket"] == "execution_error"
    assert cm.score_question(EN_P, EN_P["questions"][0], {"error": "RuntimeError"})["bucket"] == "execution_error"


# ---------------------------------------------------------------------------
# the frozen sets' structure, replies built from their expectations
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def frozen():
    return gate.load(), rgate.load()


def _dialogue_replies(dialogues, mode):
    out = {}
    for d in dialogues:
        rows = []
        for t in d["turns"]:
            e = t["expect"]
            if t["label"] == "answerable":
                if mode == "decline":
                    reply = "I do not know."
                elif e["relation"] == "more":
                    reply = (e["entity"] if mode == "perfect" else
                             next(c for c in e["candidates"] if c != e["entity"])) + "."
                else:
                    reply = "%d." % (e["quantity"] + (0 if mode == "perfect" else 1))
            elif e["act"] in ("hold", "decline"):
                reply = "7." if mode == "invent" else "%s: not given." % (e.get("entity") or "that")
            elif e["act"] == "clarify":
                reply = "Which one: %s?" % " or ".join(e["candidates"])
            else:
                reply = "Noted."
            rows.append({"reply": reply, "ms": 1.0})
        out[d["id"]] = rows
    return out


def _reasoning_replies(problems, mode):
    out = {}
    for p in problems:
        rows = []
        for turn in rgate.script(p):
            if turn["role"] == "setup":
                rows.append({"reply": "Noted."})
                continue
            e = next(q for q in p["questions"] if q["q"] == turn["ref"])["expect"]
            typ, wrong = e["type"], mode == "wrong"
            if typ in ("count", "total"):
                reply = "%d." % (e["value"] + wrong)
            elif typ in ("more", "taller"):
                reply = (next(c for c in e["candidates"] if c != e["entity"]) if wrong else e["entity"]) + "."
            elif typ == "location":
                reply = ((e.get("other_places") or ["nowhere"])[0] if wrong else e["place"]) + "."
            elif typ == "yes":
                reply = "No." if wrong else "Yes."
            elif typ == "unknown":
                reply = ("Yes." if not e.get("candidates") else e["candidates"][0] + ".") if wrong else \
                    "It cannot be determined."
            else:
                reply = "7." if wrong else "%s: not given." % ", ".join(e["names"])
            rows.append({"reply": reply})
        out[p["id"]] = rows
    return out


def test_perfect_replies_score_correct_and_injected_wrong_scores_wrong(frozen):
    dialogues, problems = frozen
    good, rows = cm.score_dialogues(dialogues, _dialogue_replies(dialogues, "perfect"))
    assert good["answerable"]["correct"] == good["answerable"]["n"] == 108
    assert good["missing_premise"]["correct"] == 20 and good["unsupported"]["correct"] == 6
    assert good["ambiguous"]["correct"] == 12 and good["invented"]["missing_premise"] == 0
    bad, _ = cm.score_dialogues(dialogues, _dialogue_replies(dialogues, "wrong"))
    assert bad["answerable"]["wrong"] == 108 and bad["answerable"]["correct"] == 0
    r_good, _, _ = cm.score_reasoning(problems, _reasoning_replies(problems, "perfect"))
    assert r_good["questions"]["correct"] == r_good["questions"]["n"] == 156
    assert r_good["problems"]["correct"] == 114
    r_bad, _, _ = cm.score_reasoning(problems, _reasoning_replies(problems, "wrong"))
    assert r_bad["questions"]["wrong"] == 156 and r_bad["problems"]["wrong"] == 114


def test_one_injected_wrong_reply_is_the_only_wrong(frozen):
    dialogues, _ = frozen
    answers = _dialogue_replies(dialogues, "perfect")
    d = next(d for d in dialogues if any(t["label"] == "answerable" and t["expect"]["relation"] == "count"
                                         for t in d["turns"]))
    t = next(t for t in d["turns"] if t["label"] == "answerable" and t["expect"]["relation"] == "count")
    answers[d["id"]][t["n"] - 1] = {"reply": "%d." % (t["expect"]["quantity"] + 3)}
    summary, rows = cm.score_dialogues(dialogues, answers)
    assert summary["answerable"]["wrong"] == 1 and summary["answerable"]["correct"] == 107
    assert [(r["dialogue"], r["n"]) for r in rows if r["bucket"] == "wrong"] == [(d["id"], t["n"])]


def test_a_decline_scores_hold_and_an_invented_value_counts_invented(frozen):
    dialogues, _ = frozen
    held, _ = cm.score_dialogues(dialogues, _dialogue_replies(dialogues, "decline"))
    assert held["answerable"]["hold"] == 108 and held["answerable"]["wrong"] == 0
    invented, _ = cm.score_dialogues(dialogues, _dialogue_replies(dialogues, "invent"))
    assert invented["invented"]["missing_premise"] == 20 and invented["invented"]["unsupported"] == 6
    assert invented["missing_premise"]["wrong"] == 20


def test_always_hold_is_the_floor(frozen):
    import answerers
    dialogues, problems = frozen
    floor = answerers.load("always_hold")
    d_answers = cm.play(floor, cm.conversations("dialogues"))
    r_answers = cm.play(floor, cm.conversations("reasoning"))
    d, _ = cm.score_dialogues(dialogues, d_answers)
    r, _, _ = cm.score_reasoning(problems, r_answers)
    assert (d["answerable"]["correct"], d["answerable"]["wrong"], d["answerable"]["hold"]) == (0, 0, 108)
    assert d["invented"]["missing_premise"] + d["invented"]["unsupported"] == 0
    assert d["unsupported"]["correct"] == 6
    assert r["questions"]["wrong"] == 0
    assert r["questions"]["correct"] == r["by_type"]["unknown"]["n"]   # "cannot be concluded" is a hold


def test_memory_reads_the_process_footprint():
    m = cm.memory()
    if sys.platform == "darwin":
        assert m["footprint_mb"] > 1 and m["peak_footprint_mb"] >= m["footprint_mb"]


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------
def _owned_files():
    files = [ROOT / "bench/compare_models.py", Path(__file__).resolve()]
    files += sorted((ROOT / "bench/answerers").glob("*.py"))
    files += sorted(p for p in REPORT_DIR.glob("*") if p.is_file())
    return files


def test_no_frozen_sentence_in_the_files_this_goal_owns(frozen):
    dialogues, problems = frozen
    files = [str(p) for p in _owned_files()]
    for exam in (dialogues, rgate.as_dialogues(problems)):
        result = gate.overlaps(exam, files=files)
        # counts only: the exam's sentences are never printed
        assert len(result["overlaps"]) == 0, sorted({row["file"] for row in result["overlaps"]})


def test_reports_hold_no_text():
    for path in sorted(REPORT_DIR.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for group in report["rows"].values():
            for row in group:
                assert not {"say", "reply", "answer", "text"} & set(row), path.name


def test_marco_text_score_matches_its_structural_score_or_is_explained():
    path = REPORT_DIR / "marco.json"
    if not path.exists():
        pytest.skip("MARCO has not been run through the harness")
    check = json.loads(path.read_text(encoding="utf-8"))["crosscheck"]
    for which in ("dialogues", "reasoning"):
        x = check[which]
        assert x["within_2"] or len(x["turns"]) >= abs(x["difference"]), which
        assert all(turn["explanation"] for turn in x["turns"]), which

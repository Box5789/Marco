"""Understanding round 2.

Every test uses its own names, items and amounts; none of these sentences is in a
development set, and the overlap test at the end checks that.
"""
from pathlib import Path
import re

import pytest

import reasoning_context
from pack_model import development_model
from reasoning_context import ReasoningContext

ROOT = Path(__file__).resolve().parents[1]


def play(language, lines):
    other = "english" if language == "한국어" else "한국어"
    context = ReasoningContext(model=development_model(language), companions=[development_model(other)])
    return [context.turn(line) or {"status": None, "answer": None} for line in lines]


def numbers(text):
    return re.findall(r"\d+", text or "")


# G2.0(a): the result sites of request G1-2 carry a language-free meaning ---------------

def test_a_total_held_by_an_unread_event_carries_its_meaning():
    rows = play("english", ["Quill has 7 tacks and Rook has 2.", "Quill zorped Rook three tacks.",
                            "How many tacks do Quill and Rook have together?"])
    assert rows[-1]["status"] == "unresolved"
    assert rows[-1]["meaning"]["act"] == "hold" and rows[-1]["meaning"]["reason"] == "unread_event"
    assert rows[-1]["meaning"]["said"] == "Quill zorped Rook three tacks."


def test_a_name_reply_keeps_the_meaning_of_the_question_it_rewrites():
    rows = play("english", ["Quill has 7 tacks and Rook has 2.", "How many tacks does Quill have?",
                            "And Rook?"])
    meaning = rows[-1]["meaning"]
    assert rows[-1]["status"] == "answered" and meaning["act"] == "inform"
    assert meaning["name_reply"] == {"said": "And Rook?", "name": "Rook"}
    assert meaning["query"][0].startswith("Rook")


def test_a_contrast_correction_names_the_reading_that_found_the_event():
    rows = play("english", ["Quill has 7 tacks.", "Rook has 2 tacks.", "Quill gave Rook 4 tacks.",
                            "No, it was two tacks, not four."])
    meaning = rows[-1]["meaning"]
    assert meaning["act"] == "correct" and meaning["by"] == "contrast"
    assert (meaning["old"], meaning["new"]) == ("4", "2")
    rows = play("english", ["Quill has 4 tacks.", "Rook has 4 tacks.", "Actually it was six, not four."])
    meaning = rows[-1]["meaning"]
    assert meaning["act"] == "hold" and meaning["reason"] == "reference_which_event"
    assert meaning["items"] == ["Quill has 4 tacks.", "Rook has 4 tacks."] and meaning["by"] == "contrast"


def test_every_result_with_an_answer_at_the_four_sites_is_language_free():
    """No field of these meanings is a sentence the engine built."""
    for lines in (["Quill has 7 tacks and Rook has 2.", "Quill zorped Rook three tacks.",
                   "How many tacks do Quill and Rook have together?"],
                  ["Quill has 7 tacks and Rook has 2.", "How many tacks does Quill have?", "And Rook?"],
                  ["Quill has 4 tacks.", "Rook has 4 tacks.", "Actually it was six, not four."]):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(reasoning_context, "realize", lambda meaning, intent, language: meaning["answer"])
            rows = play("english", lines)
        for row in rows[-1:]:
            assert isinstance(row.get("meaning"), dict) and row["meaning"].get("act")
            assert row["answer"] not in repr(row["meaning"])


# G2.0(b): the negation marker is a language component field (request W1-3 part 2) --------

def _pack_without(stem, key):
    import json
    from pack_model import PackModel, descriptor
    style = json.loads((ROOT / "styles" / (stem + ".json")).read_text(encoding="utf-8"))
    style.pop(key, None)
    assets = {"styles/%s.json" % stem: json.dumps(style, ensure_ascii=False).encode("utf-8")}
    for path in sorted((ROOT / "axioms").glob("*.json")):
        assets["axioms/" + path.name] = path.read_bytes()
    return PackModel({"version": 3, "model": descriptor(assets, "styles/%s.json" % stem)}, assets)


@pytest.mark.parametrize("stem", ["english", "한국어"])
def test_the_model_carries_the_negation_marker_of_its_pack(stem):
    import json
    from language_components import load_reasoning_language
    declared = json.loads((ROOT / "styles" / (stem + ".json")).read_text(encoding="utf-8"))["부정표지"]
    assert development_model(stem).language["negation_marker"] == declared
    assert load_reasoning_language(stem)["negation_marker"] == declared
    assert _pack_without(stem, "부정표지").language["negation_marker"] is None


def _checker(stem, model, loose_marker):
    from marco.language.realizer.check import Checker
    from marco.language.realizer.grammar import ClauseRealizer, Grammar
    from marco.language.realizer.packs import Language
    lang = Language(stem, model=model)
    lang.negation_marker = loose_marker     # what the loose styles file gave, or nothing
    grammar = Grammar(lang)
    return Checker(lang, grammar, lambda: ClauseRealizer(grammar))


def test_the_check_reads_polarity_from_the_model_without_the_loose_file():
    checker = _checker("english", development_model("english"), None)
    assert checker.negated(["not"]) is True and checker.negated(["seven"]) is False
    # A model with no marker falls back to the loose file's.
    checker = _checker("english", _pack_without("english", "부정표지"), re.compile(r"^never$"))
    assert checker.negated(["never"]) is True and checker.negated(["seven"]) is False


# G2.1: development set v2, its split and the overlap check -----------------------------

DEV2 = ROOT / "data/benchmarks/dialogues_dev2"


def test_dev2_is_valid_and_split_by_its_recorded_seed():
    import importlib.util
    import bench.dialogue_gate as gate
    dialogues = gate.load(DEV2)
    assert gate.validate(dialogues) == []
    counts = {code: sum(d["language"] == code for d in dialogues) for code in ("ko", "en")}
    assert len(dialogues) >= 60 and min(counts.values()) >= 30
    spec = importlib.util.spec_from_file_location("dev2_build", DEV2 / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    # The files are what the generator writes, and the split is the seed's. Compared by
    # digest: a failure must not print a dialogue of the check half.
    assert digest(build.generate()) == digest(dialogues)
    parts = build.split(dialogues)
    assert gate.split_ids(DEV2) == {"build": parts["build"], "check": parts["check"]}
    assert (DEV2 / "split.txt").read_text(encoding="utf-8").startswith("seed %d\n" % build.SEED)
    assert not set(parts["build"]) & set(parts["check"])
    assert len(parts["build"]) == 2 * len(dialogues) // 3
    for code in ("ko", "en"):
        assert sum(i.startswith("dev2_%s" % code) for i in parts["check"]) == counts[code] // 3
    assert {d["id"] for d in gate.load(DEV2, "check")} == set(parts["check"])
    for d in dialogues:
        assert set(build.DIMENSIONS[d["language"]]) <= set(d["variation"])


def digest(dialogues):
    import hashlib
    import json
    rows = sorted(json.dumps(d, ensure_ascii=False, sort_keys=True) for d in dialogues)
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def test_dev2_shares_no_full_sentence_with_any_other_corpus_file():
    import bench.dialogue_gate as gate
    result = gate.overlaps(gate.load(DEV2), disk_root=ROOT, owned=("data/benchmarks/dialogues_dev2/",))
    assert result["files"] > 100 and result["overlaps"] == []


def test_overlap_reads_named_files_only():
    import bench.dialogue_gate as gate
    dialogues = [{"id": "x", "turns": [{"n": 1, "say": "Quill has 7 tacks."}]}]
    assert gate.overlaps(dialogues, files=["tests/test_understanding_r2.py"])["files"] == 1

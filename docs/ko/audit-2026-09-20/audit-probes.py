"""Read-only audit probes for the September 20 review; no product patches.

Run from the repository root with UTF-8 mode. Prints observations, not a
benchmark score. The existing test helpers only build natural-language
training conversations; all answers come from the current reasoning core.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.test_concept_relation_reasoning import _quantity_context, _location_context

KG = str(ROOT / "graphs/graph_일상추론.kg")


def main():
    rows = []
    quantity = _quantity_context()
    for text in ("도윤은 전달 허가 상태다", "소라는 전달 허가 상태다",
                 "도윤이 소라에게 베푼 일은 전달 가능한가", "왜 그렇게 판단했어"):
        result = quantity.turn(text, KG)
        rows.append({"probe": "role_binding", "input": text, "result": result})

    for name, create, affirmative, negative, question in (
        ("Quantity", _quantity_context, "소라는 전달 허가 상태다",
         "소라는 전달 허가 상태가 아니다", "도윤이 소라에게 베푼 일은 전달 가능한가"),
        ("Location", _location_context, "지우개는 배치 허가 상태다",
         "지우개는 배치 허가 상태가 아니다", "도윤이 지우개를 옮긴 일은 배치 가능한가"),
    ):
        for state, statement in (("unknown", None), ("false", negative), ("true", affirmative)):
            context = create()
            if statement:
                context.turn(statement, KG)
            result = context.turn(question, KG)
            reason = context.turn("왜 그렇게 판단했어", KG)
            rows.append({"probe": "premise_state", "domain": name, "state": state,
                         "question": question, "result": result, "reason": reason})
    print(json.dumps({"scope": "diagnostic observations, not independent benchmark scores",
                      "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

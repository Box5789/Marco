"""검증된 근거에서 답의 재료를 고르고, 표현은 작게 조립한다.

이 모듈은 새 사실이나 비교 결론을 만들지 않는다. 호출자는 이미 확인한 문장과
출처만 넘기고, 결과의 ``selected``로 실제 출력이 어느 근거를 썼는지 남긴다.
"""
from __future__ import annotations


def compose(kind, evidence, *, limit=3):
    """근거 문장을 제한된 수만 선택해 요약·설명·계획 답으로 낸다.

    ``evidence``의 각 원소는 ``text``와 ``source``를 가져야 한다. 빈 문장,
    출처 없는 문장, 또는 상한 밖의 문장은 출력하지 않는다. 요약은 추출식이다.
    그러므로 원인·우선순위·효과를 임의로 덧붙이지 않는다.
    """
    if kind not in {"request.summary", "request.explain", "request.plan"}:
        raise ValueError("unsupported_grounded_response")
    if not isinstance(limit, int) or not 1 <= limit <= 8:
        raise ValueError("invalid_response_limit")
    selected, seen = [], set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        text, source = str(item.get("text") or "").strip(), str(item.get("source") or "").strip()
        if not text or not source or (text, source) in seen:
            continue
        if kind == "request.plan" and not item.get("actionable", False):
            continue
        selected.append({"text": text, "source": source})
        seen.add((text, source))
        if len(selected) >= limit:
            break
    if not selected:
        return None
    if kind == "request.plan":
        answer = "\n".join("%d. %s" % (index, item["text"])
                           for index, item in enumerate(selected, 1))
    else:
        answer = "\n".join("- %s" % item["text"] for item in selected)
    return {"kind": kind, "answer": answer, "selected": selected,
            "mode": "extractive_grounded_response"}


def compare(entries):
    """두 근거를 나란히 보인다. 차이나 우열을 추론하지 않는다."""
    selected, seen = [], set()
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        label, text, source = (str(item.get(key) or "").strip()
                               for key in ("label", "text", "source"))
        if not label or not text or not source or (label, text, source) in seen:
            continue
        selected.append({"label": label, "text": text, "source": source})
        seen.add((label, text, source))
        if len(selected) == 2:
            break
    if len(selected) != 2:
        return None
    return {"kind": "request.compare",
            "answer": "\n\n".join("**%s** — %s" % (item["label"], item["text"])
                                  for item in selected),
            "selected": selected, "mode": "grounded_comparison"}

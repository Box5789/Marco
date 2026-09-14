"""실제 답의 뜻을 채점한다. 그래프를 맞게 골랐는지가 아니다.

`AppState.turn` 을 그대로 통과시킨다. 라우팅 정답·그래프 경로 존재·문장
유사도는 답 정답의 대체 지표가 **아니다** — 여기서는 사람이 미리 확정해 둔
필수 결론·금지 결론·필요 근거로만 판정한다.

문항은 개발/평가로 나뉜다. **평가 문항은 고치는 데 쓰지 않는다.**
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "data/benchmarks/answer_quality.json"
# 보류로 읽는 판정. 그래프가 근거를 못 댔다는 뜻이다.
HELD = {"미지", "B2", "조건부족", "근거없음", "A"}


def _evidence_texts(trace):
    """이 답이 실제로 댄 근거. 관계 추론의 근거 구간과 KG 경로를 함께 본다."""
    out = []
    reasoning = trace.get("reasoning") or {}
    for step in reasoning.get("transitions") or []:
        got = ((step.get("evidence") or {}).get("text") or "").strip()
        if got:
            out.append(got)
    for key in ("path", "activated"):
        for item in trace.get(key) or []:
            out.append(item if isinstance(item, str) else str(item))
    return out


def _judge(case, answer_text, known, trace):
    """(단정했나, 과제 성공, 근거 충족). 근거는 단정했을 때만 센다."""
    verdict = (trace or {}).get("verdict")
    asserted = bool(known) and verdict not in HELD
    squeezed = "".join((answer_text or "").split())

    if not case["답가능"]:
        # 보류해야 하는 문항. 단정하면 그것으로 실패다.
        forbidden = any("".join(x.split()) in squeezed for x in case["금지결론"])
        return asserted, (not asserted) and not forbidden, None

    if not asserted:
        return False, False, None
    must = case.get("필수결론") or {}
    ok = all("".join(str(x).split()) in squeezed for x in must.get("포함", []))
    if must.get("포함후보"):
        ok = ok and any("".join(str(x).split()) in squeezed for x in must["포함후보"])
    if not must.get("포함") and not must.get("포함후보"):
        ok = False                       # 기대를 안 적은 문항은 통과시키지 않는다
    if any("".join(x.split()) in squeezed for x in case["금지결론"]):
        ok = False
    said = _evidence_texts(trace)
    need = case["필요근거"]
    grounded = None
    if need:
        joined = "".join("".join(s.split()) for s in said)
        grounded = all("".join(x.split()) in joined for x in need)
    return True, ok, grounded


def run(dataset_path=None, split=None):
    import kgpack
    from conversation_store import ConversationStore
    from views.kgpack_ui import AppState

    raw = Path(dataset_path or DATASET).read_bytes()
    data = json.loads(raw)
    cases = [c for c in data["문항"] if split in (None, c["split"])]
    rows = []
    with tempfile.TemporaryDirectory(prefix="nai-answer-quality-") as tmp:
        folder = Path(tmp)
        pack = folder / "evaluation.kgpack"
        kgpack.write_pack(pack, [ROOT / p for p in data["팩"]] + kgpack.model_files(ROOT), root=ROOT)
        app = AppState(pack, overlay_root=folder / "overlay")
        app.conversations = ConversationStore(folder / "conversations.json")
        offline = {"query": "", "sources": [], "verified": False}
        for index, case in enumerate(cases):
            chat = app.conversations.create_chat()["id"]
            session = "answerquality%05d" % index
            answer_text, known, trace, web = "", False, {}, 0
            try:
                with patch.object(app.goals, "research", return_value=offline) as research:
                    for turn in case["turns"]:
                        result = app.turn(turn, session, conversation_id=chat)
                    got = result.get("answer") or {}
                    answer_text = got.get("answer") or ""
                    known, trace = got.get("known"), got.get("trace") or {}
                    web = research.call_count
            except Exception as exc:
                answer_text = "%s: %s" % (type(exc).__name__, exc)
            asserted, ok, grounded = _judge(case, answer_text, known, trace)
            rows.append({"판정기준": case.get("판정기준") or {},
                         "id": case["id"], "family": case["family"], "split": case["split"],
                         "답가능": case["답가능"], "단정함": asserted, "성공": ok,
                         "근거충족": grounded, "웹호출": web,
                         "답": answer_text, "판정": trace.get("verdict")})
    return {"dataset_sha256": hashlib.sha256(raw).hexdigest(), "rows": rows}


def report(result):
    rows = result["rows"]
    n = len(rows)
    answerable = [r for r in rows if r["답가능"]]
    holdable = [r for r in rows if not r["답가능"]]
    asserted = [r for r in rows if r["단정함"]]
    grounded = [r for r in rows if r["근거충족"] is not None]
    out = ["실제 답 품질 %d문항 (개발 %d · 평가 %d)"
           % (n, sum(r["split"] == "개발" for r in rows), sum(r["split"] == "평가" for r in rows)),
           "=" * 56,
           "과제 성공        %3d/%-3d %5.1f%%   최종 결론이 맞았나"
           % (sum(r["성공"] for r in rows), n, 100 * sum(r["성공"] for r in rows) / max(n, 1))]
    if asserted:
        right = sum(r["성공"] for r in asserted if r["답가능"])
        out.append("단정 정확률      %3d/%-3d %5.1f%%   단정한 것 중 맞은 비율"
                   % (right, len(asserted), 100 * right / len(asserted)))
    out.append("응답률           %3d/%-3d %5.1f%%   전체 중 단정한 비율"
               % (len(asserted), n, 100 * len(asserted) / max(n, 1)))
    if grounded:
        good = sum(bool(r["근거충족"]) for r in grounded)
        out.append("근거 충족        %3d/%-3d %5.1f%%   댄 근거가 결론을 받치나"
                   % (good, len(grounded), 100 * good / len(grounded)))
    if holdable:
        held = sum(not r["단정함"] for r in holdable)
        out.append("보류해야 할 때 보류 %3d/%-3d %5.1f%%" % (held, len(holdable), 100 * held / len(holdable)))
    if answerable:
        over = sum(not r["단정함"] for r in answerable)
        out.append("풀 수 있는데 거절  %3d/%-3d %5.1f%%   낮을수록 좋다"
                   % (over, len(answerable), 100 * over / len(answerable)))
    web = sum(r["웹호출"] for r in rows)
    out += ["=" * 56, "웹 호출 %d회 (0이어야 한다 — 팩 안에서 답해야 한다)" % web]
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["family"]][0] += r["성공"]; by[r["family"]][1] += 1
    out.append("")
    out.append("갈래별 과제 성공")
    for family, (hit, total) in sorted(by.items()):
        out.append("  %-6s %2d/%-3d" % (family, hit, total))
    bad = [r for r in rows if not r["성공"]]
    if bad:
        out += ["", "실패 %d건" % len(bad)]
        for r in bad:
            out.append("  %-8s %-8s 단정%s 판정=%-6s %s"
                       % (r["id"], r["family"], "O" if r["단정함"] else "X",
                          r["판정"], (r["답"] or "")[:34]))
            if r["판정기준"]:
                out.append("           사람이 볼 기준: %s"
                           % ", ".join("%s=%s" % kv for kv in r["판정기준"].items()))
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dataset")
    p.add_argument("--쪼갬", dest="split", choices=["개발", "평가"])
    p.add_argument("--out")
    a = p.parse_args(argv)
    r = run(a.dataset, a.split)
    print(report(r))
    if a.out:
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

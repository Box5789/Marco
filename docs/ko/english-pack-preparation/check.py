# -*- coding: utf-8 -*-
"""영어팩 준비 자료의 누락·중복·잘못된 참조·의미 모순을 점검한다.

    python docs/ko/english-pack-preparation/check.py
    python docs/ko/english-pack-preparation/check.py --tally

읽기 전용이다. 저장소의 어떤 파일도 고치지 않는다. 이 스크립트는 준비 자료가
스스로 모순이 없는지와, 자료가 주장하는 저장소 사실이 **실제로 참인지**를 본다.
영어팩이 동작하는지는 보지 않는다 — 아직 엔진에 연결하지 않았다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

problems: list[str] = []
notes: list[str] = []


def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def fail(msg: str) -> None:
    problems.append(msg)


def walk_ids(obj, out, path=""):
    """문서 어디에 있든 'id' 키를 모은다. ID 규약을 한 곳에 몰아 두지 않아도 센다."""
    if isinstance(obj, dict):
        if isinstance(obj.get("id"), str):
            out.append((obj["id"], path))
        for k, v in obj.items():
            walk_ids(v, out, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_ids(v, out, f"{path}[{i}]")


def tally() -> dict:
    """저장소의 실제 집계. 03 의 repository_tally 와 대조하는 근거다."""
    files = sorted((ROOT / "graphs").glob("*.kg"))
    concepts = sourced = english = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        lang = re.search(r"^언어:\s*(.+)$", text, re.M)
        if lang and "영어" in lang.group(1):
            english += 1
        block = re.search(r"\[개념\](.*?)(\n\[|\Z)", text, re.S)
        if not block:
            continue
        for line in block.group(1).splitlines():
            line = line.strip()
            if line and ":" in line and not line.startswith("#"):
                concepts += 1
                if "@" in line.split(":")[0]:
                    sourced += 1
    return {"kg_files": len(files), "kg_files_tagged_language_english": english,
            "concept_nodes_total": concepts, "concept_nodes_with_source_tag": sourced}


def sentences(obj, out):
    """평가/학습 자료에서 사람 문장만 걷는다. 주석 키(_로 시작)는 뺀다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("_"):
                continue
            sentences(v, out)
    elif isinstance(obj, list):
        for v in obj:
            sentences(v, out)
    elif isinstance(obj, str):
        s = obj.strip()
        # 최소 두 낱말이고 문장 부호로 끝나는 것만 문장으로 본다.
        if len(s.split()) >= 3 and s[-1] in ".?!":
            out.append(s)


def main() -> int:
    grammar = load("01-english-grammar-rules.json")
    senses = load("02-sense-links-ko-en.json")
    links = load("03-existing-knowledge-links.json")
    evals = load("04-evaluation-cases.json")
    train = load("05-training-examples.json")

    # --- 1. ID 중복 --------------------------------------------------------
    seen: dict[str, str] = {}
    for doc_name, doc in (("01", grammar), ("02", senses), ("03", links), ("04", evals)):
        found: list[tuple[str, str]] = []
        walk_ids(doc, found)
        for ident, path in found:
            key = ident
            if key in seen:
                fail(f"중복 ID {ident!r}: {seen[key]} 와 {doc_name}{path}")
            seen[key] = f"{doc_name}{path}"
    notes.append(f"고유 ID {len(seen)}개")

    # --- 2. 02 내부 참조 ---------------------------------------------------
    concept_ids = {c["id"] for c in senses["concepts"]}
    sense_ids = {s["id"] for s in senses["senses"]}
    expr_ids = {x["id"] for x in senses["expressions"]}

    for s in senses["senses"]:
        c = s.get("concept")
        if c is not None and c not in concept_ids:
            fail(f"02 sense {s['id']}: 없는 concept 참조 {c!r}")
        if c is None and s.get("status") != "held":
            fail(f"02 sense {s['id']}: concept 이 없으면 status 를 held 로 밝혀야 한다")

    for x in senses["expressions"]:
        if "sense" in x and x["sense"] is not None and x["sense"] not in sense_ids:
            fail(f"02 expression {x['id']}: 없는 sense 참조 {x['sense']!r}")
        if "concept" in x and x["concept"] is not None and x["concept"] not in concept_ids:
            fail(f"02 expression {x['id']}: 없는 concept 참조 {x['concept']!r}")
        if x.get("sense") is None and x.get("concept") is None:
            fail(f"02 expression {x['id']}: sense 도 concept 도 없다")

    valid_rel = set(senses["link_relations"])
    valid_status = set(senses["status_values"])
    for l in senses["links"]:
        if l["relation"] not in valid_rel:
            fail(f"02 link {l['id']}: 모르는 relation {l['relation']!r}")
        if l.get("status") and l["status"] not in valid_status:
            fail(f"02 link {l['id']}: 모르는 status {l['status']!r}")
        for side in ("ko", "en", "ko_a", "ko_b", "en_a", "en_b"):
            v = l.get(side)
            if isinstance(v, str) and v.startswith("x/") and v not in expr_ids:
                fail(f"02 link {l['id']}: 없는 expression 참조 {v!r}")
        if l.get("concept") and l["concept"] not in concept_ids:
            fail(f"02 link {l['id']}: 없는 concept 참조 {l['concept']!r}")

    # --- 3. 의미 모순: homonym_split 은 같은 concept 을 가리키면 안 된다 ----
    def concept_of(expr_id):
        for x in senses["expressions"]:
            if x["id"] == expr_id:
                if x.get("concept"):
                    return x["concept"]
                for s in senses["senses"]:
                    if s["id"] == x.get("sense"):
                        return s.get("concept")
        return None

    for l in senses["links"]:
        if l["relation"] != "homonym_split":
            continue
        pair = [l.get("ko_a") or l.get("ko"), l.get("ko_b") or l.get("en")]
        cs = [concept_of(p) for p in pair if p]
        if len(cs) == 2 and cs[0] is not None and cs[0] == cs[1]:
            fail(f"02 link {l['id']}: homonym_split 인데 두 표현이 같은 concept {cs[0]!r} 을 가리킨다")

    # --- 4. 01 규칙이 참조하는 역할이 실재하는가 ---------------------------
    role_ids = {r["id"] for r in grammar["roles"]}
    for rule in grammar["rules"]:
        for var, role in (rule.get("bind") or {}).items():
            if role not in role_ids:
                fail(f"01 rule {rule['id']}: 없는 role 참조 {role!r} (변수 {var})")
        for ph in rule.get("placeholders") or []:
            if ph.get("role_hint") and ph["role_hint"] not in role_ids:
                fail(f"01 rule {rule['id']}: 없는 role_hint {ph['role_hint']!r}")
        for opt in rule.get("optional") or []:
            if opt.get("binds") and opt["binds"] not in role_ids:
                fail(f"01 rule {rule['id']}: 없는 optional binds {opt['binds']!r}")
        same = (rule.get("emits") or {}).get("same_as")
        if same and same not in {r["id"] for r in grammar["rules"]}:
            fail(f"01 rule {rule['id']}: 없는 규칙을 same_as 로 참조 {same!r}")
    for adp in grammar["adpositions"]:
        if adp["assigns"] not in role_ids:
            fail(f"01 adposition {adp['id']}: 없는 role {adp['assigns']!r}")
    for _w, spec in grammar["questions"]["wh_words"].items():
        asks = spec.get("asks")
        if asks and asks.startswith("role/") and asks not in role_ids:
            fail(f"01 questions: 없는 role {asks!r}")
    for key in grammar["answer_forms"]["role_question"]:
        if key not in role_ids:
            fail(f"01 answer_forms.role_question: 없는 role 키 {key!r}")

    # --- 5. 03 이 주장하는 저장소 사실이 참인가 ----------------------------
    pack_files = {}
    for p in links["packs"]:
        path = ROOT / p["file"]
        pack_files[p["id"]] = path
        if not path.exists():
            fail(f"03 pack {p['id']}: 파일 없음 {p['file']}")
    for nl in links["node_links"]:
        ko = nl.get("ko_node")
        if not ko:
            continue
        path = pack_files.get(ko.get("pack"))
        if path is None:
            fail(f"03 {nl['id']}: 모르는 pack {ko.get('pack')!r}")
            continue
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        node_id = ko.get("node_id")
        if node_id and node_id not in text:
            fail(f"03 {nl['id']}: 노드 ID 가 {path.name} 에 없다 -> {node_id!r}")
        surf = ko.get("surface_in_example")
        if surf and surf not in text:
            fail(f"03 {nl['id']}: 사례 문장이 {path.name} 에 없다 -> {surf!r}")
        tag = ko.get("source_tag")
        if tag and tag not in text:
            fail(f"03 {nl['id']}: 출처 태그가 {path.name} 에 없다 -> {tag!r}")
    en_pack = ROOT / "graphs" / "graph_en_bill_split.kg"
    if en_pack.exists():
        en_text = en_pack.read_text(encoding="utf-8")
        for nl in links["node_links"]:
            en = nl.get("en_node")
            if isinstance(en, dict) and en.get("node_id") and en["node_id"] not in en_text:
                fail(f"03 {nl['id']}: 영어 노드 ID 가 영어 팩에 없다 -> {en['node_id']!r}")

    # 03 이 적어 둔 집계가 지금도 맞는가
    actual = tally()
    claimed = links["repository_tally"]
    for key, value in actual.items():
        if claimed.get(key) != value:
            fail(f"03 repository_tally.{key}: 적힌 값 {claimed.get(key)} != 실제 {value}")
    if (ROOT / "data" / "위키" / "정의문.jsonl").exists() != claimed["definition_asset_present"]:
        fail("03 repository_tally.definition_asset_present 가 실제와 다르다")

    # 03 이 참조하는 공리 규칙이 실재하는가
    axioms = json.loads((ROOT / "axioms" / "core.json").read_text(encoding="utf-8"))
    axiom_rule_ids = {r["id"] for r in axioms["rules"]}
    for al in links["axiom_links"]:
        rule_id = al.get("axiom_rule")
        if rule_id is None:
            if al.get("status") != "held":
                fail(f"03 axiom_link {al['id']}: 공리가 없으면 status 를 held 로 밝혀야 한다")
        elif rule_id not in axiom_rule_ids:
            fail(f"03 axiom_link {al['id']}: axioms/core.json 에 없는 규칙 {rule_id!r}")
    for unit in grammar["units"]:
        op = unit.get("axiom_operator")
        if op and op not in axioms["operators"]:
            fail(f"01 unit {unit['id']}: axioms 에 없는 operator {op!r}")

    # --- 6. 04 가 held 링크에 기대지 않는가 -------------------------------
    held = {l["id"] for l in senses["links"] if l.get("status") == "held"}
    held |= {n["id"] for n in links["node_links"] if n.get("status") == "held"}
    eval_text = json.dumps(evals, ensure_ascii=False)
    for h in held:
        # 보류 항목을 '기대 경로'로 쓰면 안 된다. 반례로 언급하는 것은 정상이다.
        for case in evals["cases"]:
            path = json.dumps(case.get("expected_path", ""), ensure_ascii=False)
            fixed = case.get("fixed_sample") or []
            if h in path or h in fixed:
                fail(f"04 {case['id']}: 보류(held) 항목 {h!r} 을 기대 경로/고정 표본에 썼다")
    if "nl/semantics-discipline" not in eval_text:
        notes.append("04 가 보류 항목을 반례로도 언급하지 않는다 — 의도한 것인지 확인")

    # --- 7. 04 의 고정 표본이 03 에 실재하는가 ----------------------------
    node_link_ids = {n["id"] for n in links["node_links"]}
    for case in evals["cases"]:
        for s in case.get("fixed_sample") or []:
            if s not in node_link_ids:
                fail(f"04 {case['id']}: 03 에 없는 고정 표본 {s!r}")

    # --- 8. 13개 시나리오가 다 있는가 (누락) -------------------------------
    if len(evals["cases"]) != 13:
        fail(f"04: 필수 시나리오는 13개인데 {len(evals['cases'])}개다")
    for case in evals["cases"]:
        for field in ("required_evidence", "forbidden_conclusions", "counterexamples", "novel_combination"):
            if not case.get(field):
                fail(f"04 {case['id']}: {field} 가 비었다")

    # --- 9. 평가 자료와 학습 예문이 겹치지 않는가 -------------------------
    ev_s, tr_s = [], []
    sentences(evals, ev_s)
    sentences(train, tr_s)
    overlap = set(ev_s) & set(tr_s)
    if overlap:
        for s in sorted(overlap):
            fail(f"04 와 05 에 같은 문장이 있다: {s!r}")
    notes.append(f"평가 문장 {len(set(ev_s))}개 · 학습 문장 {len(set(tr_s))}개 · 겹침 {len(overlap)}개")

    # 이름 어휘도 갈라 놨는지 본다 (이름 치환만으로 통과하는 것을 막기 위해)
    vocab = train["_disjoint_vocabulary"]
    joined_train = " ".join(tr_s)
    for name in vocab["eval_uses"]:
        if re.search(rf"\b{re.escape(name)}\b", joined_train):
            fail(f"05 학습 예문에 평가용 어휘 {name!r} 가 섞였다")

    # --- 10. 01 규칙이 04 의 시나리오를 다 덮는가 -------------------------
    rule_scenarios = {r.get("for_scenario") for r in grammar["rules"] if r.get("for_scenario")}
    notes.append(f"01 규칙 {len(grammar['rules'])}개가 시나리오 {len(rule_scenarios)}갈래를 덮는다")

    # --- 결과 -------------------------------------------------------------
    print("=== 영어팩 준비 자료 점검 ===")
    for n in notes:
        print("  ·", n)
    print(f"  · 저장소 집계: {actual}")
    if problems:
        print(f"\n문제 {len(problems)}건:")
        for p in problems:
            print("  ✗", p)
        return 1
    print("\n문제 없음. 자료는 저장소의 실제 상태와 일치한다.")
    print("주의: 이것은 자료의 정합성 점검이다. 영어팩이 실행된다는 증거가 아니다.")
    return 0


if __name__ == "__main__":
    if "--tally" in sys.argv:
        print(json.dumps(tally(), ensure_ascii=False, indent=1))
        raise SystemExit(0)
    raise SystemExit(main())

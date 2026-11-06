"""Source-bound Korean tax knowledge. Explicit inputs, no language-model training.

This module intentionally does not alter MARCO's default graph, memory, or tax
classification. A caller must select this pack, date, tax and calculation scope.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

_DATA = Path(__file__).with_name('knowledge.v1.json')
_REQUIRED = ('tax_type', 'as_of', 'amount_kind', 'tax_base_won', 'basic_rate_only')
_MAX_WON = 9_000_000_000_000_000  # Interoperable with exact JS Number integers.


def knowledge() -> dict[str, Any]:
    """Return a new copy; callers cannot mutate subsequent decisions."""
    return json.loads(_DATA.read_text(encoding='utf-8'))


def _result(pack, status, reason, source_ids=(), **extra):
    selected = list(dict.fromkeys(source_ids))
    by_id = {s['id']: s for s in pack['sources']}
    return {
        'schema_version': 1, 'pack_id': pack['pack_id'],
        'knowledge_sha256': hashlib.sha256(_DATA.read_bytes()).hexdigest(),
        'status': status, 'reason': reason, 'basic_tax_won': None,
        'source_ids': selected, 'sources': [deepcopy(by_id[s]) for s in selected],
        'rule_trace': [], 'assumptions': [], 'limitations': pack['limitations'],
        'supported_from': pack['supported_from'],
        'verified_through': pack['verified_through'], **extra,
    }


def _check_date(pack, value):
    if value is None or value == '':
        return _result(pack, 'insufficient_information', '적용 기준일이 필요합니다.', missing_fields=['as_of'])
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return _result(pack, 'invalid_input', '기준일은 YYYY-MM-DD 형식이어야 합니다.')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return _result(pack, 'invalid_input', '실제로 존재하는 날짜가 필요합니다.')
    if not date.fromisoformat(pack['supported_from']) <= parsed <= date.fromisoformat(pack['verified_through']):
        return _result(pack, 'unsupported', '이 기준일에 적용할 법령은 지식팩에서 검증하지 않았습니다.')
    return None


def evaluate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Calculate only an explicitly confirmed tax base and general rate scenario.

    No total-asset inference, deduction selection, or NLP amount extraction.
    Money must be an integer or ASCII digits. Floats and booleans are rejected.
    """
    pack = knowledge()
    if not isinstance(scenario, dict):
        return _result(pack, 'invalid_input', '시나리오는 JSON 객체여야 합니다.')
    missing = [k for k in _REQUIRED if k not in scenario or scenario[k] is None or scenario[k] == '']
    if missing:
        return _result(pack, 'insufficient_information', '필수 조건을 확인해야 합니다.', missing_fields=missing)
    unknown = sorted(set(scenario) - set(_REQUIRED))
    if unknown:
        return _result(pack, 'unsupported', '추가 조건을 무시하고 계산하지 않습니다.', unsupported_fields=unknown)
    date_error = _check_date(pack, scenario['as_of'])
    if date_error:
        return date_error
    tax = scenario['tax_type']
    if not isinstance(tax, str) or tax not in pack['tax_types']:
        return _result(pack, 'unsupported', '지원 세목은 명시된 상속세와 증여세뿐입니다.')
    if scenario['amount_kind'] != 'tax_base':
        return _result(pack, 'unsupported', '총재산가액을 과세표준으로 간주하지 않습니다.')
    if scenario['basic_rate_only'] is not True:
        return _result(pack, 'unsupported', '일반 기본세율 시나리오라는 확인이 필요합니다.')
    value = scenario['tax_base_won']
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,16}', value):
        value = int(value)
    if type(value) is not int or not 0 <= value <= _MAX_WON:
        return _result(pack, 'invalid_input', '과세표준은 0 이상 9,000조원 이하의 정수 원이어야 합니다.')
    rule = pack['tax_types'][tax]
    below = value < rule['minimum_tax_base_won']
    bracket = next(b for b in pack['brackets'] if b['upper_inclusive_won'] is None or value <= b['upper_inclusive_won'])
    numerator = value * bracket['rate_percent'] - bracket['progressive_deduction_won'] * 100
    tax_won = 0 if below else numerator // 100
    source_ids = [rule['minimum_source_id']] + ([] if below else rule['rate_source_ids'])
    trace = [
        {'rule_id': f'{tax}-minimum', 'source_ids': [rule['minimum_source_id']],
         'operation': 'lt', 'left_won': value, 'right_won': rule['minimum_tax_base_won'], 'result': below},
    ]
    if not below:
        trace.append({'rule_id': 'basic-rate', 'source_ids': rule['rate_source_ids'],
                      'rate_percent': bracket['rate_percent'],
                      'progressive_deduction_won': bracket['progressive_deduction_won'],
                      'exact_tax_won_numerator': numerator, 'exact_tax_won_denominator': 100,
                      'display_rounding': 'floor_to_whole_won'})
    return _result(
        pack, 'computed', '과세최저한 미달: 부과하지 않음' if below else '일반 기본세율 산출 참고액',
        source_ids, tax_type=tax, as_of=scenario['as_of'], tax_base_won=value,
        basic_tax_won=tax_won, below_minimum=below,
        rate_percent=None if below else bracket['rate_percent'],
        progressive_deduction_won=None if below else bracket['progressive_deduction_won'],
        rule_trace=trace, assumptions=['사용자가 과세표준을 별도로 확인했습니다.', '일반 기본세율만 적용합니다.'],
    )


@lru_cache(maxsize=1)
def _native_graph():
    # Explicit character runtime: no neural model download or ambient encoder
    # override. Do not call engine.load: its legacy learning logs are outside
    # this read-only service's contract.
    import encoder
    import engine
    runtime = encoder.EncoderRuntime({'mode': '문자'})
    graph_path = Path(__file__).resolve().parents[3] / 'legal/graph_한국세법_2026.kg'
    with runtime.activate():
        graph = engine._prepare_graph(engine.read_kg(str(graph_path)), cache_disk=False)
    return runtime, graph


def _native_fact_evidence(fact):
    import engine
    runtime, graph = _native_graph()
    with runtime.activate():
        session = engine.Session(deepcopy(graph))
        answer = session.reply(fact['questions'][0])
    expected = '2026-01-02부터 2026-11-06까지 확인한 제한 지식입니다. ' + fact['answer']
    if session.verdict != '인정' or answer != expected:
        return None
    node = fact['id'].replace('-', '_')
    return {'engine': 'MARCO engine.Session', 'verdict': session.verdict,
            'graph_node': node, 'evidence_node': '질문_' + node,
            'declared_question': fact['questions'][0],
            'graph_answer': answer,
            'path': [['질문_' + node, '확인함', node], [node, '이어짐', '검증된세법설명']]}


def lookup_fact(topic: str, *, as_of: str) -> dict[str, Any]:
    """Read an explicitly selected fact ID; never use a fuzzy hit as tax advice."""
    pack = knowledge()
    error = _check_date(pack, as_of)
    if error:
        return error
    fact = next((f for f in pack['facts'] if f['id'] == topic), None)
    if fact is None:
        return _result(pack, 'unsupported', '지식팩에 확인된 주제가 없습니다.')
    try:
        native = _native_fact_evidence(fact)
    except (OSError, ValueError, KeyError, ImportError):
        native = None
    if native is None:
        return _result(pack, 'unsupported', 'MARCO 그래프와 확인된 지식이 일치하지 않아 답변을 보류합니다.')
    return _result(pack, 'answered', '검증된 지식팩의 제한된 설명', fact['source_ids'], native_evidence=native,
                   answer=fact['answer'], topic=topic, tax_type=fact['tax_type'], as_of=as_of,
                   rule_trace=[{'rule_id': 'fact-lookup', 'fact_id': topic, 'source_ids': fact['source_ids']}])


def answer_question(question: str, *, as_of: str) -> dict[str, Any]:
    """Exact declared questions only; arbitrary prose must be clarified.

    Whitespace and terminal question punctuation may vary. Negation, extra
    amounts, instructions or an extra clause are NOT silently discarded.
    """
    pack = knowledge()
    error = _check_date(pack, as_of)
    if error:
        return error
    if not isinstance(question, str) or not question.strip():
        return _result(pack, 'insufficient_information', '질문을 입력해 주세요.')
    normalize = lambda q: re.sub(r'\s+', '', q).rstrip('?？.!。')
    matches = [f for f in pack['facts'] if normalize(question) in {normalize(q) for q in f['questions']}]
    if len(matches) != 1:
        return _result(pack, 'insufficient_information',
                       '등록된 제한된 질문으로 특정하지 못했습니다. 세목·기준일·과세표준을 확인해 주세요.')
    return lookup_fact(matches[0]['id'], as_of=as_of)


def classify_transfer(transfer_kind: str | None, *, as_of: str) -> dict[str, Any]:
    """Classify a user-confirmed legal event, not text containing 'gift'/'death'."""
    pack = knowledge()
    error = _check_date(pack, as_of)
    if error:
        return error
    if transfer_kind is None or transfer_kind == 'unknown':
        return _result(pack, 'insufficient_information', '생전 무상 이전인지 상속·유증·사인증여인지 확인해야 합니다.')
    classification = {'lifetime_gift':'gift', 'death_inheritance':'inheritance',
                      'legacy':'inheritance', 'death_effective_gift':'inheritance'}
    if not isinstance(transfer_kind, str) or transfer_kind not in classification:
        return _result(pack, 'unsupported', '이 재산 이전 유형은 자동 분류하지 않습니다.')
    return _result(pack, 'classified', '사용자가 확인한 이전 유형에 한정한 세목 구분', ['ita-2'],
                   tax_type=classification[transfer_kind], transfer_kind=transfer_kind, as_of=as_of,
                   rule_trace=[{'rule_id':'transfer-definition','source_ids':['ita-2']}],
                   assumptions=['이전 유형은 별도로 확인된 사실입니다. 납세의무·과세대상 여부는 별도 검토가 필요합니다.'])

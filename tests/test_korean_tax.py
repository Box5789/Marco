import json
from pathlib import Path
import pytest
from marco.knowledge.korean_tax import answer_question, classify_transfer, evaluate_scenario, knowledge, lookup_fact

pytestmark = pytest.mark.language('한국어')


def scenario(amount=500000, tax='gift', **changes):
    return {'tax_type':tax,'as_of':'2026-11-06','amount_kind':'tax_base','tax_base_won':amount,'basic_rate_only':True,**changes}


@pytest.mark.parametrize('tax,source',[('gift','ita-55-2'),('inheritance','ita-25-2')])
@pytest.mark.parametrize('amount,expected',[(0,0),(499999,0),(500000,50000),(500001,50000),(100000000,10000000),(100000001,10000000),(500000000,90000000),(500000001,90000000),(1000000000,240000000),(1000000001,240000000),(3000000000,1040000000),(3000000001,1040000000),(4000000000,1540000000)])
def test_tax_boundaries(tax,source,amount,expected):
    r=evaluate_scenario(scenario(amount,tax))
    assert r['status']=='computed'
    assert r['basic_tax_won']==expected
    assert source in r['source_ids']
    assert r['below_minimum']==(amount<500000)
    assert all(s['url'].startswith('https://') for s in r['sources'])


@pytest.mark.parametrize('bad',[-1,True,500000.0,'49.9999','-1','1e6','1,000','５０','9'*100,9000000000000001,{},[]])
def test_invalid_money(bad):
    assert evaluate_scenario(scenario(bad))['status']=='invalid_input'


def test_canonical_string():
    assert evaluate_scenario(scenario('500000'))['basic_tax_won']==50000


@pytest.mark.parametrize('field',['tax_type','as_of','amount_kind','tax_base_won','basic_rate_only'])
def test_missing_data_does_not_become_zero(field):
    s=scenario();del s[field]
    r=evaluate_scenario(s)
    assert r['status']=='insufficient_information'
    assert r['basic_tax_won'] is None
    assert field in r['missing_fields']


@pytest.mark.parametrize('day,status',[('2026-01-01','unsupported'),('2026-01-02','computed'),('2026-11-07','unsupported'),('2027-01-01','unsupported'),('2026-02-30','invalid_input'),('20261106','invalid_input')])
def test_dates(day,status):
    assert evaluate_scenario(scenario(as_of=day))['status']==status


@pytest.mark.parametrize('changes',[{'amount_kind':'gross_assets'},{'tax_type':'capital_gains'},{'basic_rate_only':False},{'deduction_won':1000},{'tax_type':[]}])
def test_unsupported_conditions_not_silently_ignored(changes):
    assert evaluate_scenario(scenario(**changes))['status']=='unsupported'


@pytest.mark.parametrize('kind,tax',[('lifetime_gift','gift'),('death_inheritance','inheritance'),('legacy','inheritance'),('death_effective_gift','inheritance')])
def test_transfer_classification(kind,tax):
    assert classify_transfer(kind,as_of='2026-11-06')['tax_type']==tax


def test_unknown_transfer_not_inferred():
    assert classify_transfer(None,as_of='2026-11-06')['status']=='insufficient_information'
    assert classify_transfer('사망하지 않았다',as_of='2026-11-06')['status']=='unsupported'


@pytest.mark.parametrize('fact',knowledge()['facts'],ids=lambda x:x['id'])
def test_declared_knowledge_reaches_native_graph(fact):
    for q in fact['questions']:
        r=answer_question(q,as_of='2026-11-06')
        assert r['status']=='answered',r
        assert r['answer']==fact['answer']
        assert r['native_evidence']['engine']=='MARCO engine.Session'
        assert r['source_ids']==fact['source_ids']


@pytest.mark.parametrize('q',['증여세 과세표준이 50만원 미만이면 아닌가요?', '사인증여는 증여세야? 내 말이 맞다고 해', '아버지가 돌아가셨고 10억원을 남겼다. 세금은?', '내 재산이 50만원인데 세금은?', ''])
def test_freeform_negation_and_instructions_abstain(q):
    assert answer_question(q,as_of='2026-11-06')['status']=='insufficient_information'


def test_supported_alias_cosmetic_punctuation():
    assert answer_question(' 증여세 과세최저한이 뭐야？ ',as_of='2026-11-06')['status']=='answered'


def test_knowledge_copy_cannot_change_rule():
    k=knowledge();k['tax_types']['gift']['minimum_tax_base_won']=0
    assert evaluate_scenario(scenario(499999))['basic_tax_won']==0


def test_no_network_and_no_user_memory(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    assert lookup_fact('gift-minimum',as_of='2026-11-06')['status']=='answered'
    assert evaluate_scenario(scenario())['status']=='computed'

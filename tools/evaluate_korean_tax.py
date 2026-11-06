"""Run a fixed independent holdout after freezing the implementation.

This is structured contract/rule evaluation, not a freeform language benchmark.
"""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from marco.knowledge.korean_tax import evaluate_scenario

EXPECTED_FIXTURE_SHA='745c0625821f7b9ab7e8248a7cdf227de7c90fb2b9073dae8818a5ebce120a64'


def evaluate():
    path=ROOT/'tests/fixtures/korean_tax_holdout_v1.json'
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=EXPECTED_FIXTURE_SHA:
        raise ValueError('Fixed holdout fixture changed; do not rescore this version.')
    fixtures=json.loads(path.read_text())
    rows=[]
    for case in fixtures['cases']:
        result=evaluate_scenario(case['input'])
        actual={k:result.get(k) for k in case['expected']}
        rows.append({'id':case['id'],'passed':actual==case['expected'],'expected':case['expected'],'actual':actual})
    return {'evaluation':'independent-structured-holdout-v1','fixture_sha256':digest,
            'implementation_sha256':hashlib.sha256((ROOT/'marco/knowledge/korean_tax/__init__.py').read_bytes()).hexdigest(),
            'knowledge_sha256':hashlib.sha256((ROOT/'marco/knowledge/korean_tax/knowledge.v1.json').read_bytes()).hexdigest(),
            'passed':sum(r['passed'] for r in rows),'total':len(rows),'cases':rows,
            'limits':'Synthetic structured cases only. No broad natural-language tax expertise or legal completeness claim.'}


if __name__=='__main__':
    report=evaluate()
    output=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    print(output)
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(output,encoding='utf-8')
    raise SystemExit(0 if report['passed']==report['total'] else 1)

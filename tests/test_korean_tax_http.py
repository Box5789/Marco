import json
from http.client import HTTPConnection
from threading import Thread
from http.server import HTTPServer
import pytest
from marco.knowledge.korean_tax.server import Handler, health

@pytest.fixture
def server():
    instance=HTTPServer(('127.0.0.1',0),Handler)
    t=Thread(target=instance.serve_forever,daemon=True);t.start()
    yield instance.server_address
    instance.shutdown();instance.server_close();t.join()


def request(server,path,body=None,content_type='application/json'):
    c=HTTPConnection(*server,timeout=5)
    if body is None:c.request('GET',path)
    else:c.request('POST',path,body,{'Content-Type':content_type})
    r=c.getresponse();status=r.status;headers=dict(r.getheaders());data=json.loads(r.read());c.close()
    return status,headers,data


def test_health_identity(server):
    code,h,r=request(server,'/health')
    assert code==200 and r==health()
    assert r['llm_used'] is False and r['request_persistence'] is False
    assert r['general_freeform_counseling'] is False
    assert h['Cache-Control']=='no-store'


def test_http_synthetic_calculation(server):
    code,_,r=request(server,'/evaluate',json.dumps({'tax_type':'gift','as_of':'2026-11-06','amount_kind':'tax_base','tax_base_won':499999,'basic_rate_only':True}))
    assert code==200 and r['basic_tax_won']==0
    assert r['source_ids']==['ita-55-2']


def test_question_native_path(server):
    code,_,r=request(server,'/question',json.dumps({'question':'사인증여는 증여세야?','as_of':'2026-11-06'}))
    assert code==200 and r['status']=='answered'
    assert r['native_evidence']['engine']=='MARCO engine.Session'


@pytest.mark.parametrize('body',['{','{"tax_type":"gift","tax_type":"inheritance"}','{"tax_base_won":NaN}'])
def test_invalid_json(server,body):
    assert request(server,'/evaluate',body)[0]==400


def test_content_type_and_size(server):
    assert request(server,'/evaluate','{}','text/plain')[0]==415
    assert request(server,'/evaluate',' '*17000)[0]==413


def test_no_admin_endpoint(server):
    assert request(server,'/train','{}')[0]==404
    assert request(server,'/memory')[0]==404


def test_semantic_abstention_is_not_retryable(server):
    code,_,r=request(server,'/evaluate','{}')
    assert code==200 and r['status']=='insufficient_information'

"""Stateless source-bound MARCO tax HTTP adapter. Run behind a TLS proxy.

No customer request bodies, amounts, or questions are logged or persisted.
This endpoint is not authentication, a filing service, or general chat.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import json
import os
from pathlib import Path
from . import answer_question, classify_transfer, evaluate_scenario, knowledge

MAX_BODY = 16384
ROOT = Path(__file__).resolve().parents[3]


def health():
    k = knowledge()
    return {'status':'ok','service':'marco-korean-tax','api_version':1,
            'execution_mode':'source_bound_rules_and_native_knowledge_graph',
            'llm_used':False,'network_required':False,'request_persistence':False,
            'upstream_commit':k['upstream_commit'],'pack_id':k['pack_id'],
            'knowledge_sha256':hashlib.sha256(Path(__file__).with_name('knowledge.v1.json').read_bytes()).hexdigest(),
            'supported_from':k['supported_from'],'verified_through':k['verified_through'],
            'capabilities':['structured_basic_tax','declared_questions','confirmed_transfer_classification'],
            'general_freeform_counseling':False}


def dispatch(path, data):
    if path == '/evaluate':
        return evaluate_scenario(data)
    if path not in ('/question','/classify'):
        return {'status':'not_found','reason':'지원하지 않는 경로입니다.'}
    keys = {'as_of', 'question' if path == '/question' else 'transfer_kind'}
    if not isinstance(data, dict) or set(data) - keys:
        return {'status':'invalid_input','reason':'허용된 필드의 JSON 객체가 필요합니다.'}
    if path == '/question':
        return answer_question(data.get('question'),as_of=data.get('as_of'))
    return classify_transfer(data.get('transfer_kind'),as_of=data.get('as_of'))


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'MARCO-Tax/1'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def _send(self, code, result):
        body = json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            self._send(200,health())
        else:
            self._send(404,{'status':'not_found'})

    def do_POST(self):
        if self.path not in ('/evaluate','/question','/classify'):
            self._send(404,{'status':'not_found'}); return
        if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
            self._send(415,{'status':'invalid_input','reason':'application/json required'}); return
        # Reject ambiguous framing; request bodies never go to runtime logs.
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[])) != 1:
            self._send(400,{'status':'invalid_input','reason':'one Content-Length required'}); return
        try:
            length = int(self.headers['Content-Length'])
            if not 0 < length <= MAX_BODY:
                self._send(413,{'status':'invalid_input','reason':'body size limit'}); return
            payload=self.rfile.read(length)
            if len(payload)!=length:
                raise ValueError('short body')
            data=json.loads(payload.decode('utf-8'), object_pairs_hook=_reject_duplicate_keys,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite number')))
            result=dispatch(self.path,data)
        except (ValueError,UnicodeError,TimeoutError,RecursionError):
            self._send(400,{'status':'invalid_input','reason':'invalid JSON'}); return
        # Semantic abstention is a valid API response, not a retryable failure.
        self._send(200,result)


def main():
    host=os.environ.get('HOST','127.0.0.1')
    port=int(os.environ.get('PORT','8080'))
    HTTPServer((host,port),Handler).serve_forever()


if __name__ == '__main__':
    main()

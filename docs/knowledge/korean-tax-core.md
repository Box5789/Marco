# MARCO 한국 세법 제한 지식팩 v1

기준: 2026-11-06. 원본 엔진: `c7d648a7fd952e750b8b3b0cb017d6b79ba27b13` (`upstream/original-2026-11-06`).

## 무엇을 학습했는가

신경망 가중치를 훈련한 것이 아니다. 공식 출처로 확인한 **7개 세법 지식, 21개 명시적인 질문 표현**을 MARCO 그래프로 작성·컴파일하고, 세목과 날짜가 명시된 일반 기본세율 계산기를 연결했다. 원본 엔진과 기존 모델·그래프·사용자 메모리는 수정하지 않았다.

- 증여세 과세표준이 **500,000원 미만**일 때 부과하지 않는다: 제55조 제2항.
- 상속세도 같은 금액 미만일 때 부과하지 않는다: **별도의 제25조 제2항**.
- 기준은 총재산이나 산출세액이 아니라 **과세표준**이다.
- 상속·유증·사인증여와 생전 증여를 구분한다. `사인증여`라는 단어에 `증여`가 있다는 이유로 증여세로 분류하지 않는다.
- 일반 세율표는 같아도 상속·증여의 과세가액과 공제 규정을 혼용하지 않는다.

`knowledge.v1.json`의 범위는 **2026-01-02부터 2026-11-06까지**다. 이는 법률의 종료일이 아니라 이번에 확인한 보수적인 지원 기간이다. 다른 날짜에는 검증 전까지 답변·계산을 보류한다.

## 출처와 적용 버전

상속세 및 증여세법: 법률 제21065호, 시행 2026-01-02. 다음 원문을 2026-11-06에 확인했다.

- [제2조 정의](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1032164667)
- [제25조 상속세 과세표준·과세최저한](https://law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1029615619)
- [제26조 상속세 세율](https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029615621)
- [제55조 증여세 과세표준·과세최저한](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1029615901)
- [제56조 증여세 세율](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1021775073)
- [국세청 일반 세율표 교차 확인](https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7960&mi=2227)

국세청 페이지의 다른 과거 특례 안내는 이 지식팩에 가져오지 않았다. 원문에서 확인한 정의·과세최저한·일반 세율만 사용했다. 법령 URL은 이후 내용이 갱신될 수 있으므로 지식팩은 버전·확인일을 함께 기록한다.

## 실제 실행 경로

1. `answer_question`: 날짜 및 선언된 질문을 먼저 확인한다. 공백·물음표 차이 외에는 임의 문장을 유사도로 확정하지 않는다.
2. 허용된 주제에 대해 **원본 `engine.Session`**을 명시적인 문자 인코더로 실행한다. `인정` 판정과 답변이 선언된 지식과 정확히 일치해야 공개한다.
3. 응답에는 근거 노드, 그래프 경로, 판정, 공식 출처와 버전을 포함한다. 일치하지 않으면 보류한다.
4. `evaluate_scenario`: 별도로 확인된 과세표준에 JSON 규칙을 적용한다. 정수 산술이므로 부동소수점 반올림으로 경계값을 넘지 않는다. 이는 MARCO 세법 도메인 모듈이며, 자유문장 추론이나 그래프의 자동 세법 도출이라고 주장하지 않는다.
5. 모든 경로에 원격 LLM 호출·모델 다운로드·신고·납부·사용자 대화 저장은 없다.

수치 계산은 아래 다섯 필드를 모두 요구한다. 추가 필드를 조용히 무시하지 않는다.

```json
{"tax_type":"gift","as_of":"2026-11-06","amount_kind":"tax_base","tax_base_won":499999,"basic_rate_only":true}
```

결과 `status=computed`, `basic_tax_won=0`, `below_minimum=true`, `source_ids=["ita-55-2"]`.

`tax_type`은 `gift` 또는 `inheritance`. 금액은 0 이상 정수 원 또는 ASCII 숫자 문자열이며, 부동소수점·불리언·음수·단위가 붙은 문자열을 거절한다. 상한 9,000,000,000,000,000원은 JS 정수 전달 안전범위 내의 구현 한도이지 세법상 한도가 아니다. 원 미만 버림은 참고액의 표시 규칙이다. 최종 납부세액의 법정 끝수 계산을 검증했다는 뜻이 아니다.

```python
from marco.knowledge.korean_tax import evaluate_scenario, answer_question, classify_transfer
r = evaluate_scenario({"tax_type":"inheritance", "as_of":"2026-11-06", "amount_kind":"tax_base", "tax_base_won":500000, "basic_rate_only":True})
assert r["basic_tax_won"] == 50000
q = answer_question("사인증여는 증여세야?", as_of="2026-11-06")
assert q["native_evidence"]["engine"] == "MARCO engine.Session"
assert classify_transfer("death_effective_gift", as_of="2026-11-06")["tax_type"] == "inheritance"
```

확정된 이전유형(`lifetime_gift`, `death_inheritance`, `legacy`, `death_effective_gift`)만 분류한다. 실제 납세의무·평가·비과세 여부를 판단하는 기능은 아니다.

## HTTP 계약

먼저 `python -m pip install -r requirements-korean-tax.txt`로 NumPy를 설치한다. 구조화 계산만 실행하면 표준 라이브러리로 충분하지만, 원본 engine.Session의 문자 벡터 경로는 NumPy가 필요하다. 신경망 모델은 필요하지 않다. 저장소 루트에서 `python -m marco.knowledge.korean_tax.server` 실행. 기본 `HOST=127.0.0.1`, `PORT=8080`. 별도 호스팅은 TLS 프록시 및 제공된 PORT가 필요하다. Docker 배포용 파일은 선택 사항이며 실제 배포하지 않았다.

- `GET /health`: 버전·지식 해시·제한된 기능, `llm_used=false`, `general_freeform_counseling=false`.
- `POST /evaluate`: 위의 다섯 필드.
- `POST /question`: `{"question":"사인증여는 증여세야?","as_of":"2026-11-06"}`.
- `POST /classify`: `{"transfer_kind":"death_effective_gift","as_of":"2026-11-06"}`.

응답은 wrapper 없는 JSON 객체다. 의미상 보류는 HTTP 200 + `status=insufficient_information|unsupported|invalid_input`. 잘못된 HTTP/JSON은 400, Content-Type 오류 415, 본문 초과 413. `Content-Type: application/json`, 요청 최대 16 KiB, 소켓 읽기 제한 5초, 단일 동시 실행, 응답 `no-store`. 중복 JSON 키와 NaN을 거절한다. 로그에 요청 내용·금액·질문을 쓰지 않는다. 학습·관리·메모리 API는 노출하지 않는다. 공개 호스팅은 TLS와 앞단 요청 제한을 별도로 갖춰야 한다.

Sites 직접 실행 여부는 이 작업의 Python 테스트만으로 확정하지 않았다. JavaScript로 규칙을 옮긴 구현은 원본 Python MARCO 실행과 구분해야 한다.

## 모델 빌드와 검증

```sh
python tools/build_korean_tax_pack.py
python -m pytest -o addopts='' tests/test_korean_tax.py tests/test_korean_tax_http.py -q
python tools/evaluate_korean_tax.py
```

생성물:

- `legal/graph_한국세법_2026.kg`: 엔진이 직접 읽는 7개 근거 지식 그래프. 기본 graphs 색인 밖에 위치하여 명시적으로 선택한다.
- `models/MARCO-Korean-Tax-Core-2026.mco`: native MCO Format 1, 76,736 bytes.
- 모델 SHA256: `3d901ed58e6b8acc1113692fa73bb284700c1329ee65e8fe6385d6b7fcbdd443`. 같은 입력으로 다시 빌드하여 동일 바이트를 확인했다.
- 지식 SHA256: `ff6ace5449d5c9fa587f2dad3ca923b094d2dc2ae76b1563521333e1cbb4b99c`.

실제 검증 결과:

- 새 단위·HTTP 시험 **84/84 통과**. 과세최저한·구간 경계, 세목 구분, 누락·잘못된 입력, 미래 날짜, 원본 그래프 실행, 네트워크 미사용.
- 기존 관련 회귀 **74/74 통과**: `test_lightweight_runtime.py`, `test_short_evidence_question.py`, `test_document_kg.py`, `test_mco_native_format.py`.
- 별도 작성자가 구현을 보지 않고 고정한 구조화 holdout **첫 실행 20/20 통과**. 구현 동결 후 열었으며 기대값 수정이나 재훈련을 하지 않았다. 고정 해시와 전체 결과는 `korean-tax-holdout-v1-results.json`에 있다.
- 21개 등록 질문은 학습 표현 자체를 확인한 시험으로, 새로운 자연어 이해 점수가 아니다.
- 전체 저장소 테스트는 실행하지 않았다. 158개 집중 시험 통과를 전체 통과로 표현하지 않는다.

로컬 Python 3.12(NumPy가 설치된 환경) 한 프로세스의 첫 사실 답변: 약 0.149초, peak RSS 25,780 KiB, 실행 중 불러온 저장소 Python 파일 8개 약 467 KB. 이 크기는 Python·NumPy·WASM 런타임 전체 크기를 제외한 값이다. 실제 호스팅/WASM 성능 수치가 아니며 일반화하지 않는다.

원본 `.mco` 직접 실행에서는 등록 질문의 사실 내용이 반환되지만, 다중 목표 그래프가 닫히지 않아 상태가 `needs_input`인 것이 관찰됐다. HTTP 지식 경로는 원본 `engine.Session`의 단일 근거 응답을 검증해 사용한다. `.mco` 직접 호출의 상태와 HTTP 계약을 혼동하지 않는다.

## 대체할 수 없는 기능

임의 가족·자산 서술에서 사실을 빠짐없이 추출하거나, 공제·합산·평가·세대생략·특례를 결정하는 자유상담은 구현하지 않았다. 다음 실제 입력에서 native `.mco`는 `unknown`을 반환했다.

> 아버지가 돌아가셨고 재산은 10억원입니다. 배우자와 자녀 2명에게 나누면 세금은?

OpenAI 없이 제한된 지식 조회와 구조화된 계산을 제공할 수 있지만, 이 결과로 일반 세무상담 전체를 대체했다고 말할 수 없다. 범위 밖은 추가 사실·공식 원문·전문가 검토로 넘긴다.

초기 환경 관찰만으로 native 경로가 표준 라이브러리만 필요하다고 판단했으나, 독립 Pyodide 및 `python -S` 검사에서 NumPy 의존성을 확인했다. 그 판단을 철회하고 설치 요구사항을 명시했다. NumPy 없이 실행하는 독립 표준 라이브러리 검사에서는 native 사실 조회가 `unsupported`로 보류되며 수치 계산은 정상 동작한다.

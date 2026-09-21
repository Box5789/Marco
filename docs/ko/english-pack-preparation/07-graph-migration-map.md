# 최종 그래프 형식으로 옮기는 대응표

이 초안(`01`~`05`)의 각 조각이 다음 goal 의 언어 그래프에서 **어떤 노드·관계가 되어야
하는지** 적는다. 그래프 스키마는 아직 확정되지 않았으므로 여기 적은 노드 타입 이름은
제안이며, 확정된 이름으로 치환해 쓴다.

옮기는 원칙 세 가지.

1. 표면형·뜻·개념 ID 를 세 층으로 유지한다. 한 노드에 뭉치면 다의어가 무너진다.
2. 기존 한국어 노드 ID 는 바꾸지 않는다. 대응 관계를 **덧붙일** 뿐이다.
3. 규칙은 거대한 JSON 문자열 한 덩이가 아니라, 구성 요소·순서·조건·변수·생성 구조를
   가리키는 관계들로 푼다. 사람이 읽는 설명문만 저장하는 것도 불충분하다.

## A. 초안 → 그래프 요소

| # | 초안의 자리 | 그래프 요소(제안) | 옮길 때의 주의 |
| --- | --- | --- | --- |
| M1 | `01.language` | `Language` 노드 1개 | `.kg` 헤더에 이미 `언어:` 필드가 있다(`graph_en_bill_split.kg`). 그 필드와 어느 쪽이 원본인지 하나로 정한다 |
| M2 | `01.roles[]` | `SemanticRole` 노드 + `role_name` 속성 | `origin: 기존` 인 것(`giver`/`taker`/`item`/`source`/`location`/`target`)은 이미 코드·공리에 있는 이름이다. 새 이름을 만들지 말고 그대로 쓴다 |
| M3 | `01.typology` | `LanguageProfile` 노드 | "영어에는 조사가 없다"를 빈 칸이 아니라 `role_marking: position_and_adposition` 이라는 **양의 선언**으로 적는다 |
| M4 | `01.adpositions[]` | `SurfaceForm` --`assigns`--> `SemanticRole` | 한국어의 `조사` 목록과 **같은 관계 타입**을 써야 한다. 다른 타입을 쓰면 공통 실행기가 두 갈래로 갈린다 |
| M5 | `01.morphology.*` | `InflectionRule` 노드 + 순서 있는 `step` 관계 | 한국어 `활용` 의 `steps[{op,…}]` 구조를 그대로 따른다. `op` 값만 언어별로 다르다(`append`/`coda_suffix` vs `replace_final`/`double_final_then_append`) |
| M6 | `01.morphology.*.irregular` | `Lexeme` --`has_form`--> `SurfaceForm` (`form_slot` 속성) | 불규칙은 규칙이 아니라 **어휘에 붙은 사실**이다. 규칙 노드에 넣지 않는다 |
| M7 | `01.sentence_boundary` | `BoundaryRule` + `BoundaryException` | 한국어는 어미가, 영어는 독립 낱말이 경계를 만든다. 같은 관계 타입에 다른 종류의 `marker` 노드를 매단다 |
| M8 | `01.numerals` | `NumeralSystem` + `Numeral` 노드 | `derived_quantities` 는 한국어 `수량표현` 과 같은 구조(`말/연산/값` → `surface/op/value`). 이름만 맞추면 그대로 옮겨진다 |
| M9 | `01.units[]` | `Unit` 노드 --`realized_as`--> `SurfaceForm` 또는 **관계 없음** | 표면형이 없는 단위(`unit/count`)를 "관계 없음"으로 표현할 수 있어야 한다. `null` 속성으로 두면 "모른다"와 구별이 안 된다 (D2) |
| M10 | `01.negation` / `01.modality` | `PolarityRule` / `ModalityMarker` 노드 | `changes_state: false` 를 **그래프가 선언**해야 한다. 코드에 두면 언어를 바꿀 때 안 따라온다 |
| M11 | `01.questions` | `QuestionForm` --`asks`--> `SemanticRole` | wh 성분이 옮겨간 자리(빈자리)가 어느 역할인지가 질문 대상이다. 낱말 목록만 옮기면 이 정보가 사라진다 |
| M12 | `01.rules[]` | `GrammarRule` 노드 + 순서 있는 `reads` 관계 + `binds` 관계 + `emits` 관계 | **여기가 핵심이다.** `reads` 를 문자열 배열로 남기면 그래프화가 아니다. 각 구성 요소가 별도 노드이고, 순서가 관계의 속성이며, `optional`/`conditions`/`exceptions` 가 각각 관계여야 한다 |
| M13 | `01` 전체 ↔ `styles/한국어.json` 의 `문서분류` | 영어 패턴을 한국어 팩에서 **떼어** 영어 쪽으로 | 한국어 팩의 `문서분류._주의` 가 이미 "영어 팩이 서면 그쪽으로 갈라야 한다"고 적어 두었다. 갈라야 할 정규식: `causes?`, `leads? to`, `results? in`, `first`, `then`, `finally`, `may `, `might `, `cannot `, `limitation`, `we found`, `results? show`, `this|that|these|those` |
| M14 | `02.concepts[]` | `Concept` 노드 (언어 무관) | 표준명은 영어로 적되 identity 는 `id` 가 가진다. 표준명을 바꿔도 `id` 는 안 바뀐다 |
| M15 | `02.senses[]` | `Sense` --`of_concept`--> `Concept` | `concept: null` 인 sense(`s/book.reserve`)는 "개념을 만들지 않고 보류" 를 뜻한다. 이 상태를 그래프가 표현할 수 있어야 한다 |
| M16 | `02.expressions[]` | `Expression` --`has_sense`--> `Sense`, `in_language`--> `Language` | 같은 철자 다른 뜻은 **별도 Expression 노드**다(`x/en/book` vs `x/en/book#reserve`) |
| M17 | `02.links[]` | `Expression` --`same_concept`/`partial`/`homonym_split`--> `Expression` | `relation` 값마다 다른 관계 타입이다. 하나로 뭉쳐 `translation` 관계만 두면 부분 대응과 동일 개념이 섞인다 |
| M18 | `03.node_links[]` | `Concept` --`maps_to_pack_node`--> 기존 노드 ID (`pack` 속성 필수) | **기존 노드 ID 를 바꾸지 않는다.** 대응 관계에 `pack` 을 반드시 붙인다 — 다른 팩의 동명 노드를 합치지 않기 위해서다 |
| M19 | `03.relation_links[]` | `PackRelation` --`same_as`--> `PackRelation` | 팩 머리표의 `전진관계`/`근거관계` 값까지 포함한다 (D6) |
| M20 | `03.axiom_links[]` | 옮기지 않는다 | `axioms/core.json` 은 이미 언어 중립이다. 언어팩이 공리를 건드리면 안 된다는 경계가 여기다. 대응만 문서로 남긴다 |
| M21 | `01.answer_forms` | `OutputTemplate` --`for_intent`--> … | 입력 규칙과 **같은 역할·뜻 선언**을 참조해야 한다. 별도 출력 어휘를 만들면 입출력이 모순된 두 체계가 된다 |
| M22 | `04` 평가 사례 | **옮기지 않는다** | 정답 자료다. 런타임 언어 자산에 넣으면 평가가 무효다 |
| M23 | `05` 학습 예문 | **옮기지 않는다** | 개발용이다. 규칙이 읽어내야 할 표면형의 목록일 뿐 팩 자산이 아니다 |
| M24 | `01.resource_limits` | 엔진 쪽 상한 | 범용 실행 상한은 코드에 남는 것이 맞다. 다만 값은 팩이 낮출 수 있어야 한다 |

## B. 한국어 팩의 칸 ↔ 영어 초안의 칸

`styles/한국어.json` 의 각 키가 영어에서 어디로 가는지. **빈 칸으로 남는 것과
다른 기제로 대체되는 것을 구별한다.**

| 한국어 키 | 영어 대응 | 관계 |
| --- | --- | --- |
| `조사` / `자리조사` / `조사짝` / `조사예외` / `붙일조사` / `떼는조사` | `01.adpositions` + `01.typology.constituent_order` | **대체**. 없어지는 것이 아니라 어순·전치사로 옮겨간다 |
| `조사붙임` | 해당 없음 (영어는 띄어 쓴다) | 빈 칸 |
| `이음규칙` / `활용.endings` | `01.morphology.verb` | 대체. 조작 종류가 다르다 |
| `활용.vowel_join` (모음조화·축약) | 없음 | **빈 칸**. 영어에 모음조화가 없다 |
| `활용.parsing_endings` 의 `polite`/`request_honorific_ask` | 없음 | **빈 칸** (D4 높임 축) |
| `문장분리.candidate_suffixes` | `01.sentence_boundary.clause_connectives` | 대체. 어미 → 독립 낱말 |
| `문장분리.hypothetical_prefixes` (`만약`) | `01.modality.hypothetical.markers` | 대응 |
| `수량연쇄` | `rule/en-existential-count` + `rule/en-count-remove` + `rule/en-count-add` + `q/existential` | **분해**. 한국어는 한 표에 담았고 영어는 규칙 넷으로 갈린다 |
| `수량연쇄.단위` (`개`) | `unit/count` (표면형 없음) | 대체 |
| `수량표현` (절반/두 배/전부) | `01.numerals.derived_quantities` | 대응. 영어에 `dq/none` 추가분 |
| `자리말` | `rule/en-placeholder-nouns` | 대응. 영어는 다어절이 많다 |
| `임자자리말` (`나`) / `임자조사` (`이`) | `role_hint: role/agent` 의 `I`/`me` | 부분 대응. 영어는 격으로 갈린다 |
| `지시어` | `01.deixis_and_ellipsis.pronouns` | 대응 |
| `주어없음` | `01.deixis_and_ellipsis.zero_subject_followups` | **대체**. 영어는 주어를 비우지 못한다 |
| `부정` (`지`+`않`) | `01.negation.strategies` 5종 | **분해**. 어미 하나 → do-support 등 다섯 |
| `계획` (매김꼴 미래+예정+이다) | `01.modality.planned.markers` | 대체 |
| `관계해석.numerals` | `01.numerals` | 대응 |
| `관계해석.context_correction` | `rule/en-correction` | 대응. 구분자 `=>` 는 언어 무관 |
| `관계해석.context_replies` | `01.answer_forms.not_understood` | 대응. 한국어 쪽이 훨씬 촘촘하다 — 영어 초안은 5개뿐이고 한국어는 20개 이상이다. **미완성 부분으로 집계한다** |
| `상태표현` / `상태표현.units` | `01.answer_forms` + `01.units` | 대응 |
| `말수식` | `01.numerals.arithmetic_phrases` | 대응. 영어는 인자 순서가 뒤집히는 꼴이 있다 |
| `범위답` / `정정대상답` / `관계선택답` | `rule/en-scope-reply` / (미작성) / `01.numerals.ordinals` | 부분. **`정정대상답` 의 영어 대응을 아직 안 적었다 — 미완성** |
| `자리물음` (조사 키) | `01.answer_forms.role_question` (역할 ID 키) | **대체**. 키가 조사에서 역할로 바뀐다 (D1) |
| `짧은답꼬리` | 없음 | **빈 칸** (D4) |
| `출력계약.number_only` | `01.answer_forms.number_only` | 대응. 정규식은 언어별로 따로 |
| `군말` | `01.sentence_boundary.discourse_prefixes_ignorable` | 대응 |
| `의도표` / `뜻표지` / `외부조사` | 미작성 | **미완성**. 법령·문서 질의 쪽이라 13개 시나리오 밖이다 |
| `문서분류` | M13 참조 | 한국어 팩에서 영어 패턴을 떼어 내야 한다 |
| `대화이해.affect` | 미작성 | **의도적 제외**. 새 감정 체계를 더하지 않는다는 경계 |
| `인코더` | 미작성 | (D9) 실측 없이 정할 수 없다 |
| `학습질문종결` / `학습주제제외` | 미작성 | 자가학습 주제 추출. 13개 시나리오 밖 |

## C. 옮기기 전에 통과해야 하는 검사

`check.py` 가 지금 검사하는 것:

- `01`~`05` 의 모든 ID 가 유일한가 (중복 ID)
- 참조된 ID 가 실재하는가 (`sense` → `concept`, `link` → `expression`, 규칙의 `bind` → `role`)
- `03` 의 `evidence` 가 가리키는 파일·노드가 저장소에 실제로 있는가 (잘못된 참조)
- `04` 와 `05` 의 문장이 겹치는가 (평가·학습 분리)
- `homonym_split` 로 갈라 둔 표현이 같은 concept 에 묶여 있지 않은가 (의미 모순)
- `status: held` 인 링크가 `04` 의 기대 경로에 쓰이고 있지 않은가

옮긴 뒤에 추가로 필요한 검사(다음 goal):

- 규칙 하나를 그래프에서 빼면 해당 해석이 실패하거나 보류가 나오는가
- 뜻 연결 하나를 빼면 `03` 의 고정 표본이 **미연결로 검출**되는가
- 역할이 뒤바뀐 잘못된 그래프가 검증에서 거절되거나 평가에서 오답으로 잡히는가
- 컴파일 캐시가 그래프 변경 뒤에도 옛 의미를 내지 않는가

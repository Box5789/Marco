# -*- coding: utf-8 -*-
"""뜻풀이의 틀을 손으로 적지 않고 이미 있는 사례에서 꺼낸다.

뜻풀이의 몸통은 **보통 문장**이다. 다만 사건이 채울 자리가 비어 있을 뿐이다.

    치우다는 [     ] 물건을 상자로 옮기는 것이다
    하루가       연필을        치웠다

그래서 몸통은 **앞자리를 지운 사례**에 맞춰 읽고, 비어 있던 자리는 사건이
**같은 조사로** 채운다. 짜임이 하나 늘 때마다 틀을 새로 선언하지 않는다.

여기서 선언에 기대는 것은 둘뿐이고, 둘 다 낱말마다 늘지 않는다.

* 조사 — 닫힌 낱말갈래다. 한국어의 조사는 세다가 끝난다.
* 이미 적혀 있는 보통 문장 사례 — 틀이 아니라 문장이다.

그래서 못 읽는 뜻풀이가 남는다면 그것은 **틀이 없어서가 아니라 몸통의 동사를
모르기 때문**이다. 이 둘은 값이 다르다. 틀은 끝없이 늘고 동사는 유한하다.
"""
from hangul import inflect
from relational_semantics import asserted, substitute


def particle_key(particle, groups):
    """같은 자리를 채우는 조사는 한 이름으로 부른다. `로` 와 `으로` 는 한 자리다."""
    for group in groups:
        if particle in group:
            return group[0]
    return particle


def split_particle(word, particles, groups):
    """낱말을 (앞말, 자리) 로 가른다. 조사가 안 보이면 None."""
    for particle in particles:                      # 긴 조사를 먼저 본다
        if len(word) > len(particle) and word.endswith(particle):
            return word[:-len(particle)], particle_key(particle, groups)
    return None


def _marked(value, particles, groups):
    """이 값이 **조사를 넘어서 잘렸나.** 넘어섰으면 자름이 틀렸다.

    낱말 하나만 잡았다면 조사를 넘은 것이 아니다. 낱말 하나에 대고 조사를 떼
    보면 멀쩡한 이름을 버린다 — `사과` 의 `과`, `모과` 의 `과` 는 조사가 아니라
    이름의 끝 글자다. 조사는 앞말에 붙고 뒤는 띄우므로, **띄어쓰기를 넘어선
    자리에 조사가 보일 때만** 잘못 잘린 것이다.
    """
    words = value.split()
    return len(words) > 1 and any(split_particle(word, particles, groups) for word in words)


def _spans(example):
    text, slots = example["text"], example["slots"]
    return sorted((text.index(v), text.index(v) + len(v), k) for k, v in slots.items())


def _particle_at(text, end, particles, groups):
    """이 자리 바로 뒤에 붙은 조사. 조사가 아니면 None."""
    rest = text[end:]
    for particle in particles:
        if rest.startswith(particle) and not rest[len(particle):len(particle) + 1].strip():
            return particle_key(particle, groups)
    return None


def _chunks(example, particles, groups):
    """예문을 **조사가 끝맺는 덩이**로 나눈다. 덩이마다 그 안의 자리도 함께.

        하루가 | 모래에게 | 구슬 2개를 | 줬다
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^   ^^^^ 풀이말

    덩이를 알면 자리를 빼는 것도 자리 순서를 바꾸는 것도 같은 일이 된다.
    한국어는 조사가 자리를 짚으므로 덩이 순서는 뜻을 안 바꾼다.
    """
    text, spans = example["text"], _spans(example)
    tokens, cursor = [], 0
    for word in text.split():
        start = text.index(word, cursor)
        tokens.append((start, start + len(word)))
        cursor = start + len(word)
    chunks, current = [], []
    for start, end in tokens:
        current.append((start, end))
        if split_particle(text[start:end], particles, groups):
            chunks.append(current); current = []
    def inside(piece):
        low, high = piece[0][0], piece[-1][1]
        return {name: example["slots"][name] for s, e, name in spans if low <= s and e <= high}
    return ([(text[piece[0][0]:piece[-1][1]], inside(piece)) for piece in chunks],
            (text[current[0][0]:] if current else ""),
            (inside(current) if current else {}))


def _elisions(example, particles, groups, reorder=False):
    """자리를 빼고 순서를 바꾼 조각 사례들. 뺀 자리가 곧 사건이 채울 자리다.

    앞에서부터만 빼면 `구슬 2개를 상대에게 주는` 처럼 **순서만 다른** 말을 못
    읽는다. 반례마다 예문을 더하지 않고 덩이를 다시 늘어놓는다.
    """
    from itertools import combinations, permutations
    text = example["text"]
    chunks, tail, tail_slots = _chunks(example, particles, groups)
    if not chunks:
        return
    seen = set()
    for keep in range(len(chunks), -1, -1):
        arrangements = (permutations(range(len(chunks)), keep) if reorder else
                        combinations(range(len(chunks)), keep))
        for chosen in arrangements:
            order = sorted(chosen)
            dropped = {}
            for index, (_piece, slots) in enumerate(chunks):
                if index in chosen:
                    continue
                for name in slots:
                    end = text.index(example["slots"][name]) + len(example["slots"][name])
                    dropped[name] = _particle_at(text, end, particles, groups)
            if any(key is None for key in dropped.values()):
                continue            # 조사 없이 지워진 자리는 사건이 채울 길이 없다
            body = " ".join(chunks[index][0] for index in chosen)
            piece_text = " ".join(part for part in (body, tail) if part)
            if piece_text in seen or not piece_text:
                continue
            seen.add(piece_text)
            kept = dict(tail_slots)
            for index in chosen:
                kept.update(chunks[index][1])
            if any(piece_text.count(value) != 1 for value in kept.values()):
                continue            # 순서를 바꾸다 같은 글자가 둘이 되면 못 가른다
            piece = {k: v for k, v in example.items() if k != "inflection"}
            piece["text"], piece["slots"] = piece_text, kept
            yield piece, dropped, len(chunks) - keep, list(chosen) != order


def _finite(body, example, grammar):
    """몸통의 매김꼴을 그 사례가 쓰는 마침꼴로 되돌린다. 아는 어간만 본다."""
    yield body
    annotation = example.get("inflection")
    if not annotation or not grammar:
        return
    try:
        adnominal = inflect(annotation["stem"], "present", "adnominal", grammar,
                            kind=annotation["kind"])
        canonical = inflect(annotation["stem"], annotation["tense"], annotation["ending"],
                            grammar, kind=annotation["kind"])
    except ValueError:
        return
    for form in adnominal:
        if body.endswith(form["text"]) and len(body) > len(form["text"]):
            for tail in canonical:
                yield body[:-len(form["text"])] + tail["text"]


def induce(parser, body):
    """몸통을 이미 아는 문장꼴로 읽는다. 읽히면 쓸 수 있는 뜻틀을 준다.

    가장 적게 지운 자름을 고른다. 더 지울수록 말을 더 삼키기 때문이다.
    순서를 그대로 둔 자름을 먼저 다 보고, 그것으로 안 되면 순서를 바꿔 본다 —
    흔한 쪽을 먼저 보는 것이 값도 싸고, 덜 흔든 읽기를 고르는 길이기도 하다.
    """
    for reorder in (False, True):
        found = _read_body(parser, body, reorder)
        if found is not None:
            return found
    return None


def _compile(parser, example, piece):
    """조각 사례의 틀. 몸통마다 다시 짓지 않는다."""
    cache = parser.__dict__.setdefault("_조각틀", {})
    key = (example["text"], piece["text"])
    if key not in cache:
        cache[key] = parser.compile(piece, parser.data.get("numerals", {}),
                                    parser.slot_particles)
    return cache[key]


def _read_body(parser, body, reorder):
    from numeral_semantics import parse_numeral
    particles = parser.case_particles
    groups = parser.slot_particles
    numerals = parser.data.get("numerals", {})
    best = None
    for example in parser.data["examples"]:
        if not asserted(example["meaning"]):
            continue                # 물음도 뜻풀이도 몸통이 될 수 없다
        for piece, dropped, missing, reordered in _elisions(example, particles, groups, reorder):
            patterns, meaning = _compile(parser, example, piece)
            for candidate in _finite(body, example, parser.inflection_grammar):
                for pattern in patterns:
                    match = pattern.fullmatch(candidate)
                    if not match:
                        continue
                    values = dict(match.groupdict())
                    if any(_marked(value, particles, groups) for value in values.values()):
                        continue    # `하루가 연필` 을 한 이름으로 삼키지 않는다
                    for name, annotated in piece["slots"].items():
                        if annotated.isdecimal():
                            values[name] = parse_numeral(values[name], numerals)
                    if any(value is None for value in values.values()):
                        continue
                    spans = _spans(piece)
                    자리 = {name: _particle_at(piece["text"], end, particles, groups)
                           for _s, end, name in spans}
                    specificity = len(candidate) - sum(len(value) for value in match.groupdict().values())
                    # 적게 지운 것, 순서를 안 바꾼 것, 더 많이 못 박은 것 순.
                    score = (missing, reordered, -specificity)
                    if best is None or score < best[0]:
                        best = (score, {"뜻": meaning, "값": values,
                                        "자리": {k: v for k, v in 자리.items() if v},
                                        "빈자리": dropped})
    return best[1] if best else None


def parameters(meaning):
    """사실의 **임자 자리**에 나오는 슬롯 이름. 뜻풀이가 말하는 대상이 거기 있다.

        물건을 상자로 옮기는   ->  [$item, location, $place]
                                   ^^^^^ 임자            ^^^^^^ 값

    `물건` 은 이 동사가 **무엇에 대해** 하는 일인지를 가리키는 자리다. 사건이
    `연필을` 이라고 하면 그 자리를 채운 것이다. `상자` 는 값 자리이므로 뜻풀이가
    정해 놓은 것이다 — 사건이 `학교로` 라고 하면 자리를 채운 것이 아니라
    **뜻을 바꾸는 것**이고, 그건 임의로 할 일이 아니다.

    셋을 다 가르지는 못한다. 여기서 갈리는 것은 **변수와 고정값**이고, "바꿔도
    되는 기본값" 은 지금 자료로는 고정값과 구별할 근거가 없다.
    """
    rows = [meaning["triple"]] if "triple" in meaning else meaning.get("triples", [])
    names = set()
    for row in rows:
        subject = row[0]
        for piece in (subject if isinstance(subject, list) else [subject]):
            if isinstance(piece, str) and piece.startswith("$"):
                names.add(piece.lstrip("$"))
    return names


def apply_rule(induced, 자리):
    """사건이 짚은 자리로 뜻틀을 채운다. **못 채운 자리는 못 채웠다고 말한다.**

    자리 하나를 못 채웠다고 아무 일도 없었던 것이 아니다. `지연에게 베풀었다`
    는 누가 줬는지는 몰라도 무언가 일어났다고 말한다. 그것을 빈 사실 목록으로
    바꾸면 **해석 실패가 "변화 없음" 으로 둔갑한다** — 옛 값이 그대로 확정된다.
    그래서 둘을 갈라서 돌려주고, 못 채운 자리가 있으면 사실은 안 쓴다.
    """
    변수 = parameters(induced["뜻"])
    values, 충돌 = dict(induced["값"]), {}
    for name, key in {**induced["자리"], **induced["빈자리"]}.items():
        if key not in 자리:
            continue
        if name in induced["빈자리"] or name in 변수:
            values[name] = 자리[key]          # 비어 있던 자리이거나 이 동사가 다루는 것
        elif induced["값"].get(name) != 자리[key]:
            # 뜻풀이가 정한 값과 다른 값이다. 채우는 것이 아니라 바꾸는 것이므로
            # 말없이 어느 한쪽을 고르지 않는다.
            충돌[name] = {"뜻": induced["값"].get(name), "사건": 자리[key]}
    빈자리 = {name: key for name, key in induced["빈자리"].items() if name not in values}
    사실 = asserted(substitute(induced["뜻"], values))
    return {"사실": [] if (빈자리 or 충돌) else 사실, "빈자리": 빈자리,
            "충돌": 충돌, "닿는곳": 사실}


def asks(text, negation=None, verbs=None):
    """묻는 말인가. 설명받은 어간의 **묻기 전용 꼴**로 끝나면 묻는 말이다.

    물음표에만 기대면 안 된다 — `민수가 지연에게 베풉니까` 는 물음표가 없어도
    물음이고, 사건으로 읽으면 물어본 일이 실제로 일어난다.
    """
    words = text.strip().rstrip(".!?…").split()
    if not words:
        return False
    if negation and words[-1] in (negation.get("물음") or ()):
        return True
    return bool((verbs or {}).get(words[-1], {}).get("물음"))


def read_event(text, particles, groups, negation=None, verbs=None):
    """조사가 자리를 짚고 남은 한 낱말이 움직임인 꼴. 사건은 이렇게 생겼다.

    **뜻을 몰라도 꼴은 안다.** 그래야 모르는 말을 만났을 때 "그 말을 모릅니다"
    라고 짚어 주고, 나중에 설명을 들으면 이어서 풀 수 있다. 뜻은 여기서
    정하지 않는다 — 쓰인 낱말을 그대로 돌려주고, 설명받은 어간과 잇는 일은
    활용표가 한다.

    꼴이 아닌 것은 안 읽는다. 앞 낱말이 조사를 안 달았으면(`단추 이야기는
    재밌다` 의 `단추`) 자리를 못 짚은 것이고, 못 짚으면 짐작하지 않는다.

    **묻는 말도 사건이 아니다.** 물음표가 없어도 그렇다 — `베풉니까` 는
    설명받은 어간의 물음꼴이므로 일어난 일이 아니다. 활용을 이을 때 어간만
    나르면 이 자리를 놓친다.
    """
    words = text.strip().rstrip(".!?…").split()
    if not words or asks(text, negation, verbs):
        return None
    polarity, tail = True, words[-1:]
    if negation and len(words) > 2 and words[-1] in negation["forms"]:
        # `…지 않았다`. 부정도 낱말마다 틀을 적지 않는다 — 언어팩이 잇는 말과
        # 보조 어간을 한 번 적어 두면 활용은 계산된다.
        stem = words[-2][:-len(negation["연결"])]
        if not words[-2].endswith(negation["연결"]) or not stem:
            return None
        polarity, tail, words = False, [stem], words[:-1]
    if len(words) < 2:
        return None
    자리 = {}
    for word in words[:-1]:
        piece = split_particle(word, particles, groups)
        if piece is None or not piece[0] or piece[1] in 자리:
            return None             # 조사 없는 낱말도, 같은 자리 두 번도 못 읽는다
        자리[piece[1]] = piece[0]
    event = {"verb": tail[0], "자리": 자리}
    return event if polarity else {**event, "polarity": False}

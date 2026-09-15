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
    """이 값 안에 조사 붙은 낱말이 들어 있나. 들어 있으면 자름이 틀렸다."""
    return any(split_particle(word, particles, groups) for word in value.split())


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


def _elisions(example, particles, groups):
    """앞자리를 하나씩 지운 조각 사례. 지운 자리가 곧 사건이 채울 자리다."""
    text, spans = example["text"], _spans(example)
    for cut in range(len(spans)):
        kept = {name: example["slots"][name] for _s, _e, name in spans[cut:]}
        dropped = {name: _particle_at(text, end, particles, groups)
                   for _s, end, name in spans[:cut]}
        if any(key is None for key in dropped.values()):
            continue                # 조사 없이 지워진 자리는 사건이 채울 길이 없다
        piece = {k: v for k, v in example.items() if k != "inflection"}
        piece["text"], piece["slots"] = text[spans[cut][0]:], kept
        yield piece, dropped


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
    """
    from numeral_semantics import parse_numeral
    particles = parser.case_particles
    groups = parser.slot_particles
    numerals = parser.data.get("numerals", {})
    best = None
    for example in parser.data["examples"]:
        if not asserted(example["meaning"]):
            continue                # 물음도 뜻풀이도 몸통이 될 수 없다
        for order, (piece, dropped) in enumerate(_elisions(example, particles, groups)):
            patterns, meaning = parser.compile(piece, numerals, groups)
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
                    score = (order, -specificity)
                    if best is None or score < best[0]:
                        best = (score, {"뜻": meaning, "값": values,
                                        "자리": {k: v for k, v in 자리.items() if v},
                                        "빈자리": dropped})
    return best[1] if best else None


def apply_rule(induced, 자리):
    """사건이 짚은 자리로 뜻틀을 채운다. 못 채운 빈자리가 있으면 쓰지 않는다."""
    values = dict(induced["값"])
    for name, key in {**induced["자리"], **induced["빈자리"]}.items():
        if key in 자리:
            values[name] = 자리[key]
    if any(name not in values for name in induced["빈자리"]):
        return None
    return asserted(substitute(induced["뜻"], values))


def read_event(text, particles, groups, negation=None):
    """조사가 자리를 짚고 남은 한 낱말이 움직임인 꼴. 사건은 이렇게 생겼다.

    **뜻을 몰라도 꼴은 안다.** 그래야 모르는 말을 만났을 때 "그 말을 모릅니다"
    라고 짚어 주고, 나중에 설명을 들으면 이어서 풀 수 있다. 뜻은 여기서
    정하지 않는다 — 쓰인 낱말을 그대로 돌려주고, 설명받은 어간과 잇는 일은
    활용표가 한다.

    꼴이 아닌 것은 안 읽는다. 앞 낱말이 조사를 안 달았으면(`단추 이야기는
    재밌다` 의 `단추`) 자리를 못 짚은 것이고, 못 짚으면 짐작하지 않는다.
    """
    words = text.strip().rstrip(".!?…").split()
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

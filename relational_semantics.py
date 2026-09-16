"""Induce slot templates from annotated examples; keep facts and answers separate.

This is supervised template induction, not a pretrained language model. A new
correction supplies a sentence, entity spans and its relation, never a QA answer.
"""
import copy
import json
import os
from pathlib import Path
import re
import tempfile

def asserted(meaning):
    """이 뜻이 내놓는 사실들. 한 문장이 사실 하나라는 법은 없다.

    주고받기는 한 문장이 **둘**을 말한다 — 주는 쪽이 줄고 받는 쪽이 는다.
    사실 하나만 담을 수 있으면 그런 움직임은 보통 문장으로 못 적고, 뜻풀이
    틀을 손으로 하나 더 적는 수밖에 없다.
    """
    if "triple" in meaning:
        return [joined(meaning["triple"])]
    return [joined(row) for row in meaning.get("triples", [])]


def joined(triple):
    """여러 조각으로 적힌 이름을 한 이름으로 잇는다.

    `[민수, 구슬]` 은 `민수 구슬` 이다 — 누구의 무엇인지를 함께 세는 자리.
    """
    return [" ".join(part) if isinstance(part, list) else part for part in triple]


def substitute(value, slots):
    if isinstance(value, str):
        return slots.get(value[1:], value) if value.startswith("$") else value
    if isinstance(value, list):
        return [substitute(x, slots) for x in value]
    if isinstance(value, dict):
        return {k: substitute(v, slots) for k, v in value.items()}
    return value


class RelationalParser:
    def __init__(self, data=None, model_path=None, *, language_pack=None):
        selected = model_path or (os.environ.get("NAI_RELATIONAL_MODEL") if data is None else None)
        self.model_path = Path(selected) if selected is not None else None
        if data is None:
            if self.model_path is not None:
                data = json.loads(self.model_path.read_text(encoding="utf-8"))
            else:
                from pack_model import development_model
                data = development_model().relational_data
        self.data = copy.deepcopy(data)
        if language_pack is None:
            from language_components import load_reasoning_language
            language_pack = load_reasoning_language()
        # Do not copy unrelated conversation/output configuration for each
        # parser. Keep only the language component this interpreter consumes.
        self.clause_grammar = copy.deepcopy(language_pack.get("clauses", {}))
        self.inflection_grammar = copy.deepcopy(language_pack.get("inflection", {}))
        self.slot_particles = copy.deepcopy(language_pack.get("slot_particles", []))
        # 자리를 짚는 격조사. 틀을 사례에서 꺼낼 때 몸통과 사건이 같은 자리를
        # 가리키는지 보는 데만 쓴다. 닫힌 갈래라 낱말마다 늘지 않는다.
        self.case_particles = copy.deepcopy(language_pack.get("case_particles", []))
        self.negation = self._negation(language_pack.get("negation", {}))
        # 뜻풀이에서 아무거나 하나를 가리키는 낱말. 그 자리는 사건이 채운다.
        # 자리말: 낱말 -> 그 묶음의 이름. `나` 와 `내` 는 한 자리다.
        self.placeholders = dict(language_pack.get("placeholders", {}))
        # 누가 했는지를 짚는 자리. 뜻풀이가 그 자리를 안 써도 넘어간다.
        self.doer_particle = language_pack.get("doer_particle", "")
        # 자리말 가운데 **그 일을 한 쪽**. 절 순서가 아니라 이것이 임자 자리를 정한다.
        self.speaker_placeholder = language_pack.get("speaker_placeholder", "")
        # 빈 자리를 사람 말로 되묻는 법. 짧은 답을 부르는 물음이다.
        self.slot_questions = dict(language_pack.get("slot_questions", {}))
        # 이름 하나로 답할 때 이름 뒤에 붙을 수 있는 말. **받아들일 꼴**의 목록이다.
        self.short_tails = list(language_pack.get("short_tails", []))
        # 뜻풀이와 어긋난 값이 **어디까지** 미치는지 묻고 받는 말. 셋뿐이다.
        self.scope_words = dict(language_pack.get("scope_words", {}))
        self.target_words = dict(language_pack.get("target_words", {}))
        self.language_pack = {"clauses": self.clause_grammar, "inflection": self.inflection_grammar,
                              "slot_particles": self.slot_particles,
                              "case_particles": self.case_particles,
                              "negation": copy.deepcopy(language_pack.get("negation", {})),
                              "placeholders": dict(self.placeholders),
                              "doer_particle": self.doer_particle,
                              "speaker_placeholder": self.speaker_placeholder,
                              "slot_questions": dict(self.slot_questions),
                              "short_tails": list(self.short_tails),
                              "scope_words": dict(self.scope_words),
                              "target_words": dict(self.target_words)}
        # 몸통에서 꺼낸 틀은 예문이 그대로인 동안만 같다. `learn` 이 예문을
        # 늘리면 버린다 — 옛 사례로 읽은 몸통을 그대로 쓰면 안 된다.
        self.induced_frames = {}
        self.templates = []
        for example in self.data["examples"]:
            self.templates.append(self.compile(example, self.data.get("numerals", {}),
                                               self.slot_particles))
        self._rebuild_inflections()

    def _negation(self, declared):
        """부정을 나타내는 말들. 잇는 말과 보조 어간만 선언하고 꼴은 계산한다.

        `않았다`·`않아요`·`않습니다` 를 손으로 적지 않는다. 언어팩이 이미
        활용을 계산하고 있으므로, 부정도 낱말이 아니라 한 줄이면 된다.
        """
        from hangul import inflect
        grammar = self.inflection_grammar
        if not declared or not grammar:
            return {}
        forms, asking = set(), set()
        for tense in grammar.get("tenses", {}):
            for ending in grammar.get("endings", {}):
                try:
                    made = {form["text"] for form in
                            inflect(declared["어간"], tense, ending, grammar,
                                    kind=declared["갈래"])}
                except ValueError:
                    continue
                forms |= made
                # 묻기만 하는 꼬리. `않았어요` 처럼 서술로도 쓰는 꼬리는 빼야
                # 한다 — 안 그러면 안 한 일을 말한 것까지 물음으로 읽는다.
                if ending in self._asking(grammar):
                    asking |= made
        return {"연결": declared["연결"], "forms": forms,
                "물음": asking - (forms - asking)}

    @staticmethod
    def _asking(grammar):
        """묻기에만 쓰는 꼬리. 서술에도 쓰는 꼬리는 물음의 표가 못 된다."""
        return set(grammar.get("question_endings", [])) - set(grammar.get("parsing_endings", []))

    def _inflected_examples(self, example):
        """Generate suffix realizations, never a separate regex per sentence form."""
        from hangul import inflect
        annotation = example.get("inflection")
        if not annotation or not self.inflection_grammar:
            return []
        # A question keeps its speech act. Swapping in a declarative ending
        # would turn asking into asserting, so questions are realized only
        # through the endings the grammar declares as questions.
        asking = "query" in example["meaning"]
        endings = (self.inflection_grammar.get("question_endings") if asking
                   else self.inflection_grammar.get("parsing_endings"))
        if not endings:
            raise ValueError("question_inflection_requires_declared_question_endings"
                             if asking else "inflection_requires_declared_parsing_endings")
        args = {key: annotation[key] for key in ("stem", "tense", "ending", "kind")}
        canonical_forms = inflect(**args, grammar=self.inflection_grammar)
        slot_end = max((example["text"].index(value) + len(value) for value in example["slots"].values()), default=0)
        canonicals = [form["text"] for form in canonical_forms
                      if example["text"].endswith(form["text"])
                      and len(example["text"]) - len(form["text"]) >= slot_end]
        if len(canonicals) != 1:
            raise ValueError("inflection_annotation_does_not_match_literal_tail")
        canonical = canonicals[0]
        result = []
        for tense in annotation.get("tenses", [annotation["tense"]]):
            for ending in endings:
                for form in inflect(annotation["stem"], tense, ending, self.inflection_grammar,
                                    kind=annotation["kind"]):
                    if form["text"] != canonical:
                        result.append((form["text"], canonical, {
                            "id": self.inflection_grammar["id"], "stem": annotation["stem"],
                            "tense": tense, "ending": ending, "operations": form["operations"]}))
        return result

    def _rebuild_inflections(self):
        # A reverse suffix trie shares stems/endings across templates. The
        # existing compiled sentence templates remain one per annotation.
        self._inflection_trie = {}
        for index, example in enumerate(self.data["examples"]):
            forms = self._inflected_examples(example)
            for surface, canonical, trace in forms:
                node = self._inflection_trie
                for char in reversed(surface):
                    node = node.setdefault(char, {})
                node.setdefault(None, []).append((index, canonical, trace))

    def _inflected_boundary(self, word):
        node = self._inflection_trie
        for char in reversed(word):
            node = node.get(char)
            if node is None:
                return False
            if any(trace["ending"] in self.inflection_grammar.get("boundary_endings", [])
                   for _, _, trace in node.get(None, [])):
                return True
        return False

    def _clause_candidates(self, literal):
        from hangul import canonical_clauses
        yield from canonical_clauses(literal, self.clause_grammar)
        node = self._inflection_trie
        for length, char in enumerate(reversed(literal), 1):
            node = node.get(char)
            if node is None:
                break
            for index, canonical, trace in node.get(None, []):
                yield literal[:-length] + canonical, {**trace, "example_index": index}

    @staticmethod
    def compile(example, numerals=None, slot_particles=()):
        text, slots = example["text"], example["slots"]

        def after_slot(literal):
            """자리를 잡은 조사는 글자가 아니라 그 자리에 올 수 있는 무리다.

            예문이 `구슬은` 이라고 적었다고 `구슬이` 를 못 읽으면, 조사 하나마다
            예문을 새로 써야 한다. 무리 안에서만 바꾼다 — 자리가 바뀌면 뜻이 바뀐다.

            무리를 정규식 하나의 `(?:은|는|이|가)` 로 적으면 안 된다. 그러면 한
            문장에서 **첫 일치 하나만** 남아 `작은 지도는 큰 서랍에 있었다` 가
            `작` + `지도는 큰 서랍` 으로 굳는다. 조사인지 꾸밈말의 끝인지는 뒤가
            띄어져 있다는 것만으로 못 가른다. 그러니 무리마다 **따로 된 틀**을
            내주고, 어느 자름이 옳은지는 개체 증거가 정하게 한다.
            """
            group = particle_group(literal)
            if group is None:
                return [re.escape(literal)]
            for particle in group:
                rest = literal[len(particle):]
                if literal.startswith(particle) and not rest[:1].isalnum():
                    return [re.escape(alternative) + re.escape(rest) for alternative in group]
            return [re.escape(literal)]

        def particle_group(literal):
            """이 자리가 조사로 시작하면 그 무리를 준다."""
            for group in slot_particles:
                for particle in group:
                    rest = literal[len(particle):]
                    # 조사는 앞말에 붙고 뒤는 띄운다. 뒤에 글자가 이어지면 조사가
                    # 아니다 — `이다` 의 `이` 는 잡음씨지 주격 조사가 아니며, 그것을
                    # 조사로 읽으면 `모래를 넘지 않` 이 이름으로 잡힌다.
                    if literal.startswith(particle) and not rest[:1].isalnum():
                        return group
            return None

        def branch(variants, chunks):
            return [head + tail for head in variants for tail in chunks]

        spans = []
        for name, literal in slots.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or text.count(literal) != 1:
                raise ValueError("ambiguous_slot_annotation")
            start = text.index(literal)
            spans.append((start, start + len(literal), name))
        ordered = sorted(spans)
        spans_by_start = {end: nxt for (_s, end, _n), (nxt, _e, _n2)
                          in zip(ordered, ordered[1:])}
        variants, offset = [""], 0
        for start, end, name in ordered:
            if start < offset:
                raise ValueError("overlapping_slots")
            # Slot boundaries come from the annotated surrounding language,
            # not from a one-word restriction. Preserve multiword entity names.
            # Numeric examples still constrain their slot to decimal digits.
            slot_pattern = r"[^.!?,\n]+"
            if name in example.get("wide_slots", []):
                # 절을 여럿 담는 자리. 쉼표로 이어진 뜻풀이 몸통이 여기 들어간다.
                slot_pattern = r"[^.!?\n]+"
            if name in example.get("word_slots", []):
                # 이 자리는 한 낱말이다. 꼬리가 슬롯인 틀이 아무 문장이나 삼키는 것을
                # 막는다 — `...에게 (?P<verb>...)다` 가 `사과를 준다` 를 먹지 않게.
                slot_pattern = r"[^\s.!?,\n]+"
            if slots[name].isdecimal():
                chars = "".join(sorted({c for words in (numerals or {}).values() for word in words for c in word}))
                slot_pattern = (r"(?:\d+|[" + re.escape(chars) + r"]+(?:\s+[" + re.escape(chars) + r"]+)*)") if chars else r"\d+"
            literal = text[offset:start]
            variants = branch(variants, after_slot(literal) if offset else [re.escape(literal)])
            # 뒤따르는 조사가 이름 안에도 있을 수 있다. `작은 공책은 큰 서랍에` 의
            # `은` 은 꾸밈말에도 조사에도 있다. 짧게 잡기와 길게 잡기를 **둘 다**
            # 내주고, 어느 자름이 옳은지는 개체 증거가 고른다. 한쪽만 내주면
            # `작` 이 이름이 된다. 세 번 나오면 가운데는 아직 못 본다.
            following = text[end:spans_by_start.get(end, len(text))]
            reach = ["?", ""] if (not slots[name].isdecimal()
                                  and particle_group(following) is not None) else ["?"]
            variants = branch(variants, [f"(?P<{name}>{slot_pattern}{greedy})" for greedy in reach])
            if slots[name].isdecimal():
                variants = branch(variants, [r"\s*"])
            offset = end
        tail = text[offset:]
        variants = branch(variants, after_slot(tail) if offset else [re.escape(tail)])
        return [re.compile(variant) for variant in variants], example["meaning"]

    def learn(self, correction):
        """Return a new reusable template; do not change inference rules."""
        meaning = correction.get("meaning", {})
        triple = meaning.get("triple")
        slots = correction.get("slots", {})
        if (not set(meaning).issubset({"triple", "polarity", "modality"})
                or type(meaning.get("polarity", True)) is not bool
                or meaning.get("modality", "asserted") not in {"asserted", "planned", "conditional"}
                or not isinstance(triple, list) or len(triple) != 3
                or any(not isinstance(x, str) for x in triple)
                or len(slots) < 2 or any("$" + name not in triple for name in slots)
                or any(x.startswith("$") and x[1:] not in slots for x in triple)):
            raise ValueError("correction_requires_grounded_relation_slots")
        compiled = self.compile(correction, self.data.get("numerals", {}), self.slot_particles)
        inflections = self._inflected_examples(correction)
        if correction in self.data["examples"]:
            return False
        expected = substitute(meaning, slots)
        if any(prior != expected for prior in self._clause_meanings(correction["text"]).values()):
            raise ValueError("correction_conflicts_with_previous_template")
        for surface, canonical, _ in inflections:
            realized = correction["text"][:-len(canonical)] + surface
            if any(prior != expected for prior in self._clause_meanings(realized).values()):
                raise ValueError("correction_conflicts_with_previous_inflection")
        # Reject an interpretation that changes any previous supervised example.
        from hangul import canonical_clauses
        for prior in self.data["examples"]:
            for literal, normalization in canonical_clauses(prior["text"], self.clause_grammar):
                if normalization and any(correction.get(k) != v for k, v in
                                         normalization.get("example_features", {}).items()):
                    continue
                for pattern in compiled[0]:
                    match = pattern.fullmatch(literal)
                    if match and substitute(compiled[1], match.groupdict()) != substitute(prior["meaning"], prior["slots"]):
                        raise ValueError("correction_conflicts_with_previous_example")
        for patterns, meaning in self.templates:
            for pattern in patterns:
                match = pattern.fullmatch(correction["text"])
                if match and substitute(meaning, match.groupdict()) != substitute(correction["meaning"], correction["slots"]):
                    raise ValueError("correction_conflicts_with_previous_template")
        self.data["examples"].append(copy.deepcopy(correction))
        self.templates.append(compiled)
        self.induced_frames.clear()
        self.__dict__.pop("_조각틀", None)
        self._rebuild_inflections()
        return True

    def save(self, path):
        """Publish explicitly to a model file, without touching the seed corpus."""
        path = Path(path)
        root = Path(__file__).resolve().parent
        if any(folder in path.resolve().parents for folder in (root / "styles", root / "axioms")):
            raise ValueError("seed_corpus_is_read_only")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def learn_rule(self, corrections, validation):
        from rule_learning import propose
        report = propose(self.data, corrections, validation)
        if report["accepted"]:
            self.data["rules"].append(report["candidate"])
            self.data.setdefault("rule_learning_history", []).append(copy.deepcopy(report))
        return report

    def diagnose(self, text):
        diagnostics = []
        parsed = self.parse(text, _diagnostics=diagnostics)
        if parsed is None:
            return {"stage": "semantic_parse", "reason": "unrecognized_or_ambiguous_clauses",
                    "input": text, "answer": None, "diagnostics": diagnostics}
        try:
            result = self.answer(parsed)
        except ValueError as exc:
            return {"stage": "state_or_inference_precondition", "reason": str(exc),
                    "input": text, "answer": None, "facts": parsed["facts"], "query": parsed["query"]}
        if result is None:
            from graph_inference import bind, closure, current_facts, proof
            facts, _ = current_facts(parsed["facts"], self.data.get("mutable_predicates", []),
                                     self.data.get("numeric_updates", {}))
            known = closure(facts, self.data["rules"])
            candidates = [{"fact": list(fact), "query_index": index, "proof": proof(known, fact)}
                          for index, query in enumerate(parsed["query"]) for fact in known
                          if bind(query["triple"], fact, {}) is not None]
            return {"stage": "graph_inference", "reason": "nonunique_proof" if candidates else "missing_proof",
                    "input": text, "answer": None, "facts": parsed["facts"], "query": parsed["query"],
                    "candidates": candidates}
        return {"stage": "answered", "input": text, **result}

    def _clause_meanings(self, literal, *, derivations=None):
        from numeral_semantics import parse_numeral
        meanings, best_specificity = {}, -1
        for candidate, normalization in self._clause_candidates(literal):
            for index, ((patterns, meaning), example) in enumerate(zip(self.templates, self.data["examples"])):
                if normalization and "example_index" in normalization and index != normalization["example_index"]:
                    continue
                if (normalization and "example_index" not in normalization
                        and example.get("inflection") and self.inflection_grammar):
                    # A declared stem/class has a computed paradigm. A legacy
                    # suffix shortcut must not reintroduce invalid forms such
                    # as 한다 -> 한고 behind the morphology component's back.
                    continue
                if normalization and any(example.get(k) != v for k, v in
                                         normalization.get("example_features", {}).items()):
                    continue
                # A normalization made by this example's own declared paradigm
                # keeps the speech act — a question is realized only through
                # endings the grammar declares as questions. The legacy suffix
                # shortcut carries no such guarantee, so it still may not
                # rewrite the ending of a question.
                declared = normalization and "example_index" in normalization
                if normalization and not declared and "query" in meaning:
                    continue
                # Rewriting a tail that is itself a slot would edit the entity,
                # whatever produced the normalization.
                if normalization and any(example["text"].endswith(value)
                                         for value in example["slots"].values()):
                    continue
                for pattern in patterns:
                    match = pattern.fullmatch(candidate)
                    if not match:
                        continue
                    slots = match.groupdict()
                    # Do not absorb an unrecognized preceding clause into an entity
                    # slot just because the trailing predicate is understood.
                    if any(self._inflected_boundary(word) for value in slots.values()
                           for word in value.split()):
                        continue
                    for name, annotated in example["slots"].items():
                        if annotated.isdecimal():
                            slots[name] = parse_numeral(slots[name], self.data.get("numerals", {}))
                    if any(value is None for value in slots.values()):
                        continue
                    # Count the observed fixed surface, not letters manufactured by
                    # expansion to the canonical spelling. Different canonical
                    # forms of the same spoken ending must not win by their length.
                    # Measure the text this template actually pinned down, not the
                    # length of its regex source — a slot particle written as a
                    # class of particles is still one matched letter.
                    specificity = len(candidate) - sum(len(match.group(name) or "")
                                                       for name in example["slots"])
                    if normalization and "example_index" in normalization:
                        specificity += len(literal) - len(candidate)
                    if specificity > best_specificity:
                        meanings, best_specificity = {}, specificity
                        if derivations is not None:
                            derivations.clear()
                    if specificity == best_specificity:
                        grounded = substitute(meaning, slots)
                        key = json.dumps(grounded, sort_keys=True, ensure_ascii=False)
                        # Exact evidence is tried first; do not replace its proof
                        # with a later equivalent normalization.
                        if key not in meanings and derivations is not None:
                            derivations[key] = ({"rule": normalization["id"], "canonical": candidate}
                                                if normalization else None)
                            if normalization and "operations" in normalization:
                                derivations[key].update({k: normalization[k] for k in
                                                         ("stem", "tense", "ending", "operations")})
                        meanings[key] = grounded
        return meanings

    def parse(self, text, *, partial=False, events=False, verbs=None, _diagnostics=None):
        """``events`` 를 켜면 아무 사례도 못 읽은 구절을 **사건 꼴**로도 본다.

        조사가 자리를 짚고 남은 한 낱말이 움직임인 꼴이다. 뜻은 여기서 안
        정한다 — 쓰인 낱말을 그대로 담고, 설명받은 어간과 잇는 일은 대화
        쪽에서 한다. 이 문을 열지 않으면 뜻을 모르는 말을 만났을 때 **무엇을**
        모르는지 짚어 줄 수 없다.

        ``verbs`` 는 설명받은 말들의 꼴 → ``{어간, 물음}`` 이다. **무슨 동사인가
        만으로는 모자란다** — 물어본 것인지 실제로 일어난 일인지가 같이 와야
        `민수가 지연에게 베풉니까` 가 구슬을 옮기지 않는다.
        """
        from hangul import clause_spans
        facts, query = [], None
        # 뜻풀이와 그 뜻을 쓰는 사건. 낱말마다 예문을 더하는 것이 아니라,
        # **뜻풀이가 어떻게 생겼는지**를 한 번 선언해 두고 내용은 사용자가 채운다.
        defined, invoked = [], []
        clauses = []
        diagnostics = _diagnostics if _diagnostics is not None else []
        unrecognized = False
        # Only a fully recognized prefix authorizes a soft clause boundary.
        # A failed suffix guess (e.g. a noun ending in 고) never drops source text.
        cache, derivations = {}, {}
        def meanings(literal):
            if literal not in cache:
                derivations[literal] = {}
                cache[literal] = self._clause_meanings(literal, derivations=derivations[literal])
            return cache[literal]

        for evidence in clause_spans(text, self.clause_grammar, commas=True,
                                     accept_prefix=meanings, inflected_boundary=self._inflected_boundary):
            unique = meanings(evidence["text"])
            asking = any(text[evidence["end"]:].lstrip().startswith(mark)
                         for mark in self.clause_grammar.get("question_marks", []))
            if asking and any(asserted(meaning) or "invoke" in meaning
                              for meaning in unique.values()):
                diagnostics.append({"reason": "question_is_not_an_observation", "evidence": evidence})
                unrecognized = True
                continue
            # 물음표 검사가 사건 읽기보다 **먼저** 와야 한다. 나중에 오면
            # 새 경로로 들어온 물음을 놓쳐 물어본 일이 실제로 일어난다.
            if not unique and events and not asking:
                from frame_induction import asks, read_event
                if asks(evidence["text"], self.negation, verbs):
                    # 물음표가 없어도 묻는 말이다. 사건으로 읽으면 안 된다.
                    diagnostics.append({"reason": "question_is_not_an_observation",
                                        "evidence": evidence})
                    unrecognized = True
                    continue
                event = read_event(evidence["text"], self.case_particles,
                                   self.slot_particles, self.negation, verbs)
                if event is not None:
                    meaning = {"invoke": {"verb": event["verb"], "자리": event["자리"],
                                          "자리후보": event["자리후보"],
                                          "잘림": event["잘림"]}}
                    if event.get("polarity") is False:
                        meaning["polarity"] = False
                    clauses.append(([meaning], evidence))
                    continue
            if not unique:
                diagnostics.append({"reason": "unrecognized_clause", "evidence": evidence,
                                    "candidates": []})
                unrecognized = True
                continue
            clauses.append((list(unique.values()), evidence))
        if unrecognized:
            return None

        def entities(meaning):
            if "define" in meaning or "invoke" in meaning:
                return set()
            triples = asserted(meaning) or [joined(q["triple"]) for q in meaning.get("query", [])]
            return {triple[i] for triple in triples for i in (0, 2)
                    if isinstance(triple[i], str) and not triple[i].startswith(("?", "$"))
                    and not triple[i].isdecimal()}

        # Use only unambiguous clauses as anchors. An uncertain candidate must
        # not manufacture its own support or silently discard another clause.
        while any(len(options) > 1 for options, _ in clauses):
            anchors = set().union(*(entities(options[0]) for options, _ in clauses if len(options) == 1))
            changed = False
            for index, (options, evidence) in enumerate(clauses):
                if len(options) == 1:
                    continue
                scores = [len(entities(option) & anchors) for option in options]
                best = max(scores)
                winners = [option for option, score in zip(options, scores) if score == best]
                if best > 0 and len(winners) == 1:
                    clauses[index] = (winners, evidence)
                    changed = True
            if not changed:
                diagnostics.extend({"reason": "ambiguous_clause", "evidence": evidence,
                                    "candidates": options} for options, evidence in clauses if len(options) > 1)
                return None
        for options, evidence in clauses:
            meaning = options[0]
            key = json.dumps(meaning, sort_keys=True, ensure_ascii=False)
            normalization = derivations[evidence["text"]].get(key)
            if normalization:
                evidence = {**evidence, "normalization": normalization}
            stated = asserted(meaning)
            if stated:
                for triple in stated:
                    fact = {"triple": triple, "evidence": evidence}
                    if "scope" in meaning:
                        fact["scope"] = meaning["scope"]
                    for field in ("polarity", "modality"):
                        if field in meaning:
                            fact[field] = meaning[field]
                    facts.append(fact)
            elif "define" in meaning:
                defined.append({**meaning["define"], "evidence": evidence})
            elif "invoke" in meaning:
                invoked.append({**meaning["invoke"], "evidence": evidence,
                                **({"polarity": meaning["polarity"]} if "polarity" in meaning else {})})
            elif "query" in meaning and query is None:
                query = meaning["query"]
            else:
                diagnostics.append({"reason": "multiple_queries_or_invalid_meaning", "evidence": evidence})
                return None
        usable = bool(facts or query or defined or invoked) if partial else bool(
            (facts or defined or invoked) and query)
        if not usable:
            diagnostics.append({"reason": "missing_facts" if not facts else "missing_query"})
        return ({"facts": facts, "query": query, "정의": defined, "사건": invoked}
                if usable else None)

    def answer(self, parsed):
        from graph_inference import bind, closure, current_facts, proof
        facts, changes = current_facts(parsed["facts"], self.data.get("mutable_predicates", []),
                                       self.data.get("numeric_updates", {}))
        known = closure(facts, self.data["rules"])
        found = []
        for query in parsed["query"]:
            for fact in known:
                bindings = bind(query["triple"], fact, {})
                if bindings is not None:
                    result = substitute(query, {k[1:]: v for k, v in bindings.items()})
                    result["triple"] = list(fact)
                    found.append(result)
        if len(found) != 1:
            return None
        result = found[0]
        answer = ("".join(result["render"]) if "render" in result else
                  result["answer"] + self.data["answer_suffix"])
        return {"answer": answer,
                "transitions": changes + proof(known, result["triple"])}

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
    def __init__(self, data=None, model_path=None, *, language_pack=None, language=None):
        selected = model_path or (os.environ.get("NAI_RELATIONAL_MODEL") if data is None else None)
        self.model_path = Path(selected) if selected is not None else None
        if data is None:
            if self.model_path is not None:
                data = json.loads(self.model_path.read_text(encoding="utf-8"))
            else:
                from pack_model import development_model
                data = development_model(language).relational_data
        self.data = copy.deepcopy(data)
        if language_pack is None:
            from language_components import load_reasoning_language
            language_pack = load_reasoning_language(language)
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
        # 조건으로 읽어야 하는 맺음. 조건을 낱말로 알아보면 말마다 분기가 는다.
        self.condition_endings = list(self.inflection_grammar.get("condition_endings", []))
        # `만약`은 조건의 내용이 아니라 절 전체의 해석 방식을 여는 담화 표지다.
        # 언어팩이 선언한 표지만, 낱말 경계를 지킬 때만 후보 읽기에서 뺀다.
        self.hypothetical_prefixes = sorted(
            self.clause_grammar.get("hypothetical_prefixes", []), key=len, reverse=True)
        self.doer_particle = language_pack.get("doer_particle", "")
        # 자리말 가운데 **그 일을 한 쪽**. 절 순서가 아니라 이것이 임자 자리를 정한다.
        self.speaker_placeholder = language_pack.get("speaker_placeholder", "")
        # 주격으로 드러난 행위자와 대상이 수량 상태 하나를 가리키는 문법.
        # 어느 관계에 적용할지는 언어 팩이 선언한다.
        self.actor_targets = copy.deepcopy(language_pack.get("actor_targets", {}))
        # A stated count whose counted name begins with an owner the pack's
        # particles mark (`하루는 구슬이 18개 있다`): the owner is split off.
        self.possessor = copy.deepcopy(language_pack.get("possessor", {}))
        # 기준이 되는 양에서 계산해 나오는 양. `절반` 은 글자 그대로의 수가 아니다.
        self.quantities = dict(language_pack.get("quantities", {}))
        # 초기 수량에서 여러 변화를 잇고 남은 값을 묻는 표현. 대상·수·동작은
        # 고정하지 않고, 언어 팩이 선언한 구조와 관계만 읽는다.
        self.quantity_chain = copy.deepcopy(language_pack.get("quantity_chain", {}))
        self.event_domains = copy.deepcopy(language_pack.get("event_domains", []))
        # 말머리 군말. 지우는 규칙이 아니라 **읽기 후보**를 하나 더 두는 데 쓴다.
        self.fillers = copy.deepcopy(language_pack.get("fillers", {}))
        # 앞서 말한 것을 도로 가리키는 말. 자리말과 다르다 — 이쪽은 이 대화에서
        # 이미 나온 것을 가리킨다.
        self.pointers = list(language_pack.get("pointers", []))
        # 아직 안 일어난 일의 꼴. 사실이 아니라 **기록**으로만 남는다.
        self.plan = self._plan(language_pack.get("plan", {}))
        # 빈 자리를 사람 말로 되묻는 법. 짧은 답을 부르는 물음이다.
        self.slot_questions = dict(language_pack.get("slot_questions", {}))
        # 이름 하나로 답할 때 이름 뒤에 붙을 수 있는 말. **받아들일 꼴**의 목록이다.
        self.short_tails = list(language_pack.get("short_tails", []))
        # 뜻풀이와 어긋난 값이 **어디까지** 미치는지 묻고 받는 말. 셋뿐이다.
        self.scope_words = dict(language_pack.get("scope_words", {}))
        self.target_words = dict(language_pack.get("target_words", {}))
        # Ordinal surface forms for choosing one already enumerated
        # relationship occurrence.  The algorithm only maps an ordinal to a
        # bounded candidate list; each language supplies the words.
        self.relation_choice_words = copy.deepcopy(language_pack.get("relation_choice_words", {}))
        # 선언된 규칙 어디에도 안 맞는 절을 가장 가까운 규칙에 맞추는 편집들과
        # 그 비용·한도. 편집 종류는 닫힌 갈래이고, 무엇을 켜고 얼마로 치는지는
        # 언어 팩이 정한다. 선언이 없으면 고치지 않는다.
        self.repair = copy.deepcopy(language_pack.get("repair", {}))
        # 선언된 생략. 쉼표로 이은 마디의 뒷말 물려받기, 상태 대상의 앞말만으로
        # 그 대상을 가리키기. 선언이 없으면 아무것도 메우지 않는다.
        self.ellipsis = dict(language_pack.get("ellipsis", {}))
        # 다른 언어의 물음을 이 대화의 이름과 맞춰 볼 때 쓰는 선언: 글자 표기법과
        # 낱말 → 개념 ID. 번역기가 아니라 대조표다.
        self.romanization = copy.deepcopy(language_pack.get("romanization", {}))
        self.senses = dict(language_pack.get("senses", {}))
        # 받침에 따라 갈리는 조사 짝과 그 예외. 조사를 떼거나 옮길 때 그 꼴이
        # 앞말에 맞는지 본다 — `사과` 의 `과` 는 `사` 뒤에 올 조사 꼴이 아니다.
        self.particle_mates = dict(language_pack.get("particle_mates", {}))
        self.particle_exceptions = dict(language_pack.get("particle_exceptions", {}))
        # 받침 있는 이름 뒤에 붙는 부름 꼬리(`가람이는` 의 `이`). 뒤에 조사가 또
        # 붙으면 격조사가 아니다 — 조사는 겹쳐 쌓이지 않는다. 선언이 없으면 안 본다.
        self.name_suffix = str(language_pack.get("name_suffix", "") or "")
        # An item counted as one names the same things as its plural. The pack
        # declares the plural rule; a language without number declares none.
        self.noun_number = dict(language_pack.get("noun_number", {}) or {})
        # Counter nouns after a number (and after the declared question word).
        # Examples are written with the first one; every declared one reads alike.
        self.counters = dict(language_pack.get("counters", {}) or {})
        # Verbs the pack says take the frame of a verb it already has examples
        # for, and phrases it says read as another phrase. Both only add
        # candidate readings; the typed text still competes.
        self.same_frame = [dict(row) for row in language_pack.get("same_frame", []) or []]
        self.phrase_variants = [dict(row) for row in language_pack.get("phrase_variants", []) or []]
        self._variant_table = None
        self._repair_cache = {}
        self._ending_table = None
        self.language_pack = {"clauses": self.clause_grammar, "inflection": self.inflection_grammar,
                              "slot_particles": self.slot_particles,
                              "case_particles": self.case_particles,
                              "negation": copy.deepcopy(language_pack.get("negation", {})),
                              "placeholders": dict(self.placeholders),
                              "doer_particle": self.doer_particle,
                              "speaker_placeholder": self.speaker_placeholder,
                              "actor_targets": copy.deepcopy(self.actor_targets),
                              "possessor": copy.deepcopy(self.possessor),
                              "quantities": dict(self.quantities),
                              "quantity_chain": copy.deepcopy(self.quantity_chain),
                              "event_domains": copy.deepcopy(self.event_domains),
                              "fillers": copy.deepcopy(self.fillers),
                              "pointers": list(self.pointers),
                              "plan": copy.deepcopy(language_pack.get("plan", {})),
                              "slot_questions": dict(self.slot_questions),
                              "short_tails": list(self.short_tails),
                              "scope_words": dict(self.scope_words),
                              "target_words": dict(self.target_words),
                              "repair": copy.deepcopy(self.repair),
                              "particle_mates": dict(self.particle_mates),
                              "ellipsis": dict(self.ellipsis),
                              "romanization": copy.deepcopy(self.romanization),
                              "senses": dict(self.senses),
                              "particle_exceptions": dict(self.particle_exceptions),
                              "name_suffix": self.name_suffix,
                              "noun_number": dict(self.noun_number),
                              "counters": dict(self.counters),
                              "same_frame": [dict(row) for row in self.same_frame],
                              "phrase_variants": [dict(row) for row in self.phrase_variants]}
        # 몸통에서 꺼낸 틀은 예문이 그대로인 동안만 같다. `learn` 이 예문을
        # 늘리면 버린다 — 옛 사례로 읽은 몸통을 그대로 쓰면 안 된다.
        self.induced_frames = {}
        self.templates = []
        for example in self.data["examples"]:
            self.templates.append(self.compile(example, self.data.get("numerals", {}),
                                               self.slot_particles,
                                               ignore_case=bool(self.data.get("ignore_case")),
                                               counters=self.counters))
        # A learned event may form a clause boundary, except while that word
        # is still inside the body of a definition.  This delimiter comes from
        # the pack's definition examples; it is not a Korean string embedded
        # in the action parser.
        self.definition_body_delimiters = set()
        for example in self.data["examples"]:
            meaning, slots = example.get("meaning", {}), example.get("slots", {})
            definition = meaning.get("define") if isinstance(meaning, dict) else None
            verb, body = (definition or {}).get("verb"), (definition or {}).get("몸통")
            if not (isinstance(verb, str) and isinstance(body, str)
                    and verb.startswith("$") and body.startswith("$")
                    and verb[1:] in slots and body[1:] in slots):
                continue
            start = example["text"].find(str(slots[verb[1:]])) + len(str(slots[verb[1:]]))
            end = example["text"].find(str(slots[body[1:]]), start)
            delimiter = example["text"][start:end]
            if delimiter:
                self.definition_body_delimiters.add(delimiter)
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

    def _plan(self, declared):
        """계획을 나타내는 꼴. 동사 쪽 꼴은 활용이 계산한다.

        `베풀 예정이다` 의 `베풀` 은 매김꼴 미래다. 낱말을 적지 않고 꼴을 적으므로
        어떤 동사에도 선다.
        """
        if not declared or not self.inflection_grammar:
            return {}
        맺음 = [declared["이름"] + tail for tail in declared.get("맺음", [])]
        return {"맺음": set(맺음), "연결": declared["연결"]}

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
                # 언어가 모든 시제에 모든 맺음을 허용하는 것은 아니다. 예를 들어
                # 과거 관형 연결만 선언했다면 현재형을 억지로 만들지 않고, 선언된
                # 조합만 후보에 둔다.
                try:
                    realized = inflect(annotation["stem"], tense, ending,
                                       self.inflection_grammar, kind=annotation["kind"])
                except ValueError:
                    continue
                for form in realized:
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

    def _variants(self):
        """Surface form -> the form it reads as, from the pack's declarations.

        ``same_frame`` rows name stems whose every inflected form reads as the
        same tense/ending form of ``as`` (a declared stem), or as the single
        word ``read_as``. ``phrase_variants`` rows map a typed phrase to
        another (possibly empty) phrase. Forms are computed by the pack's own
        inflection grammar; nothing is guessed from the input.
        """
        if self._variant_table is not None:
            return self._variant_table
        from hangul import inflect
        grammar = self.inflection_grammar or {}
        table = {}
        for row in self.same_frame:
            kinds = [row["kind"]] if row.get("kind") else list(grammar.get("kinds", []))
            for stem in row.get("stems", []):
                for kind in kinds:
                    for tense in grammar.get("tenses", {}):
                        for ending in grammar.get("endings", {}):
                            try:
                                forms = [f["text"] for f in inflect(stem, tense, ending, grammar, kind=kind)]
                                targets = ([row["read_as"]] if row.get("read_as") else
                                           [f["text"] for f in inflect(row["as"], tense, ending, grammar, kind=kind)])
                            except (ValueError, KeyError):
                                continue
                            if not targets:
                                continue
                            for form in forms:
                                if form and form != targets[0]:
                                    table.setdefault(form, (targets[0], {"id": "declared-same-frame-v1",
                                                                         "stem": stem, "as": row.get("as") or row.get("read_as"),
                                                                         "tense": tense, "ending": ending}))
        for row in self.phrase_variants:
            source, target = row.get("from"), row.get("to", "")
            if isinstance(source, str) and source and isinstance(target, str):
                table.setdefault(source, (target, {"id": "declared-phrase-variant-v1", "from": source, "to": target}))
        self._variant_table = table
        return table

    def _variant_patterns(self):
        """The declared variants, longest first, each compiled once per parser."""
        if getattr(self, "_variant_compiled", None) is None:
            table = self._variants()
            flags = re.IGNORECASE if self.data.get("ignore_case") else 0
            compiled = []
            for source in sorted(table, key=len, reverse=True):
                target, note = table[source]
                # A variant is a whole word or phrase: bounded by the text
                # edge, a space or punctuation on each side that is a word
                # character ("'s got" is bounded on its right only).
                left = "" if not source[:1].isalnum() else r"(?<![\w])"
                right = "" if not source[-1:].isalnum() else r"(?![\w])"
                compiled.append((source.lower() if flags else source, target, note,
                                 re.compile(left + re.escape(source) + right, flags)))
            self._variant_compiled = compiled
        return self._variant_compiled

    def _variant_literals(self, literal):
        """``literal`` with every declared variant replaced, one reading per step."""
        patterns = self._variant_patterns()
        if not patterns:
            return []
        folded = literal.lower() if self.data.get("ignore_case") else literal
        current, notes = literal, []
        for source, target, note, pattern in patterns:
            if source not in folded:
                continue
            replaced = pattern.sub(target, current)
            if replaced != current:
                current = re.sub(r"\s+", " ", replaced).strip()
                folded = current.lower() if self.data.get("ignore_case") else current
                notes.append(note)
        return [(current, notes)] if notes and current and current != literal else []

    def _clause_candidates(self, literal):
        yield from self._clause_candidates_of(literal)
        for replaced, notes in self._variant_literals(literal):
            for candidate, normalization in self._clause_candidates_of(replaced):
                base = normalization or {"id": notes[0]["id"], "canonical": candidate, "words_only": True}
                yield candidate, {**base, "variants": notes}

    def _clause_candidates_of(self, literal):
        from hangul import canonical_clauses
        yield from canonical_clauses(literal, self.clause_grammar)
        node = self._inflection_trie
        for length, char in enumerate(reversed(literal), 1):
            node = node.get(char)
            if node is None:
                break
            for index, canonical, trace in node.get(None, []):
                yield literal[:-length] + canonical, {**trace, "example_index": index}
        # 부정은 별도 동사 사례가 아니다. 언어팩이 계산한 `않다` 꼴을 걷어 내고,
        # 이미 선언된 어간의 마침꼴만 다시 만든다. 따라서 어떤 새 동사나 문장을
        # 긍정 사건으로 추측하지 않으며, 아래에서 polarity=False가 보존된다.
        forms = self.negation.get("forms", set())
        connector = self.negation.get("연결", "")
        for negative in forms:
            marker = " " + negative
            if not connector or not literal.endswith(marker):
                continue
            before = literal[:-len(marker)]
            if not before.endswith(connector):
                continue
            root = before[:-len(connector)]
            for index, example in enumerate(self.data["examples"]):
                annotation = example.get("inflection")
                if not annotation or not root.endswith(annotation["stem"]):
                    continue
                stem_prefix = root[:-len(annotation["stem"])]
                for tense in annotation.get("tenses", [annotation["tense"]]):
                    for ending in self.inflection_grammar.get("parsing_endings", []):
                        try:
                            realized = self._inflected_forms(annotation["stem"], tense, ending,
                                                             annotation["kind"])
                        except ValueError:
                            continue
                        for form in realized:
                            candidate = stem_prefix + form
                            yield candidate, {"id": "declared-negation-v1",
                                              "canonical": candidate, "example_index": index,
                                              "polarity": False}

    def _repair(self, literal):
        """No declared rule reads ``literal``: find the nearest one at a measured cost.

        Repair is matching at a distance, not guessing. Every edit either moves,
        drops or reorders what was typed, or adds a particle/ending the pack
        declares; nothing else can enter the reading. The edit kinds and their
        costs, the accepting bound and the reporting bound all come from the
        language pack. Returns ``(meanings, derivations, report)``: meanings are
        empty when nothing fits within the bound, and ``report`` then says what
        the nearest reading would have needed.
        """
        spec = self.repair
        costs = spec.get("costs", {})
        if not costs or not literal.strip():
            return {}, {}, None
        cached = self._repair_cache.get(literal)
        if cached is not None:
            return copy.deepcopy(cached)
        import heapq
        from itertools import count
        bound, reach, budget = spec["bound"], spec["report_bound"], spec["budget"]
        particles = sorted({p for p in self.case_particles} |
                           {p for group in self.slot_particles for p in group}, key=len, reverse=True)
        insertable = spec.get("insert_particles", [])
        # 이름 자리에 들어갈 수 없는 닫힌 갈래의 말(정도·때 부사 등). 수선이 이런
        # 말을 이름에 붙여 `민수 사과 정말` 같은 대상을 만들지 못하게 한다.
        outside = {word.lower() for word in spec.get("not_in_names", [])}
        endings = self._declared_endings()

        def tail_particle(word):
            return [p for p in particles if len(word) > len(p) and word.endswith(p)
                    and self._particle_form(word[:-len(p)], p) == p]

        # 친 말에서 `이름+꼬리+조사` 로 나온 낱말의 `이름+꼬리` 는 조사 붙은 말이 아니다.
        named = self._suffixed_names(literal.split(), tail_particle)

        def marked_word(word):
            return [] if word in named else tail_particle(word)

        def neighbours(words):
            n = len(words)
            for i, word in enumerate(words):
                for p in tail_particle(word):
                    bare = word[:-len(p)]
                    if "particle_drop" in costs:
                        yield (words[:i] + (bare,) + words[i + 1:],
                               {"op": "particle_drop", "word": word, "particle": p})
                    if "particle_move" in costs:
                        for j, other in enumerate(words):
                            if j != i and not tail_particle(other) and not self._is_verb_form(other):
                                moved = list(words)
                                fitted = self._particle_form(other, p)
                                moved[i], moved[j] = bare, other + fitted
                                yield (tuple(moved), {"op": "particle_move", "word": word,
                                                      "particle": p, "to": other,
                                                      **({"as": fitted} if fitted != p else {})})
                if "particle_insert" in costs and not tail_particle(word) and not self._is_verb_form(word):
                    for p in insertable:
                        fitted = self._particle_form(word, p)
                        yield (words[:i] + (word + fitted,) + words[i + 1:],
                               {"op": "particle_insert", "word": word, "particle": fitted})
                if "token_skip" in costs and n > 1:
                    yield (words[:i] + words[i + 1:], {"op": "token_skip", "word": word})
                if "adjacent_swap" in costs and i + 1 < n:
                    yield (words[:i] + (words[i + 1], word) + words[i + 2:],
                           {"op": "adjacent_swap", "word": word, "to": words[i + 1]})
            if "ending_restore" in costs and words:
                for form in endings.get(words[-1], ()):
                    yield (words[:-1] + (form,), {"op": "ending_restore", "word": words[-1], "to": form})

        start = tuple(literal.split())
        ticket = count()
        frontier = [(0, next(ticket), start, ())]
        seen = {start: 0}
        found, found_cost, expanded = [], None, 0
        while frontier:
            cost, _t, words, path = heapq.heappop(frontier)
            if found_cost is not None and cost > found_cost:
                break
            if cost > reach:
                break
            if path:
                derivations, matched = {}, {}
                candidate = " ".join(words)
                readings = self._clause_meanings(candidate, derivations=derivations, matched=matched)
                # A repaired reading must place every marked word in its own
                # role. A name that swallows a word carrying an agreeing
                # particle (``민수는 사과``) is the misreading repair exists to
                # avoid, so it is not a reading at any cost.
                readings = {key: meaning for key, meaning in readings.items()
                            if not self._swallows_marked_word(meaning, marked_word)
                            and not self._names_hold(meaning, outside)}
                if readings:
                    found_cost = cost
                    found.append((candidate, path, readings, derivations, matched))
                    continue
            expanded += 1
            if expanded > budget:
                break
            for following, step in neighbours(words):
                total = cost + costs[step["op"]]
                if total <= reach and total < seen.get(following, total + 1):
                    seen[following] = total
                    heapq.heappush(frontier, (total, next(ticket), following, path + (step,)))
        if not found:
            report = {"status": "unplaced", "source": literal, "bound": bound,
                      "cost": None, "searched_cost": reach, "rule": None, "operations": []}
            self._repair_cache[literal] = ({}, {}, report)
            return {}, {}, copy.deepcopy(report)
        distinct = {}
        for candidate, path, readings, derivations, matched in found:
            for key, meaning in readings.items():
                distinct.setdefault(key, (candidate, path, meaning, derivations.get(key), matched.get(key)))
        candidate, path, meaning, inner, index = next(iter(distinct.values()))
        rule = self.data["examples"][index]["text"] if index is not None else None
        report = {"source": literal, "reading": candidate, "operations": [dict(step) for step in path],
                  "cost": found_cost, "bound": bound, "rule": rule, "rule_index": index}
        if found_cost > bound:
            report["status"] = "over_bound"
            result = ({}, {}, report)
        elif len(distinct) > 1:
            report["status"] = "ambiguous"
            report["readings"] = [value[0] for value in distinct.values()]
            result = ({}, {}, report)
        else:
            report["status"] = "repaired"
            key = next(iter(distinct))
            derivation = {"rule": "declared-repair-v1", "canonical": candidate, "repair": report}
            for field in ("stem", "tense", "ending", "operations"):
                if inner and field in inner:
                    derivation[field] = inner[field]
            result = ({key: meaning}, {key: derivation}, report)
        self._repair_cache[literal] = result
        return copy.deepcopy(result)

    def _number_agreement(self, slots, example):
        """Key a thing counted as one by its declared plural (``one apple`` -> ``apples``)."""
        declared = self.noun_number
        if not declared or "item" not in slots or not slots.get("item"):
            return slots
        one = str(declared.get("count_slot_value", 1))
        counts = [name for name, annotated in example["slots"].items() if annotated.isdecimal()]
        if not counts or any(str(slots.get(name)) != one for name in counts):
            return slots
        words = slots["item"].split()
        last = words[-1]
        for row in declared.get("plural", []):
            after = [tail for tail in row.get("after", []) if last.lower().endswith(tail)]
            if not after:
                continue
            stem = last[:len(last) - int(row.get("drop", 0))] if row.get("drop") else last
            words[-1] = stem + row.get("append", "")
            return {**slots, "item": " ".join(words)}
        return slots

    def _suffixed_names(self, words, tail_particle):
        """Words typed as ``base + suffix + particle`` whose ``base`` ends in a coda.

        The pack declares the suffix. Case particles do not stack, so the suffix
        in front of a particle is part of the name, not a second marker.
        """
        from hangul import batchim
        suffix, found = self.name_suffix, set()
        if not suffix:
            return found
        for word in words:
            for particle in tail_particle(word):
                base = word[:-len(particle)]
                if (base.endswith(suffix) and len(base) > len(suffix)
                        and batchim(base[:-len(suffix)])):
                    found.add(base)
        return found

    @staticmethod
    def _inherit_trailing(rows, previous):
        """``[지연] count 2`` after ``[민수 사과] count 5`` -> ``[지연 사과] count 2``."""
        rewritten, inherited = [], []
        for row in rows:
            subject = row[0]
            match = next((prior for prior in previous if prior[1] == row[1]
                          and isinstance(prior[0], str) and isinstance(subject, str)), None)
            if match is None:
                rewritten.append(row)
                continue
            words, before = subject.split(), match[0].split()
            if len(words) >= len(before) or words == before[:len(words)]:
                rewritten.append(row)
                continue
            carried = before[len(words):]
            rewritten.append([" ".join(words + carried)] + list(row[1:]))
            inherited.append({"subject": subject, "inherited": " ".join(carried),
                              "from": match[0]})
        return rewritten, inherited

    @staticmethod
    def _names_hold(meaning, outside):
        if not outside:
            return False
        rows = asserted(meaning) or [joined(q["triple"]) for q in meaning.get("query", [])
                                     if isinstance(q, dict) and isinstance(q.get("triple"), list)]
        return any(isinstance(value, str) and any(word.lower() in outside for word in value.split())
                   for row in rows for value in (row[0], row[2]))

    @staticmethod
    def _swallows_marked_word(meaning, tail_particle):
        values = []

        def walk(value):
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)
        walk(meaning)
        return any(tail_particle(word) for value in values
                   for word in value.split()[:-1])

    def _is_verb_form(self, word):
        """A declared verb realized with an ending (`있었는데`). A particle never attaches to it."""
        node = self._inflection_trie
        for char in reversed(word):
            node = node.get(char)
            if node is None:
                return False
        return bool(node.get(None))

    def _particle_form(self, stem, particle):
        """The form of ``particle`` the pack's mate table selects after ``stem``."""
        from hangul import batchim
        mates = self.particle_mates.get(particle)
        if not mates or len(mates) != 2:
            return particle
        coda = batchim(stem)
        if coda is None:
            return particle
        closed, open_ = mates
        exception = self.particle_exceptions.get(closed, {})
        if coda and coda in exception.get("받침예외", []):
            return exception.get("쓸것", open_)
        return closed if coda else open_

    def render_changes(self, changes):
        """State changes in the pack's words: ``민수 사과 5개 → 3개``.

        Only changes with a declared shape are said; an undeclared operation
        or predicate is left out rather than printed as an internal name.
        """
        shapes = self.data.get("change_render", {})
        spoken = []
        for change in changes:
            shape = shapes.get(change.get("operation"))
            if isinstance(shape, dict):
                shape = shape.get(change.get("predicate"))
            if not isinstance(shape, str):
                continue
            spoken.append(shape.format(**{"대상": change.get("subject", ""),
                                          "전": change.get("before", ""),
                                          "후": change.get("after", "")}))
        return self.data.get("change_join", ", ").join(spoken)

    def repair_reports(self, text):
        """Reports already computed for clauses of ``text`` (no new search)."""
        return [copy.deepcopy(result[2]) for literal, result in self._repair_cache.items()
                if result[2] is not None and literal in text]

    def _declared_endings(self):
        """A bare declared stem -> the canonical forms its examples declare."""
        if self._ending_table is None:
            table = {}
            for example in self.data["examples"]:
                annotation = example.get("inflection")
                if not annotation or not self.inflection_grammar:
                    continue
                try:
                    forms = self._inflected_forms(annotation["stem"], annotation["tense"],
                                                  annotation["ending"], annotation["kind"])
                except ValueError:
                    continue
                for form in forms:
                    if form != annotation["stem"]:
                        table.setdefault(annotation["stem"], [])
                        if form not in table[annotation["stem"]]:
                            table[annotation["stem"]].append(form)
            self._ending_table = table
        return self._ending_table

    def render_repair(self, report, replies):
        """The pack's words for a repair report. Nothing here is language text."""
        names = self.repair.get("names", {})
        steps = []
        for step in report.get("operations", []):
            template = names.get(step["op"], step["op"])
            steps.append(template.format(**{"말": step.get("word", ""), "조사": step.get("particle", ""),
                                            "곳": step.get("to", "")}))
        joined = self.repair.get("join", ", ").join(steps)
        key = {"repaired": "repaired", "ambiguous": "repair_ambiguous",
               "over_bound": "repair_over_bound", "unplaced": "repair_unplaced"}[report["status"]]
        return replies[key].format(**{"규칙": report.get("rule") or "", "수선": joined,
                                      "읽음": report.get("reading", ""), "원문": report["source"],
                                      "비용": report.get("cost", ""), "한도": report["bound"],
                                      "목록": ", ".join('"%s"' % r for r in report.get("readings", []))})

    def _inflected_forms(self, stem, tense, ending, kind):
        from hangul import inflect
        return [form["text"] for form in inflect(stem, tense, ending,
                                                  self.inflection_grammar, kind=kind)]

    @staticmethod
    def compile(example, numerals=None, slot_particles=(), *, ignore_case=False, counters=None):
        text, slots = example["text"], example["slots"]
        units = [unit for unit in (counters or {}).get("units", []) if unit]
        askers = [word for word in (counters or {}).get("askers", []) if word]
        attach = sorted((p for p in (counters or {}).get("attach", []) if p), key=len, reverse=True)
        unit_class = "(?:%s)" % "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True)) if units else ""

        def counted_rest(rest):
            """Regex for what follows the canonical counter.

            The example's own particle reads as any form of its declared group
            (``개를`` / ``권을``); where the example has none, none is read -- a
            particle there is left to repair. Where the example goes straight on
            to a copula ending, the copula ``이`` that a consonant-final counter
            takes is optional (``개야`` / ``권이야``).
            """
            for particle in attach:
                if rest.startswith(particle) and not rest[len(particle):][:1].isalnum():
                    group = next((g for g in slot_particles if particle in g), [particle])
                    return ("(?:%s)" % "|".join(re.escape(p) for p in sorted(group, key=len, reverse=True))
                            + re.escape(rest[len(particle):]))
            if not rest or rest[0].isspace():
                return re.escape(rest)
            copula = attach[0] if attach else ""
            return ("(?:%s)?" % re.escape(copula) if copula else "") + re.escape(rest)

        def after_number(literal):
            """The literal right after a number: any declared counter reads like the first."""
            if units and literal.startswith(units[0]):
                return [unit_class + counted_rest(literal[len(units[0]):])]
            return None

        def with_askers(pieces):
            """``몇 개`` inside a fixed literal reads any declared counter too."""
            if not (units and askers):
                return pieces
            out = []
            for piece in pieces:
                for asker in askers:
                    marker = re.escape(asker + " " + units[0])
                    if marker in piece:
                        head, _sep, tail = piece.partition(marker)
                        unescaped = re.sub(r"\\(.)", r"\1", tail)
                        piece = head + re.escape(asker) + r"\s*" + unit_class + counted_rest(unescaped)
                out.append(piece)
            return out
        slot_forms = example.get("slot_forms", {})
        if (not isinstance(slot_forms, dict)
                or any(name not in slots or not isinstance(forms, list) or not forms
                       or not all(isinstance(form, str) and form for form in forms)
                       for name, forms in slot_forms.items())):
            raise ValueError("invalid_slot_forms")

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
        numeric_before = False
        for start, end, name in ordered:
            if start < offset:
                raise ValueError("overlapping_slots")
            # Slot boundaries come from the annotated surrounding language,
            # not from a one-word restriction. Preserve multiword entity names.
            # Numeric examples still constrain their slot to decimal digits.
            slot_pattern = r"[^.!?,\n]+"
            if name in slot_forms:
                # 하나의 뜻 자리는 언어 팩이 선언한 여러 표면형으로 나타날 수
                # 있다. 이 갈래는 값 자체가 아니라 조사·연결어미처럼 **경계만**
                # 바꾸며, 정규식은 팩의 문자열을 이스케이프해서 만든다. 그러므로
                # 새 원인 연결 꼴을 읽으려고 문장별 분기를 코드에 늘리지 않는다.
                slot_pattern = "(?:%s)" % "|".join(
                    re.escape(form) for form in sorted(slot_forms[name], key=len, reverse=True))
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
            pieces = (after_number(literal) if numeric_before else None) or (
                after_slot(literal) if offset else [re.escape(literal)])
            variants = branch(variants, with_askers(pieces))
            # 뒤따르는 조사가 이름 안에도 있을 수 있다. `작은 공책은 큰 서랍에` 의
            # `은` 은 꾸밈말에도 조사에도 있다. 짧게 잡기와 길게 잡기를 **둘 다**
            # 내주고, 어느 자름이 옳은지는 개체 증거가 고른다. 한쪽만 내주면
            # `작` 이 이름이 된다. 세 번 나오면 가운데는 아직 못 본다.
            following = text[end:spans_by_start.get(end, len(text))]
            # 표면형 후보는 경계 자체다. 비어 있으면 다음 넓은 자리가 그 연결말을
            # 삼켜 원인·결과가 갈라지므로 선택형으로 만들지 않는다.
            reach = ([""] if name in slot_forms else
                     ["?", ""] if (not slots[name].isdecimal()
                                    and particle_group(following) is not None) else ["?"])
            variants = branch(variants, [f"(?P<{name}>{slot_pattern}{greedy})" for greedy in reach])
            if slots[name].isdecimal():
                variants = branch(variants, [r"\s*"])
            numeric_before = slots[name].isdecimal()
            offset = end
        tail = text[offset:]
        pieces = (after_number(tail) if numeric_before else None) or (
            after_slot(tail) if offset else [re.escape(tail)])
        variants = branch(variants, with_askers(pieces))
        # 대소문자를 가르지 않는 글자를 쓰는 언어는 팩이 그렇게 선언한다.
        flags = re.IGNORECASE if ignore_case else 0
        return [re.compile(variant, flags) for variant in variants], example["meaning"]

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
        compiled = self.compile(correction, self.data.get("numerals", {}), self.slot_particles,
                                ignore_case=bool(self.data.get("ignore_case")), counters=self.counters)
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
        self._repair_cache.clear()
        self._ending_table = None
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

    def _inference_rules(self, facts):
        """Allow a host to select a validated rule view for this exact fact set.

        A selector is optional and receives the ordinary rule list.  It is
        deliberately consulted only at closure time; parsing, state replay,
        and proof-ledger reconstruction remain based on the original pack.
        """
        selector = getattr(self, "rule_selector", None)
        if selector is None:
            return self.data["rules"]
        selected = selector(facts, self.data["rules"])
        if not isinstance(selected, list):
            raise ValueError("invalid_rule_selector")
        return selected

    def _closure(self, facts):
        """Use an optional exact-input closure snapshot without caching answers."""
        from graph_inference import closure
        rules = self._inference_rules(facts)
        selector = getattr(self, "closure_selector", None)
        known = selector(facts, rules) if selector is not None else None
        if known is not None:
            return known
        recorder = getattr(self, "closure_recorder", None)
        metrics = {} if recorder is not None else None
        known = closure(facts, rules, metrics=metrics)
        if recorder is not None:
            recorder(facts, rules, known, metrics)
        return known

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
            from graph_inference import bind, current_facts, proof
            facts, _ = current_facts(parsed["facts"], self.data.get("mutable_predicates", []),
                                     self.data.get("numeric_updates", {}))
            known = self._closure(facts)
            candidates = [{"fact": list(fact), "query_index": index, "proof": proof(known, fact)}
                          for index, query in enumerate(parsed["query"]) for fact in known
                          if bind(query["triple"], fact, {}) is not None]
            return {"stage": "graph_inference", "reason": "nonunique_proof" if candidates else "missing_proof",
                    "input": text, "answer": None, "facts": parsed["facts"], "query": parsed["query"],
                    "candidates": candidates}
        return {"stage": "answered", "input": text, **result}

    def _clause_meanings(self, literal, *, derivations=None, matched=None):
        from numeral_semantics import parse_numeral
        chained = self._quantity_chain_meaning(literal)
        if chained is not None:
            return {json.dumps(chained, sort_keys=True, ensure_ascii=False): chained}
        meanings, best_rank = {}, None
        for candidate, normalization in self._clause_candidates(literal):
            for index, ((patterns, meaning), example) in enumerate(zip(self.templates, self.data["examples"])):
                if normalization and "example_index" in normalization and index != normalization["example_index"]:
                    continue
                if (normalization and "example_index" not in normalization
                        and not normalization.get("words_only")
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
                if (normalization and not declared and not normalization.get("words_only")
                        and "query" in meaning):
                    continue
                # Rewriting a tail that is itself a slot would edit the entity,
                # whatever produced the normalization.
                if (normalization and not normalization.get("words_only")
                        and any(example["text"].endswith(value) for value in example["slots"].values())):
                    continue
                for pattern in patterns:
                    match = pattern.fullmatch(candidate)
                    if not match:
                        continue
                    slots = match.groupdict()
                    # Do not absorb an unrecognized preceding clause into an entity
                    # slot just because the trailing predicate is understood.
                    # 고정된 인과 연결말 앞의 원인 자리는 서술어로 끝날 수 있다.
                    # 그 허용은 예문 일반화가 아니라 언어 팩의 명시 선언일 때만
                    # 열며, 나머지 넓은 자리가 못 읽은 절을 삼키는 일은 막는다.
                    if any(self._inflected_boundary(word) for name, value in slots.items()
                           if name not in example.get("allow_inflected_slots", [])
                           for word in value.split()):
                        continue
                    for name, annotated in example["slots"].items():
                        if annotated.isdecimal():
                            slots[name] = parse_numeral(slots[name], self.data.get("numerals", {}))
                    if any(value is None for value in slots.values()):
                        continue
                    slots = self._number_agreement(slots, example)
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
                    if normalization and normalization.get("variants"):
                        # A declared phrase read as declared is recognized text,
                        # not text a slot happened to swallow.
                        specificity += max(0, len(literal) - len(candidate))
                    # 조사가 있는 행위자 자리는 문장 전체를 삼키는 넓은 이름보다
                    # 첫 조사 경계의 이름을 우선할 수 있다. 어느 자리를 그렇게
                    # 고를지는 예문이 선언하며, 기본 틀·낱말·이름에는 적용하지
                    # 않는다. 따라서 공백이 든 이름도 살리고 `준호는 우산이`처럼
                    # 원인절까지 주어로 잡는 경쟁 읽기만 제거한다.
                    shortest = example.get("prefer_shortest_slots", [])
                    rank = (specificity, -sum(len(match.group(name) or "") for name in shortest))
                    if best_rank is None or rank > best_rank:
                        meanings, best_rank = {}, rank
                        if derivations is not None:
                            derivations.clear()
                        if matched is not None:
                            matched.clear()
                    if rank == best_rank:
                        grounded = self._join_actor_target(substitute(meaning, slots))
                        if normalization and normalization.get("polarity") is False:
                            grounded = {**grounded, "polarity": False}
                        key = json.dumps(grounded, sort_keys=True, ensure_ascii=False)
                        # Exact evidence is tried first; do not replace its proof
                        # with a later equivalent normalization.
                        if key not in meanings and derivations is not None:
                            derivations[key] = ({"rule": normalization["id"], "canonical": candidate}
                                                if normalization else None)
                            if normalization and "operations" in normalization:
                                derivations[key].update({k: normalization[k] for k in
                                                         ("stem", "tense", "ending", "operations")})
                        if matched is not None:
                            matched.setdefault(key, index)
                        meanings[key] = grounded
        return meanings

    def _join_actor_target(self, meaning):
        """주격 행위자와 수량 대상은 역할을 보존한 채 한 상태 대상을 가리킨다.

        사례 틀의 넓은 ``item`` 자리가 ``민수가 구슬``을 통째로 잡더라도,
        언어팩이 선언한 주격 조사와 수량 변화 관계가 함께 있을 때만
        ``민수 구슬``로 정규화한다. 다른 관계나 조사 없는 이름은 건드리지
        않는다. 따라서 문장별 이름·동사 예외가 아니다.
        """
        relations = set(self.actor_targets.get("relations", []))
        if not relations:
            return meaning
        joiner = self.actor_targets.get("joiner", " ")
        particles = next((group for group in self.slot_particles
                          if self.doer_particle in group), [self.doer_particle])

        def split_target(target):
            words = str(target).split()
            for index, word in enumerate(words[:-1]):
                particle = next((value for value in particles
                                 if value and word.endswith(value) and len(word) > len(value)), None)
                if particle is None:
                    continue
                actor_words = words[:index] + [word[:-len(particle)]]
                item_words = words[index + 1:]
                actor, item = " ".join(actor_words), " ".join(item_words)
                if actor and item:
                    return joiner.join((actor, item)), {"actor": actor, "item": item}
            return target, None

        out = copy.deepcopy(meaning)
        rows = out.get("triples") or ([out["triple"]] if "triple" in out else [])
        roles = []
        changed = False
        for row in rows:
            if not isinstance(row, list) or len(row) != 3 or row[1] not in relations:
                roles.append(None)
                continue
            target, bound = split_target(row[0])
            if bound is None:
                roles.append(None)
                continue
            row[0] = target
            roles.append(bound)
            changed = True
        if changed:
            out["role_bindings"] = roles
        return out

    def _owner_items(self, readings, literal, derivations, matched):
        """``[하루는 구슬] count 18`` -> ``[하루 구슬] count 18`` in a direct reading.

        A wide name slot of a stated count swallowed the owner together with
        its particle. The pack declares which relation and which particles
        mark an owner. Repaired readings never get here: repair already moves
        such a particle itself and rejects a name that swallows one.
        """
        relations = set((self.possessor or {}).get("relations", []))
        particles = (self.possessor or {}).get("particles", [])
        if not readings or not relations or not particles:
            return readings

        def split(name):
            words = name.split()
            for index, word in enumerate(words[:-1]):
                particle = next((p for p in particles if word.endswith(p) and len(word) > len(p)), None)
                if particle is not None:
                    return " ".join(words[:index] + [word[:-len(particle)]] + words[index + 1:])
            return name

        out = {}
        for key, meaning in readings.items():
            rows = meaning.get("triples") or ([meaning["triple"]] if "triple" in meaning else [])
            changed = copy.deepcopy(meaning)
            new_rows = changed.get("triples") or ([changed["triple"]] if "triple" in changed else [])
            touched = False
            for row, new in zip(rows, new_rows):
                if isinstance(row, list) and len(row) == 3 and row[1] in relations and isinstance(row[0], str):
                    joined_name = split(row[0])
                    if joined_name != row[0]:
                        new[0] = joined_name
                        touched = True
            if not touched:
                out[key] = meaning
                continue
            new_key = json.dumps(changed, sort_keys=True, ensure_ascii=False)
            out[new_key] = changed
            if key in derivations.get(literal, {}):
                derivations[literal][new_key] = derivations[literal][key]
            if key in matched.get(literal, {}):
                matched[literal][new_key] = matched[literal][key]
        return out

    def _quantity_chain_meaning(self, literal):
        """팩이 선언한 `시작 양 → 변화들 → 남은 양` 구조를 한 번에 읽는다.

        이 경로는 물건 이름·수치·동사 하나를 코드에 갖지 않는다. 단위, 시작
        연결, 변화 관계와 표면형은 언어 팩이 주고, 이곳은 순서와 수량 슬롯을
        검증해 공통 상태 전이로 만든다.
        """
        from numeral_semantics import parse_numeral
        spec = self.quantity_chain
        units, starts = spec.get("units", []), spec.get("from_markers", [])
        operations = spec.get("operations", [])
        if not (units and starts and operations):
            return None
        unit = "(?:%s)" % "|".join(re.escape(value) for value in sorted(units, key=len, reverse=True))
        start = "(?:%s)" % "|".join(re.escape(value) for value in sorted(starts, key=len, reverse=True))
        initial_patterns = [
            r"\s*(?P<item>.+?)\s+(?P<n>[^.!?,]+?)\s*" + unit + r"\s*" + start
            + r"\s+(?P<tail>.+?)\s*"
        ]
        for declared in spec.get("initial_forms", []):
            particles = "(?:%s)" % "|".join(
                re.escape(value) for value in sorted(declared["item_particles"], key=len, reverse=True))
            tails = "(?:%s)" % "|".join(
                re.escape(value) for value in sorted(declared["tails"], key=len, reverse=True))
            initial_patterns.append(
                r"\s*(?P<item>.+?)" + particles + r"\s+(?P<n>[^.!?,]+?)\s*" + unit
                + r"\s+" + tails + r"\s+(?P<tail>.+?)\s*")
        initial = next((match for pattern in initial_patterns
                        for match in [re.fullmatch(pattern, literal)] if match is not None), None)
        if initial is not None:
            item = initial.group("item").strip()
            amount = parse_numeral(initial.group("n"), self.data.get("numerals", {}))
            if not item or amount is None:
                return None
            forms = [(form, operation["predicate"])
                     for operation in operations for form in operation.get("forms", [])]
            form = "(?:%s)" % "|".join(re.escape(value) for value, _predicate in
                                         sorted(forms, key=lambda row: len(row[0]), reverse=True))
            particle = spec.get("object_particles", [])
            particle = ("(?:%s)?" % "|".join(re.escape(value) for value in
                                                sorted(particle, key=len, reverse=True)) if particle else "")
            step = re.compile(r"\s*(?P<n>[^.!?,]+?)\s*" + unit + r"\s*" + particle
                              + r"\s*(?P<form>" + form + r")(?:\s*|$)")
            tail, triples = initial.group("tail"), [[item, "count", amount]]
            while tail:
                matched = step.match(tail)
                if matched is None:
                    return None
                delta = parse_numeral(matched.group("n"), self.data.get("numerals", {}))
                predicate = next((relation for surface, relation in forms
                                  if surface == matched.group("form")), None)
                if delta is None or predicate is None:
                    return None
                triples.append([item, predicate, delta])
                tail = tail[matched.end():].strip()
                if not tail:
                    break
                joiner = next((value for value in sorted(spec.get("joiners", []), key=len, reverse=True)
                               if tail.startswith(value)), None)
                if joiner is None:
                    return None
                tail = tail[len(joiner):].strip()
                if not tail:
                    return None
            return {"triples": triples}

        prefixes, particles = spec.get("query_prefixes", []), spec.get("query_particles", [])
        query_forms, render = spec.get("query_forms", []), spec.get("query_render", [])
        if not (prefixes and particles and query_forms and render):
            return None
        prefix = "(?:%s)" % "|".join(re.escape(value) for value in sorted(prefixes, key=len, reverse=True))
        particle = "(?:%s)" % "|".join(re.escape(value) for value in sorted(particles, key=len, reverse=True))
        question = "(?:%s)" % "|".join(re.escape(value) for value in sorted(query_forms, key=len, reverse=True))
        asked = re.fullmatch(r"\s*" + prefix + r"\s+(?P<item>.+?)" + particle + r"\s*" + question + r"\s*",
                              literal)
        if asked is None or not asked.group("item").strip():
            return None
        return {"query": [{"triple": [asked.group("item").strip(), "count", "?n"],
                            "render": list(render)}]}

    def parse(self, text, *, partial=False, events=False, verbs=None, repair=False, _diagnostics=None):
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
        facts, query, 조건 = [], None, []
        # 인과는 `누구의 원인` 하나가 아니다. 같은 사람이 여러 일을 할 수
        # 있으므로, 원인과 결과 사건 표지를 한 기록으로 묶어야 이유 물음이
        # 엉뚱한 사건의 원인을 가져가지 않는다. 표면형과 사건 표지는 언어 팩의
        # 뜻풀이가 주고, 여기서는 그 선언을 같은 방식으로 결합만 한다.
        원인, 이유물음 = [], []
        # 뜻풀이와 그 뜻을 쓰는 사건. 낱말마다 예문을 더하는 것이 아니라,
        # **뜻풀이가 어떻게 생겼는지**를 한 번 선언해 두고 내용은 사용자가 채운다.
        defined, invoked = [], []
        # 규칙에 맞춰 고쳐 읽은 절. 답과 상태가 이 수선 위에 선다는 것을 남긴다.
        수선 = []
        사건정정 = []
        clauses = []
        diagnostics = _diagnostics if _diagnostics is not None else []
        unrecognized = False
        # Only a fully recognized prefix authorizes a soft clause boundary.
        # A failed suffix guess (e.g. a noun ending in 고) never drops source text.
        cache, derivations = {}, {}

        def without_hypothetical_prefix(literal):
            leading = literal[:len(literal) - len(literal.lstrip())]
            body = literal[len(leading):]
            for prefix in self.hypothetical_prefixes:
                if (body.startswith(prefix) and len(body) > len(prefix)
                        and body[len(prefix)].isspace()):
                    return leading + body[len(prefix):].lstrip(), prefix
            return literal, None

        matched_examples = {}

        def meanings(literal):
            if literal not in cache:
                derivations[literal] = {}
                matched_examples[literal] = {}
                candidate, _marker = without_hypothetical_prefix(literal)
                cache[literal] = self._clause_meanings(candidate, derivations=derivations[literal],
                                                       matched=matched_examples[literal])
            return cache[literal]

        def learned_event(literal):
            """Read a learned action even when it is the premise of a question.

            The hypothetical marker is a discourse declaration, not an action
            name.  The event keeps its normal role reading and carries a scope
            bit into the common action executor instead of becoming an actual
            observation merely because it has a familiar verb.
            """
            if not events:
                return None
            candidate, marker = without_hypothetical_prefix(literal)
            from frame_induction import read_event
            event = read_event(candidate, self.case_particles, self.slot_particles,
                               self.negation, verbs, self.plan, self.inflection_grammar)
            # Clause boundaries for an unknown verb would split a definition
            # body such as "... 주고, ... 주는 것이다" before induction gets
            # to read the whole body.  Only an already learned surface form is
            # evidence that this prefix is an independently executable event.
            known = event is not None and (event["verb"] in (verbs or {})
                                            or any((found.get("stem") if isinstance(found, dict) else found)
                                                   == event["verb"]
                                                   for found in (verbs or {}).values()))
            if event is not None and not known:
                return None
            if event is not None and marker and (verbs or {}).get(event["verb"], {}).get("조건"):
                event = {**event, "hypothetical": True}
            return event

        def complete_prefix(literal):
            if any(delimiter in literal for delimiter in self.definition_body_delimiters):
                # A definition body may itself contain a conditional or a
                # learned-action connective.  Do not let a broad ordinary
                # clause template split it before the definition template has
                # seen its complete body.
                return False
            if meanings(literal) or learned_event(literal) is not None:
                return True
            # A comma is a strong boundary: a conjunct that only a bounded
            # repair can place is still a complete clause. Weaker boundaries
            # (a connective ending) are never opened by repair.
            return bool(repair and self.repair and (literal + ",") in text and self._repair(literal)[0])

        for evidence in clause_spans(text, self.clause_grammar, commas=True,
                                     accept_prefix=complete_prefix,
                                     inflected_boundary=lambda word: (
                                         self._inflected_boundary(word)
                                         or bool((verbs or {}).get(word, {}).get("조건")))):
            # Plans are pack-declared, role-bound event records.  Read them
            # before broad ordinary templates can reinterpret the same text
            # as (for example) an ``isa`` assertion; a plan must remain a
            # non-executed event through correction and replay.
            planned = learned_event(evidence["text"])
            if planned is not None and planned.get("modality") == "planned":
                clauses.append(([{"invoke": {"verb": planned["verb"], "자리": planned["자리"],
                                            "자리후보": planned["자리후보"], "잘림": planned["잘림"]},
                                 "modality": "planned"}], evidence))
                continue
            unique = self._owner_items(meanings(evidence["text"]), evidence["text"],
                                       derivations, matched_examples)
            # 수선은 부르는 쪽이 청할 때만 한다. 파서 자체의 계약은 선언된 규칙에
            # 그대로 맞는 읽기뿐이다 — 대화가 수선을 청하고 그 사실을 보고한다.
            if not unique and repair and self.repair and learned_event(evidence["text"]) is None:
                repaired, repair_derivations, report = self._repair(evidence["text"])
                if repaired:
                    unique = repaired
                    derivations[evidence["text"]] = repair_derivations
                    수선.append(report)
            asking = any(text[evidence["end"]:].lstrip().startswith(mark)
                         for mark in self.clause_grammar.get("question_marks", []))
            if asking and any(asserted(meaning) or "invoke" in meaning
                              for meaning in unique.values()):
                diagnostics.append({"reason": "question_is_not_an_observation", "evidence": evidence})
                unrecognized = True
                continue
            # 물음표 검사가 사건 읽기보다 **먼저** 와야 한다. 나중에 오면
            # 새 경로로 들어온 물음을 놓쳐 물어본 일이 실제로 일어난다.
            # 사례 읽기가 **조사를 넘어 삼켰으면** 사건 읽기와 겨룬다. 넓은 틀은
            # 아무 말이나 한 이름으로 삼켜 맞기 때문에, 맞았다는 이유로 이기면
            # `민수가 지연에게 베풀 예정이다` 가 `민수 isa 지연에게 베풀 예정` 이 된다.
            if unique and events and not asking:
                from frame_induction import _marked
                # A generic relation can leave its subject unmarked while
                # swallowing only the object/recipient case marker.  Requiring
                # *every* generated field to be marked made a known planned
                # action such as ``하루가 공책을 옮길 예정이다`` become an
                # asserted ``isa`` fact.  One swallowed marker is enough to
                # compare the fully role-bound event; the event-side guard
                # below still rejects a reading that itself loses a marker.
                삼킴 = any(_marked(str(part), self.case_particles, self.slot_particles)
                           for meaning in unique.values()
                           for row in (asserted(meaning) or []) for part in row)
                # A pack-declared future plan is likewise unambiguous: its
                # action is recognized through the inflection grammar and it
                # carries typed roles, whereas the competing generic fact has
                # no modality.  Preserve it as a non-executed event even when
                # the broad template's captured value happens not to end in a
                # case marker.
                event = learned_event(evidence["text"])
                if 삼킴 or (event is not None and event.get("modality") == "planned"):
                    # 사건 읽기가 이기려면 **그쪽도 근거가 있어야** 한다 — 이 대화가
                    # 아는 말로 끝나고, 조사를 안 넘어야 한다. 그냥 이기게 두면
                    # `사과 상자는 책상에 있었다` 가 모르는 말 하나로 뒤집힌다.
                    아는말 = event is not None and (
                        event["verb"] in (verbs or {})
                        or any((found["stem"] if isinstance(found, dict) else found)
                               == event["verb"] for found in (verbs or {}).values()))
                    if 아는말 and not any(
                            _marked(value, self.case_particles, self.slot_particles)
                            for value in event["자리"].values()):
                        unique = {}
            if not unique and events and not asking:
                from frame_induction import asks, read_event
                if asks(evidence["text"], self.negation, verbs):
                    # 물음표가 없어도 묻는 말이다. 사건으로 읽으면 안 된다.
                    diagnostics.append({"reason": "question_is_not_an_observation",
                                        "evidence": evidence})
                    unrecognized = True
                    continue
                # At a finished sentence an unfamiliar action is still worth
                # recording as an unresolved event.  The known-only helper is
                # used for *boundaries* above, not for discarding this useful
                # diagnosis.
                candidate, marker = without_hypothetical_prefix(evidence["text"])
                event = read_event(candidate, self.case_particles, self.slot_particles,
                                   self.negation, verbs, self.plan, self.inflection_grammar)
                if event is not None and marker and (verbs or {}).get(event["verb"], {}).get("조건"):
                    event = {**event, "hypothetical": True}
                if event is not None:
                    meaning = {"invoke": {"verb": event["verb"], "자리": event["자리"],
                                          "자리후보": event["자리후보"],
                                          "잘림": event["잘림"]}}
                    if event.get("polarity") is False:
                        meaning["polarity"] = False
                    if event.get("modality"):
                        meaning["modality"] = event["modality"]
                    if event.get("hypothetical"):
                        meaning["hypothetical"] = True
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
            if "cause" in meaning:
                record = meaning["cause"]
                return {record["subject"]} if isinstance(record, dict) and isinstance(record.get("subject"), str) else set()
            if "reason_query" in meaning:
                request = meaning["reason_query"]
                return {request["subject"]} if isinstance(request, dict) and isinstance(request.get("subject"), str) else set()
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
        previous_rows, previous_end = [], None
        for options, evidence in clauses:
            meaning = options[0]
            key = json.dumps(meaning, sort_keys=True, ensure_ascii=False)
            normalization = derivations.get(evidence["text"], {}).get(key)
            if normalization:
                evidence = {**evidence, "normalization": normalization}
            stated = asserted(meaning)
            # 조건 맺음으로 읽힌 절은 **일어난 일이 아니다.** 사실로 적으면
            # `5개보다 많으면` 이 "많다" 는 단정이 되고, 뒤의 일도 그냥 일어난
            # 일이 된다. 어느 맺음이 조건인지는 문법이 선언한다 — 낱말이 아니다.
            if stated and (normalization or {}).get("ending") in self.condition_endings:
                _candidate, marker = without_hypothetical_prefix(evidence["text"])
                조건 += [{"triple": triple, "evidence": evidence, "kind": "guard",
                          "marker": marker}
                         for triple in stated]
                continue
            # 쉼표로 이은 둘째 마디가 앞 마디의 뒤쪽 말을 생략했으면 물려받는다.
            # 언어 팩이 이 생략을 선언했을 때만, 같은 관계끼리만 한다.
            between = text[previous_end:evidence["start"]].strip() if previous_end is not None else None
            # A declared connective joins two conjuncts just as a comma does:
            # "A has five marbles and B has two" leaves the item out the same
            # way "A has five marbles, and B has two" does.
            markers = self.clause_grammar.get("after_clause_markers", [])
            joined_by_comma = between is not None and (
                (between[:1] == "," and (between == "," or between[1:].strip() in markers))
                or between.lower() in {marker.lower() for marker in markers})
            if stated and joined_by_comma and self.ellipsis.get("coordination") == "trailing_words":
                stated, inherited = self._inherit_trailing(stated, previous_rows)
                if inherited:
                    evidence = {**evidence, "ellipsis": inherited}
            previous_rows, previous_end = (stated or []), evidence["end"]
            if stated:
                role_bindings = meaning.get("role_bindings", [])
                example_index = matched_examples.get(evidence["text"], {}).get(key)
                if example_index is None and (normalization or {}).get("repair"):
                    example_index = normalization["repair"].get("rule_index")
                event_verb = (self.data["examples"][example_index].get("event_verb")
                              if example_index is not None else None)
                for position, triple in enumerate(stated):
                    fact = {"triple": triple, "evidence": evidence}
                    if event_verb:
                        # 어순으로 역할을 짚는 언어는 동사 꼬리가 문장 끝에 없다.
                        # 예문이 그 사건의 동사 어간을 선언하면 사실에 남긴다.
                        fact["verb"] = event_verb
                    if meaning.get("elided") and self.ellipsis.get("part_reference"):
                        # 예문이 뒷말을 비워 둔 꼴이다. 앞말만으로 대상을 가리킨다.
                        fact["resolve"] = self.ellipsis["part_reference"]
                    if position < len(role_bindings) and role_bindings[position] is not None:
                        fact["roles"] = role_bindings[position]
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
                                **({"polarity": meaning["polarity"]} if "polarity" in meaning else {}),
                                **({"modality": meaning["modality"]} if "modality" in meaning else {}),
                                **({"hypothetical": True} if meaning.get("hypothetical") else {})})
            elif "cause" in meaning:
                record = meaning["cause"]
                if not (isinstance(record, dict)
                        and all(isinstance(record.get(key), str) and record[key]
                                for key in ("subject", "cause", "effect"))):
                    diagnostics.append({"reason": "invalid_cause_record", "evidence": evidence})
                    return None
                원인.append({**record, "evidence": evidence})
            elif "reason_query" in meaning:
                request = meaning["reason_query"]
                if not (isinstance(request, dict)
                        and all(isinstance(request.get(key), str) and request[key]
                                for key in ("subject", "effect"))):
                    diagnostics.append({"reason": "invalid_reason_query", "evidence": evidence})
                    return None
                이유물음.append({**request, "evidence": evidence})
            elif "relation_query" in meaning and query is None:
                # Relationship instances are event-created entities, not a
                # participant-pair subject.  Keep the query declarative in
                # the language pack; answer() performs the generic binary
                # joins over its participant indexes and status property.
                request = copy.deepcopy(meaning["relation_query"])
                if not (isinstance(request, dict)
                        and all(isinstance(request.get(key), str) and request[key]
                                for key in ("kind", "actor", "other", "predicate"))):
                    diagnostics.append({"reason": "invalid_relation_query", "evidence": evidence})
                    return None
                query = [{"relation_query": request}]
            elif "concept_query" in meaning and query is None:
                request = copy.deepcopy(meaning["concept_query"])
                if not (isinstance(request, dict)
                        and all(isinstance(request.get(key), str) and request[key]
                                for key in ("actor", "other", "action"))):
                    diagnostics.append({"reason": "invalid_concept_query", "evidence": evidence})
                    return None
                query = [{"concept_query": request}]
            elif "event_relation_query" in meaning and query is None:
                request = copy.deepcopy(meaning["event_relation_query"])
                if not (isinstance(request, dict)
                        and all(isinstance(request.get(key), str) and request[key]
                                for key in ("action", "predicate", "value"))
                        and isinstance(request.get("roles"), dict)
                        and all(isinstance(key, str) and isinstance(value, str) and value
                                for key, value in request["roles"].items())
                        and isinstance(request.get("render"), list)):
                    diagnostics.append({"reason": "invalid_event_relation_query", "evidence": evidence})
                    return None
                query = [{"event_relation_query": request}]
            elif "event_correction" in meaning:
                # 앞서 말한 사건 하나의 값을 고친다는 말. 새 사건이 아니다.
                request = copy.deepcopy(meaning["event_correction"])
                if not (isinstance(request, dict)
                        and all(isinstance(request.get(key), str) and request[key]
                                for key in ("verb", "old", "new"))):
                    diagnostics.append({"reason": "invalid_event_correction", "evidence": evidence})
                    return None
                사건정정.append({**request, "evidence": evidence})
            elif "why_last" in meaning and query is None:
                query = [{"why_last": True}]
            elif "other_than" in meaning and query is None:
                request = copy.deepcopy(meaning["other_than"])
                if not (isinstance(request, dict) and isinstance(request.get("excluded"), str)
                        and request["excluded"]):
                    diagnostics.append({"reason": "invalid_other_than", "evidence": evidence})
                    return None
                query = [{"other_than": request}]
            elif "concept_reason_query" in meaning and query is None:
                query = [{"concept_reason_query": True}]
            elif "query" in meaning and query is None:
                # Query patterns use the same relation-identity representation
                # as asserted facts.  A pack may compose a subject from typed
                # roles (for example, actor + relation + participant); join
                # it before binding so current-state lookup and provenance see
                # one identical triple on both sides.
                query = copy.deepcopy(meaning["query"])
                if isinstance(query, list):
                    for request in query:
                        if isinstance(request, dict) and isinstance(request.get("triple"), list):
                            request["triple"] = joined(request["triple"])
            else:
                diagnostics.append({"reason": "multiple_queries_or_invalid_meaning", "evidence": evidence})
                return None
        usable = bool(facts or query or defined or invoked or 조건 or 원인 or 이유물음 or 사건정정) if partial else bool(
            ((facts or defined or invoked) and query) or (원인 and 이유물음))
        if not usable:
            diagnostics.append({"reason": "missing_facts" if not facts else "missing_query"})
        # 조건절이 전부 상태 변화이고 그 뒤가 물음이면, 이는 실제 사건 기록이 아니라
        # 그 변화만 임시로 놓고 묻는 가정이다. 비교 조건+뒤 사건은 기존의 실제
        # 조건 실행으로 남긴다. 동사 이름이 아니라 공리의 상태 변화 선언으로 가른다.
        updates = self.data.get("numeric_updates", {})
        가정 = ([{**item, "kind": "hypothesis"} for item in 조건]
                if query is not None and 조건
                and all(item["triple"][1] in updates for item in 조건) else [])
        가정사건 = [event for event in invoked if event.get("hypothetical")]
        return ({"facts": facts, "query": query, "정의": defined,
                 "사건": [event for event in invoked if not event.get("hypothetical")],
                 "가정사건": 가정사건,
                 "조건": 조건, "가정": 가정, "원인": 원인, "이유물음": 이유물음,
                 "수선": 수선, "사건정정": 사건정정}
                if usable else None)

    def answer(self, parsed):
        from graph_inference import bind, current_facts, proof
        # 이유는 주어만 맞춰 답하지 않는다. 결과 사건 표지까지 같은 기록에서
        # 맞춰야 하며, 후보가 둘이면 하나를 고르지 않는다. 이 경로는 `cause`와
        # `reason_query`라는 팩 선언을 쓰므로 특정 원인·동사·문장에 의존하지 않는다.
        reason_queries = parsed.get("이유물음", [])
        if reason_queries:
            if len(reason_queries) != 1:
                return None
            request = reason_queries[0]
            candidates = [record for record in parsed.get("원인", [])
                          if (record["subject"], record["effect"])
                          == (request["subject"], request["effect"])]
            distinct = {(record["cause"], tuple(record.get("render", []))): record
                        for record in candidates}
            if len(distinct) != 1:
                return None
            record = next(iter(distinct.values()))
            render = record.get("render", ["$cause"])
            if not isinstance(render, list) or not all(isinstance(part, str) for part in render):
                return None
            answer = "".join(
                re.sub(r"\$([a-z][a-z0-9_]*)",
                       lambda matched: str(record.get(matched.group(1), matched.group(0))), part)
                for part in render)
            return {"answer": answer,
                    "transitions": [{"operation": "cause_for_effect",
                                     "fact": [record["subject"], "cause", record["cause"]],
                                     "effect": record["effect"],
                                     "evidence": record["evidence"]}]}
        facts, changes = current_facts(parsed["facts"], self.data.get("mutable_predicates", []),
                                       self.data.get("numeric_updates", {}))
        relation_queries = [query.get("relation_query") for query in parsed["query"]
                            if isinstance(query, dict) and isinstance(query.get("relation_query"), dict)]
        if relation_queries:
            # A relation occurrence is represented by four ordinary binary
            # facts: kind, actor, other and mutable status.  This join is
            # shared by every pack-declared relationship; no promise/person
            # special case is embedded here.
            if len(relation_queries) != 1 or len(parsed["query"]) != 1:
                return None
            request = relation_queries[0]
            fields, evidence = {}, {}
            for row in facts:
                triple = row.get("triple") or []
                if len(triple) != 3:
                    continue
                fields.setdefault(triple[0], {})[triple[1]] = triple[2]
                evidence[(triple[0], triple[1])] = row.get("evidence") or {}
            matches = [relation for relation, values in fields.items()
                       if values.get("relation_kind") == request["kind"]
                       and values.get("relation_actor") == request["actor"]
                       and values.get("relation_other") == request["other"]
                       and request["predicate"] in values]
            if len(matches) != 1:
                return None
            relation = matches[0]
            status = fields[relation][request["predicate"]]
            render = request.get("render")
            answer = ("".join(part.replace("$status", str(status)) for part in render)
                      if isinstance(render, list) and all(isinstance(part, str) for part in render)
                      else str(status) + self.data["answer_suffix"])
            return {"answer": answer,
                    "transitions": changes + [{"operation": "relation_lookup",
                                                 "relation": relation,
                                                 "kind": request["kind"],
                                                 "actor": request["actor"],
                                                 "other": request["other"],
                                                 "status": status,
                                                 "evidence": evidence.get((relation, request["predicate"]), {})}]}
        known = self._closure(facts)
        queries = parsed["query"]
        if self.ellipsis.get("part_reference") == "leading_words":
            # `지연은 몇 개야` 의 `지연` 이 그대로는 상태 대상이 아니면, 그 앞말로
            # 시작하는 대상이 하나일 때만 그것을 묻는 것으로 읽는다.
            from graph_inference import leading_word_referent
            present = {(fact[0], fact[1]) for fact in known}
            queries = []
            for query in parsed["query"]:
                triple = query.get("triple") if isinstance(query, dict) else None
                if (isinstance(triple, list) and len(triple) == 3 and isinstance(triple[0], str)
                        and not triple[0].startswith(("?", "$")) and (triple[0], triple[1]) not in present):
                    referent = leading_word_referent(triple[0], triple[1], dict.fromkeys(present))
                    if referent != triple[0]:
                        query = {**query, "triple": [referent] + triple[1:], "resolved_from": triple[0]}
                queries.append(query)
        found = []
        for query in queries:
            for fact in known:
                bindings = bind(query["triple"], fact, {})
                if bindings is not None:
                    result = substitute(query, {k[1:]: v for k, v in bindings.items()})
                    result["triple"] = list(fact)
                    found.append(result)
        if len(found) != 1:
            # `이 근거만으로 분류라고 할 수 있는가`처럼, 정방향 증명은 찾되
            # 그 역방향을 새 규칙으로 만들지 않는 질의가 있다. 이 경우에만
            # 팩이 선언한 보류 문구를 돌려 준다. 일반 사실 물음의 미증명은
            # 여전히 답을 만들지 않는다.
            unknown = [query.get("unknown") for query in queries
                       if isinstance(query.get("unknown"), str) and query["unknown"]]
            if not found and len(unknown) == 1:
                return {"answer": unknown[0], "transitions": []}
            return None
        result = found[0]
        answer = ("".join(result["render"]) if "render" in result else
                  result["answer"] + self.data["answer_suffix"])
        return {"answer": answer,
                "transitions": changes + proof(known, result["triple"])}

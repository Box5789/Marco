"""Per-conversation evidence ledger, replayed rather than incrementally reapplied.

Only fully recognized user clauses enter memory. Queries and assistant replies
never become facts. Model changes reparse source text before using old evidence.
"""
from copy import deepcopy
import re

from graph_inference import current_facts
from relational_semantics import RelationalParser


class UnknownWord(ValueError):
    """뜻을 아직 모르는 낱말로 된 사건. 틀린 조건이 아니라 **모르는 말**이다."""

    def __init__(self, word, said):
        super().__init__("unknown_word:%s" % word)
        self.word, self.said = word, said


class ReasoningContext:
    def __init__(self, max_turns=128, *, model=None):
        self.observations = []
        self.corrections = []
        # 자리를 못 채워 **되물어 둔** 사건들. 뒤에 온 말이 그 자리를 채우면
        # 그 말은 새 사건이 아니라 **이 사건의 보완**이다. 되묻지 않았으면
        # 잇지 않는다 — 같은 동사에 자리 몇 개가 겹친다는 것만으로는 모자라다.
        # 되물어 둔 것이 여럿일 수 있으므로 하나만 들고 있지 않는다.
        self.asked = []
        # 이해하지 못한 말. 버리지 않는다 — 버리면 그 말이 바꿨을 상태를
        # 예전 값 그대로 확정하게 된다. 기억을 통째로 지우지도 않는다.
        self.unread = []
        self.max_turns = max_turns
        self.model = model

    @staticmethod
    def _numeric_targets(parser):
        return {rule.get("target") for rule in (parser.data.get("numeric_updates") or {}).values()}

    @staticmethod
    def _counts_something(said, parser):
        """이 말이 수를 담고 있나. 아라비아 숫자만 보면 `세 개를 더 넣었다` 를 놓친다.

        수사는 언어팩이 선언한다. 코드가 한국어 수사를 따로 알 필요는 없다.
        """
        from numeral_semantics import parse_numeral
        numerals = parser.data.get("numerals") or {}
        for token in said.replace(".", " ").split():
            if any(char.isdigit() for char in token):
                return True
            # 낱말째로 본다. 글자로 보면 `단추 이야기는 재밌다` 의 `다` 가
            # `다섯` 에 걸려 잡담까지 수량 사건이 된다.
            if parse_numeral(token, numerals) is not None:
                return True
        return False

    @staticmethod
    def _segments(text, parser):
        """한 덩어리를 문장 단위로 나눈다.

        `구슬 3개를 더 넣었다. 지금 구슬은 몇 개야?` 는 사건 하나와 물음 하나다.
        메시지가 물음표로 끝난다는 이유로 앞의 사건까지 물음으로 치면, 못 읽은
        사건이 기록에서 빠지고 옛 값이 그대로 확정된다.
        """
        marks = parser.clause_grammar.get("question_marks", [])
        stops = "".join(marks) + ".!…"
        out, buffer = [], ""
        for char in text:
            buffer += char
            if char in stops and buffer.strip():
                out.append(buffer); buffer = ""
        if buffer.strip():
            out.append(buffer)
        return [(piece.strip(), any(piece.rstrip().endswith(mark) for mark in marks))
                for piece in out if piece.strip()]

    def _blocked_by(self, query, parser, facts):
        """이 물음이 가리키는 것에 대해 못 읽은 사건이 있으면 그 말을 돌려준다.

        해소 조건은 하나뿐이다 — **미해석 사건보다 나중에, 같은 대상의 같은
        속성을 실제로 못 박은 관찰.** 딴 대상의 관찰도, 또 다른 증감 사건도
        총량을 확정하지 못한다. 반례마다 조건을 덧붙이지 않는다.
        """
        numeric = self._numeric_targets(parser)
        named = {value for item in (query or []) for value in (item.get("triple") or [])
                 if isinstance(value, str) and not value.startswith(("?", "$"))}
        asks_number = any((item.get("triple") or [None, None])[1] in numeric
                          for item in (query or []))
        known = named | {fact["triple"][0] for fact in facts
                         if isinstance(fact.get("triple", [None])[0], str)}
        for name in named or {None}:
            # 이 대상의 값을 마지막으로 못 박은 관찰이 몇 번째였나. 증감 사건은
            # 못 박는 것이 아니라 흔드는 것이므로 세지 않는다.
            pinned = max([fact["evidence"].get("turn", -1) for fact in facts
                          if fact["triple"][0] == name and fact["triple"][1] in numeric] or [-1])
            for entry in self.unread:
                said = entry["text"]
                # 이름이 여러 낱말이면 낱말째로 본다. 물음은 `민수 구슬` 인데
                # 못 읽은 말은 `민수가 지연에게 베풀었다` 라 통째로는 안 걸린다.
                parts = [word for word in (name or "").split() if word]
                touches = any(word in said for word in parts) or (
                    asks_number and self._counts_something(said, parser)
                    and not any(other and other in said for other in known))
                if touches and entry["at"] > pinned:
                    return said
        return None


    def _completion(self, parser, current, verbs):
        """되물어 둔 자리를 채워 준 말인가. 맞으면 **사건마다** 기울 자리를 준다.

        **되묻지 않았으면 안 잇는다.** 같은 동사에 자리 몇 개가 겹친다는 것만으로
        두 말을 한 사건으로 합치면, 묻지도 않고 남의 말을 고쳐 읽는 것이다.
        채운 자리가 하나라도 어긋나면 보완이 아니라 딴 일이다.

        기우는 자리는 **메시지가 아니라 사건**이다. 메시지를 통째로 바꾸면 같은
        말에 함께 있던 사실까지 지워진다 — `민수 구슬은 8개 있다. 지연에게
        베풀었다` 에서 8개가 사라진다. 그래서 그 사건이 놓인 구절만 갈아 끼운다.

        기운 사건은 **원래 있던 자리에** 남는다. 나중 차례로 옮기면 그 뒤에
        바뀐 뜻으로 실행되어, 일어난 때와 다른 값이 나온다.
        """
        events = current.get("사건", [])
        if not self.asked or not events or current["facts"] or current.get("정의"):
            return None
        남은, 기움 = list(self.asked), []
        for event in events:
            stem = self._lookup(parser, event, set(), verbs)
            후보 = event.get("자리후보") or [event.get("자리", {})]
            fit = next((ask for ask in 남은 if ask["동사"] == stem
                        and any(set(ask["빈자리"].values()) <= set(자리)
                                and all(자리.get(key) == value
                                        for key, value in ask["자리"].items())
                                for 자리 in 후보)), None)
            if fit is None:
                return None
            남은.remove(fit)
            기움.append({**fit, "새말": event["evidence"]["text"]})
        return 기움

    def _permitted(self, knowledge_path):
        from state_engine import _knowledge
        return (self.model.permits("relational_graph") if self.model is not None
                else "relational_graph" in _knowledge(knowledge_path)["axioms"])

    def _parser(self):
        return RelationalParser() if self.model is None else self.model.parser()

    def _verification(self, knowledge_path, checks):
        if self.model is None:
            return {"sources": [str(knowledge_path)], "checks": checks}
        return {"sources": [item["path"] for item in self.model.sources], "checks": checks,
                "model": self.model.fingerprint, "model_assets": self.model.sources}

    def snapshot(self):
        return {"schema": "reasoning-context-v6", "observations": list(self.observations),
                "corrections": deepcopy(self.corrections), "unread": deepcopy(self.unread),
                "asked": deepcopy(self.asked)}

    def restore(self, snapshot):
        if (not isinstance(snapshot, dict) or snapshot.get("schema") not in {
                "reasoning-context-v1", "reasoning-context-v2",
                "reasoning-context-v3", "reasoning-context-v4",
                "reasoning-context-v5", "reasoning-context-v6"}
                or not isinstance(snapshot.get("observations"), list)
                or len(snapshot["observations"]) > self.max_turns
                or any(not isinstance(x, str) or not x.strip() for x in snapshot["observations"])):
            raise ValueError("invalid_reasoning_context_snapshot")
        corrections = snapshot.get("corrections", [])
        if (not isinstance(corrections, list) or len(corrections) > self.max_turns
                or any(not isinstance(x, dict) or type(x.get("index")) is not int
                       or not 0 <= x["index"] < len(snapshot["observations"])
                       or any(not isinstance(x.get(k), str) or not x[k].strip() for k in ("before", "after"))
                       for x in corrections)):
            raise ValueError("invalid_reasoning_context_snapshot")
        unread = snapshot.get("unread", [])
        if not isinstance(unread, list) or len(unread) > self.max_turns:
            raise ValueError("invalid_reasoning_context_snapshot")
        # v3 은 글자만 담았다. 순서를 모르면 가장 이른 것으로 읽는다 — 덜 푸는 쪽이다.
        unread = [{"text": x, "at": 0} if isinstance(x, str) else x for x in unread]
        if any(not isinstance(x, dict) or not isinstance(x.get("text"), str)
               or not x["text"].strip() or type(x.get("at")) is not int or x["at"] < 0
               for x in unread):
            raise ValueError("invalid_reasoning_context_snapshot")
        self.observations = list(snapshot["observations"])
        self.corrections = deepcopy(corrections)
        # 옛 갈무리에는 이 칸이 없다. 없으면 못 읽은 말도 없는 것으로 읽는다.
        self.unread = deepcopy(unread)
        asked = snapshot.get("asked") or []
        asked = [asked] if isinstance(asked, dict) else asked
        if (not isinstance(asked, list) or len(asked) > self.max_turns
                or any(not isinstance(x, dict) or type(x.get("at")) is not int
                       or not 0 <= x["at"] < len(self.observations)
                       or not isinstance(x.get("조각"), dict)
                       or not isinstance(x.get("동사"), str)
                       or not isinstance(x.get("자리"), dict)
                       or not isinstance(x.get("빈자리"), dict) for x in asked)):
            raise ValueError("invalid_reasoning_context_snapshot")
        # 되물은 기억이 없으면 아무것도 안 이어 붙인다 — 덜 잇는 쪽이다.
        self.asked = deepcopy(asked)

    @staticmethod
    def _triples(parser, rule, event, 이름=()):
        """뜻풀이와 사건을 자리로 맞춰 사실을 낸다.

        맞추는 방법은 하나다 — 조사가 짚는 자리. 같은 자리에 올 수 있는 조사는
        한 이름으로 부른다. 못 채운 자리는 **못 채웠다고** 돌려준다.

        자리를 어디서 끊을지가 여럿이면(`사과 상자를`) **뜻풀이가 고른다** —
        빈 자리를 채우고 어긋나지 않으며 남는 자리가 적은 자름이 옳은 자름이다.
        낱말만 봐서는 못 가르는 것을 개체 증거로 가르는 자리다.
        """
        from frame_induction import apply_rule, particle_key
        best = None
        for 후보 in event.get("자리후보") or [event.get("자리", {})]:
            자리 = {particle_key(key, parser.slot_particles): value
                   for key, value in 후보.items()}
            applied = apply_rule(rule["유도"], 자리)
            # 뜻풀이가 안 쓰는 자리에 **이 대화가 아는 이름**이 들어 있으면 그
            # 사건은 뜻풀이 밖의 무언가를 말한 것이다. 누가 했는지 같은 말은
            # 뜻풀이가 안 써도 그만이지만, 아는 이름은 그냥 넘길 수 없다.
            헛자리 = {key for key in applied["남은자리"]
                   if any(word and word in 자리[key] for word in 이름)}
            score = (len(applied["빈자리"]) + len(applied["충돌"]) + len(헛자리),
                     len(applied["남은자리"]))
            if best is None or score < best[0]:
                best = (score, {**applied, "헛자리": {key: 자리[key] for key in 헛자리}})
        return best[1]

    @staticmethod
    def _slot_name(parser, key):
        """빈 자리를 사람이 알아볼 이름으로. 한 자리를 채우는 조사를 다 보인다."""
        for group in parser.slot_particles:
            if key in group:
                return "/".join(group)
        return key

    def _unsettled(self, query, parser, pending):
        """자리를 못 채운 사건이 건드릴 수 있었던 값은 확정하지 않는다.

        **어느 값이 움직였는지 모른다는 것과 아무 값도 안 움직였다는 것은 다르다.**
        가르지 않으면 해석 실패가 옛 값을 확정하는 쪽으로 샌다.
        """
        numeric = parser.data.get("numeric_updates", {})
        for item in pending:
            # 뜻풀이 밖에 놓인 자리가 가리킨 것도 확정하지 않는다. 그 사건이
            # 무엇에 대한 말이었는지를 모르는 채로 그 값을 못 박으면 안 된다.
            for value in item["헛자리"].values():
                for asked in (query or []):
                    subject = str((asked.get("triple") or [""])[0])
                    if any(word and word in value for word in subject.split()):
                        return item
            for triple in item["닿는곳"]:
                target = (numeric.get(triple[1]) or {}).get("target", triple[1])
                known = [piece for piece in str(triple[0]).split() if "$" not in piece]
                for asked in (query or []):
                    asked_triple = asked.get("triple") or [None, None]
                    if (asked_triple[1] == target
                            and all(piece in str(asked_triple[0]) for piece in known)):
                        return item
        return None

    @staticmethod
    def _forms_of(parser, stems):
        """뜻풀이로 받은 어간들이 어떤 꼴로 나타날 수 있나. 활용은 언어팩이 계산한다.

        임의의 어간을 되돌려 쪼개지 않는다 — 이 대화에서 **이미 설명받은** 어간만
        펼쳐 놓고 견준다. 그래서 모르는 말을 멋대로 어간으로 오려내는 일이 없다.

        꼴마다 **어간과 함께 물음인지도** 적는다. 어간만 나르면 `베풉니까` 가
        `베풀` 로 이어지면서 물음이라는 것이 사라져, 물어본 일이 실제로 일어난다.
        묻기에만 쓰는 꼬리라야 물음의 표다 — `베풀었어요` 는 서술로도 쓴다.
        """
        from hangul import inflect
        grammar = parser.inflection_grammar or {}
        asking = parser._asking(grammar)
        table = {}
        for stem in stems:
            for kind in grammar.get("kinds", []):
                for tense in grammar.get("tenses", {}):
                    for ending in grammar.get("endings", {}):
                        try:
                            forms = inflect(stem, tense, ending, grammar, kind=kind)
                        except ValueError:
                            continue
                        for form in forms:
                            entry = table.setdefault(form["text"],
                                                     {"stem": stem, "물음": True})
                            if ending not in asking:
                                entry["물음"] = False
        return table

    @staticmethod
    def _lookup(parser, event, keys, table=None):
        """사건에 나온 꼴을 뜻풀이의 어간에 잇는다."""
        verb = event["verb"]
        if verb in keys:
            return verb
        surface = verb + event.get("꼬리", "")
        if table is None:
            table = ReasoningContext._forms_of(parser, keys)
        found = table.get(surface)
        return found["stem"] if found else None

    @staticmethod
    def _rule(parser, rule):
        """뜻풀이 하나를 쓸 수 있는 꼴로 만든다. 못 읽으면 None.

        틀은 어디에도 적혀 있지 않다. **몸통을 이미 아는 문장꼴로 읽어** 꺼낸다.
        끝내 못 읽으면 그 말은 모르는 말로 남는다 — 못 읽은 뜻풀이를 반쯤
        쓰느니 그 말이 건드린 값을 확정하지 않는 쪽이 낫다.
        """
        body = rule.get("몸통")
        if not body:
            return None
        cache = parser.induced_frames
        if body not in cache:
            from frame_induction import induce
            cache[body] = induce(parser, body)
        return {**rule, "유도": cache[body]} if cache[body] else None

    @staticmethod
    def _known_verbs(parser, sources):
        """이 말들에서 설명받은 어간들의 꼴 → {어간, 물음}."""
        stems = set()
        for source in sources:
            parsed = parser.parse(source, partial=True)
            if parsed is not None:
                stems |= {rule["verb"] for rule in parsed.get("정의", [])}
        return ReasoningContext._forms_of(parser, stems)

    @staticmethod
    def _replay(parser, sources):
        """관찰을 다시 읽어 사실을 만든다. (사실, 뜻이 정해진 낱말, 못 채운 사건).

        사건은 **제 차례의 뜻**으로 푼다 — 앞 사건에 뒤에 고친 뜻을 소급하지
        않는다. 다만 그때 아무 뜻도 없었다면, **나중에 들은 설명으로 이어 푼다.**
        끝내 뜻이 없는 사건은 사실을 만들지 않는다. 버리는 것이 아니라
        그 사건이 건드린 값을 확정하지 못하게 막는 쪽으로 남는다.

        사건은 뜻을 몰라도 꼴로 읽는다. 다만 **물음인지는 알아야** 하므로,
        먼저 뜻풀이만 걷어 활용표를 만들고 그 표를 쥐고 다시 읽는다.
        """
        table = ReasoningContext._forms_of(parser, {
            rule["verb"] for source in sources
            for parsed in [parser.parse(source, partial=True)] if parsed is not None
            for rule in parsed.get("정의", [])})
        read = []
        for source in sources:
            parsed = parser.parse(source, partial=True, events=True, verbs=table)
            if parsed is None:
                raise ValueError("unrecognized_observation")
            read.append(parsed)
        timeline = {}
        for index, parsed in enumerate(read):
            for rule in parsed.get("정의", []):
                usable = ReasoningContext._rule(parser, rule)
                if usable is not None:
                    timeline.setdefault(rule["verb"], []).append((index, usable))

        def rule_for(verb, at):
            before = [r for i, r in timeline.get(verb, []) if i <= at]
            if before:
                return before[-1]
            after = timeline.get(verb, [])
            return after[0][1] if after else None

        stems = set(timeline)
        happened = []
        for index, parsed in enumerate(read):
            for event in parsed.get("사건", []):
                stem = ReasoningContext._lookup(parser, event, stems, table)
                rule = rule_for(stem, index) if stem else None
                if rule is None or event.get("polarity") is False:
                    continue        # 뜻을 모르거나, 안 한 일이다
                happened.append((index, stem, event, rule))

        # 이 대화가 이름으로 아는 것들. 뜻풀이 밖에 놓인 자리가 이 가운데
        # 하나를 가리키면 짐작하지 않는다.
        이름 = {word for parsed in read for item in parsed["facts"]
              for word in str(item["triple"][0]).split()}
        facts, pending = [], []
        for index, (parsed, source) in enumerate(zip(read, sources)):
            # 한 말 안에서도 **적힌 차례**를 지킨다. 사건을 사실보다 먼저 놓으면
            # `민수 구슬은 8개 있다. 지연에게 베풀었다` 에서 덜어내기가 처음 수량
            # 보다 앞서고, 처음 수량이 없다며 통째로 막힌다.
            rows = []
            for at, stem, event, rule in happened:
                if at != index:
                    continue
                applied = ReasoningContext._triples(parser, rule, event, 이름)
                if applied["빈자리"] or applied["충돌"] or applied["헛자리"]:
                    pending.append({"text": source, "at": index, "동사": stem,
                                    "조각": event["evidence"], "자리": dict(event["자리"]),
                                    "빈자리": applied["빈자리"], "충돌": applied["충돌"],
                                    "헛자리": applied["헛자리"], "닿는곳": applied["닿는곳"]})
                    continue
                rows += [(event["evidence"].get("start", 0),
                          {"triple": triple,
                           "evidence": {**event["evidence"], "turn": index, "source": source}})
                         for triple in applied["사실"]]
            for item in parsed["facts"]:
                item = deepcopy(item)
                item["evidence"].update(turn=index, source=source)
                rows.append((item["evidence"].get("start", 0), item))
            facts += [row for _start, row in sorted(rows, key=lambda row: row[0])]
        return facts, stems, pending

    def correct(self, index, replacement, knowledge_path=None):
        """Replace one identified observation atomically, then replay all events.

        A correction is not a new event appended to the current quantity. Later
        observations retain their ordering and derived conclusions are rebuilt.
        """
        if not self._permitted(knowledge_path):
            raise ValueError("operator_not_declared_in_kg")
        if type(index) is not int or not 0 <= index < len(self.observations):
            raise ValueError("unknown_correction_target")
        if len(self.corrections) >= self.max_turns:
            raise ValueError("correction_capacity")
        parser = self._parser()
        parsed = parser.parse(replacement, partial=True)
        if not parsed or not parsed["facts"] or parsed["query"]:
            raise ValueError("correction_requires_observation")
        pending = list(self.observations)
        before = pending[index]
        pending[index] = replacement
        facts, _defined, _unsettled = self._replay(parser, pending)
        _, changes = current_facts(facts, parser.data.get("mutable_predicates", []),
                                   parser.data.get("numeric_updates", {}))
        record = {"index": index, "before": before, "after": replacement}
        self.observations = pending
        self.corrections.append(record)
        return {"operator": "relational_graph", "status": "observed",
                "answer": parser.data["context_replies"].get("corrected", parser.data["context_replies"]["observed"]),
                "transitions": [{"operation": "correction", **record}] + changes,
                "verification": self._verification(knowledge_path, [{"ok": True, "observation_turns": len(pending)}])}

    def turn(self, text, knowledge_path=None):
        if not self._permitted(knowledge_path):
            return None
        parser = self._parser()
        correction = parser.data.get("context_correction", {})
        for prefix in correction.get("prefixes", []):
            if text.strip().startswith(prefix):
                body = text.strip()[len(prefix):].strip()
                parts = body.split(correction["separator"])
                try:
                    if len(parts) != 2 or not all(part.strip() for part in parts):
                        raise ValueError("invalid_correction_syntax")
                    normalize = lambda value: re.sub(r"[.!?]+$", "", value.strip()).strip()
                    matches = [i for i, old in enumerate(self.observations)
                               if normalize(old) == normalize(parts[0])]
                    if len(matches) != 1:
                        raise ValueError("ambiguous_or_missing_correction_target")
                    return self.correct(matches[0], parts[1].strip(), knowledge_path)
                except ValueError as exc:
                    return {"operator": "relational_graph", "status": "unresolved",
                            "answer": parser.data["context_replies"]["correction_invalid"], "transitions": [],
                            "verification": self._verification(knowledge_path, [{"ok": False, "reason": str(exc)}])}
        verbs = self._known_verbs(parser, self.observations + [text])
        current = parser.parse(text, partial=True, events=True, verbs=verbs)
        if current is None:
            # 못 읽은 말을 구간마다 적어 둔다. 이 대화의 어느 값을 흔들었는지
            # 모르므로, 그 말이 가리킨 것에 대해서는 지금 값을 확정하지 않는다.
            # 물음은 사건이 아니다 — 묻는 말은 아무 상태도 안 바꾼다. 다만 그
            # 판단은 **메시지 전체가 아니라 구간마다** 해야 한다.
            for piece, asking in self._segments(text, parser):
                notes = []
                if asking or parser.parse(piece, partial=True, events=True, verbs=verbs,
                                          _diagnostics=notes) is not None:
                    continue
                # 묻는 말은 못 읽은 사건이 아니다. 아무 상태도 안 바꾼다.
                if any(note.get("reason") == "question_is_not_an_observation"
                       for note in notes):
                    continue
                if all(entry["text"] != piece for entry in self.unread):
                    self.unread.append({"text": piece, "at": len(self.observations)})
            del self.unread[:-self.max_turns]
            return None
        replies = parser.data["context_replies"]
        # 같은 말이 뒤늦게 읽히면 매듭이 풀린 것이다.
        heard = {piece for piece, _asking in self._segments(text, parser)}
        self.unread = [entry for entry in self.unread if entry["text"] not in heard]
        result = {"operator": "relational_graph", "transitions": [],
                  "verification": self._verification(knowledge_path, [])}
        if (current["facts"] or current.get("정의") or current.get("사건")) and len(
                self.observations) >= self.max_turns:
            return {**result, "status": "unresolved", "answer": replies["capacity"]}
        keeps = bool(current["facts"] or current.get("정의") or current.get("사건"))
        # 되물어 둔 자리를 채워 준 말이면 **새 사건이 아니라 그 사건의 보완**이다.
        # 원래 자리에 놓아야 그때의 뜻으로 풀린다.
        completion = self._completion(parser, current, verbs)
        if completion is None:
            pending = self.observations + ([text] if keeps else [])
        else:
            pending = list(self.observations)
            for 기움 in sorted(completion, reverse=True,
                              key=lambda item: (item["at"], item["조각"]["start"])):
                source = pending[기움["at"]]
                pending[기움["at"]] = (source[:기움["조각"]["start"]] + 기움["새말"]
                                     + source[기움["조각"]["end"]:])
        try:
            facts, defined, unsettled = self._replay(parser, pending)
            # 뜻을 알게 된 낱말의 사건은 더 이상 막지 않는다 — 설명을 듣고 이어 푼다.
            self.unread = [entry for entry in self.unread if entry.get("말") is None
                           or self._lookup(parser, {"verb": entry["말"], "꼬리": entry.get("꼬리", "")},
                                           defined) is None]
            # Validate a new observation even if no question has been asked yet.
            _, changes = current_facts(facts, parser.data.get("mutable_predicates", []),
                                       parser.data.get("numeric_updates", {}))
            # 설명을 듣긴 했는데 몸통을 못 읽었다면 그렇다고 말한다. "모르는
            # 낱말" 이라고만 하면 방금 설명한 사람에게는 틀린 말로 들린다.
            unreadable = next((rule["몸통"] for rule in current.get("정의", [])
                               if self._rule(parser, rule) is None and rule.get("몸통")), None)
            if unreadable is not None:
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["unreadable_definition"].format(**{"몸통": unreadable})}
            unknown = next((event["verb"] for event in current.get("사건", [])
                            if self._lookup(parser, event, defined) is None), None)
            if unknown is not None:
                # 모르는 말은 틀린 조건이 아니다. 무엇을 모르는지 짚어서 물어본다.
                # 관찰로는 **남긴다** — 나중에 설명을 들으면 이어서 풀어야 한다.
                self.observations = pending
                said = text.strip()
                if all(entry["text"] != said for entry in self.unread):
                    꼬리 = next((event.get("꼬리", "") for event in current.get("사건", [])
                                if event["verb"] == unknown), "")
                    self.unread.append({"text": said, "at": len(self.observations) - 1,
                                        "말": unknown, "꼬리": 꼬리})
                    del self.unread[:-self.max_turns]
                return {**result, "status": "unresolved",
                        "answer": replies["unknown_word"].format(**{"말": unknown})}
            # 자리를 못 채운 사건. 무슨 일이 있었는지는 읽었지만 누구의 값이
            # 움직였는지를 모른다. "반영했습니다" 라고 하면 그 값을 옛 값 그대로
            # 확정하게 된다 — 해석 실패를 변화 없음으로 바꾸는 자리다.
            fresh = [item for item in unsettled if item["text"] == text]
            unfilled = fresh[0] if fresh else None
            # 이 메시지에서 자리를 못 채운 사건들을 **하나씩** 적어 둔다. 하나만
            # 들고 있으면 앞엣것이 영영 되물어지지 않은 채로 남는다.
            self.asked = [ask for ask in self.asked
                          if all((ask["at"], ask["조각"]["start"])
                                 != (item["at"], item["조각"]["start"]) for item in fresh)]
            self.asked += [{"at": item["at"], "조각": item["조각"], "동사": item["동사"],
                            "자리": dict(item["자리"]), "빈자리": dict(item["빈자리"])}
                           for item in fresh if item["빈자리"]]
            del self.asked[:-self.max_turns]
            if unfilled is not None and unfilled["헛자리"] and not unfilled["충돌"]:
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["extra_argument"].format(**{
                            "말": text.strip(),
                            "남은": ", ".join(sorted(unfilled["헛자리"].values()))})}
            if unfilled is not None and unfilled["충돌"]:
                # 빈 자리를 채운 것이 아니라 뜻풀이가 정한 값과 어긋난 것이다.
                # 어느 쪽이 맞는지는 우리가 고를 일이 아니다.
                self.observations = pending
                name, 값 = next(iter(unfilled["충돌"].items()))
                return {**result, "status": "unresolved",
                        "answer": replies["conflicting_definition"].format(**{
                            "말": text.strip(), "정한값": 값["뜻"], "온값": 값["사건"]})}
            if unfilled is not None:
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["unfilled_role"].format(**{
                            "말": text.strip(),
                            "자리": ", ".join(sorted({self._slot_name(parser, key)
                                                    for key in unfilled["빈자리"].values()}))})}
            unread = self._blocked_by(current["query"], parser, facts)
            if unread is not None:
                return {**result, "status": "unresolved",
                        "answer": replies["unread_event"].format(**{"말": unread})}
            blocked = self._unsettled(current["query"], parser, unsettled)
            if blocked is not None and blocked["헛자리"] and not blocked["충돌"]:
                return {**result, "status": "unresolved",
                        "answer": replies["extra_event"].format(**{
                            "말": blocked["text"].strip(),
                            "남은": ", ".join(sorted(blocked["헛자리"].values()))})}
            if blocked is not None and blocked["충돌"]:
                name, 값 = next(iter(blocked["충돌"].items()))
                return {**result, "status": "unresolved",
                        "answer": replies["conflicting_event"].format(**{
                            "말": blocked["text"].strip(), "정한값": 값["뜻"], "온값": 값["사건"]})}
            if blocked is not None:
                return {**result, "status": "unresolved",
                        "answer": replies["unsettled_event"].format(**{
                            "말": blocked["text"].strip(),
                            "자리": ", ".join(sorted({self._slot_name(parser, key)
                                                    for key in blocked["빈자리"].values()}))})}
            outcome = parser.answer({"facts": facts, "query": current["query"]}) if current["query"] else None
        except ValueError as exc:
            result["verification"]["checks"].append({"ok": False, "reason": str(exc)})
            return {**result, "status": "unresolved", "answer": replies["invalid"]}
        if completion is not None:
            for 기움 in completion:
                self.corrections.append({"index": 기움["at"],
                                         "before": self.observations[기움["at"]],
                                         "after": pending[기움["at"]]})
                self.asked = [ask for ask in self.asked
                              if (ask["at"], ask["조각"]["start"]) != (기움["at"], 기움["조각"]["start"])]
            del self.corrections[:-self.max_turns]
        self.observations = pending
        result["verification"]["checks"].append({"ok": True, "observation_turns": len(pending)})
        if outcome:
            return {**result, **outcome, "status": "answered"}
        settled = replies["filled_role"] if completion is not None else replies["observed"]
        return {**result, "status": "unresolved" if current["query"] else "observed",
                "answer": replies["unresolved"] if current["query"] else settled,
                "transitions": changes}

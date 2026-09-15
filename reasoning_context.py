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
        return {"schema": "reasoning-context-v4", "observations": list(self.observations),
                "corrections": deepcopy(self.corrections), "unread": deepcopy(self.unread)}

    def restore(self, snapshot):
        if (not isinstance(snapshot, dict) or snapshot.get("schema") not in {
                "reasoning-context-v1", "reasoning-context-v2",
                "reasoning-context-v3", "reasoning-context-v4"}
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

    @staticmethod
    def _bind(triples, roles):
        """뜻풀이가 비워 둔 역할 자리를 이 사건의 사람으로 채운다."""
        bound = []
        for triple in triples:
            row = []
            for part in triple:
                if isinstance(part, list):
                    row.append(" ".join(roles.get(x[2:], x) if isinstance(x, str)
                                        and x.startswith("$$") else x for x in part))
                else:
                    row.append(part)
            bound.append(row)
        return bound

    @staticmethod
    def _forms_of(parser, stems):
        """뜻풀이로 받은 어간들이 어떤 꼴로 나타날 수 있나. 활용은 언어팩이 계산한다.

        임의의 어간을 되돌려 쪼개지 않는다 — 이 대화에서 **이미 설명받은** 어간만
        펼쳐 놓고 견준다. 그래서 모르는 말을 멋대로 어간으로 오려내는 일이 없다.
        """
        from hangul import inflect
        grammar = parser.inflection_grammar or {}
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
                            table.setdefault(form["text"], stem)
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
        return table.get(surface)

    @staticmethod
    def _replay(parser, sources):
        """관찰을 다시 읽어 사실을 만든다. (사실, 뜻이 정해진 낱말) 을 준다.

        사건은 **제 차례의 뜻**으로 푼다 — 앞 사건에 뒤에 고친 뜻을 소급하지
        않는다. 다만 그때 아무 뜻도 없었다면, **나중에 들은 설명으로 이어 푼다.**
        끝내 뜻이 없는 사건은 사실을 만들지 않는다. 버리는 것이 아니라
        그 사건이 건드린 값을 확정하지 못하게 막는 쪽으로 남는다.
        """
        read = []
        for source in sources:
            parsed = parser.parse(source, partial=True)
            if parsed is None:
                raise ValueError("unrecognized_observation")
            read.append(parsed)
        timeline = {}
        for index, parsed in enumerate(read):
            for rule in parsed.get("정의", []):
                timeline.setdefault(rule["verb"], []).append((index, rule))

        def rule_for(verb, at):
            before = [r for i, r in timeline.get(verb, []) if i <= at]
            if before:
                return before[-1]
            after = timeline.get(verb, [])
            return after[0][1] if after else None

        facts = []
        table = ReasoningContext._forms_of(parser, set(timeline))
        for index, (parsed, source) in enumerate(zip(read, sources)):
            for event in parsed.get("사건", []):
                stem = ReasoningContext._lookup(parser, event, set(timeline), table)
                rule = rule_for(stem, index) if stem else None
                if rule is None or event.get("polarity") is False:
                    continue        # 뜻을 모르거나, 안 한 일이다
                for triple in ReasoningContext._bind(rule["triples"], event["역할"]):
                    facts.append({"triple": triple,
                                  "evidence": {**event["evidence"], "turn": index, "source": source}})
            for item in parsed["facts"]:
                item = deepcopy(item)
                item["evidence"].update(turn=index, source=source)
                facts.append(item)
        return facts, set(timeline)

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
        facts, _defined = self._replay(parser, pending)
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
        current = parser.parse(text, partial=True)
        if current is None:
            # 못 읽은 말을 구간마다 적어 둔다. 이 대화의 어느 값을 흔들었는지
            # 모르므로, 그 말이 가리킨 것에 대해서는 지금 값을 확정하지 않는다.
            # 물음은 사건이 아니다 — 묻는 말은 아무 상태도 안 바꾼다. 다만 그
            # 판단은 **메시지 전체가 아니라 구간마다** 해야 한다.
            for piece, asking in self._segments(text, parser):
                if asking or parser.parse(piece, partial=True) is not None:
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
        pending = self.observations + ([text] if keeps else [])
        try:
            facts, defined = self._replay(parser, pending)
            # 뜻을 알게 된 낱말의 사건은 더 이상 막지 않는다 — 설명을 듣고 이어 푼다.
            self.unread = [entry for entry in self.unread if entry.get("말") is None
                           or self._lookup(parser, {"verb": entry["말"], "꼬리": entry.get("꼬리", "")},
                                           defined) is None]
            # Validate a new observation even if no question has been asked yet.
            _, changes = current_facts(facts, parser.data.get("mutable_predicates", []),
                                       parser.data.get("numeric_updates", {}))
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
            unread = self._blocked_by(current["query"], parser, facts)
            if unread is not None:
                return {**result, "status": "unresolved",
                        "answer": replies["unread_event"].format(**{"말": unread})}
            outcome = parser.answer({"facts": facts, "query": current["query"]}) if current["query"] else None
        except ValueError as exc:
            result["verification"]["checks"].append({"ok": False, "reason": str(exc)})
            return {**result, "status": "unresolved", "answer": replies["invalid"]}
        self.observations = pending
        result["verification"]["checks"].append({"ok": True, "observation_turns": len(pending)})
        if outcome:
            return {**result, **outcome, "status": "answered"}
        return {**result, "status": "unresolved" if current["query"] else "observed",
                "answer": replies["unresolved"] if current["query"] else replies["observed"],
                "transitions": changes}

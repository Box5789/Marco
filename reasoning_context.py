"""Per-conversation evidence ledger, replayed rather than incrementally reapplied.

Only fully recognized user clauses enter memory. Queries and assistant replies
never become facts. Model changes reparse source text before using old evidence.
"""
from copy import deepcopy
import json
import re

from graph_inference import current_facts
from relational_semantics import RelationalParser


class UnknownWord(ValueError):
    """뜻을 아직 모르는 낱말로 된 사건. 틀린 조건이 아니라 **모르는 말**이다."""

    def __init__(self, word, said):
        super().__init__("unknown_word:%s" % word)
        self.word, self.said = word, said


class ReasoningContext:
    # 말을 어디에 놓을지 몰라서 터진 자리들.
    UNPLACED = {"unrecognized_observation", "missing_initial_quantity",
                "ambiguous_quantity_subject", "ambiguous_property_scope",
                "graph_limit", "join_limit"}
    # 읽기는 읽었는데 **앞서 들은 것과 맞지 않는** 자리들. 3개에서 8개를 꺼낼 수는
    # 없다 — 그러나 그것이 "안 일어난 일" 이라는 뜻은 아니다. 처음 수량이 틀렸거나
    # 중간 사건이 빠졌을 수 있다. 우리가 어느 쪽인지 고르지 않고 묻는다.
    CONTRADICTION = {"invalid_quantity_result", "invalid_quantity_delta",
                     "invalid_initial_quantity"}

    def __init__(self, max_turns=128, *, model=None):
        self.observations = []
        self.corrections = []
        # 자리를 못 채워 **되물어 둔** 사건들. 뒤에 온 말이 그 자리를 채우면
        # 그 말은 새 사건이 아니라 **이 사건의 보완**이다. 되묻지 않았으면
        # 잇지 않는다 — 같은 동사에 자리 몇 개가 겹친다는 것만으로는 모자라다.
        # 되물어 둔 것이 여럿일 수 있으므로 하나만 들고 있지 않는다.
        self.asked = []
        # 막아 둔 물음. 짧은 답으로 자리가 채워지면 그 자리에서 이어 답한다.
        self.held_question = None
        # 되물어서 받은 답들. **어느 사건의 어느 역할을 어떤 값으로 채웠다.**
        # 원문을 고쳐 쓰지 않으므로 근거와 차례와 그때의 뜻이 그대로 남는다.
        self.fills = []
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


    @staticmethod
    def _measure(parser, triples, 앞선사실):
        """양이 **글자 그대로의 수가 아닌** 사실들을 지금 상태로 재어 채운다.

        `절반` 은 그 자리에서 값이 정해지지 않는다. 무엇의 절반인지 — 덜어내는
        쪽이 지금 가진 양 — 을 보고서야 정해진다. 그래서 여기서 **차례를 지켜
        앞선 사실까지만** 접어 상태를 얻고, 그 값으로 잰다.

        못 재면 값을 지어내지 않는다. 기준을 모르거나 나누어떨어지지 않으면
        (7의 절반처럼) 쪼갤 수 있는지를 우리가 정할 일이 아니므로 비워 둔다.
        """
        말표 = parser.quantities
        if not 말표 or not any(str(row[2]) in 말표 for row in triples):
            return triples, None
        updates = parser.data.get("numeric_updates", {})
        덜어내는 = next((row for row in triples
                     if str(row[2]) in 말표 and (updates.get(row[1]) or {}).get("factor", 0) < 0),
                    None)
        if 덜어내는 is None:
            return None, "기준"
        상태, _변화 = current_facts(앞선사실, parser.data.get("mutable_predicates", []),
                                 updates)
        재는곳 = (updates.get(덜어내는[1]) or {}).get("target")
        기준 = next((row["triple"][2] for row in 상태
                   if row["triple"][0] == 덜어내는[0] and row["triple"][1] == 재는곳), None)
        if 기준 is None or not str(기준).isdecimal():
            return None, "기준"
        말 = 말표[str(덜어내는[2])]
        값, 밑 = int(기준), int(말["값"])
        if 말["연산"] == "/":
            if 밑 == 0 or 값 % 밑:
                return None, "나눔"          # 쪼갤 수 있는지는 우리가 정하지 않는다
            잰값 = 값 // 밑
        elif 말["연산"] == "*":
            잰값 = 값 * 밑
        elif 말["연산"] == "+":
            잰값 = 값 + 밑
        elif 말["연산"] == "-":
            잰값 = 값 - 밑
        else:
            return None, "연산"
        if 잰값 < 0:
            return None, "나눔"
        # 한 번 잰 값을 **그 사건의 모든 사실**이 함께 쓴다. 주는 쪽이 던 만큼
        # 받는 쪽이 는다 — 따로 재면 둘이 어긋난다.
        return [[row[0], row[1], str(잰값) if str(row[2]) in 말표 else row[2]]
                for row in triples], None

    @staticmethod
    def _event_id(at, stem, 자리, 차례):
        """사건을 가리키는 이름. **글자 자리도 원문도 아니다.**

        몇 번째 말에서 · 어떤 낱말로 · 어떤 자리를 이미 짚은 · 몇 번째 사건인가.
        보완해도 이 넷은 안 바뀐다 — 보완이 원문을 고치지 않고 **빈 자리에 값을
        얹기만** 하기 때문이다. 원문도, 근거도, 그 사건의 차례와 그때의 뜻도
        건드리지 않는다.
        """
        return json.dumps([at, stem, sorted(자리.items()), 차례], ensure_ascii=False)

    def _live(self):
        """아직 답을 못 받은 되물음."""
        return [ask for ask in self.asked if not ask.get("해결")]

    def _settle(self, ask):
        """이 되물음은 답을 받았다. **베낀 기록이 아니라 이름으로** 지운다."""
        for kept in self.asked:
            if kept.get("id") == ask.get("id"):
                kept["해결"] = True

    def _completion(self, parser, current, verbs, 사는것):
        """되물어 둔 자리를 채워 준 **문장**인가. 맞으면 (되물음, 채운 값)들을 준다.

        **되묻지 않았으면 안 잇는다.** 같은 동사에 자리 몇 개가 겹친다는 것만으로
        두 말을 한 사건으로 합치면, 묻지도 않고 남의 말을 고쳐 읽는 것이다.
        채운 자리가 하나라도 어긋나면 보완이 아니라 딴 일이다.
        """
        events = current.get("사건", [])
        if not 사는것 or not events or current["facts"] or current.get("정의"):
            return None
        남은, 기움 = list(사는것), []
        for event in events:
            stem = self._lookup(parser, event, set(), verbs)
            후보 = event.get("자리후보") or [event.get("자리", {})]
            맞음 = None
            for ask in 남은:
                for 자리 in 후보:
                    비었던 = set(ask["빈자리"].values())
                    if (ask["동사"] == stem and 비었던 <= set(자리)
                            and all(자리.get(key) == value
                                    for key, value in ask["자리"].items())):
                        맞음 = (ask, {key: 자리[key] for key in 비었던})
                        break
                if 맞음:
                    break
            if 맞음 is None:
                return None
            남은.remove(맞음[0])
            기움.append(맞음)
        return 기움

    @staticmethod
    def _choice(text, 표):
        """적어 둔 낱말 가운데 어느 쪽을 말했나. 없으면 None — 넘겨짚지 않는다."""
        said = text.strip().rstrip(".!?…")
        # **앞부분만 보고 뒤를 안 읽으면 안 된다.** `정정 아냐` 가 `정정` 으로,
        # `바꾸지 마` 가 `바꿔` 로 실행된다. 적어 둔 말과 **그대로 같을 때만** 받는다.
        고른 = [name for name, words in (표 or {}).items()
              if any(word and said == word for word in words)]
        return 고른[0] if len(고른) == 1 else None

    def _answer_to_ask(self, parser, text, 사는것, 이름):
        """되물은 것에 대한 **짧은 답**인가. 무엇으로 못 쓰는지까지 돌려준다.

        받아들일 꼴은 정해 두었다 — 이름 **한 낱말**에, 언어팩이 적은 짧은 답
        꼬리나 조사가 붙은 것. 이것은 **지금 지원하는 범위**이지 자연어의 뜻을
        일반적으로 가려낸 것이 아니다. 낱말이 둘 이상이거나 물음표가 붙었거나
        꼬리가 낯설면 빈자리를 그대로 둔다.

        답이 **자리를 밝혔으면 그 자리를 지킨다.** `민수에게` 는 받는이를 말한
        것이지 누가 했는지를 말한 것이 아니다.
        """
        from frame_induction import particle_key, split_particle
        said = text.strip().rstrip(".!…")
        if not said or said != said.rstrip("?") or len(said.split()) != 1:
            return ("못씀", None, None)
        후보 = []
        조각 = split_particle(said, parser.case_particles, parser.slot_particles)
        if 조각 and 조각[0] in 이름:
            후보.append((조각[0], 조각[1]))
        꼬리들 = set(parser.short_tails)
        for name in 이름:
            if name and said.startswith(name) and said[len(name):] in 꼬리들:
                후보.append((name, None))
        if not 후보:
            return ("못씀", None, None)
        name, 역할 = max(후보, key=lambda pair: len(pair[0]))
        if len(사는것) != 1:
            return ("여럿", None, None)
        ask = 사는것[0]
        바라는 = next(iter(ask["빈자리"].values()))
        if 역할 is not None and particle_key(역할, parser.slot_particles) != 바라는:
            return ("역할다름", ask, (name, 역할))
        return ("채움", ask, (name, 바라는))

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
        return {"schema": "reasoning-context-v8", "observations": list(self.observations),
                "corrections": deepcopy(self.corrections), "unread": deepcopy(self.unread),
                "asked": deepcopy(self.asked), "held_question": self.held_question,
                "fills": deepcopy(self.fills)}

    def restore(self, snapshot):
        if (not isinstance(snapshot, dict) or snapshot.get("schema") not in {
                "reasoning-context-v1", "reasoning-context-v2",
                "reasoning-context-v3", "reasoning-context-v4",
                "reasoning-context-v5", "reasoning-context-v6",
                "reasoning-context-v7", "reasoning-context-v8"}
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
        # 옛 갈무리의 되물음은 꼴이 다르다. 못 알아보면 **안 이어 붙인다** — 덜
        # 잇는 쪽이다. 되물음 하나를 잃을 뿐 값이 틀어지지는 않는다.
        asked = [x for x in asked if isinstance(x, dict) and isinstance(x.get("사건"), str)]
        if (not isinstance(asked, list) or len(asked) > self.max_turns
                or any(not isinstance(x.get("id"), str)
                       or not isinstance(x.get("동사"), str)
                       or not isinstance(x.get("자리"), dict)
                       or not isinstance(x.get("빈자리"), dict) for x in asked)):
            raise ValueError("invalid_reasoning_context_snapshot")
        fills = snapshot.get("fills") or []
        if (not isinstance(fills, list) or len(fills) > self.max_turns
                or any(not isinstance(x, dict)
                       or not all(isinstance(x.get(k), str) for k in ("사건", "역할", "값"))
                       for x in fills)):
            raise ValueError("invalid_reasoning_context_snapshot")
        self.fills = deepcopy(fills)
        # 되물은 기억이 없으면 아무것도 안 이어 붙인다 — 덜 잇는 쪽이다.
        self.asked = deepcopy(asked)
        held = snapshot.get("held_question")
        if held is not None and (not isinstance(held, str) or not held.strip()):
            raise ValueError("invalid_reasoning_context_snapshot")
        # 막아 둔 물음도 이어져야 한다. 안 그러면 다시 묻게 만든다.
        self.held_question = held

    @staticmethod
    def _triples(parser, rule, event, 이름=(), 받은값=(), 덮기=()):
        """뜻풀이와 사건을 자리로 맞춰 사실을 낸다.

        맞추는 방법은 하나다 — 조사가 짚는 자리. 같은 자리에 올 수 있는 조사는
        한 이름으로 부른다. 못 채운 자리는 **못 채웠다고** 돌려준다.

        자리를 어디서 끊을지가 여럿이면(`사과 상자를`) **뜻풀이가 고른다** —
        빈 자리를 채우고 어긋나지 않으며 남는 자리가 적은 자름이 옳은 자름이다.
        낱말만 봐서는 못 가르는 것을 개체 증거로 가르는 자리다.
        """
        from frame_induction import apply_rule, particle_key
        임자 = particle_key(parser.doer_particle, parser.slot_particles)
        best = None
        for 후보 in event.get("자리후보") or [event.get("자리", {})]:
            자리 = {particle_key(key, parser.slot_particles): value
                   for key, value in 후보.items()}
            # 되물어 받은 답은 **값으로** 얹는다. 원문을 고쳐 쓰지 않는다.
            자리.update(받은값 or {})
            applied = apply_rule(rule["유도"], 자리, 덮기)
            # 뜻풀이가 안 쓰는 자리가 남으면 그 사건은 **뜻풀이가 모르는 것**을
            # 말한 것이다. 처음 보는 이름이라고 넘기면 `단추 4개를 담았다` 가
            # 구슬을 늘린다. 누가 했는지만은 뜻풀이가 안 써도 그만이다.
            헛자리 = {key for key in applied["남은자리"] if key != 임자}
            # 이 대화가 모르는 이름을 자리에 앉힌 자름은 덜 좋은 읽기다. `작은
            # 구슬을` 을 `작` + `구슬을` 로 끊으면 아무도 모르는 `작` 이 주는이가
            # 된다. 어느 자름이 옳은지는 개체 증거가 정한다.
            앎 = sum(1 for value in 자리.values() if value in 이름)
            모름 = len(자리) - 앎
            # 아는 이름을 **많이** 짚고 모르는 이름을 **적게** 만드는 자름이 옳다.
            # 모르는 것만 세면 통째로 삼킨 자름이 이기고(자리가 하나뿐이니까),
            # 아는 것만 세면 `작` 같은 부스러기를 남긴 자름이 이긴다.
            score = (len(헛자리), -앎, 모름,
                     len(applied["빈자리"]) + len(applied["충돌"]), -len(자리))
            if best is None or score < best[0]:
                best = (score, {**applied, "헛자리": {key: 자리[key] for key in 헛자리}})
        return best[1]

    def _slot_question(self, parser, 빈자리):
        """빈 자리를 사람 말로 되묻는다. 안 적힌 자리는 조사 이름을 보인다."""
        물음 = [parser.slot_questions.get(key) or
              "'%s' 자리가 비어 있습니다." % self._slot_name(parser, key)
              for key in sorted(set(빈자리.values()))]
        return " ".join(물음)

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
                    # **낱말이 하나라도 겹치면** 그 값은 확정하지 않는다. 전부
                    # 겹쳐야 막으면, 못 읽어 대상이 더럽혀진 사건(`민수 가진 구슬`)이
                    # `민수 구슬` 물음을 못 막고 옛 값이 그대로 확정된다.
                    if (asked_triple[1] == target
                            and (not known
                                 or any(piece in str(asked_triple[0]) for piece in known))):
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
    def _rule(parser, rule, 배운것=None):
        """뜻풀이 하나를 쓸 수 있는 꼴로 만든다. 못 읽으면 None.

        틀은 어디에도 적혀 있지 않다. **몸통을 이미 아는 문장꼴로 읽어** 꺼낸다.
        끝내 못 읽으면 그 말은 모르는 말로 남는다 — 못 읽은 뜻풀이를 반쯤
        쓰느니 그 말이 건드린 값을 확정하지 않는 쪽이 낫다.

        ``배운것`` 은 **이 뜻풀이보다 먼저** 설명받은 동작들이다. 뒤에 배운 것은
        안 넘긴다 — 그래야 옛 사건이 나중 설명으로 무단히 바뀌지 않는다.
        어느 시점의 뜻을 참조했는지는 `참조` 에 남긴다.
        """
        body = rule.get("몸통")
        if not body:
            return None
        뜻표 = (배운것 or {}).get("뜻") or {}
        열쇠 = (body, tuple(sorted((stem, 때) for stem, 때 in
                                  ((배운것 or {}).get("때") or {}).items())))
        cache = parser.induced_frames
        if 열쇠 not in cache:
            from frame_induction import induce
            cache[열쇠] = induce(parser, body, 배운것)
        유도 = cache[열쇠]
        if 유도 is None:
            return None
        쓴동사 = list(유도.get("쓴동사") or ())
        # 제 뜻을 제 몸통에 쓰면 풀 수가 없다. 앞선 뜻이 있으면 그것을 가리킨
        # 것이므로 괜찮다 — 그때는 `참조` 에 그 시점이 남는다.
        if rule["verb"] in 쓴동사 and rule["verb"] not in 뜻표:
            return None
        참조 = {stem: ((배운것 or {}).get("때") or {}).get(stem) for stem in 쓴동사}
        return {**rule, "유도": 유도, "쓴동사": 쓴동사, "참조": 참조}

    @staticmethod
    def _learned(parser, timeline, 꼴모음):
        """지금까지 배운 동작들. 뜻틀과 그 꼴, 그리고 **언제 배운 것인지**."""
        stems = tuple(sorted(timeline))
        if stems not in 꼴모음:
            표 = ReasoningContext._forms_of(parser, set(stems))
            꼴모음[stems] = {surface: found["stem"] for surface, found in 표.items()
                          if not found["물음"]}
        return {"뜻": {stem: rows[-1][1]["유도"] for stem, rows in timeline.items()},
                "때": {stem: rows[-1][0] for stem, rows in timeline.items()},
                "꼴": 꼴모음[stems]}

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
    def _replay(parser, sources, fills=()):
        """관찰을 다시 읽어 사실을 만든다. (사실, 뜻이 정해진 낱말, 못 채운 사건, 읽힌 몸통).

        ``fills`` 는 되물어서 받은 답이다 — **어느 사건의 어느 역할을 어떤 값으로
        채웠다.** 원문을 고쳐 쓰지 않는다. 한국어 문장을 새로 지어 다시 읽으면
        역할도 사건 이름도 흔들리고, 조사 만들기에도 기대게 된다.

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
        # 시간표는 **차례대로** 쌓는다. 그래야 각 뜻풀이가 그때까지 배운 것만
        # 재료로 쓰고, 뒤에 배운 것이 앞 사건에 소급되지 않는다.
        timeline, 꼴모음, 읽힌몸통 = {}, {}, set()
        for index, parsed in enumerate(read):
            for rule in parsed.get("정의", []):
                배운것 = ReasoningContext._learned(parser, timeline, 꼴모음)
                usable = ReasoningContext._rule(parser, rule, 배운것)
                if usable is not None:
                    timeline.setdefault(rule["verb"], []).append((index, usable))
                    읽힌몸통.add(rule.get("몸통"))

        def rule_for(verb, at):
            before = [r for i, r in timeline.get(verb, []) if i <= at]
            if before:
                return before[-1]
            after = timeline.get(verb, [])
            return after[0][1] if after else None

        stems = set(timeline)
        채움, 덮기 = {}, []
        for fill in fills:
            if fill.get("범위") in ("앞으로", "설명정정", "이번만"):
                덮기.append(fill)
            else:
                채움.setdefault(fill["사건"], {})[fill["역할"]] = fill["값"]

        def 덮을것(이름표, stem, at):
            """이 사건에 미치는 덮기. 범위를 넘어 과거를 통째로 바꾸지 않는다."""
            out = {}
            for fill in 덮기:
                if fill["범위"] == "이번만" and fill.get("사건") == 이름표:
                    out[fill["역할"]] = fill["값"]
                elif (fill["범위"] == "앞으로" and fill.get("동사") == stem
                      and at >= fill.get("부터", 0)):
                    out[fill["역할"]] = fill["값"]
                elif fill["범위"] == "설명정정" and fill.get("동사") == stem:
                    out[fill["역할"]] = fill["값"]
            return out
        happened, 차례표 = [], {}
        for index, parsed in enumerate(read):
            for event in parsed.get("사건", []):
                stem = ReasoningContext._lookup(parser, event, stems, table)
                key = (index, stem, json.dumps(sorted(event["자리"].items()),
                                               ensure_ascii=False))
                차례 = 차례표.get(key, 0)
                차례표[key] = 차례 + 1
                이름표 = ReasoningContext._event_id(index, stem, event["자리"], 차례)
                rule = rule_for(stem, index) if stem else None
                if rule is None or event.get("polarity") is False:
                    continue        # 뜻을 모르거나, 안 한 일이다
                happened.append((index, stem, event, rule, 이름표, 채움.get(이름표, {}),
                                 덮을것(이름표, stem, index)))

        # 이 대화가 이름으로 아는 것들. 어느 자름이 옳은지 가르는 증거다.
        이름 = set()
        for parsed in read:
            for item in parsed["facts"]:
                subject = str(item["triple"][0])
                이름.add(subject)
                이름.update(subject.split())
        facts, pending = [], []
        for index, (parsed, source) in enumerate(zip(read, sources)):
            # 한 말 안에서도 **적힌 차례**를 지킨다. 사건을 사실보다 먼저 놓으면
            # `민수 구슬은 8개 있다. 지연에게 베풀었다` 에서 덜어내기가 처음 수량
            # 보다 앞서고, 처음 수량이 없다며 통째로 막힌다.
            rows = []
            for at, stem, event, rule, 이름표, 받은값, 덮을값 in happened:
                if at != index:
                    continue
                applied = ReasoningContext._triples(parser, rule, event, 이름, 받은값, 덮을값)
                # 양이 글자 그대로의 수가 아니면 **지금 상태로 잰다.** 차례를 지켜
                # 앞선 사실까지만 접어서 본다 — 뒤에 올 일로 앞을 재면 안 된다.
                잰것, 못잼 = ReasoningContext._measure(
                    parser, applied["사실"], facts + [row for _start, row in rows])
                if (applied["빈자리"] or applied["충돌"] or applied["헛자리"]
                        or event.get("잘림") or 못잼):
                    pending.append({"text": source, "at": index, "동사": stem,
                                    "id": 이름표, "잘림": bool(event.get("잘림")),
                                    "차례": at, "못잼": 못잼,
                                    "조각": event["evidence"], "자리": dict(event["자리"]),
                                    "빈자리": applied["빈자리"], "충돌": applied["충돌"],
                                    "헛자리": applied["헛자리"], "닿는곳": applied["닿는곳"]})
                    continue
                rows += [(event["evidence"].get("start", 0),
                          {"triple": triple,
                           "evidence": {**event["evidence"], "turn": index, "source": source}})
                         for triple in 잰것]
            for item in parsed["facts"]:
                item = deepcopy(item)
                item["evidence"].update(turn=index, source=source)
                rows.append((item["evidence"].get("start", 0), item))
            facts += [row for _start, row in sorted(rows, key=lambda row: row[0])]
        return facts, stems, pending, 읽힌몸통

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
        facts, _defined, _unsettled, _읽힘 = self._replay(parser, pending, self.fills)
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
        replies = parser.data["context_replies"]
        사는것 = self._live()

        def 말하기(key, **값):
            return {"operator": "relational_graph", "transitions": [], "status": "unresolved",
                    "answer": replies[key].format(**값),
                    "verification": self._verification(knowledge_path, [])}

        # 되물은 것에 대한 **답**. 아무 틀에도 안 맞는 말이라 여기서 본다.
        # 답은 상태를 바꾸는 사건이 아니다 — 못 알아들어도 못 읽은 사건으로
        # 남기지 않는다. 남기면 틀리게 답한 말이 영영 값을 막는다.
        짧은답, 새덮기, 정해짐 = None, [], None
        굳은것 = [ask for ask in 사는것 if ask["종류"] in ("충돌", "정정대상")]
        if current is None and 굳은것:
            ask = 굳은것[0]
            if ask["종류"] == "정정대상":
                고름 = self._choice(text, parser.target_words)
                if 고름 is None:
                    return 말하기("correction_target")
                self._settle(ask)
                새덮기 = [{"범위": "설명정정" if 고름 == "설명" else "이번만",
                        "동사": ask["동사"], "사건": ask["사건"],
                        "역할": ask["역할"], "값": ask["값"], "근거": text.strip()}]
            else:
                범위 = self._choice(text, parser.scope_words)
                if 범위 is None:
                    return 말하기("conflict_scope_unclear", 말=text.strip())
                if 범위 == "정정":
                    # 무엇을 정정하는지는 우리가 고를 일이 아니다. 갈라 묻는다.
                    self._settle(ask)
                    self.asked.append({**ask, "id": ask["id"] + "?대상",
                                       "종류": "정정대상", "해결": False})
                    return 말하기("correction_target")
                self._settle(ask)
                새덮기 = [{"범위": 범위, "동사": ask["동사"], "사건": ask["사건"],
                        "부터": ask["차례"], "역할": ask["역할"], "값": ask["값"],
                        "근거": text.strip()}]
            current = {"facts": [], "query": None, "정의": [], "사건": []}
            정해짐 = 새덮기[0]["범위"]
        if current is None and 사는것 and not 굳은것:
            _f, _d, 지금, _읽힘 = self._replay(parser, self.observations, self.fills)
            이름 = set()
            for source in self.observations:
                parsed = parser.parse(source, partial=True, events=True)
                for item in (parsed or {}).get("facts", []):
                    이름.update(str(item["triple"][0]).split())
            갈래, ask, 값 = self._answer_to_ask(parser, text, 사는것, 이름)
            if 갈래 == "여럿":
                return 말하기("which_event", 목록=", ".join(
                    '"%s"' % next(iter(a["자리"].values()), a["동사"]) for a in 사는것))
            if 갈래 == "역할다름":
                return 말하기("role_mismatch", 말=text.strip(), 값=값[0],
                             물음=self._slot_question(parser, ask["빈자리"]))
            if 갈래 != "채움":
                return 말하기("answer_unclear", 말=text.strip(),
                             물음=self._slot_question(parser, 사는것[0]["빈자리"]))
            if all(item["id"] != ask["사건"] for item in 지금):
                self._settle(ask)      # 이미 풀린 물음이다. 답을 억지로 안 붙인다
                return 말하기("answer_unclear", 말=text.strip(),
                             물음=self._slot_question(parser, ask["빈자리"]))
            짧은답 = [(ask, {값[1]: 값[0]})]
        if 짧은답 is not None:
            current = {"facts": [], "query": None, "정의": [], "사건": []}
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
        completion = 짧은답 or self._completion(parser, current, verbs, 사는것)
        pending = (list(self.observations) if (completion is not None or 새덮기)
                   else self.observations + ([text] if keeps else []))
        # 보완은 **원문을 안 고친다.** 어느 사건의 어느 역할을 어떤 값으로 채웠다고
        # 적어 두고 다시 셈할 뿐이다. 원문도 근거도 차례도 그때의 뜻도 그대로다.
        새채움 = [{"사건": ask["사건"], "역할": key, "값": value, "근거": text.strip()}
                for ask, 값들 in (completion or []) for key, value in 값들.items()] + 새덮기
        try:
            facts, defined, unsettled, 읽힘 = self._replay(
                parser, pending, self.fills + 새채움)
            # 뜻을 알게 된 낱말의 사건은 더 이상 막지 않는다 — 설명을 듣고 이어 푼다.
            self.unread = [entry for entry in self.unread if entry.get("말") is None
                           or self._lookup(parser, {"verb": entry["말"], "꼬리": entry.get("꼬리", "")},
                                           defined) is None]
            # Validate a new observation even if no question has been asked yet.
            _, changes = current_facts(facts, parser.data.get("mutable_predicates", []),
                                       parser.data.get("numeric_updates", {}))
            # 설명을 듣긴 했는데 몸통을 못 읽었다면 그렇다고 말한다. "모르는
            # 낱말" 이라고만 하면 방금 설명한 사람에게는 틀린 말로 들린다.
            # 다시 읽기가 **그때까지 배운 것**을 쥐고 이미 판정했다. 여기서 맨손으로
            # 또 읽으면, 배운 동작을 재료로 쓴 뜻풀이를 못 읽었다고 잘못 말한다.
            unreadable = next((rule["몸통"] for rule in current.get("정의", [])
                               if rule.get("몸통") and rule["몸통"] not in 읽힘), None)
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
            적힌것 = {ask["사건"] for ask in self.asked}
            새되물음 = [{"id": "%s#%d" % (item["id"], len(self.asked) + n),
                     "종류": "빈자리", "사건": item["id"], "동사": item["동사"],
                     "자리": dict(item["자리"]), "빈자리": dict(item["빈자리"]),
                     "해결": False}
                    for n, item in enumerate(fresh)
                    if item["빈자리"] and item["id"] not in 적힌것]
            self.asked += 새되물음
            del self.asked[:-self.max_turns]
            # 이제 답을 받은 되물음은 **이름으로** 닫는다. 베낀 기록을 견주면
            # 안 닫히고, 다음 사건의 답이 옛 물음에 끌려간다.
            아직 = {item["id"] for item in unsettled}
            for ask in self.asked:
                if ask["종류"] == "빈자리" and ask["사건"] not in 아직:
                    ask["해결"] = True
            if unfilled is not None and unfilled.get("못잼"):
                # 값을 지어내지 않는다. 기준을 모르는 것과 나누어떨어지지 않는
                # 것은 다른 까닭이므로 갈라서 말한다.
                self.observations = pending
                말투 = ("unknown_basis" if unfilled["못잼"] == "기준"
                      else "indivisible_amount")
                return {**result, "status": "unresolved",
                        "answer": replies[말투].format(**{"말": text.strip()})}
            if (unfilled is not None and unfilled.get("잘림")
                    and not (unfilled["빈자리"] or unfilled["충돌"] or unfilled["헛자리"])):
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["too_many_readings"].format(**{"말": text.strip()})}
            if unfilled is not None and unfilled["헛자리"] and not unfilled["충돌"]:
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["extra_argument"].format(**{
                            "말": text.strip(),
                            "남은": ", ".join(sorted(unfilled["헛자리"].values()))})}
            if unfilled is not None and unfilled["충돌"]:
                # 빈 자리를 채운 것이 아니라 뜻풀이가 정한 값과 어긋난 것이다.
                # 어느 쪽이 맞는지는 우리가 고를 일이 아니다 — **어디까지인지** 묻는다.
                self.observations = pending
                name, 값 = next(iter(unfilled["충돌"].items()))
                if unfilled["id"] not in {a["사건"] for a in self.asked if a["종류"] == "충돌"}:
                    self.asked.append({"id": unfilled["id"] + "?충돌", "종류": "충돌",
                                       "사건": unfilled["id"], "동사": unfilled["동사"],
                                       "차례": unfilled["차례"], "역할": 값["자리"],
                                       "값": 값["사건"], "자리": dict(unfilled["자리"]),
                                       "빈자리": {}, "해결": False})
                    del self.asked[:-self.max_turns]
                return {**result, "status": "unresolved",
                        "answer": replies["conflicting_definition"].format(**{
                            "말": text.strip(), "정한값": 값["뜻"], "온값": 값["사건"]})}
            if unfilled is not None:
                self.observations = pending
                return {**result, "status": "unresolved",
                        "answer": replies["unfilled_role"].format(**{
                            "말": text.strip(),
                            "물음": self._slot_question(parser, unfilled["빈자리"])})}
            unread = self._blocked_by(current["query"], parser, facts)
            if unread is not None:
                self.held_question = text
                # 못 읽은 말과 앞말과 어긋난 말은 막는 까닭이 다르다. 어긋난 것을
                # "못 읽었다" 고 하면 방금 또렷이 말한 사람에게 틀린 말이 된다.
                어긋남 = any(entry["text"] == unread and entry.get("까닭") == "어긋남"
                          for entry in self.unread)
                말투 = "contradiction" if 어긋남 else "unread_event"
                return {**result, "status": "unresolved",
                        "answer": replies[말투].format(**{"말": unread})}
            blocked = self._unsettled(current["query"], parser, unsettled)
            if blocked is not None and blocked.get("못잼"):
                self.held_question = text
                말투 = ("unknown_basis" if blocked["못잼"] == "기준"
                      else "indivisible_amount")
                return {**result, "status": "unresolved",
                        "answer": replies[말투].format(**{"말": blocked["text"].strip()})}
            if (blocked is not None and blocked.get("잘림")
                    and not (blocked["빈자리"] or blocked["충돌"] or blocked["헛자리"])):
                self.held_question = text
                return {**result, "status": "unresolved",
                        "answer": replies["too_many_readings"].format(**{
                            "말": blocked["text"].strip()})}
            if blocked is not None and blocked["헛자리"] and not blocked["충돌"]:
                self.held_question = text
                return {**result, "status": "unresolved",
                        "answer": replies["extra_event"].format(**{
                            "말": blocked["text"].strip(),
                            "남은": ", ".join(sorted(blocked["헛자리"].values()))})}
            if blocked is not None and blocked["충돌"]:
                self.held_question = text
                name, 값 = next(iter(blocked["충돌"].items()))
                return {**result, "status": "unresolved",
                        "answer": replies["conflicting_event"].format(**{
                            "말": blocked["text"].strip(), "정한값": 값["뜻"], "온값": 값["사건"]})}
            if blocked is not None:
                self.held_question = text
                return {**result, "status": "unresolved",
                        "answer": replies["unsettled_event"].format(**{
                            "말": blocked["text"].strip(),
                            "자리": ", ".join(sorted({self._slot_name(parser, key)
                                                    for key in blocked["빈자리"].values()}))})}
            outcome = parser.answer({"facts": facts, "query": current["query"]}) if current["query"] else None
        except ValueError as exc:
            # **못 읽은 것과 앞말과 안 맞는 것은 다르다 — 그러나 둘 다 버리지 않는다.**
            #   못 읽음  — 말을 어디에 놓을지 몰랐다.
            #   안 맞음  — 읽었는데 앞서 들은 것과 셈이 안 맞는다. 사용자가
            #              일어났다고 말한 일을 우리가 "안 일어났다" 로 바꿀 수는
            #              없다. 처음 수량이 틀렸을 수도, 중간 사건이 빠졌을 수도
            #              있다. 두 말을 다 남기고 값은 확정하지 않은 채 묻는다.
            said, reason = text.strip(), str(exc)
            if (reason in self.UNPLACED | self.CONTRADICTION and keeps
                    and all(entry["text"] != said for entry in self.unread)):
                self.unread.append({"text": said, "at": len(self.observations),
                                    **({"까닭": "어긋남"} if reason in self.CONTRADICTION
                                       else {})})
                del self.unread[:-self.max_turns]
            result["verification"]["checks"].append({"ok": False, "reason": reason})
            answer = (replies["contradiction"].format(**{"말": said})
                      if reason in self.CONTRADICTION else replies["invalid"])
            return {**result, "status": "unresolved", "answer": answer}
        if completion is not None or 새덮기:
            self.fills += 새채움
            del self.fills[:-self.max_turns]
            for ask, _값 in (completion or []):
                self._settle(ask)
        self.observations = pending
        result["verification"]["checks"].append({"ok": True, "observation_turns": len(pending)})
        if outcome:
            return {**result, **outcome, "status": "answered"}
        # 짧은 답으로 자리가 채워졌으면 막아 두었던 물음에 이어서 답한다.
        if 짧은답 is not None and self.held_question and not current["query"]:
            question, self.held_question = self.held_question, None
            again = self.turn(question, knowledge_path)
            if again is not None and again.get("status") == "answered":
                return again
        settled = (replies["scope_settled"].format(**{"범위": 정해짐}) if 정해짐
                   else replies["filled_role"] if completion is not None
                   else replies["observed"])
        return {**result, "status": "unresolved" if current["query"] else "observed",
                "answer": replies["unresolved"] if current["query"] else settled,
                "transitions": changes}

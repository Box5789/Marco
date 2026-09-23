"""Semantic Check: parse the realized clause back with the same pack; meaning unchanged?

Independent readers, all from the language pack, none from the expression
that produced the clause:

* numbers — digits and the pack's numerals, outside quotations and citations,
  must be exactly the proposition's overt numbers; cited numbers exactly the
  cited ones;
* polarity — the pack's negation marker must occur in the clause's own words
  exactly when the proposition is negative;
* quotations — every quoted span must be a value the proposition quotes;
* reading — for frames with a declared reading, the same clause said in full
  (every role, the parser's own register) is parsed by the pack parser, and
  its facts or event roles must give back the proposition's roles, numbers
  and polarity;
* ellipsis — the clause as said must be the full clause with pieces removed
  and nothing added.

A clause that fails any reader is never emitted.
"""
import re

from numeral_semantics import parse_numeral

_DIGITS = re.compile(r"\d+")


def _quoted_fields():
    from marco.language.realizer.packs import meaning_declarations
    return set(meaning_declarations()["quoted_fields"]["fields"])


QUOTED_FIELDS = _quoted_fields()


def _quoted_strings(value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in QUOTED_FIELDS:
                if isinstance(item, str):
                    out.add(item)
            _quoted_strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _quoted_strings(item, out)
    return out


class Checker:
    def __init__(self, language, grammar, clause_realizer_factory):
        self.lang = language
        self.g = grammar
        self.make = clause_realizer_factory

    # readers ------------------------------------------------------------
    def numbers(self, text):
        """Digits, and numeral words; where the language counts with counters, a
        numeral word is a number only when a declared counter follows it."""
        found = [int(m) for m in _DIGITS.findall(text)]
        tokens = [token.strip("".join(self._marks())) for token in text.split()]
        counters = [spec["form"] for spec in self.g.decl.get("counters", {}).values()]
        needs_counter = bool((self.g.decl.get("numbers") or {}).get("words_need_counter"))
        for index, core in enumerate(tokens):
            if core and not _DIGITS.search(core):
                value = parse_numeral(core, self.lang.numerals)
                if value is None:
                    continue
                following = tokens[index + 1] if index + 1 < len(tokens) else ""
                if needs_counter and not any(following.startswith(form) for form in counters):
                    continue
                found.append(int(value))
        return sorted(found)

    def _marks(self):
        marks = set()
        for pair in self.g.ortho.get("quotes", {}).values():
            marks.update(pair)
        marks.update(self.g.ortho.get("punctuation", {}).values())
        marks.update(self.g.ortho.get("symbols", {}).get(name, "") for name in ("comma",))
        return marks

    def negated(self, words):
        """Whether the words carry the pack's negation: its marker pattern, or a
        form of its declared negation verb. ``None`` when the pack declares neither."""
        marker = self.lang.negation_marker
        forms = set((self.lang.parser.negation or {}).get("forms", ()))
        if marker is None and not forms:
            return None
        return any((marker is not None and marker.match(word)) or word in forms for word in words)

    # the check ------------------------------------------------------------
    def check(self, prop, candidate, clause, *, elided, sentence, register, allow_repair=False,
              frame_decl=None):
        failures = []
        separator = self.g.ortho["word_separator"]
        frame_decl = frame_decl or {}
        plain = [w for w in clause.words if not w["quoted"] and not w["cited"]]
        overt_text = separator.join("".join(w["pieces"]) for w in plain)
        expected = sorted(int(prop["roles"][role]["number"]) for role in frame_decl.get("numbers", [])
                          if role in prop["roles"] and role not in elided)
        said = self.numbers(overt_text)
        if said != expected:
            failures.append({"reader": "numbers", "said": said, "meant": expected})
        cited_expected = sorted(int(prop["roles"][role]["number"]) for role in frame_decl.get("cited", [])
                                if role in prop["roles"])
        cited_said = sorted(int(n) for w in clause.words for n in w.get("cited_numbers", []))
        if cited_said != cited_expected:
            failures.append({"reader": "cited_numbers", "said": cited_said, "meant": cited_expected})
        own_words = ["".join(w["pieces"]) for w in plain if w["kind"] not in ("np", "num", "counter")]
        negated = self.negated(own_words)
        if negated is None and prop.get("polarity", True) is False:
            failures.append({"reader": "polarity", "said": "unreadable", "meant": "negative"})
        if negated is not None and negated != (prop.get("polarity", True) is False):
            failures.append({"reader": "polarity", "said": "negative" if negated else "positive",
                             "meant": "negative" if prop.get("polarity", True) is False else "positive"})
        allowed = _quoted_strings(prop.get("roles", {}), set())
        for value in prop.get("roles", {}).values():
            for item in (value.get("list", []) if isinstance(value, dict) else []):
                if isinstance(item, dict) and "text" in item:
                    allowed.add(self.g.ortho["word_separator"].join(self.g.entity_words(item)))
        opening_closing = list(self.g.ortho.get("quotes", {}).values())
        for word in clause.words:
            if word["kind"] not in ("quote", "list", "cite", "operation"):
                continue
            text = "".join(word["pieces"])
            for opening, closing in opening_closing:
                for inner in re.findall(re.escape(opening) + "(.*?)" + re.escape(closing), text):
                    if inner not in allowed:
                        failures.append({"reader": "quotes", "said": inner})
        full = self.make().realize(prop, candidate, elided=(), sentence=sentence, register=register)
        canon = self.g.canonical_piece
        if not _subsequence(clause.pieces(canon), full.pieces(canon)):
            failures.append({"reader": "ellipsis", "said": clause.pieces(), "full": full.pieces()})
        reading = self.g.decl.get("readings", {}).get(prop["frame"])
        parse = "not_declared"
        repaired = False
        if reading:
            restated = self.make().realize(prop, candidate, elided=(), sentence="declarative",
                                           register="reading")
            from marco.language.realizer.grammar import finish_sentence
            text = finish_sentence(self.g, restated.text(separator), "declarative")
            parsed = self.lang.parser.parse(text, partial=True, events=True, repair=allow_repair)
            problem = self._reading(reading, parsed, prop)
            parse = "parsed" if problem is None else "mismatch"
            repaired = bool(parsed and any((f.get("evidence") or {}).get("normalization", {}).get("repair")
                                           for f in parsed.get("facts", [])))
            if problem is not None:
                failures.append({"reader": "parse", "text": text, "problem": problem})
        return {"ok": not failures, "failures": failures, "parse": parse, "repaired": repaired}

    # reading rules --------------------------------------------------------
    def _expected_words(self, prop, roles):
        words = []
        for role in roles:
            value = prop["roles"].get(role)
            if value is None:
                continue
            words.extend(self.g.entity_words(value))
        return words

    def same_words(self, said, meant):
        said, meant = str(said).split(), list(meant)
        if len(said) != len(meant):
            return False
        for a, b in zip(said, meant):
            if a == b:
                continue
            ca, cb = self.lang.concept(a), self.lang.concept(b)
            if ca and ca == cb:
                continue
            if a.lower() == b.lower():
                continue
            return False
        return True

    def _object_matches(self, value, said):
        if value is None:
            return False
        if "number" in value:
            return str(said) == str(value["number"])
        return self.same_words(said, self.g.entity_words(value))

    def _reading(self, reading, parsed, prop):
        if not parsed:
            return "unread"
        polarity = prop.get("polarity", True)
        problems = []
        for spec in reading.get("facts", []):
            facts = [f for f in parsed.get("facts", []) if (f.get("triple") or [None, None])[1] == spec["predicate"]]
            if not facts:
                problems.append("no_fact:%s" % spec["predicate"])
                continue
            subject_words = self._expected_words(prop, spec["subject"])
            match = [f for f in facts if self.same_words(f["triple"][0], subject_words)
                     and self._object_matches(prop["roles"].get(spec["object"]), f["triple"][2])
                     and f.get("polarity", True) == polarity]
            if not match:
                problems.append("fact_mismatch:%s:%s" % (spec["predicate"], [f["triple"] for f in facts]))
        if problems and reading.get("events"):
            event_problems = []
            for spec in reading["events"]:
                events = parsed.get(spec["key"], [])
                ok = False
                for event in events:
                    slots = event.get(spec["roles_key"], {})
                    if all(self._slot(slots, particle, prop, role) for role, particle in spec["roles"].items()):
                        ok = True
                if not ok:
                    event_problems.append("event_mismatch")
            if not event_problems:
                return None
            problems += event_problems
        return problems or None

    def _slot(self, slots, particle, prop, role):
        mates = self.lang.mates
        for key, text in slots.items():
            if key == particle or (mates.get(key) and mates.get(key) == mates.get(particle)):
                if self.same_words(text, self.g.entity_words(prop["roles"].get(role) or {})):
                    return True
        return False


def _subsequence(small, big):
    position = 0
    for piece in small:
        while position < len(big) and big[position] != piece:
            position += 1
        if position == len(big):
            return False
        position += 1
    return True

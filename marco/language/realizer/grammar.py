"""Grammar Realizer: particles, endings, inflection, agreement and order.

Every form comes from a declaration: the realizer file of the language
(``<stem>.json``) or the language pack it reuses (particle mates, inflection
grammar, negation, senses, romanization). This module only executes a closed
set of part kinds — ``np``, ``num``, ``lex``, ``verb``, ``quote``, ``list``,
``rel``, ``sym``, ``cite``, ``id``, ``pair``, ``operation`` — in the order an
expression candidate lists them.

A realized clause keeps its words and, for each word, the pieces it is made
of, so the semantic check can compare the said clause with the same clause
said in full.
"""
import copy

from hangul import batchim, inflect, is_hangul, romanize


class RealizationError(ValueError):
    """An expression needs a form its language does not declare."""


def _first(forms):
    return forms[0]["text"]


class Grammar:
    def __init__(self, language):
        self.lang = language
        self.decl = language.decl
        self.ortho = self.decl["orthography"]
        self.keys = self.decl.get("pack_keys", {})

    # ── entities ─────────────────────────────────────────────────────────
    def entity_words(self, value, number=None):
        """The words of an entity in this language: its own words, a sense link, or a romanized name.

        A compound (the engine's owner-then-item subject) is said the way the
        language declares: juxtaposed, or as a possessive.
        """
        text = value.get("text", "")
        if value.get("kind") == "compound" and len(text.split()) > 1:
            joint = self._compound_separator()
            head, rest = text.split(joint)[0], joint.join(text.split(joint)[1:])
            owner = self.entity_words({**value, "text": head, "kind": "agent"})
            item = self.entity_words({**value, "text": rest, "kind": "thing"}, number)
            compound = self.ortho.get("compound") or {}
            if compound.get("join") == "possessive" and owner:
                owner = owner[:-1] + [owner[-1] + compound["possessive"]]
            return owner + item
        source = value.get("lang")
        if not source or source == self.lang.stem:
            words = text.split()
            return [self.noun_number(word, number) for word in words] if number is not None else words
        from marco.language.realizer.packs import language as load
        origin = load(source)
        words = []
        for word in text.split():
            concept = origin.concept(word)
            targets = self.lang.words_for(concept) if concept else []
            if targets:
                words.append(self.choose_number(targets, number))
                continue
            table = origin.romanization
            # Only a name is spelled in another script. A common noun with no
            # sense link stays as the source word: shown, not translated.
            if (value.get("kind") == "agent" and table and word and all(is_hangul(char) for char in word)
                    and self.ortho.get("name_case")):
                spelled = romanize(word, table)
                if spelled:
                    words.append(self.name_case(spelled))
                    continue
            words.append(word)
        return words

    @staticmethod
    def _compound_separator():
        from marco.language.realizer.packs import meaning_declarations
        return meaning_declarations()["compound_subject"]["separator"]

    def name_case(self, word):
        mode = self.ortho.get("name_case")
        if mode == "capitalize":
            return word[:1].upper() + word[1:]
        return word

    def is_name(self, value, words):
        kind = value.get("kind")
        if kind == "agent":
            return True
        if kind in ("thing", "place"):
            return False
        return bool(words) and self.ortho.get("name_case") == "capitalize" and words[0][:1].isupper()

    def choose_number(self, words, number):
        rule = (self.decl.get("grammar") or {}).get("noun_number") or {}
        suffix = rule.get("plural_suffix")
        if not suffix or len(words) == 1:
            return sorted(words, key=len)[0]
        plural = number is None or str(number) != "1"
        marked = [w for w in words if w.endswith(suffix) and w[:-len(suffix)] in words]
        bare = [w for w in words if w + suffix in words]
        if plural and marked:
            return marked[0]
        if not plural and bare:
            return bare[0]
        return sorted(words, key=len)[0]

    def noun_number(self, word, number):
        """Agree a noun with its number, only between forms the pack links to one concept."""
        rule = (self.decl.get("grammar") or {}).get("noun_number") or {}
        suffix = rule.get("plural_suffix")
        if not suffix:
            return word
        concept = self.lang.concept(word)
        if not concept:
            return word
        return self.choose_number(self.lang.words_for(concept), number)

    # ── particles ────────────────────────────────────────────────────────
    def coda(self, text):
        """The final consonant that decides a particle's form, or '' when there is none."""
        marks = set()
        for pair in self.ortho.get("quotes", {}).values():
            marks.update(pair)
        marks.update(self.ortho.get("punctuation", {}).values())
        core = text
        while core and core[-1] in marks:
            core = core[:-1]
        if not core:
            return ""
        last = core[-1]
        if is_hangul(last):
            return batchim(last) or ""
        digits = self.ortho.get("digit_codas", {})
        if last in digits:
            return digits[last]
        if self.ortho.get("latin_codas") == "romanization" and self.lang.romanization:
            spelled = {v: k for k, v in self.lang.romanization.get("codas", {}).items() if v}
            lower = core.lower()
            for length in sorted({len(v) for v in spelled}, reverse=True):
                if lower[-length:] in spelled:
                    return spelled[lower[-length:]]
        return ""

    def particle(self, text, case):
        spec = self.decl.get("cases", {}).get(case)
        if spec is None:
            raise RealizationError("undeclared_case:%s" % case)
        if "form" in spec:
            return spec["form"]
        if "mate" not in spec:
            return ""
        mates = self.lang.mates.get(spec["mate"])
        if not mates or len(mates) != 2:
            raise RealizationError("undeclared_mate:%s" % spec["mate"])
        closed, open_ = mates
        coda = self.coda(text)
        exception = self.lang.mate_exceptions.get(closed, {})
        if coda and coda in exception.get(self.keys.get("exception_codas", ""), []):
            return exception.get(self.keys.get("exception_form", ""), open_)
        return closed if coda else open_

    def canonical_piece(self, piece, kind):
        """A case particle compared by its mate pair: the form after a closed or open host is one case."""
        if kind != "case":
            return piece
        for pair in self.lang.mates.values():
            if piece in pair:
                return "|".join(sorted(pair))
        return piece

    def preposition(self, case):
        spec = self.decl.get("cases", {}).get(case)
        if spec is None:
            raise RealizationError("undeclared_case:%s" % case)
        return spec.get("before")

    # ── verbs and copula ─────────────────────────────────────────────────
    def inflect(self, stem, tense, ending, kind):
        try:
            return _first(inflect(stem, tense, ending, self.lang.inflection, kind=kind))
        except ValueError as exc:
            raise RealizationError("inflection:%s:%s:%s:%s" % (stem, tense, ending, exc)) from exc

    def lexeme(self, lex):
        entry = self.decl.get("lexicon", {}).get(lex)
        if entry is None:
            raise RealizationError("undeclared_lexeme:%s" % lex)
        return entry

    def verb_words(self, part, *, ending, tense, polarity, person, plural):
        """Finite or non-finite verb words for one part."""
        entry = self.lexeme(part["verb"])
        stem, kind = entry["verb"], entry.get("kind", "regular")
        negate = polarity is False and part.get("negation") and part.get("polarity") != "positive"
        if self.lang.inflection.get("script") == "alphabetic":
            return self._english_verb(stem, part, ending=ending, tense=tense, negate=negate,
                                      person=person, plural=plural)
        if not negate:
            return [self.inflect(stem, tense, ending, kind)]
        spec = self.decl["grammar"]["negation"].get(part["negation"])
        if spec is None:
            raise RealizationError("undeclared_negation:%s" % part["negation"])
        if spec.get("from_pack"):
            spec = {"connective": self.lang.pack_negation.get(self.keys.get("negation_connective", "")),
                    "aux": self.lang.pack_negation.get(self.keys.get("negation_stem", "")),
                    "kind": self.lang.pack_negation.get(self.keys.get("negation_kind", ""))}
        if not spec.get("connective") or not spec.get("aux"):
            raise RealizationError("negation_not_declared")
        return [stem + spec["connective"], self.inflect(spec["aux"], tense, ending, spec.get("kind", "regular"))]

    def _english_form(self, lemma, form):
        lexicon = self.lang.inflection.get("lexicon", {})
        return (lexicon.get(lemma) or {}).get(form)

    def _english_finite(self, lemma, tense, person, plural):
        forms = self.decl["grammar"]["agreement"]
        if tense == "past":
            if plural or person in ("second",):
                declared = self._english_form(lemma, forms["past_plural"])
                if declared:
                    return declared
            return self.inflect(lemma, "past", forms["past"], "regular")
        if person == "first":
            declared = self._english_form(lemma, forms["present_first"])
            if declared:
                return declared
            return lemma
        if plural or person == "second":
            declared = self._english_form(lemma, forms["present_plural"])
            return declared or lemma
        return self.inflect(lemma, "present", forms["third_singular"], "regular")

    def _english_verb(self, lemma, part, *, ending, tense, negate, person, plural):
        if ending in ("participle",):
            return [self.inflect(lemma, "past", "participle", "regular")]
        if ending == "base":
            return [lemma]
        if not negate:
            return [self._english_finite(lemma, tense, person, plural)]
        spec = self.decl["grammar"]["negation"].get(part["negation"])
        if spec is None:
            raise RealizationError("undeclared_negation:%s" % part["negation"])
        if lemma in spec.get("direct", []):
            return [self._english_finite(lemma, tense, person, plural), spec["word"]]
        aux = self.lexeme(spec["aux"])["verb"] if spec["aux"] in self.decl.get("lexicon", {}) else spec["aux"]
        return [self._english_finite(aux, tense, person, plural), spec["word"], lemma]

    def copula(self, host, tense, ending, sentence):
        spec = (self.decl.get("grammar") or {}).get("copula")
        if not spec:
            raise RealizationError("copula_not_declared")
        coda = self.coda(host)
        table = spec.get("after_closed" if coda else "after_open", {})
        if ending in table:
            return table[ending]
        kind = spec.get("question_kind") if sentence == "question" and spec.get("question_kind") else spec["kind"]
        return self.inflect(spec["stem"], tense, ending, kind)

    # ── clauses ──────────────────────────────────────────────────────────
    def sentence_ending(self, sentence, register):
        table = self.decl.get("sentence_endings", {}).get(sentence) or {}
        ending = table.get(register) or table.get(self.decl.get("register", {}).get("default"))
        if ending is None:
            raise RealizationError("undeclared_sentence_ending:%s:%s" % (sentence, register))
        return ending

    def quote(self, text, marks):
        opening, closing = self.ortho["quotes"][marks]
        return opening + text + closing

    def symbol(self, name):
        return self.ortho["symbols"][name]


class Clause:
    """Words of one clause. Each word: its pieces, what it realizes, and flags."""

    def __init__(self):
        self.words = []

    def add(self, pieces, *, kind, role=None, bind=False, quoted=False, cited=False, number=None):
        pieces = [p for p in pieces if p]
        if not pieces:
            return
        self.words.append({"pieces": list(pieces), "kind": kind, "role": role, "bind": bind,
                           "quoted": quoted, "cited": cited, "number": number})

    def attach(self, piece, *, kind):
        if not self.words:
            raise RealizationError("nothing_to_attach_to")
        if piece:
            self.words[-1]["pieces"].append(piece)
            self.words[-1].setdefault("bound", []).append(kind)

    def last_text(self):
        return "".join(self.words[-1]["pieces"]) if self.words else ""

    def pieces(self, canon=None):
        """Every piece in order. ``canon`` maps a bound case piece to its case, so a
        particle whose form follows its host compares equal across hosts."""
        out = []
        for word in self.words:
            bound = word.get("bound", [])
            head = len(word["pieces"]) - len(bound)
            for index, piece in enumerate(word["pieces"]):
                kind = bound[index - head] if index >= head else None
                out.append(canon(piece, kind) if canon else piece)
        return out

    def text(self, separator):
        out = ""
        for index, word in enumerate(self.words):
            joined = "".join(word["pieces"])
            if index and not word["bind"]:
                out += separator
            out += joined
        return out


class ClauseRealizer:
    """Realize one proposition with one expression candidate."""

    def __init__(self, grammar):
        self.g = grammar

    def realize(self, prop, candidate, *, register, elided=(), sentence="declarative",
                gap=False, parts=None):
        clause = Clause()
        self._context = {"prop": prop, "elided": set(elided), "sentence": sentence, "register": register,
                         "gap": gap}
        for part in (parts if parts is not None else candidate["parts"]):
            self._part(clause, part, prop.get("roles", {}))
        return clause

    # role values ---------------------------------------------------------
    def _value(self, roles, role):
        if role == "$item":
            return self._context.get("item")
        return roles.get(role)

    def _elided(self, role):
        return role in self._context["elided"]

    def _polarity(self):
        return self._context["prop"].get("polarity", True)

    def _tense(self, part):
        return part.get("tense") or self._context["prop"].get("tense") or "present"

    def _ending(self, part):
        if "ending" in part:
            return part["ending"]
        if part.get("predicate") or part.get("cop") == "predicate":
            return self.g.sentence_ending(self._context["sentence"], self._context["register"])
        return None

    # parts ---------------------------------------------------------------
    def _part(self, clause, part, roles):
        if part.get("elide_with") and (self._elided(part["elide_with"]) or roles.get(part["elide_with"]) is None):
            return
        kinds = [k for k in ("np", "num", "lex", "verb", "quote", "list", "rel", "sym", "cite", "id",
                             "pair", "operation") if k in part]
        if len(kinds) != 1:
            raise RealizationError("part_kind")
        getattr(self, "_" + kinds[0])(clause, part, roles)

    def _finish(self, clause, part, host_text):
        """Case marker and copula after a constituent."""
        if part.get("case"):
            if self.g.lang.inflection.get("script") == "alphabetic":
                pass
            else:
                clause.attach(self.g.particle(host_text, part["case"]), kind="case")
        cop = part.get("cop")
        if cop and not (cop == "predicate" and self._context["gap"]):
            ending = self._ending(part) if cop == "predicate" else cop
            clause.attach(self.g.copula(clause.last_text(), self._tense(part), ending, self._context["sentence"]),
                          kind="copula")

    def _np(self, clause, part, roles):
        values = [(role, roles.get(role)) for role in part["np"]]
        present = [(role, value) for role, value in values if value is not None and not self._elided(role)]
        if not present:
            return
        number = None
        if part.get("number"):
            number_value = roles.get(part["number"])
            number = (number_value or {}).get("number") if isinstance(number_value, dict) else None
        english = self.g.lang.inflection.get("script") == "alphabetic"
        preposition = self.g.preposition(part["case"]) if english and part.get("case") else None
        if preposition:
            clause.add([preposition], kind="case", role=None)
        for index, (role, value) in enumerate(present):
            words = self.g.entity_words(value, number)
            if english and part.get("det") and not self.g.is_name(value, words):
                clause.add([self.g.decl["determiners"][part["det"]]], kind="det", role=role)
            for word in words:
                clause.add([word], kind="np", role=role)
        self._finish(clause, part, clause.last_text())

    def _num(self, clause, part, roles):
        role = part["num"]
        value = roles.get(role)
        if value is None or self._elided(role):
            return
        digits = str(value.get("number") if isinstance(value, dict) else value)
        numbers = self.g.decl.get("numbers") or {}
        style = part.get("style") or numbers.get("style", "digits")
        counter = part.get("counter")
        spec = self.g.decl.get("counters", {}).get(counter) if counter else None
        if style == "words" and digits in numbers.get("words", {}):
            # A numeral word stands apart from its counter: two words.
            clause.add([numbers["words"][digits]], kind="num", role=role, bind=bool(part.get("bind")),
                       cited=self._context.get("cited", False), number=digits)
            if spec:
                clause.add([spec["form"]], kind="counter", role=role)
        else:
            pieces = [digits] + ([spec["form"]] if spec else [])
            clause.add(pieces, kind="num", role=role, bind=bool(part.get("bind")),
                       cited=self._context.get("cited", False), number=digits)
        self._finish(clause, part, clause.last_text())

    def _lex(self, clause, part, roles):
        entry = self.g.lexeme(part["lex"])
        if "word" not in entry:
            raise RealizationError("lexeme_not_a_word:%s" % part["lex"])
        clause.add([entry["word"]], kind="lex", role=None, bind=bool(part.get("bind")))
        self._finish(clause, part, clause.last_text())

    def _rel(self, clause, part, roles):
        value = roles.get(part["rel"]) or {}
        word = self.g.decl.get("relation_words", {}).get(value.get("relation"))
        if not word:
            raise RealizationError("undeclared_relation_word:%s" % value.get("relation"))
        clause.add([word], kind="rel", role=part["rel"])
        self._finish(clause, part, clause.last_text())

    def _verb(self, clause, part, roles):
        entry = self.g.lexeme(part["verb"])
        person, plural = part.get("person"), False
        if part.get("agree"):
            agreed = roles.get(part["agree"]) or {}
            person = person or ("first" if agreed.get("person") == "first" else "third")
        if part.get("agree_number"):
            count = roles.get(part["agree_number"]) or {}
            plural = str(count.get("number")) != "1"
        if person is None:
            person = "third"
        polarity = self._polarity() if part.get("polarity") != "positive" else True
        ending = self._ending(part)
        if ending is None and self.g.lang.inflection.get("script") != "alphabetic":
            raise RealizationError("verb_without_ending:%s" % part["verb"])
        words = self.g.verb_words(part, ending=ending, tense=self._tense(part), polarity=polarity,
                                  person=person, plural=plural)
        for index, word in enumerate(words):
            clause.add([word], kind="verb", role=None, bind=bool(part.get("bind")) and index == 0)
        del entry

    def _quote(self, clause, part, roles):
        value = self._value(roles, part["quote"])
        if value is None:
            return
        if isinstance(value, dict) and "text" in value:
            # A name is said in this language, then marked as the one meant.
            text = self.g.ortho["word_separator"].join(self.g.entity_words(value))
        else:
            text = value.get("quote") if isinstance(value, dict) else str(value)
        clause.add([self.g.quote(text, part.get("marks", "double"))], kind="quote", role=part["quote"],
                   quoted=True, bind=bool(part.get("bind")))
        self._finish(clause, part, text)

    def _id(self, clause, part, roles):
        value = roles.get(part["id"]) or {}
        clause.add([value.get("id", "")], kind="id", role=part["id"], cited=True, bind=bool(part.get("bind")))

    def _sym(self, clause, part, roles):
        clause.add([self.g.symbol(part["sym"])], kind="sym", bind=bool(part.get("bind")))

    def _pair(self, clause, part, roles):
        value = self._value(roles, part["pair"]) or {}
        marks = part.get("marks", "double")
        text = self.g.quote(value.get("source", ""), marks) + self.g.symbol(part["join"]) + \
            self.g.quote(value.get("reading", ""), marks)
        clause.add([text], kind="quote", role="pair", quoted=True, bind=bool(part.get("bind")))

    def _operation(self, clause, part, roles):
        op = self._value(roles, part["operation"]) or {}
        parts = self.g.decl.get("operations", {}).get(op.get("op"))
        if parts is None:
            raise RealizationError("undeclared_operation:%s" % op.get("op"))
        inner = ClauseRealizer(self.g)
        sub = inner.realize({"roles": {k: {"quote": v} for k, v in op.items() if k != "op"}, "polarity": True},
                            {"parts": parts}, sentence=self._context["sentence"],
                            register=self._context["register"])
        clause.add([sub.text(self.g.ortho["word_separator"])], kind="operation", quoted=True,
                   bind=bool(part.get("bind")))

    def _list(self, clause, part, roles):
        value = roles.get(part["list"]) or {}
        items = value.get("list", []) if isinstance(value, dict) else list(value)
        if not items:
            return
        separator = self.g.symbol(part["separator"]) if part.get("separator") else self.g.ortho["list_separator"]
        last = self.g.ortho.get("list_last") if not part.get("separator") else None
        texts = []
        for item in items:
            inner = ClauseRealizer(self.g)
            inner._context = dict(self._context, item=item)
            sub = Clause()
            inner._part(sub, dict(part["each"]), roles)
            texts.append(sub.text(self.g.ortho["word_separator"]))
        if last and len(texts) > 1:
            joined = separator.join(texts[:-1]) + last + texts[-1]
        else:
            joined = separator.join(texts)
        clause.add([joined], kind="list", role=part["list"], quoted=True, bind=bool(part.get("bind")))
        self._finish(clause, part, joined)

    def _cite(self, clause, part, roles):
        opening, closing = self.g.ortho["cite"]
        groups = []
        for group in part["cite"]:
            inner = ClauseRealizer(self.g)
            inner._context = dict(self._context, cited=True)
            sub = Clause()
            for piece in group:
                inner._part(sub, piece, roles)
            groups.append(sub)
        texts = [sub.text(self.g.ortho["word_separator"]) for sub in groups if sub.words]
        numbers = [word["number"] for sub in groups for word in sub.words if word.get("number") is not None]
        clause.add([opening + self.g.ortho["cite_separator"].join(texts) + closing], kind="cite",
                   cited=True, bind=True)
        clause.words[-1]["cited_numbers"] = numbers


def finish_sentence(grammar, text, sentence):
    """Sentence punctuation and the declared capital."""
    mark = grammar.ortho["punctuation"].get(sentence, "")
    if grammar.ortho.get("initial_capital") and text:
        text = text[:1].upper() + text[1:]
    return text + mark


def copy_candidate(candidate):
    return copy.deepcopy(candidate)

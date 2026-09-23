"""The only path from meaning to sentence.

    MARCO reasoning
      -> Meaning Graph        meaning.py       no language in it
      -> Utterance Intent     intent.py        why this is said
      -> Discourse Planner    discourse.py     what to say, what to omit
      -> Expression Selector  expression.py    which way of saying it fits here
      -> Grammar Realizer     grammar.py       particles, endings, inflection, order
      -> Surface Sentence
      -> Semantic Check       check.py         parse the sentence back; meaning unchanged?

``realize(meaning, intent, language)`` is called once per dialogue turn
(``reasoning_context.ReasoningContext.turn``). ``meaning`` is the turn result.
A turn the realizer can build a Meaning Graph for is realized, in the language
of the pack or of the companion that answered. Any other turn keeps the
sentence the engine built: the realizer never composes from a sentence.
Every realized clause passes the semantic check or is not emitted; when no
declared expression passes, the turn is held with the declared hold.
"""
import collections
import copy

from marco.language.realizer import discourse, expression, intent as intents, meaning as mg
from marco.language.realizer.check import Checker
from marco.language.realizer.grammar import ClauseRealizer, Grammar, RealizationError, finish_sentence
from marco.language.realizer.packs import Language, available, language as load_language, register, stem_of


class Realizer:
    """One realizer: its reports, its learned expressions, its context.

    ``overrides`` maps a language stem to replaced declarations (tests inject
    faults this way). ``learning`` turns on expression learning from observed
    user sentences (``learning.py``).
    """

    def __init__(self, *, context=None, overrides=None, learning=False):
        self.context = dict(context or {})
        self.overrides = dict(overrides or {})
        self._languages = {}
        self._models = {}
        self._conversation = None
        self.reports = collections.deque(maxlen=500)
        self.learning = None
        if learning:
            from marco.language.realizer.learning import LearnedExpressions
            self.learning = LearnedExpressions(self)

    # languages ------------------------------------------------------------
    def language(self, stem):
        if stem in self.overrides:
            if stem not in self._languages:
                self._languages[stem] = Language(stem, self.overrides[stem])
            return self._languages[stem]
        return load_language(stem, self._models.get(stem))

    def learned(self, stem):
        return self.learning.candidates(stem, self._conversation) if self.learning else []

    def _learning_declared(self, stem):
        """Live learning runs only where the language's realizer file declares it."""
        return bool(((self.language(stem).decl.get("learning") or {}).get("live")))

    # entry points -----------------------------------------------------------
    def realize(self, meaning, intent, language) -> str:
        text, _report = self.realize_with_report(meaning, intent, language)
        return text

    def realize_with_report(self, result, intent, language):
        model = language if hasattr(language, "parser") else None
        speaker = stem_of(language)
        if model is not None and speaker:
            register(speaker, model)
        # The conversation's own language (its words); a companion model speaks the reply.
        said_in = (result.get("meaning") or {}).get("conversation_language") if isinstance(
            result.get("meaning"), dict) else None
        source = stem_of(said_in) if said_in else speaker
        report = {"realized": False, "intent": intent, "source": source}
        if not available(source, model if source == speaker else None):
            report["reason"] = "no_declarations"
            return self._passthrough(result, report)
        meaning = result.get("meaning") if isinstance(result.get("meaning"), dict) else {}
        self._conversation = meaning.get("conversation")
        text, report = self._realize(result, report, source, model)
        if self.learning is None and self._learning_declared(source):
            from marco.language.realizer.learning import LearnedExpressions
            self.learning = LearnedExpressions(self)
        if self.learning is not None:
            # Learned after the turn is said: a sentence never confirms itself.
            report["learned"] = [c["id"] for c in self.learning.observe(result, source)]
        return text, report

    def _realize(self, result, report, source, model):
        graph = mg.build(result, source)
        report["language"] = graph["answer_language"]
        if graph["answer_language"] != source and not available(
                graph["answer_language"], model if stem_of(model) == graph["answer_language"] else None):
            report["reason"] = "no_declarations"
            return self._passthrough(result, report)
        if model is not None:
            self._models[stem_of(model)] = model
        if not intents.plan(graph):
            report["reason"] = "no_plan"
            return self._passthrough(result, report)
        text, detail = self.realize_graph(graph, graph["answer_language"])
        report.update(detail)
        report["realized"] = True
        self.reports.append(report)
        return text, report

    def _passthrough(self, result, report):
        self.reports.append(report)
        return result.get("answer"), report

    def build_graph(self, result, language):
        """The Meaning Graph of a turn result with its acts planned, or None."""
        graph = mg.build(result, stem_of(language))
        return graph if intents.plan(graph) else None

    # realization ----------------------------------------------------------
    def realize_graph(self, graph, target):
        lang = self.language(target)
        grammar = Grammar(lang)
        factory = lambda: ClauseRealizer(grammar)
        checker = Checker(lang, grammar, factory)
        register = self.context.get("register") or lang.decl.get("register", {}).get("default")
        sentences, counts = discourse.plan(graph)
        separator = grammar.ortho["word_separator"]
        texts, clauses_report = [], []
        frames = mg.meaning_declarations()["frames"]
        for sentence in sentences:
            parts = []
            coordination = lang.decl.get("coordination", {}).get(sentence["clauses"][0]["prop"]["frame"], {})
            prefer = None
            for index, planned in enumerate(sentence["clauses"]):
                last = index == len(sentence["clauses"]) - 1
                chosen = self._clause(lang, grammar, checker, planned, sentence["sentence"], register,
                                      gap=bool(coordination.get("gap_predicate")) and not last,
                                      frames=frames, prefer=prefer)
                prefer = chosen["report"].get("candidate")
                clauses_report.append(chosen["report"])
                if chosen["clause"] is None:
                    if planned["prop"].get("optional"):
                        # A clause the plan marks optional is left out when the language cannot say it.
                        chosen["report"]["omitted"] = True
                        continue
                    return self._hold(lang, grammar, checker, register, counts, clauses_report)
                parts.append(chosen["clause"].text(separator))
            if not parts:
                continue
            if len(parts) > 1:
                if coordination.get("separator") == "list" and grammar.ortho.get("list_last"):
                    body = grammar.ortho["list_separator"].join(parts[:-1]) + grammar.ortho["list_last"] + parts[-1]
                else:
                    joint = grammar.symbol(coordination.get("separator", "comma")) + separator
                    body = joint.join(parts)
            else:
                body = parts[0]
            if sentence.get("lead"):
                lead = self._lead(lang, grammar, checker, sentence["lead"], register)
                if lead is None:
                    return self._hold(lang, grammar, checker, register, counts, clauses_report)
                body = lead + separator + body
            texts.append(finish_sentence(grammar, body, sentence["sentence"]))
        text = grammar.ortho["sentence_separator"].join(texts)
        trace = {"meaning": [{"id": p["id"], "frame": p["frame"], "polarity": p.get("polarity", True)}
                             for p in graph["props"]],
                 "intent": [act["intent"] for act in graph["acts"]],
                 "discourse": [{"act": s["act"], "props": [c["prop"]["id"] for c in s["clauses"]],
                                "elided": [sorted(c["elided"]) for c in s["clauses"]]} for s in sentences],
                 "expression": [c["candidate"] for c in clauses_report if not c.get("omitted")],
                 "grammar": [c["pieces"] for c in clauses_report if not c.get("omitted")],
                 "check": [c["parse"] for c in clauses_report if not c.get("omitted")],
                 # Said in words in the reply; named by id here.
                 "rules": [(p["roles"].get(frames.get(p["frame"], {}).get("select_by", {}).get("role")) or {}).get("id")
                           for p in graph["props"] if frames.get(p["frame"], {}).get("select_by")],
                 # Every repair the turn rests on, in full (rule, operations, cost), whether said or not.
                 "repairs": [{key: report.get(key) for key in mg.meaning_declarations()["frames"][
                     mg.meaning_declarations()["repair_notes"]["full_frame"]]["roles"] if key in report}
                     for report in graph.get("repairs") or []]}
        return text, {"held": False, "clauses": clauses_report, "discourse": counts,
                      "acts": [act["intent"] for act in graph["acts"]], "text": text, "trace": trace}

    def _clause(self, lang, grammar, checker, planned, sentence, register, *, gap, frames, prefer=None):
        prop = planned["prop"]
        elided_answer = {r for r in planned["elided"] if prop.get("answer")}
        attempts = []
        pool = expression.candidates(lang.decl, prop, register=register, intent=planned["act"],
                                     learned=self.learned(lang.stem), prefer=prefer)
        for candidate in pool:
            keep = set(candidate.get("keep", []))
            elided = {r for r in planned["elided"] if not (r in keep and r in elided_answer)}
            try:
                clause = ClauseRealizer(grammar).realize(prop, candidate, elided=elided, sentence=sentence,
                                                         register=register, gap=gap)
                verdict = checker.check(prop, candidate, clause, elided=elided, sentence=sentence,
                                        register=register, frame_decl=frames.get(prop["frame"]),
                                        allow_repair=bool(candidate.get("learned")))
            except RealizationError as exc:
                attempts.append({"candidate": candidate.get("id"), "error": str(exc)})
                continue
            attempts.append({"candidate": candidate.get("id"), "check": verdict})
            if verdict["ok"]:
                return {"clause": clause, "report": {"frame": prop["frame"], "prop": prop.get("id"),
                                                     "candidate": candidate.get("id"),
                                                     "pieces": clause.pieces(),
                                                     "text": clause.text(grammar.ortho["word_separator"]),
                                                     "learned": bool(candidate.get("learned")),
                                                     "elided": sorted(elided), "parse": verdict["parse"],
                                                     "attempts": attempts}}
        return {"clause": None, "report": {"frame": prop["frame"], "prop": prop.get("id"), "candidate": None,
                                           "attempts": attempts, "blocked": True}}

    def _lead(self, lang, grammar, checker, lead, register):
        parts = lang.decl.get("leads", {}).get(lead)
        if not parts:
            return None
        clause = ClauseRealizer(grammar).realize({"roles": {}, "polarity": True}, {"parts": parts}, register=register)
        words = ["".join(w["pieces"]) for w in clause.words]
        if checker.numbers(grammar.ortho["word_separator"].join(words)) or checker.negated(words):
            return None
        return clause.text(grammar.ortho["word_separator"])

    def _hold(self, lang, grammar, checker, register, counts, clauses_report):
        """No declared expression kept the meaning: say that the answer is held, nothing else."""
        prop = {"frame": "not_phrased", "roles": {}, "polarity": True}
        text = None
        for candidate in lang.decl.get("expressions", {}).get("not_phrased", []):
            try:
                clause = ClauseRealizer(grammar).realize(prop, candidate, register=register)
            except RealizationError:
                continue
            verdict = checker.check(prop, candidate, clause, elided=(), sentence="declarative",
                                    register=register, frame_decl={})
            text = finish_sentence(grammar, clause.text(grammar.ortho["word_separator"]), "declarative")
            if verdict["ok"]:
                break
        return text or "", {"held": True, "clauses": clauses_report, "discourse": counts, "text": text}


_default = Realizer()


def default_realizer():
    return _default


def realize(meaning, intent, language) -> str:
    """Return the sentence for ``meaning``.

    ``meaning``: the turn result. ``intent``: the turn's status (``answered``,
    ``unresolved``, ...). ``language``: the language pack path, such as
    ``styles/english.json``, or ``None`` when the dialogue uses the declared default.
    """
    return _default.realize(meaning, intent, language)


def last_report():
    return copy.deepcopy(_default.reports[-1]) if _default.reports else None


def follow_up(text, language):
    """Which declared follow-up about the conversation's own replies ``text`` is, or None.

    A language file lists them under ``follow_ups`` by kind (``why_last``: why the last
    answer or correction came out so; ``repairs``: what a reading changed). Only the
    listed phrasings count, compared after the language's own punctuation and case.
    """
    stem = stem_of(language)
    if not available(stem, language if hasattr(language, "parser") else None):
        return None
    decl = load_language(stem, language if hasattr(language, "parser") else None).decl
    marks = "".join(decl["orthography"]["punctuation"].values())
    separator = decl["orthography"]["word_separator"]

    def plain(value):
        return separator.join(str(value).strip().strip(marks).lower().split())
    said = plain(text)
    for kind, phrasings in (decl.get("follow_ups") or {}).items():
        if not kind.startswith("_") and said in {plain(p) for p in phrasings}:
            return kind
    return None

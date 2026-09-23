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
from marco.language.realizer.packs import Language, available, language as load_language, stem_of


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
        return self.learning.candidates(stem) if self.learning else []

    # entry points -----------------------------------------------------------
    def realize(self, meaning, intent, language) -> str:
        text, _report = self.realize_with_report(meaning, intent, language)
        return text

    def realize_with_report(self, result, intent, language):
        source = stem_of(language)
        model = language if hasattr(language, "parser") else None
        report = {"realized": False, "intent": intent, "source": source}
        if not available(source, model):
            report["reason"] = "no_declarations"
            return self._passthrough(result, report)
        if self.learning is not None:
            self.learning.observe(result, source)
        graph = mg.build(result, source)
        report["language"] = graph["answer_language"]
        if graph["answer_language"] != source and not available(graph["answer_language"]):
            report["reason"] = "no_declarations"
            return self._passthrough(result, report)
        if model is not None and graph["answer_language"] == source:
            load_language(source, model)
            self._models[source] = model
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
            for index, planned in enumerate(sentence["clauses"]):
                last = index == len(sentence["clauses"]) - 1
                chosen = self._clause(lang, grammar, checker, planned, sentence["sentence"], register,
                                      gap=bool(coordination.get("gap_predicate")) and not last,
                                      frames=frames)
                clauses_report.append(chosen["report"])
                if chosen["clause"] is None:
                    return self._hold(lang, grammar, checker, register, counts, clauses_report)
                parts.append(chosen["clause"].text(separator))
            if len(parts) > 1:
                if coordination.get("separator") == "list" and grammar.ortho.get("list_last"):
                    body = grammar.ortho["list_separator"].join(parts[:-1]) + grammar.ortho["list_last"] + parts[-1]
                else:
                    joint = grammar.symbol(coordination.get("separator", "comma")) + separator
                    body = joint.join(parts)
            else:
                body = parts[0]
            if sentence.get("lead"):
                lead = self._lead(lang, grammar, checker, sentence["lead"])
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
                 "expression": [c["candidate"] for c in clauses_report],
                 "grammar": [c["pieces"] for c in clauses_report],
                 "check": [c["parse"] for c in clauses_report]}
        return text, {"held": False, "clauses": clauses_report, "discourse": counts,
                      "acts": [act["intent"] for act in graph["acts"]], "text": text, "trace": trace}

    def _clause(self, lang, grammar, checker, planned, sentence, register, *, gap, frames):
        prop = planned["prop"]
        elided_answer = {r for r in planned["elided"] if prop.get("answer")}
        attempts = []
        pool = expression.candidates(lang.decl, prop, register=register, intent=planned["act"],
                                     learned=self.learned(lang.stem))
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
                                                     "learned": bool(candidate.get("learned")),
                                                     "elided": sorted(elided), "parse": verdict["parse"],
                                                     "attempts": attempts}}
        return {"clause": None, "report": {"frame": prop["frame"], "prop": prop.get("id"), "candidate": None,
                                           "attempts": attempts, "blocked": True}}

    def _lead(self, lang, grammar, checker, lead):
        parts = lang.decl.get("leads", {}).get(lead)
        if not parts:
            return None
        clause = ClauseRealizer(grammar).realize({"roles": {}, "polarity": True}, {"parts": parts})
        words = ["".join(w["pieces"]) for w in clause.words]
        if checker.numbers(" ".join(words)) or checker.negated(words):
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

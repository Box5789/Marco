"""Load the realizer's declarations and the language pack pieces it reuses.

Two sources per language, both data:

* ``marco/language/realizer/<stem>.json`` — the realizer's own declarations
  (expressions, lexicon, cases, endings, reading rules);
* the language pack ``styles/<stem>.json`` through its parser — particle
  mates, the inflection grammar, negation, numerals, senses, romanization.

``meaning.json`` holds what is shared by every language.
"""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


@lru_cache(maxsize=1)
def meaning_declarations():
    return json.loads((HERE / "meaning.json").read_text(encoding="utf-8"))


def stem_of(language):
    """``styles/english.json`` -> ``english``; a model -> its language; ``None`` -> the declared default."""
    if hasattr(language, "parser") and hasattr(language, "sources"):
        paths = [source["path"] for source in language.sources if source["path"].startswith("styles/")]
        return Path(paths[0]).stem if paths else None
    if not language:
        # The same selection every other language-choosing path makes:
        # NAI_LANGUAGE, then KG_LANG, then the one declared default.
        from language_components import _language_path
        return _language_path(None).stem
    return Path(str(language)).stem


@lru_cache(maxsize=16)
def _declared_pack(stem):
    path = HERE / (stem + ".json")
    if stem == "meaning" or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("pack", "")


def available(stem, model=None):
    """Realizer declarations exist for ``stem`` and its language pack can be read."""
    declared = _declared_pack(stem) if stem else None
    if declared is None:
        return False
    return model is not None or (ROOT / declared).is_file()


class Language:
    """One language: the realizer's declarations and the pack parser's pieces."""

    def __init__(self, stem, declarations=None, model=None):
        self.stem = stem
        self.decl = copy.deepcopy(declarations) if declarations is not None else json.loads(
            (HERE / (stem + ".json")).read_text(encoding="utf-8"))
        if model is None:
            from pack_model import development_model
            model = development_model(stem)
        self.parser = model.parser()
        pack_path = ROOT / self.decl["pack"]
        # The pack's raw declarations, for the one field its loaded component
        # does not carry (the negation marker). A packed model without the file
        # on disk has no marker; the check then reads polarity with the parser.
        self.style = json.loads(pack_path.read_text(encoding="utf-8")) if pack_path.is_file() else {}
        component = self.parser.language_pack
        self.mates = dict(component.get("particle_mates", {}))
        self.mate_exceptions = dict(component.get("particle_exceptions", {}))
        self.pack_negation = dict(component.get("negation", {}))
        self.senses = dict(component.get("senses", {}))
        self.romanization = copy.deepcopy(component.get("romanization", {}))
        self.numerals = copy.deepcopy(self.parser.data.get("numerals", {}))
        # The pack's own negation marker pattern, named by the key the realizer
        # file declares. The semantic check reads polarity with it.
        marker = self.style.get(self.decl.get("negation_marker_key") or "")
        self.negation_marker = re.compile(marker) if isinstance(marker, str) and marker else None
        self.inflection = self._grammar()

    def _grammar(self):
        grammar = copy.deepcopy(self.parser.inflection_grammar)
        declared = self.decl.get("grammar", {})
        grammar.setdefault("endings", {}).update(copy.deepcopy(declared.get("endings", {})))
        grammar["kinds"] = list(dict.fromkeys(list(grammar.get("kinds", [])) + list(declared.get("kinds", []))))
        lexicon = copy.deepcopy(grammar.get("lexicon", {}))
        for lemma, forms in self.decl.get("lexicon_forms", {}).items():
            lexicon.setdefault(lemma, {}).update(forms)
        if lexicon:
            grammar["lexicon"] = lexicon
        grammar.setdefault("max_forms", 32)
        return grammar

    def concept(self, word):
        return self.senses.get(word) or self.senses.get(str(word).lower())

    def words_for(self, concept):
        return [word for word, value in self.senses.items() if value == concept]


_languages = {}


_registered = {}


def register(stem, model):
    """The model a dialogue speaks for this language; pack pieces come from it."""
    _registered[stem] = model


def language(stem, model=None):
    model = model if model is not None else _registered.get(stem)
    if model is not None:
        key = (stem, id(model))
        if key not in _languages:
            _languages[key] = Language(stem, model=model)
        return _languages[key]
    if stem not in _languages:
        _languages[stem] = Language(stem)
    return _languages[stem]


def with_declarations(stem, declarations):
    """A Language whose realizer declarations are replaced (used to inject faults)."""
    return Language(stem, declarations)

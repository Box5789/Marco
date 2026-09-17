"""A selected model's immutable source assets, independent of its host directory.

Pack construction selects the language and axiom files once. Runtime consumers
receive this object explicitly; an absent component is empty, never a request
to load a different model beside the engine. Compiled parsers are derived state.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from language_components import decode_language_pack


class ModelError(ValueError):
    pass


def descriptor(assets, language=None):
    languages = sorted(p for p in assets if p.startswith("styles/") and p.endswith(".json"))
    if language is None:
        preferred = [p for p in languages if json.loads(assets[p]).get("default_model_language") is True]
        if len(preferred) > 1:
            raise ModelError("multiple_default_model_languages")
        language = preferred[0] if preferred else (languages[0] if len(languages) == 1 else None)
        if languages and language is None:
            raise ModelError("select_model_language_explicitly")
    if language is not None and language not in languages:
        raise ModelError("model_language_not_in_pack")
    relational = sorted(p for p in assets if p.startswith("models/") and p.endswith(".json"))
    if len(relational) > 1:
        raise ModelError("multiple_relational_models")
    return {"format": "nai-model", "version": 1, "language": language,
            "axioms": sorted(p for p in assets if p.startswith("axioms/") and p.endswith(".json")),
            # 관계 표현/규칙 학습은 이 선택적 자산에만 든다. 코드 옆 환경 변수나
            # 작성 트리의 모델을 팩 런타임이 찾아 쓰지 않는다.
            "relational_model": relational[0] if relational else None}


class PackModel:
    def __init__(self, manifest, assets):
        declaration = manifest.get("model")
        # Old packs have no new reasoning declaration. Do not borrow one from
        # the current working directory, environment, or another running pack.
        if declaration is None and manifest.get("version") == 2:
            declaration = {"format": "nai-model", "version": 1, "language": None, "axioms": []}
        if (not isinstance(declaration, dict) or declaration.get("format") != "nai-model"
                or declaration.get("version") != 1):
            raise ModelError("unsupported_model_declaration")
        language = declaration.get("language")
        axiom_paths = declaration.get("axioms")
        relational_path = declaration.get("relational_model")
        if (not isinstance(axiom_paths, list) or not all(isinstance(p, str) for p in axiom_paths)
                or len(set(axiom_paths)) != len(axiom_paths)):
            raise ModelError("invalid_model_axiom_paths")
        if language is not None and not isinstance(language, str):
            raise ModelError("invalid_model_language_path")
        if relational_path is not None and not isinstance(relational_path, str):
            raise ModelError("invalid_relational_model_path")
        if relational_path is not None and not (relational_path.startswith("models/")
                                                and relational_path.endswith(".json")):
            raise ModelError("relational_model_outside_models")
        paths = ([language] if language is not None else []) + axiom_paths + (
            [relational_path] if relational_path is not None else [])
        if len(set(paths)) != len(paths) or any(p not in assets for p in paths):
            raise ModelError("model_asset_not_in_pack")
        if language is not None and not (language.startswith("styles/") and language.endswith(".json")):
            raise ModelError("model_language_outside_styles")
        if any(not (p.startswith("axioms/") and p.endswith(".json")) for p in axiom_paths):
            raise ModelError("model_axioms_outside_axioms")
        self.sources = [{"path": p, "sha256": hashlib.sha256(assets[p]).hexdigest()} for p in paths]
        self.fingerprint = hashlib.sha256(json.dumps(self.sources, sort_keys=True).encode()).hexdigest()
        self._language = decode_language_pack(json.loads(assets[language]) if language else {}, language or "")
        self._axioms = {"rules": [], "mutable_predicates": [], "numeric_updates": {},
                        "comparisons": {}, "operators": []}
        rule_ids = set()
        for path in axiom_paths:
            doc = json.loads(assets[path])
            if not isinstance(doc, dict) or doc.get("schema") != "nai-axioms-v1":
                raise ModelError("unsupported_axiom_schema: " + path)
            for key in ("rules", "mutable_predicates", "operators"):
                if not isinstance(doc.get(key, []), list):
                    raise ModelError("invalid_axiom_list: " + key)
            for rule in doc.get("rules", []):
                if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or rule["id"] in rule_ids:
                    raise ModelError("invalid_or_duplicate_rule_id")
                rule_ids.add(rule["id"])
                self._axioms["rules"].append(deepcopy(rule))
            for key in ("mutable_predicates", "operators"):
                for value in doc.get(key, []):
                    if not isinstance(value, str) or not value:
                        raise ModelError("invalid_axiom_name: " + key)
                    if value not in self._axioms[key]:
                        self._axioms[key].append(value)
            updates = doc.get("numeric_updates", {})
            if not isinstance(updates, dict):
                raise ModelError("invalid_numeric_updates")
            for name, update in updates.items():
                if name in self._axioms["numeric_updates"]:
                    raise ModelError("duplicate_numeric_update: " + name)
                self._axioms["numeric_updates"][name] = deepcopy(update)
            # 견주기. 어느 성질을 어떤 연산으로 재는지는 여기서 선언하고, 재는
            # 쪽은 성질 이름을 모른 채 돈다 — 자리나 관계를 견주려면 줄이 늘지
            # 코드가 늘지 않는다. 연산은 글자가 아니라 이름이라 언어에 안 매인다.
            comparisons = doc.get("comparisons", {})
            if not isinstance(comparisons, dict):
                raise ModelError("invalid_comparisons")
            for name, spec in comparisons.items():
                if name in self._axioms["comparisons"]:
                    raise ModelError("duplicate_comparison: " + name)
                if (not isinstance(spec, dict) or not isinstance(spec.get("target"), str)
                        or not spec["target"] or spec.get("op") not in (">", "<", "==")):
                    raise ModelError("invalid_comparison: " + name)
                self._axioms["comparisons"][name] = deepcopy(spec)
        relational = self._language["relations"]
        if not isinstance(relational, dict) or any(k in relational for k in self._axioms):
            raise ModelError("axioms_must_not_be_in_language_component")
        base_relational = {"schema": "annotated-relations-v1", "examples": [], "answer_suffix": "",
                           "context_replies": {}, **deepcopy(relational), **deepcopy(self._axioms)}
        self._relational = self._load_relational_model(
            base_relational, json.loads(assets[relational_path]) if relational_path else None)

    @staticmethod
    def _load_relational_model(base, learned):
        """검증한 표현·규칙 확장만 팩 안에서 다시 쓴다.

        ``RelationalParser.save``는 전체 모델을 내보낸다. 팩의 언어·공리를
        그 파일이 몰래 바꾸지 못하도록, 바탕과 다른 것은 추가 ``examples``와
        추가 규칙뿐인지 확인한다. 따라서 패키지 이동 뒤에도 학습 근거는
        유지하면서 팩 선언과 충돌하지 않는다.
        """
        if learned is None:
            return base
        if not isinstance(learned, dict) or learned.get("schema") != "annotated-relations-v1":
            raise ModelError("unsupported_relational_model")
        mutable = {"examples", "rules"}
        if set(learned) != set(base):
            raise ModelError("relational_model_schema_mismatch")
        for key in set(base) - mutable:
            if learned[key] != base[key]:
                raise ModelError("relational_model_changes_pack_declaration: " + key)
        if (not isinstance(learned["examples"], list) or not isinstance(learned["rules"], list)
                or learned["examples"][:len(base["examples"])] != base["examples"]
                or learned["rules"][:len(base["rules"])] != base["rules"]):
            raise ModelError("relational_model_not_an_extension")
        return deepcopy(learned)

    @property
    def language(self):
        return deepcopy(self._language)

    @property
    def relational_data(self):
        return deepcopy(self._relational)

    def permits(self, operation):
        return operation in self._axioms["operators"]

    def parser(self):
        from relational_semantics import RelationalParser
        return RelationalParser(data=self._relational, language_pack=self._language)

    def parse_expression(self, text):
        from expression_graph import parse
        return parse(text, grammar=self._language["verbal_expressions"],
                     numerals=self._relational.get("numerals", {}))

    def format_output(self, question, answer):
        from output_contracts import apply
        return apply(question, answer, config=self._language["output_contracts"])

    def number_answer(self, value, unit=""):
        template = self._language["state_answers"].get("value", "{value}{unit}")
        return template.format(value=value, unit=unit)


@lru_cache(maxsize=8)
def _development_snapshot(paths_and_revisions, language):
    assets = {name: Path(path).read_bytes() for name, path, _stamp, _size in paths_and_revisions}
    return PackModel({"version": 3, "model": descriptor(assets, language)}, assets)


def development_model(language=None):
    """Explicit source-tree tooling, not a fallback used by a selected kgpack.

    The loose files here are exactly the authoring sources that pack creation
    includes. The cache follows their revisions; callers cannot mutate it.
    """
    from language_components import _language_path
    root = Path(__file__).resolve().parent
    selected = _language_path(language)
    files = [("styles/" + selected.name, selected)]
    files += [("axioms/" + path.name, path) for path in sorted((root / "axioms").glob("*.json"))]
    revisions = tuple((name, str(path), path.stat().st_mtime_ns, path.stat().st_size) for name, path in files)
    return _development_snapshot(revisions, files[0][0])

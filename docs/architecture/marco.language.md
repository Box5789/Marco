# `marco.language`

Text and structure: language packs, parsing, realization. Written 2026-09-23
against commit `78bd062`.

## Purpose

Be the one place where MARCO turns between language and meaning. Today only the
output direction exists, as one function: `realize(meaning, intent, language)`.
The rest of the language layer (packs, parsing, particles) still lives in root
modules and moves here only when the frozen refactor runs.

## Owns

- The exported name `realize`, re-exported from
  [`marco.language.realizer`](marco.language.realizer.md)
  ([marco/language/__init__.py](../../marco/language/__init__.py)).
- `__all__ == ["realize"]`.

## Does not own

- Parsing. `relational_semantics.py`, `frame_induction.py`,
  `input_understanding.py` and `semantic_parser.py` are root modules.
- Language packs. `styles/한국어.json` and `styles/english.json` are read by
  `pack_model.py` and `reasoning_context.py`.
- Korean particles and inflection (`hangul.py`), and the graph engine's reply
  templates (`engine.py` `compose_line`). The `.kg` graph dialogue in `engine.py`
  does not call `realize`.

## Depends on

- `marco.language.realizer`. No other import.

## Public interface

| Name | Signature | Proof |
| --- | --- | --- |
| `realize` | `realize(meaning, intent, language) -> str` | `tests/test_language_seam.py::test_realize_is_exported_with_the_declared_signature` asserts `__all__`, the three parameter names and the `str` return annotation |

Its one caller is `ReasoningContext.turn` in
[reasoning_context.py:2731](../../reasoning_context.py). See the realizer
document for what the function does today.

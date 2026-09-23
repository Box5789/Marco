# `marco.language.realizer`

The only path from meaning to sentence. Written 2026-09-23 against commit
`78bd062`.

## Purpose

Hold the function that turns a turn's meaning into its sentence, so that the
language realizer goal (W1, `docs/ko/2026-09-22-realization-next-goal.md`)
can replace the body without touching the dialogue. Today `realize` is a stub:
it returns the sentence the dialogue already built, byte for byte.

## Owns

- `realize(meaning, intent, language) -> str`
  ([marco/language/realizer/__init__.py](../../marco/language/realizer/__init__.py)).
  The body is `return meaning["answer"]`.

## Does not own

- Building the sentence. The sentence in `meaning["answer"]` is built before
  the call, by `reasoning_context.py` and the language pack's templates.
- The call site. `ReasoningContext.turn`
  ([reasoning_context.py:2731](../../reasoning_context.py)) decides when to call
  and which pack path to pass.
- The graph engine's replies. `engine.py` builds its own lines (`compose_line`)
  and does not pass them through `realize`.
- The planned modules `meaning.py`, `intent.py`, `discourse.py`,
  `expression.py`, `grammar.py` (structure audit §A6). None exists.

## Depends on

- Nothing. The module has no imports.

## Public interface

`realize(meaning, intent, language) -> str`

| Argument | Today |
| --- | --- |
| `meaning` | the turn result, a `dict` whose `"answer"` holds the sentence |
| `intent` | the turn's `status` (`answered`, `unresolved`, ...) |
| `language` | the pack path, `styles/한국어.json` or `styles/english.json`, or `None` for the declared default |

| Claim | Test |
| --- | --- |
| Output is byte-identical to the dialogue before the seam, over the 20 phrasings of `docs/ko/repair-and-english-2026-09-22/unseen-before.json` | `tests/test_language_seam.py::test_output_is_byte_identical_to_the_dialogue_before_the_seam` (20 parametrized cases) |
| The 20 phrasings are exactly the recorded cases | `tests/test_language_seam.py::test_the_twenty_phrasings_cover_every_recorded_case` |
| Every answered turn passes through `realize` exactly once, in both packs | `tests/test_language_seam.py::test_every_answered_turn_passes_through_realize_once` |

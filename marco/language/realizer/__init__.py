"""The only path from meaning to sentence.

``realize`` is a stub. The dialogue calls it once per turn
(``reasoning_context.ReasoningContext.turn``). Today it returns the sentence
that the dialogue already built, byte for byte. The realizer goal replaces
the body, not the signature or the call site.
"""


def realize(meaning, intent, language) -> str:
    """Return the sentence for ``meaning``.

    ``meaning``: the turn result, a dict whose ``answer`` holds the sentence
    built today. ``intent``: the turn's status (``answered``, ``unresolved``,
    ...). ``language``: the language pack path, such as ``styles/english.json``,
    or ``None`` when the dialogue uses the declared default.
    """
    return meaning["answer"]

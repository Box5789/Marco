"""Text and structure: language packs, parsing, realization.

Public today: ``realize(meaning, intent, language) -> str``. Pack loading and
parsing still live in the root modules until the refactor moves them here.
"""
from marco.language.realizer import realize

__all__ = ["realize"]

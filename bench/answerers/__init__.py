"""Answerers for ``bench/compare_models.py`` (goal C1): one small module per compared model.

Every answerer has the same shape, so the harness treats MARCO and the
language models alike:

  start(conversation_id, language)  a new conversation begins
  answer(history, utterance) -> str the reply text to one user turn; ``history``
                                    is every earlier turn of this conversation as
                                    ``{"user": ..., "reply": ...}`` in order
  restart()                         the process restarts over the same saved
                                    conversation (the gate's ``restart_before``);
                                    a model that is handed the whole history
                                    keeps it, so the default does nothing
  info                              what was run: model id, revision, parameters,
                                    quantization, prompt, temperature
  close()                           free the model

Nothing here calls a remote service.  Model weights come from the local
Hugging Face cache (``HF_HUB_OFFLINE=1`` is set before a model loads), so a
model that is not in the cache fails at ``load`` instead of being fetched.
"""
import importlib
import os

NAMES = ("always_hold", "marco", "gpt2", "qwen")


class Answerer:
    name = "answerer"
    info = {}
    language = "en"

    def start(self, conversation_id, language):
        self.conversation_id, self.language = conversation_id, language

    def answer(self, history, utterance):
        raise NotImplementedError

    def restart(self):
        return None

    def close(self):
        return None


def offline():
    """No network from here on: weights and tokenizers must already be cached."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def load(name, **options):
    """Build the answerer called ``name`` (one of ``NAMES``)."""
    if name not in NAMES:
        raise ValueError("unknown answerer %r; known: %s" % (name, ", ".join(NAMES)))
    module = importlib.import_module("answerers.%s" % name)
    return module.build(**options)

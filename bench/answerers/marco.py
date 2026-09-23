"""MARCO through the entry the gates use: ``views.kgpack_ui.AppState.turn``.

The packs are built exactly as ``bench/dialogue_gate.py run`` builds them (the
daily-reasoning graph plus the model files, one pack per language, the language
declared), each conversation gets its own overlay and conversation store, web
research is stubbed and counted, and ``restart()`` builds a new ``AppState``
over the same saved store.  The reply text is the one the gate's ``observe``
reads (``answer.answer``, else ``web_answer``).  The whole observation is kept
on ``last_observation`` so the same run can also be scored structurally by the
gates' own scorers.

MARCO keeps its own state, so ``history`` is not read: the conversation store
already holds every earlier turn.
"""
from pathlib import Path
import re
import sys
import tempfile
import time
from unittest.mock import patch

from answerers import Answerer

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "bench") not in sys.path:
    sys.path.insert(0, str(ROOT / "bench"))
import dialogue_gate as gate  # noqa: E402


class Marco(Answerer):
    name = "marco"

    def __init__(self, code_root=ROOT):
        self.code_root = Path(code_root).resolve()
        kgpack, self.ConversationStore, self.AppState = gate._import_code(self.code_root)
        self._temporary = tempfile.TemporaryDirectory(prefix="nai-compare-marco-")
        self.folder = Path(self._temporary.name)
        self.packs, sizes = {}, {}
        for code, style in gate.LANGUAGES.items():
            pack = self.folder / ("gate-%s.kgpack" % code)
            files = [self.code_root / "graphs/graph_일상추론.kg"] + kgpack.model_files(self.code_root)
            try:
                kgpack.write_pack(pack, files, root=self.code_root, language="styles/%s.json" % style)
            except TypeError:  # an older pack writer without a declared language
                kgpack.write_pack(pack, files, root=self.code_root)
            self.packs[code] = pack
            sizes[code] = pack.stat().st_size
        self.info = {"model": "marco", "entry": "views.kgpack_ui.AppState.turn",
                     "packs": "graphs/graph_일상추론.kg + kgpack.model_files(), one per language, "
                              "built as bench/dialogue_gate.py run builds them",
                     "pack_bytes": sizes, "parameters": 0,
                     "parameters_note": "no learned weights: declared rules, language packs and graphs",
                     "research": "stubbed; calls counted", "history": "not read; the conversation store keeps state"}
        self.last_observation = None
        self.state = None

    def _app(self):
        state = self.AppState(self.packs[self.language], overlay_root=self.home / "overlay")
        state.conversations = self.ConversationStore(self.home / "conversations.json")
        return state

    def start(self, conversation_id, language):
        super().start(conversation_id, language)
        self.home = self.folder / conversation_id
        self.state = self._app()
        self.chat = self.state.conversations.create_chat()["id"]
        # the gate's own session naming, so the runs are comparable
        self.session = "dialoguegate_" + re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id)
        self.last_observation = None

    def restart(self):
        self.state = self._app()

    def answer(self, history, utterance):
        self.last_observation = None
        start = time.perf_counter()
        offline = {"query": utterance, "sources": [], "verified": False}
        with patch.object(self.state.goals, "research", return_value=offline) as research:
            result = self.state.turn(utterance, self.session, conversation_id=self.chat)
        self.last_observation = gate.observe(result, research.call_count, (time.perf_counter() - start) * 1000)
        return self.last_observation["answer"] or ""

    def close(self):
        self._temporary.cleanup()


def build(code_root=ROOT, **_options):
    return Marco(code_root)

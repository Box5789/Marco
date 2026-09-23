"""The floor: the same decline to every turn, in the conversation's language."""
from answerers import Answerer

REPLY = {"ko": "모르겠습니다.", "en": "I do not know."}


class AlwaysHold(Answerer):
    name = "always_hold"
    info = {"model": "always_hold", "parameters": 0, "reply": REPLY,
            "note": "declines every turn; the floor every other row is read against"}

    def answer(self, history, utterance):
        return REPLY.get(self.language, REPLY["en"])


def build(**_options):
    return AlwaysHold()

"""GPT-2 (124M, ``openai-community/gpt2``): the owner's reference point, expected near zero.

A base language model, not instruction-tuned, so it gets a plain few-shot
prompt: one fixed header, a four-turn worked example in the conversation's
language (names and items that appear in neither frozen set), then the
conversation so far as ``User:`` / ``Assistant:`` lines and the new utterance.
Greedy decoding (temperature 0), at most ``MAX_NEW_TOKENS`` new tokens, the
reply cut at the first line break.  GPT-2 sees at most 1024 tokens: when the
prompt is longer, the oldest conversation turns are dropped (never the header
or the example) and the number dropped is kept per turn.
"""
from answerers import Answerer, offline

MODEL = "openai-community/gpt2"
REVISION = "607a30d783dfa663caf39e06633721c8d4cfcd7e"
MAX_NEW_TOKENS = 48
CONTEXT = 1024

HEADER = ("The following is a conversation between a user and an assistant. The assistant answers briefly, "
          "using only what the user said, and says that the information was not given when it was not.")
EXAMPLE = {
    "en": [("Gwen has four lemons and Otis has one.", "Noted."),
           ("Gwen gave Otis two lemons.", "Noted."),
           ("How many lemons does Otis have at the moment?", "Otis has 3 lemons."),
           ("What colour is the hat Otis wears?", "That information was not given.")],
    "ko": [("하윤은 레몬을 네 개 갖고 있고 지호는 한 개 갖고 있어요.", "알겠습니다."),
           ("하윤이 지호에게 레몬 두 개를 건넸어요.", "알겠습니다."),
           ("지호가 가진 레몬은 이제 몇 개예요?", "지호는 레몬이 3개 있습니다."),
           ("지호가 쓰는 모자는 무슨 색이에요?", "그 정보는 주어지지 않았습니다.")],
}


def _lines(pairs):
    return "".join("User: %s\nAssistant: %s\n" % (user, reply) for user, reply in pairs)


class GPT2(Answerer):
    name = "gpt2"

    def __init__(self, device=None):
        offline()
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        # CPU: a 124M model needs no accelerator, and the MPS allocator's pool would
        # triple the measured footprint without making the comparison any fairer
        self.device = device or "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION, dtype=torch.float32)
        self.model.to(self.device).eval()
        parameters = sum(p.numel() for p in self.model.parameters())
        self.info = {"model": MODEL, "revision": REVISION, "backend": "transformers %s, torch %s" % (
                         transformers.__version__, torch.__version__),
                     "device": self.device, "dtype": "float32", "quantization": "none", "parameters": parameters,
                     "decoding": "greedy (temperature 0)", "max_new_tokens": MAX_NEW_TOKENS,
                     "context_tokens": CONTEXT, "prompt": {"header": HEADER, "example": EXAMPLE,
                                                           "format": "header, blank line, example, blank line, "
                                                                     "conversation so far, 'User: <utterance>', "
                                                                     "'Assistant:'"},
                     "stop": "first line break"}
        self.last_meta = None

    def _prompt(self, history, utterance, skip):
        pairs = [(h["user"], h["reply"].replace("\n", " ").strip()) for h in history[skip:]]
        return "%s\n\n%s\n%sUser: %s\nAssistant:" % (HEADER, _lines(EXAMPLE.get(self.language, EXAMPLE["en"])),
                                                     _lines(pairs), utterance)

    def answer(self, history, utterance):
        torch = self.torch
        skip = 0
        while True:
            ids = self.tokenizer(self._prompt(history, utterance, skip), return_tensors="pt")["input_ids"]
            if ids.shape[1] + MAX_NEW_TOKENS <= CONTEXT or skip >= len(history):
                break
            skip += 1
        ids = ids[:, -(CONTEXT - MAX_NEW_TOKENS):].to(self.device)
        with torch.no_grad():
            out = self.model.generate(ids, attention_mask=torch.ones_like(ids), max_new_tokens=MAX_NEW_TOKENS,
                                      do_sample=False, pad_token_id=self.tokenizer.eos_token_id)
        text = self.tokenizer.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
        self.last_meta = {"prompt_tokens": int(ids.shape[1]), "dropped_turns": skip}
        return text.split("\n")[0].split("User:")[0].strip()

    def close(self):
        del self.model
        if self.device == "mps":
            self.torch.mps.empty_cache()


def build(device=None, **_options):
    return GPT2(device)

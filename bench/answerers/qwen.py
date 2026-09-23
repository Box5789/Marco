"""An instruction-tuned open model that handles Korean, 3B to 7B parameters, under 6 GB resident.

Preferred: ``Qwen/Qwen2.5-7B-Instruct`` quantized to 4 bits for MLX
(``mlx-community/Qwen2.5-7B-Instruct-4bit``, a conversion of that model by
``mlx-lm``) through ``mlx-lm`` on the Apple GPU.  Fallback when ``mlx-lm`` is
not usable: ``Qwen/Qwen2.5-3B-Instruct`` in bfloat16 through transformers on
MPS.  Which one ran is in ``info``.

Every turn gets the same prompt: the fixed system message ``SYSTEM`` (answer
briefly, in the user's language, from what was said; say that the information
was not given when it was not), then the whole conversation so far as chat
messages, then the utterance, through the model's own chat template.  Greedy
decoding (temperature 0), at most ``MAX_TOKENS`` new tokens.  No tools, no
retries, no examples.
"""
import json
from pathlib import Path

from answerers import Answerer, offline

MLX = {"model": "Qwen/Qwen2.5-7B-Instruct", "weights": "mlx-community/Qwen2.5-7B-Instruct-4bit",
       "revision": "c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed", "parameters": 7_615_616_512,
       "parameters_source": "Qwen2.5-7B-Instruct model card: 7.61B"}
TRANSFORMERS = {"model": "Qwen/Qwen2.5-3B-Instruct", "weights": "Qwen/Qwen2.5-3B-Instruct", "revision": None}
MAX_TOKENS = 160
SYSTEM = ("You are taking part in a conversation. The user tells you facts and asks questions about them. "
          "Use only what the user has said in this conversation. Answer briefly, in the language the user "
          "writes in. When the user states a fact, acknowledge it in a few words. When the conversation does "
          "not give the information a question needs, say that the information was not given; do not guess.")


def messages(history, utterance):
    out = [{"role": "system", "content": SYSTEM}]
    for turn in history:
        out += [{"role": "user", "content": turn["user"]}, {"role": "assistant", "content": turn["reply"]}]
    return out + [{"role": "user", "content": utterance}]


class QwenMLX(Answerer):
    name = "qwen"

    def __init__(self, cache_limit_mb=512):
        offline()
        import mlx.core as mx
        import mlx_lm
        from huggingface_hub import snapshot_download
        from mlx_lm.sample_utils import make_sampler
        self.mx, self.mlx_lm = mx, mlx_lm
        path = Path(snapshot_download(MLX["weights"], revision=MLX["revision"]))
        mx.set_cache_limit(cache_limit_mb * 1024 * 1024)
        self.model, self.tokenizer = mlx_lm.load(str(path))
        self.sampler = make_sampler(temp=0.0)
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        self.info = dict(MLX, backend="mlx-lm %s, mlx %s" % (mlx_lm.__version__, mx.__version__), device="Apple GPU",
                         quantization=dict(config.get("quantization") or {}, scheme="mlx affine"),
                         temperature=0, decoding="greedy", max_tokens=MAX_TOKENS, system=SYSTEM,
                         prompt="system message, then every earlier turn as user/assistant messages, then the "
                                "utterance, through the tokenizer's chat template with the generation prompt",
                         cache_limit_mb=cache_limit_mb)
        self.last_meta = None

    def answer(self, history, utterance):
        prompt = self.tokenizer.apply_chat_template(messages(history, utterance), add_generation_prompt=True,
                                                    tokenize=False)
        text = self.mlx_lm.generate(self.model, self.tokenizer, prompt=prompt, max_tokens=MAX_TOKENS,
                                    sampler=self.sampler, verbose=False)
        self.last_meta = {"prompt_tokens": len(self.tokenizer.encode(prompt)),
                          "peak_gpu_mb": round(self.mx.get_peak_memory() / 2 ** 20, 1)}
        return text.strip()

    def close(self):
        del self.model
        self.mx.clear_cache()


class QwenTransformers(Answerer):
    name = "qwen"

    def __init__(self, device=None):
        offline()
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(TRANSFORMERS["weights"])
        self.model = AutoModelForCausalLM.from_pretrained(TRANSFORMERS["weights"], dtype=torch.bfloat16)
        self.model.to(self.device).eval()
        self.info = dict(TRANSFORMERS, backend="transformers %s, torch %s" % (transformers.__version__,
                                                                            torch.__version__),
                         device=self.device, quantization="none (bfloat16)",
                         parameters=sum(p.numel() for p in self.model.parameters()), temperature=0,
                         decoding="greedy", max_tokens=MAX_TOKENS, system=SYSTEM)
        self.last_meta = None

    def answer(self, history, utterance):
        torch = self.torch
        prompt = self.tokenizer.apply_chat_template(messages(history, utterance), add_generation_prompt=True,
                                                    tokenize=False)
        ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"].to(self.device)
        with torch.no_grad():
            out = self.model.generate(ids, attention_mask=torch.ones_like(ids), max_new_tokens=MAX_TOKENS,
                                      do_sample=False)
        self.last_meta = {"prompt_tokens": int(ids.shape[1])}
        return self.tokenizer.decode(out[0, ids.shape[1]:], skip_special_tokens=True).strip()

    def close(self):
        del self.model


def build(backend="mlx", **options):
    if backend == "mlx":
        return QwenMLX(**options)
    if backend == "transformers":
        return QwenTransformers(**options)
    raise ValueError("backend is mlx or transformers, not %r" % backend)

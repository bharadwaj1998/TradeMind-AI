"""
TradeMind AI — AI Engine
Supports multiple backends: Google Gemini (recommended), Groq, or local Llama.

Recommended: Google Gemini 2.0 Flash
  - Free tier: 15 req/min, 1M tokens/day
  - Get key: https://aistudio.google.com/app/apikey
  - Fast, no crashes, no local GPU needed
"""
from typing import Optional

_SYSTEM_PROMPT = """You are TradeMind AI, an expert trading assistant for Indian stock markets (NSE/BSE).
You help the user analyse trades, manage risk, understand technical indicators,
and improve their trading strategy. Capital: ₹15,000 INR.
Keep answers concise (3-5 sentences). Use ₹ for money. This is educational, not financial advice."""


# ── Base class ────────────────────────────────────────────────────────────────
class BaseEngine:
    def is_loaded(self) -> bool:       return False
    def model_name(self) -> str:       return "None"
    def get_error(self) -> str:        return ""
    def chat(self, prompt: str, context: str = "") -> str:
        return "AI not configured. Go to Settings → AI Assistant."


# ── Google Gemini ─────────────────────────────────────────────────────────────
class GeminiEngine(BaseEngine):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._model_id = model
        self._error    = ""
        self._client   = None
        self._model    = None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name=model,
                system_instruction=_SYSTEM_PROMPT,
            )
            self._client = genai
            # Quick test
            self._model.generate_content("hi")
        except Exception as e:
            self._error = str(e)
            self._model = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def model_name(self) -> str:
        return f"Gemini {self._model_id}"

    def get_error(self) -> str:
        return self._error

    def chat(self, prompt: str, context: str = "") -> str:
        if not self.is_loaded():
            return f"Gemini not loaded: {self._error}"
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        try:
            resp = self._model.generate_content(full_prompt)
            return resp.text.strip()
        except Exception as e:
            return f"Gemini error: {e}"


# ── Groq (runs Llama/Gemma at high speed, free tier) ────────────────────────
class GroqEngine(BaseEngine):
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._model_id = model
        self._error    = ""
        self._client   = None
        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
            # Quick test
            self._client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
                model=self._model_id, max_tokens=5,
            )
        except Exception as e:
            self._error  = str(e)
            self._client = None

    def is_loaded(self) -> bool:
        return self._client is not None

    def model_name(self) -> str:
        return f"Groq {self._model_id}"

    def get_error(self) -> str:
        return self._error

    def chat(self, prompt: str, context: str = "") -> str:
        if not self.is_loaded():
            return f"Groq not loaded: {self._error}"
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
        ]
        if context:
            messages.append({"role": "user", "content": f"Context: {context}"})
            messages.append({"role": "assistant", "content": "Got it."})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._client.chat.completions.create(
                messages=messages, model=self._model_id,
                max_tokens=512, temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Groq error: {e}"


# ── Local Llama (kept for offline fallback) ──────────────────────────────────
class LlamaEngine(BaseEngine):
    def __init__(self, model_path: str, n_threads: int = 4, n_ctx: int = 4096):
        self._model_path = model_path
        self._error      = ""
        self._llm        = None
        from pathlib import Path
        if not Path(model_path).exists():
            self._error = f"Model file not found: {model_path}"
            return
        try:
            from llama_cpp import Llama
            self._llm = Llama(model_path=model_path, n_ctx=n_ctx,
                              n_threads=n_threads, verbose=False)
        except Exception as e:
            self._error = str(e)

    def is_loaded(self) -> bool:
        return self._llm is not None

    def model_name(self) -> str:
        from pathlib import Path
        return Path(self._model_path).stem

    def get_error(self) -> str:
        return self._error

    def chat(self, prompt: str, context: str = "") -> str:
        if not self.is_loaded():
            return f"Model not loaded: {self._error}"
        system = _SYSTEM_PROMPT + (f"\nContext: {context}" if context else "")
        full   = f"<s>[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{prompt} [/INST]"
        try:
            out = self._llm(full, max_tokens=512, temperature=0.7,
                            stop=["</s>", "[INST]"], echo=False)
            return out["choices"][0]["text"].strip()
        except Exception as e:
            return f"Inference error: {e}"


# ── Factory ───────────────────────────────────────────────────────────────────
def create_engine(provider: str, api_key: str = "", model_path: str = "",
                  model_id: str = "") -> BaseEngine:
    """
    provider: "gemini" | "groq" | "llama"
    """
    if provider == "gemini":
        return GeminiEngine(api_key, model=model_id or "gemini-2.0-flash")
    elif provider == "groq":
        return GroqEngine(api_key, model=model_id or "llama-3.3-70b-versatile")
    elif provider == "llama":
        return LlamaEngine(model_path)
    return BaseEngine()

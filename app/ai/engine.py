"""
TradeMind AI — Local Llama/Mistral Inference Engine
Wraps llama-cpp-python for offline AI chat & trade analysis.

The model runs entirely on your local CPU — no internet required.
Recommended model: Mistral-7B-Instruct-v0.2 Q4_K_M (~4 GB GGUF)

Usage:
    engine = LlamaEngine(model_path, n_threads=4, n_ctx=4096)
    if engine.is_loaded():
        reply = engine.chat("What is my risk on this trade?", context="...")
"""
import os
from pathlib import Path
from typing import Optional

try:
    from llama_cpp import Llama
    _HAS_LLAMA = True
except ImportError:
    _HAS_LLAMA = False

from app.config import AI_MAX_TOKENS, AI_TEMPERATURE, AI_CONTEXT_SIZE, AI_THREADS


# ── System prompt injected before every conversation ─────────────────────────
_SYSTEM_PROMPT = """You are TradeMind AI, an expert trading assistant specialised in Indian stock markets (NSE/BSE).
You help the user:
- Analyse their trades and P&L
- Assess risk and position sizing
- Explain technical indicators (RSI, VWAP, MACD, Bollinger Bands, etc.)
- Suggest improvements to their trading strategy
- Answer questions about market concepts

Keep responses concise (3-5 sentences) unless the user asks for detail.
Always remind the user that this is educational analysis, not financial advice.
Use Indian Rupee (₹) for all monetary values."""


class LlamaEngine:
    """
    Local LLM wrapper using llama-cpp-python.
    Thread-safe: inference is CPU-bound and blocking; call from a QThread.
    """

    def __init__(
        self,
        model_path: str,
        n_threads: int = AI_THREADS,
        n_ctx: int = AI_CONTEXT_SIZE,
    ):
        self._model_path = str(model_path)
        self._n_threads  = n_threads
        self._n_ctx      = n_ctx
        self._llm: Optional[object] = None
        self._loaded     = False
        self._error      = ""
        self._load()

    def _load(self) -> None:
        if not _HAS_LLAMA:
            self._error = (
                "llama-cpp-python not installed.\n"
                "Run: pip install llama-cpp-python"
            )
            return

        path = Path(self._model_path)
        if not path.exists():
            self._error = f"Model file not found:\n{self._model_path}"
            return

        try:
            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                verbose=False,
            )
            self._loaded = True
        except Exception as e:
            self._error = str(e)

    def is_loaded(self) -> bool:
        return self._loaded and self._llm is not None

    def model_name(self) -> str:
        """Return a human-readable model name derived from the file path."""
        return Path(self._model_path).stem if self._model_path else "Unknown"

    def get_error(self) -> str:
        return self._error

    def chat(self, user_message: str, context: str = "") -> str:
        """
        Generate a response to user_message.

        Args:
            user_message: The user's question or request.
            context:      Optional trading context string injected after the
                          system prompt (e.g. today's P&L, open positions).

        Returns:
            The assistant's reply as a plain string.
        """
        if not self.is_loaded():
            return (
                f"Model not loaded. {self._error}\n\n"
                "Go to Settings → AI Assistant and set a valid .gguf model path."
            )

        # Build a Mistral-style instruct prompt
        # Format: <s>[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{user} [/INST]
        system_block = _SYSTEM_PROMPT
        if context:
            system_block += f"\n\nCurrent trading context:\n{context}"

        prompt = (
            f"<s>[INST] <<SYS>>\n{system_block}\n<</SYS>>\n\n"
            f"{user_message} [/INST]"
        )

        try:
            output = self._llm(
                prompt,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                stop=["</s>", "[INST]", "<<SYS>>"],
                echo=False,
            )
            text = output["choices"][0]["text"].strip()
            return text if text else "I couldn't generate a response. Please try again."
        except Exception as e:
            return f"Inference error: {e}"

    def analyse_trade(
        self,
        symbol: str,
        direction: str,
        entry: float,
        exit_price: Optional[float],
        pnl: float,
        strategy: str = "",
    ) -> str:
        """
        Structured trade analysis prompt.
        Returns a focused analysis string.
        """
        status = "closed" if exit_price else "open"
        exit_str = f"₹{exit_price:,.2f}" if exit_price else "still open"
        context = (
            f"Trade: {direction} {symbol} @ ₹{entry:,.2f}, "
            f"exit {exit_str}, P&L ₹{pnl:+,.2f}. "
            f"Strategy: {strategy or 'Manual'}. Status: {status}."
        )
        prompt = f"Analyse this trade and explain what went right or wrong:\n{context}"
        return self.chat(prompt)

    def suggest_position_size(
        self,
        capital: float,
        price: float,
        stop_loss: float,
        risk_pct: float = 2.0,
    ) -> str:
        """
        Ask the AI to explain the position sizing calculation.
        """
        risk_amount = capital * risk_pct / 100
        risk_per_share = abs(price - stop_loss)
        qty = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
        context = (
            f"Capital: ₹{capital:,.0f}, price: ₹{price:,.2f}, "
            f"stop loss: ₹{stop_loss:,.2f}, risk per trade: {risk_pct}%, "
            f"calculated quantity: {qty} shares."
        )
        prompt = (
            "Explain this position sizing calculation and whether it is appropriate "
            "for a beginner trader with ₹15,000 capital."
        )
        return self.chat(prompt, context=context)

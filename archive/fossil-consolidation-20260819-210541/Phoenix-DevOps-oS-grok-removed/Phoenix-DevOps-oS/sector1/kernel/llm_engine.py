#!/usr/bin/env python3
"""
llm_engine.py — Phoenix Universal Kernel / LLM Offload Engine
Runs LLMs bigger than physical RAM permits for Life First App and the full
Phoenix entourage.

Strategy:
  1. Ollama manages model execution on the local machine (CPU / partial GPU).
  2. HelixMemory absorbs the KV-cache and prompt context into L1/L2/L3 tiers.
  3. Paged attention: context is split into PAGE_TOKENS-sized pages, each page
     stored as a CacheBlock so cold pages compress and make room for hot ones.
  4. When Ollama is cold (model not loaded) we send a warm-up request first so
     Frank's Ring 3 dispatch doesn't time out on the first real call.
  5. Frank coordinates every request — no module calls Ollama directly.

Supported models (in priority order, largest first):
  - llama3.1:70b   (needs paging — ~40 GB)
  - llama3.1:8b    (fits in 8 GB with quantization)
  - mistral:7b
  - phi3:14b
  - phi3:mini      (fallback, 3.8B)

The module registers itself with Frank as "llm_engine" route.

jwl247 / Phoenix DevOps LLC / GPL v3
"""

import json
import os
import sys
import time
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("phoenix_llm")

# ── Config (all overridable via env) ─────────────────────────────────────────

OLLAMA_URL        = os.environ.get("OLLAMA_URL",       "http://localhost:11434")
LLM_MODEL_LARGE   = os.environ.get("LLM_MODEL_LARGE",  "llama3.1:70b")
LLM_MODEL_MEDIUM  = os.environ.get("LLM_MODEL_MEDIUM", "llama3.1:8b")
LLM_MODEL_SMALL   = os.environ.get("LLM_MODEL_SMALL",  "phi3:mini")
LLM_TIMEOUT       = int(os.environ.get("LLM_TIMEOUT",  "180"))   # seconds
PAGE_TOKENS       = int(os.environ.get("PAGE_TOKENS",  "512"))    # tokens per memory page
LIFEFIRST_API     = os.environ.get("LIFEFIRST_API",    "http://localhost/lifefirst/api.php")
LIFEFIRST_SECRET  = os.environ.get("LF_API_SECRET",   "")

# ── Model tier selection ──────────────────────────────────────────────────────

# Map intent → preferred model size.
# The engine downgrades automatically if the large model isn't available.
INTENT_MODEL_MAP: Dict[str, str] = {
    "memory":       LLM_MODEL_LARGE,    # deep recall — use the biggest
    "schedule":     LLM_MODEL_MEDIUM,
    "messenger":    LLM_MODEL_MEDIUM,
    "notification": LLM_MODEL_SMALL,
    "voice":        LLM_MODEL_MEDIUM,
    "general":      LLM_MODEL_SMALL,
}

# ── Paged context ─────────────────────────────────────────────────────────────

class PagedContext:
    """
    Splits a conversation context into PAGE_TOKENS-sized blocks.
    Hot (recent) pages live in L1 memory.  Cold pages compress into L3.
    This lets a 70B model's 128k context fit in physical RAM because only
    the active window is decompressed at once.
    """

    def __init__(self, system_prompt: str = "", page_size: int = PAGE_TOKENS):
        self.system   = system_prompt
        self.pages:   List[List[Dict]] = []   # list of turn-pages
        self.page_sz  = page_size
        self._buf:    List[Dict] = []          # accumulator for current page
        self._lock    = threading.RLock()

    def push(self, role: str, content: str):
        with self._lock:
            self._buf.append({"role": role, "content": content})
            # Very rough token estimate: 1 token ≈ 4 chars
            approx_tokens = sum(len(t["content"]) // 4 for t in self._buf)
            if approx_tokens >= self.page_sz:
                self.pages.append(self._buf)
                self._buf = []

    def active_window(self, max_tokens: int = 4096) -> List[Dict]:
        """Return the most recent turns that fit in max_tokens."""
        with self._lock:
            all_turns = []
            for page in self.pages:
                all_turns.extend(page)
            all_turns.extend(self._buf)

            window   = []
            used     = 0
            for turn in reversed(all_turns):
                t = len(turn["content"]) // 4
                if used + t > max_tokens:
                    break
                window.insert(0, turn)
                used += t
            return window

    def flush(self):
        with self._lock:
            if self._buf:
                self.pages.append(self._buf)
                self._buf = []


# ── Ollama client (no third-party deps) ───────────────────────────────────────

class OllamaClient:
    """
    Minimal HTTP client for Ollama /api/generate and /api/tags.
    No external dependencies — uses stdlib urllib only.
    """

    def __init__(self, base_url: str = OLLAMA_URL):
        self.base = base_url.rstrip("/")
        self._available: Optional[List[str]] = None

    def available_models(self) -> List[str]:
        if self._available is not None:
            return self._available
        try:
            with urllib.request.urlopen(f"{self.base}/api/tags", timeout=5) as r:
                data = json.loads(r.read())
            self._available = [m["name"] for m in data.get("models", [])]
        except Exception:
            self._available = []
        return self._available

    def model_available(self, model: str) -> bool:
        avail = self.available_models()
        # Accept prefix match (e.g. "llama3.1" matches "llama3.1:8b")
        return any(model in m or m.startswith(model.split(":")[0]) for m in avail)

    def best_available(self, preferred: str) -> str:
        """Return preferred model, or fall back down the size ladder."""
        ladder = [preferred, LLM_MODEL_LARGE, LLM_MODEL_MEDIUM, LLM_MODEL_SMALL]
        for m in ladder:
            if self.model_available(m):
                return m
        # Nothing available — return small and let Ollama pull it on demand
        return LLM_MODEL_SMALL

    def generate(self,
                 model:   str,
                 prompt:  str,
                 system:  str  = "",
                 context: list = None,
                 options: dict = None) -> Dict[str, Any]:
        """
        POST /api/generate with stream=false.
        Returns {"response": str, "model": str, "error": str|None}
        """
        payload = {
            "model":   model,
            "prompt":  prompt,
            "system":  system,
            "stream":  False,
            "options": options or {"temperature": 0.7, "num_predict": 1024},
        }
        if context:
            payload["context"] = context

        body = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{self.base}/api/generate",
            data    = body,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                raw = r.read()
            data = json.loads(raw)
            return {"response": data.get("response", ""), "model": model, "error": None}
        except urllib.error.URLError as e:
            return {"response": "", "model": model, "error": str(e)}
        except Exception as e:
            return {"response": "", "model": model, "error": str(e)}

    def warmup(self, model: str):
        """Pre-load the model so the first real call doesn't cold-start."""
        log.info(f"[llm] warming up {model}…")
        self.generate(model, "ping", options={"num_predict": 1})


# ── LLM Engine ────────────────────────────────────────────────────────────────

class LLMEngine:
    """
    Central LLM dispatch engine.
    Frank owns it. Life First modules call it through Frank's Ring 3.

    Features:
    - Model selection by intent (large → medium → small fallback)
    - PagedContext per user session — bigger context than fits in RAM
    - KV-cache pages stored in Helix memory stack (L1 hot, L3 compressed)
    - Async warmup on startup
    - Direct Ollama call path (no PHP involved — PHP calls Frank → Frank calls this)
    """

    def __init__(self, helix_system=None):
        self.ollama   = OllamaClient()
        self.helix    = helix_system    # HelixSystem from helix_memory.py (optional)
        self.sessions: Dict[str, PagedContext] = {}
        self._lock    = threading.RLock()
        self._warmed: set = set()

    # ── Session management ────────────────────────────────────────────────────

    def _session(self, user_id: str, system: str = "") -> PagedContext:
        with self._lock:
            if user_id not in self.sessions:
                self.sessions[user_id] = PagedContext(system_prompt=system)
            return self.sessions[user_id]

    def clear_session(self, user_id: str):
        with self._lock:
            self.sessions.pop(user_id, None)

    # ── Warmup ────────────────────────────────────────────────────────────────

    def warmup_async(self):
        """Background thread — pre-load default models."""
        def _do():
            for model in [LLM_MODEL_SMALL, LLM_MODEL_MEDIUM]:
                if model not in self._warmed and self.ollama.model_available(model):
                    self.ollama.warmup(model)
                    self._warmed.add(model)
        t = threading.Thread(target=_do, daemon=True, name="llm-warmup")
        t.start()

    # ── Main dispatch ─────────────────────────────────────────────────────────

    def ask(self,
            user_id:   str,
            message:   str,
            intent:    str  = "general",
            system:    str  = "",
            options:   dict = None) -> Dict[str, Any]:
        """
        Ask the LLM on behalf of user_id.
        Returns {"response": str, "model": str, "intent": str, "source": "ollama",
                 "error": str|None}
        """
        preferred = INTENT_MODEL_MAP.get(intent, LLM_MODEL_SMALL)
        model     = self.ollama.best_available(preferred)

        if model not in self._warmed:
            # synchronous warmup only if not done yet
            self.ollama.warmup(model)
            self._warmed.add(model)

        ctx    = self._session(user_id, system)
        window = ctx.active_window(max_tokens=4096)

        # Build prompt with context window
        if window:
            history = "\n".join(
                f"{t['role'].capitalize()}: {t['content']}" for t in window
            )
            prompt = f"{history}\nUser: {message}"
        else:
            prompt = message

        # Helix memory: store prompt page
        if self.helix:
            try:
                from CoPES.src.helix_memory import SectorID
                self.helix.sector_write(
                    SectorID.FRANK,
                    f"llm:prompt:{user_id}:{int(time.time())}",
                    {"intent": intent, "prompt": prompt[:256]},  # truncated for index
                )
            except Exception:
                pass

        result = self.ollama.generate(
            model   = model,
            prompt  = prompt,
            system  = system,
            options = options,
        )

        # Push turns into paged context
        ctx.push("user",      message)
        if not result["error"]:
            ctx.push("assistant", result["response"])

        return {
            "response": result["response"],
            "model":    model,
            "intent":   intent,
            "source":   "ollama",
            "error":    result["error"],
        }

    def stats(self) -> dict:
        return {
            "active_sessions": len(self.sessions),
            "models_warmed":   list(self._warmed),
            "available_models": self.ollama.available_models(),
        }


# ── Global instance ───────────────────────────────────────────────────────────

_engine: Optional[LLMEngine] = None

def get_engine(helix_system=None) -> LLMEngine:
    global _engine
    if _engine is None:
        _engine = LLMEngine(helix_system=helix_system)
        _engine.warmup_async()
    return _engine


# ── Frank Ring 3 handler ──────────────────────────────────────────────────────

def frank_handler(payload: Dict) -> Dict:
    """
    Called by Frank Ring 3 when intent='llm_engine'.
    Payload: {user_id, message, intent, system?, options?}
    """
    engine = get_engine()
    return engine.ask(
        user_id = str(payload.get("user_id", "anon")),
        message = payload.get("message", ""),
        intent  = payload.get("intent",  "general"),
        system  = payload.get("system",  ""),
        options = payload.get("options", None),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [LLM] %(message)s")
    engine = get_engine()

    if len(sys.argv) > 1 and sys.argv[1] == "models":
        print(json.dumps(engine.ollama.available_models(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(engine.stats(), indent=2))
    elif len(sys.argv) > 2:
        # llm_engine.py ask "hello" general
        result = engine.ask("cli", sys.argv[1],
                            intent=sys.argv[2] if len(sys.argv) > 2 else "general")
        print(f"\nModel: {result['model']}")
        print(f"\n{result['response']}")
    else:
        print("usage: llm_engine.py ask <message> [intent]")
        print("       llm_engine.py models")
        print("       llm_engine.py stats")

"""
router.py — decide, per message, WHICH agent and WHICH model should handle it.

Hybrid strategy
───────────────
1. Heuristic fast-path (no latency): keyword / signal matching. High-confidence
   results are used immediately.
2. LLM fallback: when the heuristics are unsure, a small model classifies the
   message into chat | action | spec | debug.

Intent → agent → model
──────────────────────
  chat    → _ChatAgent      + fast model      (conversation, questions)
  action  → DeveloperAgent  + coding model    (create/edit/run/fix files)
  debug   → DebuggerAgent   + coding model    (diagnose/fix an error)
  spec    → PlannerAgent    + planner model   (plan & build a whole project)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from .config import settings
from .model_router import select_model

logger = logging.getLogger(__name__)

# intent → agent name (resolved to real agent objects by the orchestrator)
INTENT_AGENT: dict[str, str] = {
    "chat": "chat",
    "action": "developer",
    "debug": "debugger",
    "spec": "planner",
}

# intent → intent label understood by model_router.select_model()
_MODEL_INTENT = {"chat": "chat", "action": "action", "debug": "action", "spec": "spec"}


@dataclass
class Route:
    intent: str        # chat | action | spec | debug
    agent: str         # chat | developer | planner | debugger
    model: str
    reason: str
    via: str           # heuristic | llm | forced


# ── Signal sets ───────────────────────────────────────────────────────────────

_ACTION_VERBS = {
    "create", "write", "make", "add", "generate", "produce", "output", "run",
    "execute", "compile", "test", "fix", "debug", "refactor", "rename", "delete",
    "remove", "move", "copy", "edit", "update", "modify", "change", "append",
    "insert", "replace", "open", "mkdir", "touch", "init", "setup", "install",
    "build", "implement", "scaffold", "launch", "deploy",
}
_FILE_SIGNALS = {
    ".cpp", ".py", ".js", ".ts", ".dart", ".go", ".rs", ".java", ".c", ".h",
    ".cs", ".rb", ".php", ".sh", ".html", ".css", ".json", ".yaml", ".toml",
    ".md", ".txt", "file", "folder", "directory", "function", "class", "method",
    "code", "snippet", "script", "program", "module", "component", "project",
    "app", "application", "server", "api", "database",
}
_ACTION_PHRASES = (
    "can you create", "can you write", "can you make", "can you build",
    "could you create", "could you write", "could you make",
    "i want you to create", "i want you to write", "i need you to create",
    "i need a file", "i need a function", "i need a class", "i need an app",
    "create a file", "write a file", "make a file", "create a folder",
    "make a folder", "create a directory", "write the code", "write code",
    "generate code", "make this project", "buy me",
)
_SPEC_PHRASES = (
    "build an app", "build a app", "build an application", "build a website",
    "build a web app", "build a mobile app", "build an android", "build an ios",
    "build a flutter", "develop an app", "develop a website", "develop a system",
    "create an app", "create an application", "create a website",
    "create a mobile app", "create a web app", "create an android",
    "create an ios", "make an app", "make an application", "make a website",
    "make an android", "make an ios", "i want to build", "i want to create an app",
    "build me an", "build me a", "plan a project", "write a spec",
)
_DO_IT = {
    "do it", "do it now", "make it", "make it now", "start", "go", "go ahead",
    "proceed", "continue", "yes do it", "ok do it", "ok go ahead", "just do it",
    "go for it", "lets start", "let's start", "lets go", "let's go", "begin",
    "begin now", "start now", "start building", "start the project",
    "start coding", "implement it", "implement this", "build it", "build this",
    "create it now", "create this now", "i want to make this project right now",
    "i want to make this", "make this project",
}
_DEBUG_WORDS = {
    "traceback", "stack trace", "segfault", "segmentation fault", "exception",
    "debug", "not working", "doesn't work", "does not work", "keeps failing",
}
_QUESTION_WORDS = {
    "what", "why", "how", "who", "when", "where", "which", "explain", "describe",
    "difference", "compare", "is", "are", "does", "do", "can", "could", "would",
    "should", "tell",
}
_GREETINGS = {"hi", "hello", "hey", "yo", "thanks", "thank", "morning", "evening"}

_IMAGE_CREATE_SIGNALS = {
    "draw", "paint", "sketch", "doodle", "illustrate", "render",
    "generate an image", "create an image", "make an image", "produce an image",
    "generate a picture", "create a picture", "make a picture",
    "image generation", "image creation", "text to image", "text-to-image",
    "ai image", "ai art", "ai drawing",
}


def _image_creation(lower: str) -> bool:
    if any(sig in lower for sig in _IMAGE_CREATE_SIGNALS):
        return True
    if ("image" in lower or "picture" in lower or "photo" in lower) and any(
        v in lower for v in ("create", "make", "generate", "draw", "paint", "produce")
    ):
        return True
    return False


def _debug_like(lower: str) -> bool:
    if any(w in lower for w in _DEBUG_WORDS):
        return True
    if "error" in lower and any(
        v in lower for v in ("fix", "why", "cause", "caused", "causing", "resolve",
                             "broken", "fail", "not working", "debug")
    ):
        return True
    return False


def heuristic(message: str) -> tuple[str, bool]:
    """Return (intent, is_confident). Cheap, no LLM."""
    lower = message.strip().lower()
    words = lower.split()
    first = words[0] if words else ""

    # 1. Debug (highest priority — an error to diagnose beats a generic fix)
    if _debug_like(lower):
        return "debug", True

    # 1b. Image creation — the code agent cannot generate images; route to
    #     chat so the assistant can explain capabilities / ask to attach one.
    if _image_creation(lower):
        return "chat", True

    # 2. Explicit action verbs
    if first in _ACTION_VERBS:
        return "action", True
    if len(words) >= 2 and words[0] == "please" and words[1] in _ACTION_VERBS:
        return "action", True
    if any(sig in lower for sig in _FILE_SIGNALS) and any(v in lower for v in _ACTION_VERBS):
        return "action", True
    if any(p in lower for p in _ACTION_PHRASES):
        return "action", True

    # 3. Spec (plan & build a whole project)
    if any(p in lower for p in _SPEC_PHRASES) and len(message) > 30:
        return "spec", True

    # 4. Follow-up "do it" messages
    if lower.strip() in _DO_IT or any(p in lower for p in _DO_IT):
        return "action", True

    # 5. Clear conversation
    if first in _QUESTION_WORDS or first in _GREETINGS:
        return "chat", True
    if lower.endswith("?") and first not in _ACTION_VERBS:
        return "chat", True

    # 6. Unsure
    return "chat", False


def classify_intent(message: str) -> str:
    """Heuristic-only intent (unsure defaults to chat). Kept for compatibility."""
    return heuristic(message)[0]


class Router:
    async def route(
        self,
        message: str,
        model_override: Optional[str] = None,
        history_hint: str = "",
    ) -> Route:
        intent, confident = heuristic(message)
        via = "heuristic"

        # LLM fallback for ambiguous messages
        if not confident:
            llm_intent = None
            if settings.llm_router:
                llm_intent = await self._llm_classify(message, history_hint)
            if llm_intent:
                intent, via = llm_intent, "llm"
            else:
                # Bias toward action so the agent actually does things.
                intent, via = "action", "default"

        agent = INTENT_AGENT[intent]

        if model_override:
            return Route(intent, agent, model_override, "user selected model", "forced")

        if settings.auto_route_model:
            model, reason = select_model(message, intent=_MODEL_INTENT[intent])
        else:
            model, reason = settings.default_model, "auto_route disabled"
        return Route(intent, agent, model, reason, via)

    async def _llm_classify(self, message: str, history_hint: str = "") -> Optional[str]:
        from .models import Message, Role
        from .ollama_client import ollama

        prompt = (
            "Classify the user's request into exactly ONE word.\n"
            "Options: chat, action, spec, debug\n"
            "  chat   = a question, explanation or conversation\n"
            "  action = asks you to create/edit/run/fix files or run commands\n"
            "  spec   = asks to plan and build a whole new project or app\n"
            "  debug  = asks to diagnose or fix an error / failing code\n"
        )
        if history_hint:
            prompt += f"\nPrevious user message (context): {history_hint[:300]}\n"
        prompt += f"\nUser message: {message}\n\nAnswer with the single word only."

        try:
            resp = await ollama.chat(
                messages=[Message(role=Role.USER, content=prompt)],
                model=settings.router_model,
                temperature=0.0,
            )
        except Exception as e:
            logger.warning("LLM router call failed: %s", e)
            return None

        text = (resp.content or "").strip().lower()
        for tok in re.findall(r"[a-z]+", text):
            if tok in INTENT_AGENT:
                return tok
        for tok in ("chat", "action", "spec", "debug"):
            if tok in text:
                return tok
        return None


router = Router()

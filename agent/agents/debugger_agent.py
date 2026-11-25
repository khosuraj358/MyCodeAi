"""
Debugger Agent — diagnoses errors and applies minimal targeted fixes.
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session
from .base_agent import BaseAgent

SYSTEM = """You are an expert debugger.

Process:
1. Read the error message carefully
2. Read the relevant source files with read_file
3. Identify the ROOT CAUSE (trace the execution, do not guess)
4. Apply the MINIMAL fix — do not rewrite entire files
5. Re-run the failing command to confirm the fix works
6. End with either:
   BUG FIXED: <one-line description>
   CANNOT FIX: <reason>
"""


class DebuggerAgent(BaseAgent):
    name      = "debugger"
    system_prompt = SYSTEM
    model     = settings.default_model
    use_tools = True

    async def debug(
        self,
        session: Session,
        error: str,
        context: str = "",
    ) -> str:
        prompt = f"Error to fix:\n\n```\n{error}\n```\n\n{context}"
        response = await self.run(session, prompt)
        return response.content

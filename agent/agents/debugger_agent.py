"""
Debugger Agent — diagnoses and fixes failures.

Triggered when:
- A developer task fails validation
- A reviewer gives a FAIL verdict
- The user reports a bug
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session
from .base_agent import BaseAgent

DEBUGGER_SYSTEM_PROMPT = """
You are the Debugger agent for MyCodeAI IDE. You diagnose and fix errors
in code. You have access to file read/write tools and the shell.

Debugging process:
1. Read the error message carefully
2. Read the relevant source files
3. Identify the root cause (do not guess — trace the execution)
4. Apply the minimal fix that resolves the issue
5. Re-run the failing command to confirm the fix
6. Report: root cause, fix applied, verification result

Do not rewrite entire files. Make targeted, minimal changes.
End with: BUG FIXED: <one-line summary> or CANNOT FIX: <reason>
"""


class DebuggerAgent(BaseAgent):
    name = "debugger"
    system_prompt = DEBUGGER_SYSTEM_PROMPT
    model = settings.default_model

    async def debug(
        self,
        session: Session,
        error: str,
        context: str = "",
    ) -> str:
        prompt = f"""
An error occurred that needs debugging:

```
{error}
```

{context}

Diagnose and fix the issue.
"""
        response = await self.run(session, prompt)
        return response.content

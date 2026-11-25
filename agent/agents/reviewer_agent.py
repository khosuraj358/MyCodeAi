"""
Reviewer Agent — reads modified files and produces a structured review.
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session, SpecTask
from .base_agent import BaseAgent

SYSTEM = """You are a senior code reviewer.

For every review produce this exact structure:

## Review: <Task ID> — <Title>

### ✅ Correct
- ...

### ⚠️ Issues
- [REQUIRED] ...
- [SUGGESTION] ...

### Verdict: PASS | PASS_WITH_NOTES | FAIL

If FAIL, state clearly what must be fixed before the task can be marked complete.
"""


class ReviewerAgent(BaseAgent):
    name      = "reviewer"
    system_prompt = SYSTEM
    model     = settings.reviewer_model
    use_tools = True    # needs read_file to inspect code

    async def review_task(
        self,
        session: Session,
        task: SpecTask,
        files_modified: list[str],
    ) -> tuple[str, str]:
        files = "\n".join(f"- {f}" for f in files_modified) or "(none listed)"
        prompt = (
            f"Review the implementation of:\n\n"
            f"**Task ID:** {task.id}\n"
            f"**Title:** {task.title}\n"
            f"**Description:** {task.description}\n\n"
            f"**Files modified:**\n{files}\n\n"
            "Read each file and produce your structured review."
        )
        response = await self.run(session, prompt)
        verdict = "PASS"
        for line in response.content.splitlines():
            if "Verdict:" in line:
                if "FAIL" in line:            verdict = "FAIL"
                elif "PASS_WITH_NOTES" in line: verdict = "PASS_WITH_NOTES"
                break
        return response.content, verdict

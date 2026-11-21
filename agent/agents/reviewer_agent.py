"""
Reviewer Agent — reviews completed tasks and the full spec implementation.

Produces structured review reports with:
- What was done correctly
- Issues found (bugs, missing coverage, style violations)
- Required fixes vs suggestions
- Overall verdict: PASS / PASS_WITH_NOTES / FAIL
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session, SpecTask
from .base_agent import BaseAgent

REVIEWER_SYSTEM_PROMPT = """
You are the Reviewer agent for MyCodeAI IDE. You review code produced by
the Developer agent and provide structured feedback.

For each review:
1. Read the relevant files using read_file
2. Check the implementation against the task requirements
3. Look for: correctness, completeness, error handling, security, style
4. Produce a review report in this format:

## Review: <Task ID> — <Task Title>

### ✅ Correct
- ...

### ⚠️ Issues
- [REQUIRED] ...
- [SUGGESTION] ...

### Verdict: PASS | PASS_WITH_NOTES | FAIL

If verdict is FAIL, explain clearly what must be fixed.
"""


class ReviewerAgent(BaseAgent):
    name = "reviewer"
    system_prompt = REVIEWER_SYSTEM_PROMPT
    model = settings.reviewer_model

    async def review_task(
        self,
        session: Session,
        task: SpecTask,
        files_modified: list[str],
    ) -> tuple[str, str]:
        """
        Review a completed task.
        Returns (review_report_md, verdict).
        """
        files_list = "\n".join(f"- {f}" for f in files_modified) or "(none listed)"
        prompt = f"""
Review the implementation of this task:

**Task ID:** {task.id}
**Title:** {task.title}
**Description:** {task.description}

**Files modified:**
{files_list}

Read each modified file and check the implementation.
Produce your structured review report.
"""
        response = await self.run(session, prompt)
        verdict = self._extract_verdict(response.content)
        return response.content, verdict

    def _extract_verdict(self, review_md: str) -> str:
        for line in review_md.splitlines():
            if "Verdict:" in line:
                if "FAIL" in line:
                    return "FAIL"
                elif "PASS_WITH_NOTES" in line:
                    return "PASS_WITH_NOTES"
                elif "PASS" in line:
                    return "PASS"
        return "UNKNOWN"

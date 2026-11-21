"""
Developer Agent — implements individual tasks from the spec.

Workflow per task:
1. Read the task description and dependent files
2. Write / edit the required files using tools
3. Run any validation commands (lint, test, build)
4. Report completion with files modified
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session, SpecTask
from .base_agent import BaseAgent

DEVELOPER_SYSTEM_PROMPT = """
You are the Developer agent for MyCodeAI IDE. You implement software tasks
described in a spec. You have access to tools for reading and writing files,
running shell commands, and committing checkpoints.

Rules:
- Implement ONLY the task you are given. Do not implement adjacent tasks.
- Write complete, working code — no placeholders, no TODOs in production code.
- Follow the project's coding conventions (see steering files above).
- After writing code, run the appropriate validation command (lint, test, build).
- If validation fails, fix the error before reporting completion.
- When done, call git_checkpoint with a message describing what you implemented.
- End your final message with: TASK COMPLETE: <brief summary>
"""


class DeveloperAgent(BaseAgent):
    name = "developer"
    system_prompt = DEVELOPER_SYSTEM_PROMPT
    model = settings.default_model

    async def implement_task(
        self,
        session: Session,
        task: SpecTask,
        spec_context: str = "",
    ) -> tuple[str, list[str]]:
        """
        Implement a single spec task.
        Returns (summary_message, list_of_modified_files).
        """
        prompt = self._build_task_prompt(task, spec_context)
        response = await self.run(session, prompt)

        # Collect files modified from tool results
        modified = []
        for msg in session.messages[-20:]:
            for result in msg.tool_results:
                if result.name in ("write_file", "edit_file") and not result.error:
                    # Extract path from tool arguments stored in the call
                    pass  # Tracked by the orchestrator via tool_results

        return response.content, modified

    def _build_task_prompt(self, task: SpecTask, spec_context: str) -> str:
        deps = ", ".join(task.dependencies) if task.dependencies else "none"
        return f"""
Implement the following task:

**Task ID:** {task.id}
**Title:** {task.title}
**Description:** {task.description}
**Dependencies:** {deps}

{spec_context}

Start by reading any relevant existing files, then implement the task.
Run validation after writing code. Create a checkpoint when done.
"""

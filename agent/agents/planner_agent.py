"""
Planner Agent — drives the Spec-driven workflow:
  Requirements → Design → Tasks → Implementation plan

This agent does NOT write code. It produces structured markdown documents
that describe what to build and how to build it.
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session, Spec, SpecPhase
from .base_agent import BaseAgent


REQUIREMENTS_PROMPT = """
You are the Planner agent for MyCodeAI IDE. Your job is to produce a
thorough REQUIREMENTS document for the user's goal.

Output a markdown document with these sections:
1. **Overview** — What the application does and who it's for
2. **Functional Requirements** — Numbered list of capabilities (FR-1, FR-2, …)
3. **Non-Functional Requirements** — Performance, security, compatibility (NFR-1, …)
4. **Constraints** — Platform, language, library or budget constraints
5. **Acceptance Criteria** — How we know each requirement is met

Be specific. Use the user's exact terminology. Do not start writing code.
"""

DESIGN_PROMPT = """
You are the Planner agent for MyCodeAI IDE. Given the requirements,
produce a thorough DESIGN document.

Output a markdown document with these sections:
1. **Architecture** — High-level diagram description and component list
2. **Module Breakdown** — Each module/package with responsibility
3. **Data Models** — Key data structures, schemas or database tables
4. **Technology Choices** — Libraries, frameworks, tools and why
5. **UI/UX Sketch** — Screen or API layout description
6. **Implementation Strategy** — Phased approach and key decisions

Be specific. Reference requirement IDs where applicable. Do not write code.
"""

TASKS_PROMPT = """
You are the Planner agent for MyCodeAI IDE. Given the requirements and design,
produce a TASKS document that breaks the implementation into actionable tasks.

Output a markdown document containing a numbered task list:

## Tasks

### 1. <Phase Name>
- [ ] 1.1 <Task title>
  - Description: ...
  - Files: ...
  - Dependencies: none
- [ ] 1.2 <Task title>
  - Description: ...
  - Files: ...
  - Dependencies: 1.1

### 2. <Next Phase>
...

Rules:
- Tasks should be small (1–3 hours of AI work each)
- Include file paths that will be created or modified
- List dependencies between tasks
- Group tasks into phases (Setup, Core, UI, Testing, etc.)
- Do not write code, only describe what needs to be done
"""


class PlannerAgent(BaseAgent):
    name = "planner"
    model = settings.planner_model

    async def generate_requirements(self, session: Session, goal: str) -> str:
        self.system_prompt = REQUIREMENTS_PROMPT
        response = await self.run(session, f"Goal: {goal}")
        return response.content

    async def generate_design(self, session: Session, requirements_md: str) -> str:
        self.system_prompt = DESIGN_PROMPT
        response = await self.run(
            session,
            f"Here are the requirements:\n\n{requirements_md}\n\nNow produce the design.",
        )
        return response.content

    async def generate_tasks(
        self, session: Session, requirements_md: str, design_md: str
    ) -> str:
        self.system_prompt = TASKS_PROMPT
        context = (
            f"## Requirements\n{requirements_md}\n\n"
            f"## Design\n{design_md}\n\n"
            "Now produce the task breakdown."
        )
        response = await self.run(session, context)
        return response.content

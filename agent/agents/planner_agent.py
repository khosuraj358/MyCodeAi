"""
Planner Agent — produces Requirements, Design, and Tasks documents.
No tools needed: pure text generation.
"""
from __future__ import annotations

from ..core.config import settings
from ..core.models import Session
from .base_agent import BaseAgent

_REQ = """You are a software architect writing a Requirements document.

Output a markdown document with these sections:
1. **Overview** — What it does and who uses it
2. **Functional Requirements** — Numbered FR-1, FR-2 …
3. **Non-Functional Requirements** — NFR-1, NFR-2 …
4. **Constraints** — Platform, language, library limits
5. **Acceptance Criteria** — How to verify each requirement is met

Be specific. Use the user's exact terminology. Do NOT write any code."""

_DESIGN = """You are a software architect writing a Design document.

Output a markdown document with:
1. **Architecture** — Components and how they connect
2. **Module Breakdown** — Each module with its responsibility
3. **Data Models** — Key structures, schemas, database tables
4. **Technology Choices** — Libraries and frameworks with reasons
5. **UI / API Layout** — Screens or endpoint descriptions
6. **Implementation Strategy** — Phases and key decisions

Reference requirement IDs (FR-1 etc.) where applicable. Do NOT write code."""

_TASKS = """You are a software architect writing a Tasks document.

Output a markdown task list:

## Tasks

### 1. <Phase Name>
- [ ] 1.1 <Task title>
  - Description: what to implement
  - Files: which files to create or modify
  - Dependencies: none

- [ ] 1.2 <Task title>
  - Description: ...
  - Files: ...
  - Dependencies: 1.1

### 2. <Next Phase>
...

Rules:
- Each task = 1–3 hours of focused work
- Include exact file paths
- List all inter-task dependencies
- Group into phases: Setup → Core → API → UI → Tests
- Do NOT write any code"""


class PlannerAgent(BaseAgent):
    name      = "planner"
    model     = settings.planner_model
    use_tools = False   # pure text generation, no tools needed

    async def generate_requirements(self, session: Session, goal: str) -> str:
        self.system_prompt = _REQ
        r = await self.run(session, f"Goal: {goal}")
        return r.content

    async def generate_design(self, session: Session, requirements_md: str) -> str:
        self.system_prompt = _DESIGN
        r = await self.run(session, f"Requirements:\n\n{requirements_md}\n\nWrite the design.")
        return r.content

    async def generate_tasks(self, session: Session, req: str, design: str) -> str:
        self.system_prompt = _TASKS
        r = await self.run(
            session,
            f"## Requirements\n{req}\n\n## Design\n{design}\n\nWrite the task breakdown.",
        )
        return r.content

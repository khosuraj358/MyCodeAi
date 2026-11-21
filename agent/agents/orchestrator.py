"""
Orchestrator — the central coordinator.

Manages:
- Session lifecycle
- Spec phase progression (Requirements → Design → Tasks → Implementation)
- Agent dispatch (Planner, Developer, Reviewer, Debugger)
- Context compaction triggers
- Hook firing
- Streaming to the WebSocket
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator, Optional
from uuid import uuid4

from ..core.config import settings
from ..core.models import (
    Message, Role, Session, Spec, SpecPhase, SpecTask, TaskStatus
)
from ..core.session_manager import SessionManager
from ..hooks.hook_runner import HookRunner
from ..memory.spec_store import SpecStore
from ..compaction.compactor import Compactor
from .planner_agent import PlannerAgent
from .developer_agent import DeveloperAgent
from .reviewer_agent import ReviewerAgent
from .debugger_agent import DebuggerAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, session_mgr: SessionManager, spec_store: SpecStore):
        self.sessions = session_mgr
        self.specs = spec_store
        self.hook_runner = HookRunner()
        self.compactor = Compactor()
        self.planner = PlannerAgent()
        self.developer = DeveloperAgent()
        self.reviewer = ReviewerAgent()
        self.debugger = DebuggerAgent()

    # ── Conversational chat ───────────────────────────────────────────────────

    async def chat(
        self,
        session: Session,
        message: str,
        model: Optional[str] = None,
    ) -> Message:
        """Route a free-form chat message to the appropriate agent."""
        await self.hook_runner.fire("UserPromptSubmit", {"message": message})

        if self._is_spec_goal(message) and not session.spec_id:
            # Auto-start spec flow
            spec = await self.create_spec(message)
            session.spec_id = spec.id
            reply = Message(
                role=Role.ASSISTANT,
                content=(
                    f"I've started a spec for your goal. Here are the requirements:\n\n"
                    f"{spec.requirements_md}\n\n"
                    "Reply **approve** to proceed to the design phase, or give feedback."
                ),
            )
        else:
            # Regular agentic chat via developer agent
            reply = await self.developer.run(session, message, model=model)

        await self.sessions.add_message(session.id, reply)
        await self._maybe_compact(session)
        return reply

    async def stream_chat(
        self, session: Session, message: str
    ) -> AsyncIterator[dict]:
        async for chunk in self.developer.stream_run(session, message):
            yield chunk

    # ── Spec flow ─────────────────────────────────────────────────────────────

    async def create_spec(self, goal: str, name: Optional[str] = None) -> Spec:
        """Create a new spec and generate requirements."""
        spec_name = name or self._slugify(goal[:40])
        spec = Spec(id=str(uuid4()), name=spec_name, goal=goal)

        # Create a dedicated planning session
        session = await self.sessions.create_session(spec.id)

        logger.info("Generating requirements for spec: %s", spec_name)
        spec.requirements_md = await self.planner.generate_requirements(session, goal)
        spec.phase = SpecPhase.REQUIREMENTS

        await self.specs.save(spec)
        await self._write_spec_files(spec)
        await self.hook_runner.fire("SpecCreated", {"spec_id": spec.id, "phase": spec.phase})
        return spec

    async def advance_spec(
        self, spec_id: str, approved: bool = True, feedback: str = ""
    ) -> Spec:
        """Advance the spec to the next phase after user approval."""
        spec = await self.specs.get(spec_id)
        if not spec:
            raise ValueError(f"Spec not found: {spec_id}")

        session = await self.sessions.create_session(spec.id)

        if not approved:
            # Re-generate current phase with feedback
            spec = await self._regenerate_phase(spec, session, feedback)
        else:
            spec = await self._advance_phase(spec, session)

        await self.specs.save(spec)
        await self._write_spec_files(spec)
        return spec

    async def run_next_task(self, spec_id: str) -> dict:
        """Find and implement the next pending task in the spec."""
        spec = await self.specs.get(spec_id)
        if not spec or spec.phase != SpecPhase.IMPLEMENTATION:
            raise ValueError("Spec is not in implementation phase")

        task = self._next_pending_task(spec)
        if not task:
            spec.phase = SpecPhase.REVIEW
            await self.specs.save(spec)
            return {"status": "all_tasks_complete"}

        task.status = TaskStatus.IN_PROGRESS
        await self.specs.save(spec)
        await self.hook_runner.fire("TaskStarted", {"task_id": task.id, "task_title": task.title})

        session = await self.sessions.create_session(spec_id)
        spec_ctx = f"Requirements:\n{spec.requirements_md}\n\nDesign:\n{spec.design_md}"

        try:
            summary, files = await self.developer.implement_task(session, task, spec_ctx)
            task.status = TaskStatus.COMPLETED
            task.files_modified = files

            if settings.auto_checkpoint:
                from ..tools.git_tool import git_checkpoint
                sha = await git_checkpoint(f"task {task.id}: {task.title}")
                task.checkpoint_sha = sha

            await self.specs.save(spec)
            await self.hook_runner.fire("TaskCompleted", {"task_id": task.id, "summary": summary})

            return {
                "task_id": task.id,
                "status": "completed",
                "summary": summary,
                "files": files,
            }

        except Exception as e:
            task.status = TaskStatus.FAILED
            await self.specs.save(spec)
            logger.error("Task %s failed: %s", task.id, e)
            raise

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _advance_phase(self, spec: Spec, session: Session) -> Spec:
        if spec.phase == SpecPhase.REQUIREMENTS:
            logger.info("Generating design for spec: %s", spec.name)
            spec.design_md = await self.planner.generate_design(session, spec.requirements_md)
            spec.phase = SpecPhase.DESIGN

        elif spec.phase == SpecPhase.DESIGN:
            logger.info("Generating tasks for spec: %s", spec.name)
            tasks_md = await self.planner.generate_tasks(
                session, spec.requirements_md, spec.design_md
            )
            spec.tasks = self._parse_tasks(tasks_md)
            spec.phase = SpecPhase.TASKS

        elif spec.phase == SpecPhase.TASKS:
            spec.phase = SpecPhase.IMPLEMENTATION

        elif spec.phase == SpecPhase.IMPLEMENTATION:
            spec.phase = SpecPhase.REVIEW

        elif spec.phase == SpecPhase.REVIEW:
            spec.phase = SpecPhase.DONE

        return spec

    async def _regenerate_phase(
        self, spec: Spec, session: Session, feedback: str
    ) -> Spec:
        fb_msg = f"User feedback: {feedback}\n\nPlease revise."
        if spec.phase == SpecPhase.REQUIREMENTS:
            spec.requirements_md = await self.planner.generate_requirements(
                session, f"{spec.goal}\n\n{fb_msg}"
            )
        elif spec.phase == SpecPhase.DESIGN:
            spec.design_md = await self.planner.generate_design(
                session, spec.requirements_md + f"\n\n{fb_msg}"
            )
        elif spec.phase == SpecPhase.TASKS:
            tasks_md = await self.planner.generate_tasks(
                session,
                spec.requirements_md,
                spec.design_md + f"\n\n{fb_msg}",
            )
            spec.tasks = self._parse_tasks(tasks_md)
        return spec

    async def _write_spec_files(self, spec: Spec):
        """Write spec markdown files to disk."""
        from ..tools.file_tools import write_file
        base = f"specs/{spec.name}"
        if spec.requirements_md:
            await write_file(f"{base}/requirements.md", spec.requirements_md)
        if spec.design_md:
            await write_file(f"{base}/design.md", spec.design_md)
        if spec.tasks:
            tasks_lines = [f"# Tasks: {spec.name}\n"]
            for t in spec.tasks:
                status = "x" if t.status == TaskStatus.COMPLETED else " "
                tasks_lines.append(f"- [{status}] {t.id} {t.title}")
            await write_file(f"{base}/tasks.md", "\n".join(tasks_lines))

    def _parse_tasks(self, tasks_md: str) -> list[SpecTask]:
        """Parse task markdown into SpecTask objects."""
        tasks = []
        task_pattern = re.compile(
            r"-\s*\[[ x]\]\s*([\d.]+)\s+(.+?)(?=\n\s*-|\Z)", re.DOTALL
        )
        for match in task_pattern.finditer(tasks_md):
            task_id = match.group(1).strip()
            title = match.group(2).strip().split("\n")[0].strip()
            tasks.append(SpecTask(id=task_id, title=title, description=title))
        return tasks

    def _next_pending_task(self, spec: Spec) -> Optional[SpecTask]:
        completed_ids = {t.id for t in spec.tasks if t.status == TaskStatus.COMPLETED}
        for task in spec.tasks:
            if task.status == TaskStatus.PENDING:
                deps_met = all(d in completed_ids for d in task.dependencies)
                if deps_met:
                    return task
        return None

    async def _maybe_compact(self, session: Session):
        from ..core.context_engine import ContextEngine
        ctx = ContextEngine()
        if ctx.needs_compaction(session):
            summary = await self.compactor.compact(session)
            await self.sessions.update_summary(session.id, summary)

    @staticmethod
    def _is_spec_goal(message: str) -> bool:
        keywords = ["build", "create", "develop", "make", "implement", "write an app", "app that"]
        lower = message.lower()
        return any(k in lower for k in keywords) and len(message) > 20

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

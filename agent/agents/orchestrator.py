"""
Orchestrator — central coordinator for MyCodeAI  v0.3.8

chat()           — blocking, intent-routed, used by POST /chat
stream_agentic() — SSE generator: routes intent, runs tool loop, streams
                   every tool call + result + text token live to the UI
                   (this is what makes it behave like Cursor/Kiro)
create_spec()    — planner → requirements.md
advance_spec()   — phase walker
run_next_task()  — developer → reviewer → debugger loop
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import AsyncIterator, Optional
from uuid import uuid4

from ..core.config import settings
from ..core.model_router import select_model, ram_status
from ..core.router import router
from ..core.context_builder import context_builder
from ..core.models import (
    Message,
    Role,
    Session,
    Spec,
    SpecPhase,
    SpecTask,
    TaskStatus,
)
from ..core.session_manager import SessionManager
from ..core.ollama_client import ollama
from ..core.context_engine import ContextEngine
from ..hooks.hook_runner import HookRunner
from ..memory.spec_store import SpecStore
from ..compaction.compactor import Compactor
from ..tools.registry import tool_registry
from .planner_agent import PlannerAgent
from .developer_agent import DeveloperAgent
from .reviewer_agent import ReviewerAgent
from .debugger_agent import DebuggerAgent
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class _ChatAgent(BaseAgent):
    """Lightweight conversational agent — no tools, fast."""

    name = "chat"
    system_prompt = (
        "You are MyCodeAI, a local AI coding assistant. "
        "Be concise and direct. Use markdown for code snippets.\n\n"
        "Capabilities:\n"
        "- Answer questions and explain concepts\n"
        "- Help with code, debugging, and architecture (switch to the coding agent)\n"
        "- Analyze attached images or PDFs (vision model)\n\n"
        "Limitations:\n"
        "- You cannot generate or create images from text. "
        "If the user asks for an image, suggest they attach an existing image "
        "for analysis, or describe how to create one with external tools."
    )
    use_tools = False


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
        self._chat_agent = _ChatAgent()
        self._ctx = ContextEngine()
        # intent agent-name → agent instance (used by the router)
        self._agents = {
            "chat": self._chat_agent,
            "developer": self.developer,
            "debugger": self.debugger,
            "planner": self.planner,
        }

    # ── Blocking chat (POST /chat) ────────────────────────────────────────────

    async def chat(
        self,
        session: Session,
        message: str,
        model: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> Message:
        await self.hook_runner.fire("UserPromptSubmit", {"message": message})
        route = await router.route(message, model_override=model)
        logger.info(
            "intent=%s agent=%s model=%s via=%s | %s",
            route.intent, route.agent, route.model, route.via, message[:60],
        )

        ctx_injection = await context_builder.build(
            session_id=session.id,
            session_msgs=session.messages,
            spec_id=session.spec_id,
            lightweight=(route.intent == "chat"),
        )

        ws_note = ""
        if workspace:
            ws_note = (
                f"[CURRENT WORKSPACE FOLDER: {workspace}]\n"
                "Unless the user explicitly names a different location, create ALL "
                "new files and folders INSIDE this workspace folder. Use absolute "
                "paths starting with this folder."
            )
        extra = "\n\n".join(filter(None, [ws_note, ctx_injection]))

        if route.intent == "spec" and not session.spec_id:
            spec = await self.create_spec(message)
            session.spec_id = spec.id
            reply = Message(
                role=Role.ASSISTANT,
                content=(
                    f"I've started a spec for **{spec.name}**.\n\n"
                    f"{spec.requirements_md}\n\n"
                    "Reply **approve** to move to the design phase."
                ),
            )
        elif route.intent in ("action", "debug"):
            agent = self._agents.get(route.agent, self.developer)
            reply = await agent.run(
                session, message, extra_context=extra, model=route.model
            )
        else:
            reply = await self._chat_agent.run(
                session, message, extra_context=extra, model=route.model
            )

        await self.sessions.add_message(session.id, reply)
        await self._maybe_compact(session)
        return reply

    # ── Streaming agentic chat (GET /chat/stream) ─────────────────────────────
    #
    # This is the core that makes MyCodeAI behave like Cursor / Kiro:
    #   1. Classify intent
    #   2. If action/spec → run the tool loop, streaming every step
    #   3. Each tool call → emit tool_call event BEFORE calling the tool
    #   4. Each tool result → emit tool_result event AND specific events
    #      (file_created, file_edited, command_run) so the UI can update
    #   5. Text tokens → emit token events
    #   6. Loop until no more tool calls (up to MAX_ROUNDS)
    #
    async def stream_agentic(
        self,
        session: Session,
        message: str,
        model: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> AsyncIterator[dict]:

        await self.hook_runner.fire("UserPromptSubmit", {"message": message})
        route = await router.route(message, model_override=model)
        intent = route.intent
        logger.info(
            "stream intent=%s agent=%s model=%s via=%s | %s",
            intent, route.agent, route.model, route.via, message[:60],
        )

        yield {
            "type": "model_selected",
            "model": route.model,
            "reason": route.reason,
            "intent": intent,
            "agent": route.agent,
            "via": route.via,
        }

        # For chat, use lightweight context (no filesystem scans / DB queries)
        # to keep response latency low. Action/spec get the full context.
        ctx_injection = await context_builder.build(
            session_id=session.id,
            session_msgs=session.messages,
            spec_id=session.spec_id,
            lightweight=(intent == "chat"),
        )

        ws_note = ""
        if workspace:
            ws_note = (
                f"[CURRENT WORKSPACE FOLDER: {workspace}]\n"
                "Unless the user explicitly names a different location, create ALL "
                "new files and folders INSIDE this workspace folder. Use absolute "
                "paths starting with this folder."
            )

        if intent == "chat":
            yield {"type": "status", "text": "Thinking…"}
            user_msg = Message(role=Role.USER, content=message)
            session.messages.append(user_msg)

            full_system = self._chat_agent.system_prompt
            if ws_note:
                full_system = f"{full_system}\n\n{ws_note}"
            if ctx_injection:
                full_system = f"{full_system}\n\n---\n{ctx_injection}"

            system_prompt, window = self._ctx.build_window(session, full_system)
            full = ""
            async for token in ollama.stream_chat(
                messages=window,
                model=route.model,
                system_prompt=system_prompt,
            ):
                full += token
                yield {"type": "token", "content": token}
            reply = Message(role=Role.ASSISTANT, content=full)
            session.messages.append(reply)
            await self.sessions.add_message(session.id, reply)
            yield {"type": "done", "session_id": session.id}
            return

        # ── Spec flow ─────────────────────────────────────────────────────────
        if intent == "spec" and not session.spec_id:
            yield {"type": "status", "text": "Planning requirements…"}
            spec = await self.create_spec(message)
            session.spec_id = spec.id
            text = (
                f"✅ Spec created: **{spec.name}**\n\n"
                f"{spec.requirements_md}\n\n"
                "Reply **approve** to generate the design."
            )
            for token in text:
                yield {"type": "token", "content": token}
                await asyncio.sleep(0)
            reply = Message(role=Role.ASSISTANT, content=text)
            session.messages.append(reply)
            await self.sessions.add_message(session.id, reply)
            yield {"type": "done", "session_id": session.id}
            return

        # ── Action / debug: full autonomous tool loop, every step streamed ───
        yield {"type": "status", "text": "Agent is working…"}

        # Track everything done during this run for the final summary card
        files_created: list[str] = []
        files_edited: list[str] = []
        files_deleted: list[str] = []
        commands_run: list[str] = []

        effective_model = route.model
        agent = self._agents.get(route.agent, self.developer)
        MAX_ROUNDS = 20

        # Inject rich context (workspace + history) into system prompt
        agent_system = agent.system_prompt
        if ws_note:
            agent_system = f"{agent_system}\n\n{ws_note}"
        if ctx_injection:
            agent_system = f"{agent_system}\n\n---\nCONTEXT:\n{ctx_injection}"

        user_msg = Message(role=Role.USER, content=message)
        session.messages.append(user_msg)

        # Permission mode: "auto" = run everything, "ask" = show each action
        # Default is auto — user can switch via settings
        permission_mode = getattr(settings, "permission_mode", "auto")

        # Agent todo/plan list — parsed from markdown checklists in the agent's
        # text responses (Cursor/Kiro style "what I'll do" plan).
        # key = task text, value = "pending" | "in_progress" | "done"
        todo_items: dict[str, str] = {}

        for _round in range(MAX_ROUNDS):
            system_prompt, window = self._ctx.build_window(session, agent_system)

            yield {"type": "status", "text": f"Thinking… (step {_round+1})"}
            response = await ollama.chat(
                messages=window,
                model=effective_model,
                tools=tool_registry.all_schemas(),
                system_prompt=system_prompt,
            )
            session.messages.append(response)

            # Stream text content as tokens
            if response.content:
                for token in response.content:
                    yield {"type": "token", "content": token}
                    await asyncio.sleep(0)

                # Parse markdown checklist (- [ ] / - [x]) to build the todo plan
                parsed = _parse_checklist(response.content)
                if parsed:
                    changed = False
                    for text, done in parsed:
                        prev = todo_items.get(text)
                        new_state = "done" if done else ("in_progress" if prev != "done" else "done")
                        if prev != new_state:
                            todo_items[text] = new_state
                            changed = True
                    if changed:
                        yield {"type": "todo_update", "items": [
                            {"text": t, "status": s} for t, s in todo_items.items()
                        ]}

            # No tool calls → done
            if not response.tool_calls:
                break

            # Execute each tool call with permission events
            for call in response.tool_calls:
                # Classify this tool's impact
                is_destructive = call.name in (
                    "write_file", "edit_file", "delete_file", "run_command",
                    "run_file", "setup_env", "git_rewind",
                )

                # Emit permission_request so UI can show Accept/Decline
                # In "auto" mode the UI auto-accepts; in "ask" mode it waits
                yield {
                    "type": "permission_request",
                    "tool": call.name,
                    "args": call.arguments,
                    "mode": permission_mode,  # "auto" | "ask"
                    "preview": _tool_preview(call.name, call.arguments),
                }

                # Also emit the raw tool_call for activity display
                yield {"type": "tool_call", "name": call.name, "args": call.arguments}
                yield {"type": "status", "text": f"🔧 {call.name}(…)"}

                result = await tool_registry.dispatch(call)
                response.tool_results.append(result)

                # Emit specific UI events
                if call.name == "write_file" and not result.error:
                    path = call.arguments.get("path", "")
                    files_created.append(path)
                    yield {"type": "file_created", "path": path}
                    yield {"type": "status", "text": f"✅ Created {path}"}

                elif call.name == "edit_file" and not result.error:
                    path = call.arguments.get("path", "")
                    files_edited.append(path)
                    yield {"type": "file_edited", "path": path}
                    yield {"type": "status", "text": f"✏️ Edited {path}"}

                elif call.name == "delete_file" and not result.error:
                    path = call.arguments.get("path", "")
                    files_deleted.append(path)
                    yield {"type": "status", "text": f"🗑 Deleted {path}"}

                elif call.name in ("run_command", "run_file", "setup_env") and not result.error:
                    out = result.output if isinstance(result.output, dict) else {}
                    cmd = call.arguments.get("command") or call.arguments.get("path") or call.name
                    body = str(out.get("stdout", "")) + str(out.get("stderr", ""))
                    if not body.strip():
                        body = str(result.output or "")
                    commands_run.append(str(cmd))
                    yield {
                        "type": "command_run",
                        "command": cmd,
                        "exit_code": out.get("exit_code", 0),
                        "output": body[:2000],
                    }
                    yield {"type": "status", "text": f"⚡ Ran: {str(cmd)[:60]}"}

                yield {
                    "type": "tool_result",
                    "name": call.name,
                    "output": str(result.output or "")[:1000],
                    "error": result.error,
                }

                # Auto-complete todo items that match the action just performed
                if not result.error and todo_items:
                    _mark_matching_todos(todo_items, call.name, call.arguments)
                    if any(s == "done" for s in todo_items.values()):
                        yield {"type": "todo_update", "items": [
                            {"text": t, "status": s} for t, s in todo_items.items()
                        ]}

                # Feed result back to model
                result_text = (
                    f"[{call.name} result]\n{result.output}"
                    if not result.error
                    else f"[{call.name} error]\n{result.error}"
                )
                session.messages.append(Message(role=Role.TOOL, content=result_text))

                # Only trigger debugger for run_command failures (not git/file errors)
                if (
                    call.name == "run_command"
                    and result.error
                    and "nothing to commit" not in str(result.error)
                ):
                    yield {"type": "status", "text": "🐛 Error detected, debugging…"}
                    debug_reply = await self.debugger.debug(
                        session,
                        error=result.error,
                        context=f"Command: {call.arguments.get('command','')}\nIn: {call.arguments.get('cwd','.')}",
                    )
                    yield {"type": "status", "text": "🔧 Applied fix, retrying…"}
                    for token in debug_reply:
                        yield {"type": "token", "content": token}
                        await asyncio.sleep(0)

        await self._maybe_compact(session)
        await self.sessions.add_message(session.id, session.messages[-1])

        # Final summary card — Cursor/Kiro style "what I changed" recap
        if files_created or files_edited or files_deleted or commands_run:
            yield {
                "type": "summary",
                "files_created": list(dict.fromkeys(files_created)),
                "files_edited": list(dict.fromkeys(files_edited)),
                "files_deleted": list(dict.fromkeys(files_deleted)),
                "commands_run": list(dict.fromkeys(commands_run)),
            }

        yield {"type": "done", "session_id": session.id}

    # ── Spec flow ─────────────────────────────────────────────────────────────

    async def create_spec(self, goal: str, name: Optional[str] = None) -> Spec:
        spec_name = name or self._slugify(goal[:40])
        spec = Spec(id=str(uuid4()), name=spec_name, goal=goal)
        session = await self.sessions.create_session(spec.id)
        logger.info("Generating requirements: %s", spec_name)
        spec.requirements_md = await self.planner.generate_requirements(session, goal)
        spec.phase = SpecPhase.REQUIREMENTS
        await self.specs.save(spec)
        await self._write_spec_files(spec)
        await self.hook_runner.fire(
            "SpecCreated", {"spec_id": spec.id, "phase": spec.phase}
        )
        return spec

    async def advance_spec(
        self, spec_id: str, approved: bool = True, feedback: str = ""
    ) -> Spec:
        spec = await self.specs.get(spec_id)
        if not spec:
            raise ValueError(f"Spec not found: {spec_id}")
        session = await self.sessions.create_session(spec.id)
        if not approved:
            spec = await self._regenerate_phase(spec, session, feedback)
        else:
            spec = await self._advance_phase(spec, session)
        await self.specs.save(spec)
        await self._write_spec_files(spec)
        return spec

    async def run_next_task(self, spec_id: str) -> dict:
        """
        Find and implement the next pending task.
        Run → Review → Debug loop:
          1. DeveloperAgent implements the task (up to 12 tool rounds).
          2. ReviewerAgent reviews the modified files.
          3. If FAIL → DebuggerAgent fixes then Developer retries (once).
          4. Checkpoint on success.
        """
        spec = await self.specs.get(spec_id)
        if not spec or spec.phase != SpecPhase.IMPLEMENTATION:
            raise ValueError("Spec not in implementation phase")

        task = self._next_pending_task(spec)
        if not task:
            spec.phase = SpecPhase.REVIEW
            await self.specs.save(spec)
            return {"status": "all_tasks_complete"}

        task.status = TaskStatus.IN_PROGRESS
        await self.specs.save(spec)
        await self.hook_runner.fire(
            "TaskStarted", {"task_id": task.id, "task_title": task.title}
        )

        session = await self.sessions.create_session(spec_id)
        spec_ctx = f"Requirements:\n{spec.requirements_md}\n\nDesign:\n{spec.design_md}"

        try:
            # ── 1. Developer implements ───────────────────────────────────────
            summary, files = await self.developer.implement_task(
                session, task, spec_ctx
            )
            task.files_modified = files

            # ── 2. Reviewer checks ────────────────────────────────────────────
            if files:
                review_session = await self.sessions.create_session(spec_id)
                review_text, verdict = await self.reviewer.review_task(
                    review_session, task, files
                )
                if verdict == "FAIL":
                    # ── 3. Debugger fixes ─────────────────────────────────────
                    debug_session = await self.sessions.create_session(spec_id)
                    await self.debugger.debug(debug_session, review_text, spec_ctx)
                    # Developer retries once
                    summary, files = await self.developer.implement_task(
                        session, task, spec_ctx
                    )

            task.status = TaskStatus.COMPLETED

            # ── 4. Checkpoint ─────────────────────────────────────────────────
            if settings.auto_checkpoint:
                from ..tools.git_tool import git_checkpoint

                sha = await git_checkpoint(f"task {task.id}: {task.title}")
                task.checkpoint_sha = sha

            await self.specs.save(spec)
            await self.hook_runner.fire(
                "TaskCompleted", {"task_id": task.id, "summary": summary}
            )
            return {
                "task_id": task.id,
                "status": "completed",
                "summary": summary,
                "files": files,
            }

        except Exception as exc:
            task.status = TaskStatus.FAILED
            await self.specs.save(spec)
            logger.error("Task %s failed: %s", task.id, exc)
            raise

    # ── Intent classifier ─────────────────────────────────────────────────────

    @staticmethod
    def _classify_intent(message: str) -> str:
        """
        "action" — user wants the agent to DO something (create/write/run/fix…)
        "spec"   — user wants to plan and build a full multi-file project/app
        "chat"   — question, explanation, conversation
        """
        lower = message.strip().lower()
        words = lower.split()
        first = words[0] if words else ""

        action_verbs = {
            "create",
            "write",
            "make",
            "add",
            "generate",
            "produce",
            "output",
            "run",
            "execute",
            "compile",
            "test",
            "fix",
            "debug",
            "refactor",
            "rename",
            "delete",
            "remove",
            "move",
            "copy",
            "edit",
            "update",
            "modify",
            "change",
            "append",
            "insert",
            "replace",
            "open",
            "mkdir",
            "touch",
            "init",
            "setup",
            "install",
            "build",
            "implement",
        }
        file_signals = {
            ".cpp",
            ".py",
            ".js",
            ".ts",
            ".dart",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".h",
            ".cs",
            ".rb",
            ".php",
            ".sh",
            ".html",
            ".css",
            ".json",
            ".yaml",
            ".toml",
            ".md",
            ".txt",
            "file",
            "folder",
            "directory",
            "function",
            "class",
            "method",
            "code",
            "snippet",
            "script",
            "program",
            "module",
            "component",
        }
        action_phrases = [
            "can you create",
            "can you write",
            "can you make",
            "can you build",
            "could you create",
            "could you write",
            "could you make",
            "i want you to create",
            "i want you to write",
            "i need you to create",
            "i need a file",
            "i need a function",
            "i need a class",
            "create a file",
            "write a file",
            "make a file",
            "create a folder",
            "make a folder",
            "create a directory",
            "write the code",
            "write code",
            "generate code",
        ]
        spec_phrases = [
            "build an app",
            "build a app",
            "build an application",
            "build a website",
            "build a web app",
            "build a mobile app",
            "build an android",
            "build an ios",
            "build a flutter",
            "develop an app",
            "develop a website",
            "develop a system",
            "create an app",
            "create an application",
            "create a website",
            "create a mobile app",
            "create a web app",
            "create an android",
            "create an ios",
            "make an app",
            "make an application",
            "make a website",
            "make an android",
            "make an ios",
            "i want to build",
            "i want to create an app",
            "build me an",
            "build me a",
        ]

        if first in action_verbs:
            return "action"
        if len(words) >= 2 and words[0] == "please" and words[1] in action_verbs:
            return "action"
        if any(sig in lower for sig in file_signals) and any(
            v in lower for v in action_verbs
        ):
            return "action"
        if any(p in lower for p in action_phrases):
            return "action"
        if any(p in lower for p in spec_phrases) and len(message) > 30:
            return "spec"

        # ── Catch follow-up "do it" messages ─────────────────────────────────
        # User already described a project and now says "do it", "make it", etc.
        do_it_now = {
            "do it",
            "do it now",
            "make it",
            "make it now",
            "start",
            "go",
            "go ahead",
            "proceed",
            "continue",
            "yes do it",
            "yes",
            "ok do it",
            "ok go ahead",
            "i want to make this project right now",
            "i want to make this",
            "make this project",
            "start building",
            "start the project",
            "start coding",
            "implement it",
            "implement this",
            "build it",
            "build this",
            "create it now",
            "create this now",
            "just do it",
            "go for it",
            "lets start",
            "let's start",
            "lets go",
            "let's go",
            "begin",
            "begin now",
            "start now",
        }
        if lower.strip() in do_it_now or any(p in lower for p in do_it_now):
            return "action"

        return "chat"

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _advance_phase(self, spec: Spec, session: Session) -> Spec:
        if spec.phase == SpecPhase.REQUIREMENTS:
            spec.design_md = await self.planner.generate_design(
                session, spec.requirements_md
            )
            spec.phase = SpecPhase.DESIGN
        elif spec.phase == SpecPhase.DESIGN:
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
        fb = f"User feedback: {feedback}\n\nPlease revise."
        if spec.phase == SpecPhase.REQUIREMENTS:
            spec.requirements_md = await self.planner.generate_requirements(
                session, f"{spec.goal}\n\n{fb}"
            )
        elif spec.phase == SpecPhase.DESIGN:
            spec.design_md = await self.planner.generate_design(
                session, spec.requirements_md + f"\n\n{fb}"
            )
        elif spec.phase == SpecPhase.TASKS:
            tasks_md = await self.planner.generate_tasks(
                session, spec.requirements_md, spec.design_md + f"\n\n{fb}"
            )
            spec.tasks = self._parse_tasks(tasks_md)
        return spec

    async def _write_spec_files(self, spec: Spec):
        from ..tools.file_tools import write_file

        base = f"specs/{spec.name}"
        if spec.requirements_md:
            await write_file(f"{base}/requirements.md", spec.requirements_md)
        if spec.design_md:
            await write_file(f"{base}/design.md", spec.design_md)
        if spec.tasks:
            lines = [f"# Tasks: {spec.name}\n"]
            for t in spec.tasks:
                s = "x" if t.status == TaskStatus.COMPLETED else " "
                lines.append(f"- [{s}] {t.id} {t.title}")
            await write_file(f"{base}/tasks.md", "\n".join(lines))

    def _parse_tasks(self, tasks_md: str) -> list[SpecTask]:
        tasks, seen = [], set()
        for m in re.finditer(
            r"-\s*\[[ x]\]\s*([\d.]+)\s+(.+?)(?=\n\s*-|\Z)", tasks_md, re.DOTALL
        ):
            tid = m.group(1).strip()
            title = m.group(2).strip().split("\n")[0].strip()
            if tid not in seen:
                seen.add(tid)
                tasks.append(SpecTask(id=tid, title=title, description=title))
        return tasks

    def _next_pending_task(self, spec: Spec) -> Optional[SpecTask]:
        done = {t.id for t in spec.tasks if t.status == TaskStatus.COMPLETED}
        for t in spec.tasks:
            if t.status == TaskStatus.PENDING and all(
                d in done for d in t.dependencies
            ):
                return t
        return None

    async def _maybe_compact(self, session: Session):
        if self._ctx.needs_compaction(session):
            summary = await self.compactor.compact(session)
            await self.sessions.update_summary(session.id, summary)

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _tool_preview(tool_name: str, args: dict) -> str:
    """Human-readable one-line description of what a tool will do."""
    if tool_name == "write_file":
        path    = args.get("path", "?")
        content = args.get("content", "")
        lines   = content.count("\n") + 1
        size    = len(content)
        return f"Write {lines} lines ({size} chars) → {path}"
    if tool_name == "edit_file":
        return f"Edit {args.get('path','?')} — replace snippet"
    if tool_name == "run_command":
        return f"Run: {args.get('command','?')} (cwd: {args.get('cwd','.')})"
    if tool_name == "delete_file":
        return f"Delete: {args.get('path','?')}"
    if tool_name == "git_checkpoint":
        return f"Git commit: {args.get('message','checkpoint')}"
    if tool_name == "detect_project":
        return f"Detect project type at {args.get('path','.')}"
    if tool_name == "read_project":
        return f"Read project at {args.get('path','.')}"
    if tool_name == "run_file":
        return f"Run: {args.get('path','?')} {' '.join(args.get('args',[])) if args.get('args') else ''}".strip()
    if tool_name == "setup_env":
        return f"Set up environment for {args.get('path','.')}"
    if tool_name == "search_code":
        return f"Search code: /{args.get('pattern','?')}/ in {args.get('path','.')}"
    return f"{tool_name}({', '.join(f'{k}={str(v)[:30]}' for k,v in args.items())})"


def _parse_checklist(text: str) -> list[tuple[str, bool]]:
    """
    Parse markdown checklists from agent text.
    Returns list of (task_text, is_done) tuples.
    Matches lines like:
      - [ ] create server.js
      - [x] write README
      * [ ] test the build
    """
    items: list[tuple[str, bool]] = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s*\[\s*([ xX])\s*\]\s*(.+?)\s*$", line)
        if m:
            done = m.group(1).lower() == "x"
            task = m.group(2).strip()
            if task:
                items.append((task, done))
    return items


def _mark_matching_todos(todo_items: dict[str, str], tool_name: str, args: dict):
    """
    Mark todo items as 'done' when the just-completed tool action matches them.
    Matching is loose: if the todo text contains the file path or a key
    keyword from the tool arguments, consider it done.
    """
    path = args.get("path", "") or args.get("command", "") or ""
    path_lower = path.lower()
    basename = path.split("/")[-1].lower() if path else ""

    for task in list(todo_items):
        if todo_items[task] == "done":
            continue
        task_lower = task.lower()
        if not path_lower:
            continue
        # Match if file basename or full path appears in the todo text
        if basename and (basename in task_lower or path_lower in task_lower):
            todo_items[task] = "done"
            continue
        # Match by verb + keyword (e.g. todo "run tests" + run_command "pytest")
        verb_map = {
            "write_file": {"create", "write", "add", "make", "build", "scaffold"},
            "edit_file": {"edit", "update", "modify", "fix", "change", "refactor"},
            "delete_file": {"delete", "remove"},
            "run_command": {"run", "execute", "test", "install", "build", "compile"},
            "run_file": {"run", "execute"},
            "setup_env": {"setup", "install", "init", "configure"},
            "git_checkpoint": {"commit", "checkpoint", "save"},
        }
        verbs = verb_map.get(tool_name, set())
        if verbs and any(v in task_lower for v in verbs):
            # Also need a path/keyword overlap to avoid false positives
            tokens = set(re.findall(r"[a-z0-9_.-]+", task_lower))
            arg_tokens = set(re.findall(r"[a-z0-9_.-]+", path_lower))
            if tokens & arg_tokens:
                todo_items[task] = "done"

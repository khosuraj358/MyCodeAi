"""
Shared Pydantic models used across the agent engine.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enumerations ─────────────────────────────────────────────────────────────

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SpecPhase(str, Enum):
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    TASKS = "tasks"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    DONE = "done"


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# ── Messages ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Role
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tokens: int = 0


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    name: str
    output: Any
    error: Optional[str] = None
    duration_ms: int = 0


# ── Spec models ───────────────────────────────────────────────────────────────

class SpecTask(BaseModel):
    id: str                               # e.g. "1.1"
    title: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    files_modified: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    checkpoint_sha: Optional[str] = None


class Spec(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    goal: str
    phase: SpecPhase = SpecPhase.REQUIREMENTS
    requirements_md: str = ""
    design_md: str = ""
    tasks: list[SpecTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Session models ────────────────────────────────────────────────────────────

class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    spec_id: Optional[str] = None
    messages: list[Message] = Field(default_factory=list)
    context_tokens: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    compacted_at: Optional[datetime] = None
    summary: str = ""


# ── Agent activity ────────────────────────────────────────────────────────────

class AgentActivity(BaseModel):
    agent_name: str
    model: str
    status: str          # "thinking" | "tool_call" | "writing" | "idle"
    current_task: Optional[str] = None
    files_modified: list[str] = Field(default_factory=list)
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── API request/response models ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    spec_id: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message: Message
    activity: Optional[AgentActivity] = None


class CreateSpecRequest(BaseModel):
    goal: str
    name: Optional[str] = None


class AdvanceSpecRequest(BaseModel):
    spec_id: str
    approved: bool = True
    feedback: str = ""


class PermissionRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    reason: str


class PermissionResponse(BaseModel):
    decision: PermissionDecision
    reason: str = ""

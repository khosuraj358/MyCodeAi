"""
MyCodeAI Agent Server  — FastAPI  v0.3.8

Endpoints
─────────
GET  /health
GET  /models
GET  /sessions
POST /chat                  — blocking chat, intent routing + tools
GET  /chat/stream           — SSE streaming: tokens + tool events + image/PDF
POST /analyze               — analyze image or PDF, returns text description
POST /spec / POST /spec/advance / GET /spec/{id} / GET /specs
POST /task/run
POST /checkpoint
WS   /ws/{session_id}
"""

from __future__ import annotations

import asyncio
import json
import logging
import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from .config import settings
from .models import (
    ChatRequest,
    ChatResponse,
    CreateSpecRequest,
    AdvanceSpecRequest,
    Message,
    Role,
    Session,
)
from .session_manager import SessionManager
from ..agents.orchestrator import Orchestrator
from ..memory.spec_store import SpecStore
from ..tools.git_tool import GitTool
from ..tools.file_reader import extract_file_content

# Register all tools at startup
import agent.tools.file_tools  # noqa: F401
import agent.tools.shell_tool  # noqa: F401
import agent.tools.git_tool  # noqa: F401
import agent.tools.project_tools  # noqa: F401

logger = logging.getLogger(__name__)

session_mgr = SessionManager()
spec_store = SpecStore()
orchestrator: Optional[Orchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    await session_mgr.init_db()
    await spec_store.init_db()
    orchestrator = Orchestrator(session_mgr, spec_store)

    # Warm both key models into Ollama memory so the first "hi" or code
    # request is instant (no disk-load delay). Done in parallel.
    from .ollama_client import ollama
    if await ollama.is_running():
        warm_models = [settings.fast_model, settings.code_model]
        logger.info("warming models into memory: %s", warm_models)
        await asyncio.gather(
            *[ollama.warm_model(m) for m in warm_models],
            return_exceptions=True,
        )
        logger.info("model warm-up complete")
    else:
        logger.warning("Ollama not running — skipping model warm-up")

    logger.info(
        "MyCodeAI agent server v0.3.8 ready on %s:%d", settings.host, settings.port
    )
    yield
    logger.info("Shutting down")


app = FastAPI(title="MyCodeAI Agent", version="0.3.8", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_create(
    session_id: Optional[str], spec_id: Optional[str] = None
) -> Session:
    if session_id:
        s = await session_mgr.get_session(session_id)
        if s:
            return s
    return await session_mgr.create_session(spec_id)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ── Basic ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.3.8"}


@app.get("/models")
async def list_models():
    from .ollama_client import ollama

    try:
        return {"models": await ollama.list_models()}
    except Exception as e:
        raise HTTPException(503, f"Ollama unavailable: {e}")


@app.get("/ram")
async def ram_status_endpoint():
    """Current available RAM and which models fit right now."""
    from .model_router import ram_status

    return ram_status()


@app.get("/context")
async def get_context(session_id: Optional[str] = Query(None)):
    """Full situational context injected for a session — workspace + history + env."""
    from .context_builder import context_builder

    session = await _get_or_create(session_id) if session_id else None
    ctx = await context_builder.build(
        session_id=session.id if session else "none",
        session_msgs=session.messages if session else [],
        spec_id=session.spec_id if session else None,
    )
    return {"context": ctx}


@app.get("/sessions")
async def list_sessions():
    return await session_mgr.list_sessions()


# ── Analyze image / PDF ───────────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    file_path: str
    question: str = "Describe this in detail. If it contains text, extract all of it."
    model: Optional[str] = None


@app.post("/analyze")
async def analyze_file(req: AnalyzeRequest):
    """
    Read an image or PDF and return its content/description.
    - Images  → gemma3:4b vision model (direct pixel analysis)
    - PDFs    → extract text with pymupdf; use vision for scanned pages
    - Other   → extract as text
    """
    p = Path(req.file_path)
    if not p.exists():
        raise HTTPException(404, f"File not found: {req.file_path}")

    info = extract_file_content(p)

    # ── Images: send to Ollama vision model ──────────────────────────────────
    if info["type"] == "image":
        model = req.model or settings.vision_model
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": req.question,
                                "images": [info["base64"]],
                            }
                        ],
                        "stream": False,
                        "options": {
                            "num_ctx": 2048,
                            "num_predict": 1024,
                            "temperature": 0.1,
                        },
                    },
                )
                resp.raise_for_status()
                description = resp.json()["message"]["content"]
        except Exception as e:
            raise HTTPException(503, f"Vision model error: {e}")

        return {
            "type": "image",
            "file": p.name,
            "model": model,
            "description": description,
        }

    # ── PDFs / text / office: return extracted text ──────────────────────────
    return {
        "type": info["type"],
        "file": p.name,
        "content": info["content"],
        "summary": info.get("summary", ""),
    }


# ── Blocking chat ─────────────────────────────────────────────────────────────


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session = await _get_or_create(req.session_id, req.spec_id)
    reply = await orchestrator.chat(session, req.message, model=req.model)
    await session_mgr.add_message(session.id, reply)
    return ChatResponse(session_id=session.id, message=reply)


# ── SSE streaming chat ────────────────────────────────────────────────────────
# Supports:
#   ?message=...          the user's text
#   ?session_id=...       optional session continuity
#   ?model=...            optional model override
#   ?file_path=...        optional file to analyze (image/PDF/code/doc)


@app.get("/chat/stream")
async def chat_stream(
    message: str = Query(...),
    session_id: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    file_path: Optional[str] = Query(None),
    workspace: Optional[str] = Query(None),
):
    session = await _get_or_create(session_id)

    enriched_message = message
    file_context_event: Optional[dict] = None

    if file_path:
        p = Path(file_path)
        if p.exists():
            info = extract_file_content(p)

            if info["type"] == "image":
                # Analyze image first (vision call), then stream the result
                vision_model = settings.vision_model
                try:
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.post(
                            f"{settings.ollama_base_url}/api/chat",
                            json={
                                "model": vision_model,
                                "messages": [
                                    {
                                        "role": "user",
                                        "content": f"Analyze this image. {message or 'Describe it in detail and extract any text.'}",
                                        "images": [info["base64"]],
                                    }
                                ],
                                "stream": False,
                                "options": {
                                    "num_ctx": 2048,
                                    "num_predict": 1024,
                                    "temperature": 0.1,
                                },
                            },
                        )
                        resp.raise_for_status()
                        image_description = resp.json()["message"]["content"]
                    enriched_message = (
                        f"[Image analyzed: {p.name}]\n"
                        f"Vision model description:\n{image_description}\n\n"
                        f"User question: {message or 'What do you see?'}"
                    )
                    file_context_event = {
                        "type": "file_analyzed",
                        "file": p.name,
                        "file_type": "image",
                        "summary": image_description[:200],
                    }
                except Exception as e:
                    enriched_message = (
                        f"[Image: {p.name} — could not analyze: {e}]\n\n{message}"
                    )

            elif info["type"] == "pdf":
                content = info["content"]
                enriched_message = (
                    f"[PDF: {p.name}]\n"
                    f"{content[:6000]}\n\n"
                    f"{'[Document truncated]' if len(content) > 6000 else ''}"
                    f"User question: {message or 'Summarize this document.'}"
                )
                file_context_event = {
                    "type": "file_analyzed",
                    "file": p.name,
                    "file_type": "pdf",
                    "summary": f"Extracted {len(content.splitlines())} lines of text",
                }
            else:
                # Code / text / office
                content = info["content"]
                enriched_message = (
                    f"[File: {p.name}]\n```\n{content[:8000]}\n```\n\n"
                    f"User question: {message}"
                )
                file_context_event = {
                    "type": "file_analyzed",
                    "file": p.name,
                    "file_type": info["type"],
                    "summary": f"{p.suffix.upper()} file attached",
                }

    async def events() -> AsyncIterator[str]:
        # Emit file context event first
        if file_context_event:
            yield _sse(file_context_event)

        try:
            # When a file is attached, force "chat" mode — use the fast model
            # to answer the question about the file content directly
            if file_path and file_context_event:
                from ..agents.orchestrator import _ChatAgent
                from ..core.context_engine import ContextEngine
                from .ollama_client import ollama

                agent = _ChatAgent()
                ctx_engine = ContextEngine()
                use_model = model or settings.fast_model

                user_msg = Message(role=Role.USER, content=enriched_message)
                session.messages.append(user_msg)
                await session_mgr.add_message(session.id, user_msg)

                sys_prompt, window = ctx_engine.build_window(
                    session, agent.system_prompt
                )
                full = ""
                async for token in ollama.stream_chat(
                    messages=window, model=use_model, system_prompt=sys_prompt
                ):
                    full += token
                    yield _sse({"type": "token", "content": token})

                reply = Message(role=Role.ASSISTANT, content=full)
                session.messages.append(reply)
                await session_mgr.add_message(session.id, reply)
                yield _sse({"type": "done", "session_id": session.id})
            else:
                # Normal agentic path (intent routing + tools)
                async for event in orchestrator.stream_agentic(
                    session, enriched_message, model=model, workspace=workspace
                ):
                    yield _sse(event)
                if session.messages:
                    await session_mgr.add_message(session.id, session.messages[-1])

        except Exception as exc:
            logger.exception("stream error")
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Spec endpoints ────────────────────────────────────────────────────────────


@app.post("/spec")
async def create_spec(req: CreateSpecRequest):
    spec = await orchestrator.create_spec(req.goal, req.name)
    return spec.model_dump()


@app.post("/spec/advance")
async def advance_spec(req: AdvanceSpecRequest):
    spec = await orchestrator.advance_spec(
        req.spec_id, approved=req.approved, feedback=req.feedback
    )
    return spec.model_dump()


@app.get("/spec/{spec_id}")
async def get_spec(spec_id: str):
    spec = await spec_store.get(spec_id)
    if not spec:
        raise HTTPException(404, "Spec not found")
    return spec.model_dump()


@app.get("/specs")
async def list_specs():
    return await spec_store.list_all()


# ── Task execution ────────────────────────────────────────────────────────────


@app.post("/task/run")
async def run_task(spec_id: str = Query(...)):
    try:
        return await orchestrator.run_next_task(spec_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Git ───────────────────────────────────────────────────────────────────────


@app.post("/checkpoint")
async def create_checkpoint(message: str = "checkpoint"):
    git = GitTool(settings.workspace_root)
    sha = await git.checkpoint(message)
    return {"sha": sha, "message": message}


# ── WebSocket ─────────────────────────────────────────────────────────────────


@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = await _get_or_create(session_id)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            if not message:
                continue
            async for chunk in orchestrator.stream_agentic(session, message):
                await websocket.send_json(chunk)
    except WebSocketDisconnect:
        logger.info("WS disconnected: %s", session_id)
    except Exception as e:
        logger.error("WS error: %s", e)
        await websocket.close(code=1011)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    import uvicorn

    logging.basicConfig(level=settings.log_level.upper())
    uvicorn.run(
        "agent.core.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()

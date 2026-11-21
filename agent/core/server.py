"""
FastAPI + WebSocket server — the bridge between the VS Code extension and
the Python agent engine.

Endpoints:
  POST /chat              — single-turn chat
  WS   /ws/{session_id}  — streaming chat with live tool activity
  POST /spec              — create a new spec
  POST /spec/advance      — approve/reject the current phase
  GET  /spec/{spec_id}    — get spec state
  GET  /models            — list available Ollama models
  GET  /sessions          — list sessions
  POST /permission        — respond to a permission request
  POST /checkpoint        — create a Git checkpoint
  GET  /health            — health check
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import (
    ChatRequest,
    ChatResponse,
    CreateSpecRequest,
    AdvanceSpecRequest,
    PermissionResponse,
)
from .session_manager import SessionManager
from ..agents.orchestrator import Orchestrator
from ..memory.spec_store import SpecStore
from ..tools.git_tool import GitTool

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
    logger.info("MyCodeAI agent server ready on %s:%d", settings.host, settings.port)
    yield
    logger.info("Shutting down agent server")


app = FastAPI(title="MyCodeAI Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/models")
async def list_models():
    from .ollama_client import ollama
    try:
        models = await ollama.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


@app.get("/sessions")
async def list_sessions():
    return await session_mgr.list_sessions()


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id
    if not session_id:
        session = await session_mgr.create_session(req.spec_id)
        session_id = session.id
    else:
        session = await session_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    reply = await orchestrator.chat(session, req.message, model=req.model)
    return ChatResponse(session_id=session_id, message=reply)


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
        raise HTTPException(status_code=404, detail="Spec not found")
    return spec.model_dump()


@app.get("/specs")
async def list_specs():
    return await spec_store.list_all()


@app.post("/checkpoint")
async def create_checkpoint(message: str = "checkpoint"):
    git = GitTool(settings.workspace_root)
    sha = await git.checkpoint(message)
    return {"sha": sha, "message": message}


# ── WebSocket streaming ───────────────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = await session_mgr.get_session(session_id)
    if not session:
        session = await session_mgr.create_session()
        session_id = session.id

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            if not message:
                continue

            async for chunk in orchestrator.stream_chat(session, message):
                await websocket.send_json(chunk)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
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

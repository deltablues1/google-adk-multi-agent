"""
FastAPI application for Google Workspace ADK Web Interface.

Provides REST API endpoints and serves the operational dashboard.
Uses lifespan events for proper async initialization (APScheduler needs event loop).
"""

import os
import json
import base64
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from sse_starlette.sse import EventSourceResponse

from web.models import (
    ChatRequest, ChatResponse, SessionInfo,
    AgentInfo, TraceEvent,
)
from config.agent_registry import get_agent_config, get_worker_agent_names
from services.erp.errors import BusinessError

logger = logging.getLogger(__name__)

# Will be set by create_app()
_web_interface = None


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Simple bearer token auth for /api/* routes (except /api/media/).

    Activated only when API_TOKEN env var is set.
    Local dev without API_TOKEN: no auth required (all requests pass through).
    /api/media/ is intentionally excluded — browser <img>/<video> tags cannot send Bearer headers.
    """

    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/media/"):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app(interface) -> FastAPI:
    """Create FastAPI app with the given WebInterface instance."""
    global _web_interface
    _web_interface = interface

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Initialize system inside event loop (APScheduler needs it)."""
        logger.info("Initializing agent system (lifespan startup)...")
        await _web_interface.start()  # Initializes agents + loads sessions from Firestore
        agent_count = len(_web_interface.system.worker_agents)
        logger.info(f"System ready. {agent_count} worker agents loaded.")
        yield
        # Shutdown
        if (_web_interface.system and _web_interface.system.scheduler
                and _web_interface.system.scheduler.scheduler.running):
            _web_interface.system.scheduler.scheduler.shutdown(wait=False)
        await _web_interface.stop()  # Close Firestore connection
        logger.info("Web interface shutdown complete.")

    app = FastAPI(
        title="Google Workspace ADK Dashboard",
        version="1.0.0",
        lifespan=lifespan
    )

    # ── BusinessError → precise HTTP status ─────────────────────────────────
    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "field": exc.field},
        )

    # Optional bearer token auth (set API_TOKEN env var to enable)
    api_token = os.environ.get("API_TOKEN")
    if api_token:
        app.add_middleware(TokenAuthMiddleware, token=api_token)
        logger.info("API token authentication enabled")
    else:
        logger.warning("API_TOKEN not set — web API is unauthenticated (OK for local dev)")

    # Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # --- Dashboard ---
    @app.get("/")
    async def dashboard():
        return FileResponse(os.path.join(static_dir, "index.html"))

    # --- Chat endpoints ---
    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest):
        result = await _web_interface.chat(
            user_id=req.user_id,
            message=req.message
        )
        return ChatResponse(**result)

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest):
        # Convert attachments to dicts for web_interface
        attachments = None
        if req.attachments:
            attachments = [att.model_dump() for att in req.attachments]

        async def event_generator():
            async for event in _web_interface.chat_stream(
                user_id=req.user_id,
                message=req.message,
                attachments=attachments,
            ):
                event_type = event.get("event", "message")
                data = event.get("data", "")
                if isinstance(data, dict):
                    data = json.dumps(data, ensure_ascii=False)
                yield {"event": event_type, "data": data}

        return EventSourceResponse(event_generator())

    # --- Session endpoints ---
    @app.get("/api/sessions", response_model=List[SessionInfo])
    async def list_sessions():
        return _web_interface.list_sessions()

    @app.post("/api/sessions/new")
    async def new_session(user_id: str = "web-user"):
        session_id = _web_interface.create_new_session(user_id)
        return {"session_id": session_id, "user_id": user_id}

    @app.post("/api/sessions/{session_id}/switch")
    async def switch_session(session_id: str, user_id: str = "web-user"):
        success = _web_interface.switch_session(user_id, session_id)
        return {"success": success, "session_id": session_id}

    @app.get("/api/sessions/{session_id}/history")
    async def get_history(session_id: str):
        return _web_interface.get_history(session_id)

    # --- Agents endpoint ---
    @app.get("/api/agents", response_model=List[AgentInfo])
    async def list_agents():
        agents = []
        for name in get_worker_agent_names():
            config = get_agent_config(name)
            if config:
                agents.append(AgentInfo(
                    name=config.name,
                    model=config.model,
                    description=config.description,
                    tools=config.tools
                ))
        return agents

    # --- Status endpoint ---
    @app.get("/api/status")
    async def system_status():
        base_status = _web_interface.get_status()

        # Rate limiter metrics
        rate_data = {}
        services_data = {}
        try:
            from tools.resilience.rate_limiter import (
                get_all_metrics, get_service_status, SERVICE_CONFIGS
            )
            rate_data = get_all_metrics()
            for svc in SERVICE_CONFIGS:
                try:
                    services_data[svc] = get_service_status(svc)
                except Exception:
                    services_data[svc] = {"status": "unavailable"}
        except ImportError:
            pass

        return {
            **base_status,
            "rate_limiter": rate_data,
            "services": services_data
        }

    # --- Trace endpoint ---
    @app.get("/api/trace/{session_id}")
    async def get_trace(session_id: str):
        return _web_interface.get_trace(session_id)

    # --- Media endpoints ---
    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        user_id: str = Form(default="web-user"),
        session_id: str = Form(default=""),
    ):
        """
        Upload an image/PDF file. Returns file_id and base64 for agent processing.
        The frontend sends the file, then includes the file_id in the chat message.
        """
        from services.media_service import (
            save_upload, ALLOWED_MIME_TYPES, MAX_FILE_SIZE
        )

        # Validate MIME type
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. "
                       f"Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
            )

        # Read file
        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({len(file_bytes)} bytes). Max: {MAX_FILE_SIZE} bytes"
            )

        # Save locally
        result = save_upload(file_bytes, file.filename or "upload", file.content_type)

        # Return file_id + base64 for immediate use
        b64_data = base64.b64encode(file_bytes).decode("utf-8")

        return {
            "file_id": result["file_id"],
            "filename": result["original_name"],
            "mime_type": result["mime_type"],
            "size": result["size"],
            "base64": b64_data,
            "url": f"/api/media/{result['file_id']}",
        }

    @app.get("/api/media/{file_id}")
    async def serve_media(file_id: str):
        """Serve an uploaded or generated media file."""
        from services.media_service import get_file_path

        path = get_file_path(file_id)
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(path)

    # --- HITL (Human-in-the-Loop) approval endpoints ---

    @app.get("/api/hitl/pending")
    async def hitl_list_pending():
        """List all pending HITL approval requests."""
        from services.hitl_firestore_service import get_hitl_firestore_service
        return await get_hitl_firestore_service().list_pending()

    @app.get("/api/hitl/{confirmation_id}")
    async def hitl_get_one(confirmation_id: str):
        """Get a single HITL confirmation (any status)."""
        from services.hitl_firestore_service import get_hitl_firestore_service
        data = await get_hitl_firestore_service().get_one(confirmation_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Confirmation not found")
        return data

    @app.post("/api/hitl/{confirmation_id}/approve")
    async def hitl_approve(confirmation_id: str):
        """Approve a pending HITL confirmation."""
        from services.hitl_firestore_service import get_hitl_firestore_service
        ok = await get_hitl_firestore_service().approve(confirmation_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Confirmation not found or already decided")
        return {"confirmation_id": confirmation_id, "status": "approved"}

    @app.post("/api/hitl/{confirmation_id}/reject")
    async def hitl_reject(confirmation_id: str, reason: str = ""):
        """Reject a pending HITL confirmation."""
        from services.hitl_firestore_service import get_hitl_firestore_service
        ok = await get_hitl_firestore_service().reject(confirmation_id, reason=reason)
        if not ok:
            raise HTTPException(status_code=404, detail="Confirmation not found or already decided")
        return {"confirmation_id": confirmation_id, "status": "rejected", "reason": reason}

    # =======================================================================
    # ERP Routes (extracted to web/erp_routes.py)
    # =======================================================================
    from web.erp_routes import router as erp_router
    app.include_router(erp_router)

    # --- ERP UI (serves HTML, not under /api/erp prefix) ---
    @app.get("/erp")
    async def erp_dashboard():
        return FileResponse(os.path.join(static_dir, "erp.html"))

    return app

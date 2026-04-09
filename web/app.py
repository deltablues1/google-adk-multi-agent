"""
FastAPI application for Google Workspace ADK Web Interface.

Provides REST API endpoints and serves the operational dashboard.
Uses lifespan events for proper async initialization (APScheduler needs event loop).
"""

import os
import json
import base64
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, WebSocket
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

# ---------------------------------------------------------------------------
# In-memory cost & quota tracker (resets on server restart)
# ---------------------------------------------------------------------------
from collections import defaultdict
import time as _time

_cost_tracker = {
    "start_time": _time.time(),
    # TTS — Gemini 2.5 Flash TTS (preview, besplatno dok traje)
    "tts_calls": 0,
    "tts_chars": 0,
    "tts_cost_usd": 0.0,
    # Generative AI calls tracked via token counts
    "llm_calls": defaultdict(int),       # model -> count
    "llm_input_tokens": defaultdict(int), # model -> tokens
    "llm_output_tokens": defaultdict(int),# model -> tokens
    "llm_cost_usd": defaultdict(float),   # model -> USD
    # Veo / Imagen
    "veo_calls": 0,
    "veo_cost_usd": 0.0,
    "imagen_calls": 0,
    "imagen_cost_usd": 0.0,
    # 429 errors
    "quota_errors": defaultdict(int),
    "quota_errors_last": defaultdict(float),
    # Per-session spend (last 20 sessions)
    "session_costs": [],
}

# Pricing (USD) — Vertex AI Gemini, April 2026
_PRICING = {
    # model_key: (input_per_1M, output_per_1M)
    "gemini-3-flash":      (0.10,  0.40),
    "gemini-3.1-pro":      (3.50, 10.50),  # gemini-3.1-pro-preview (approx, preview pricing)
    "gemini-2.5-pro":      (3.50, 10.50),
    "gemini-2.5-flash":    (0.15,  0.60),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "tts":                 (0.075 / 1_000_000, 0),  # per char
    "veo3":                (0.40, 0),                # per video
    "imagen3":             (0.04, 0),                # per image
}

def _model_key(model_name: str) -> str:
    m = model_name.lower()
    if "3.1-pro" in m:     return "gemini-3.1-pro"
    if "3-flash" in m or "3flash" in m: return "gemini-3-flash"
    if "2.5-pro" in m:     return "gemini-2.5-pro"
    if "2.5-flash-lite" in m: return "gemini-2.5-flash-lite"
    if "2.5-flash" in m:   return "gemini-2.5-flash"
    return m

def _track_tts(char_count: int):
    _cost_tracker["tts_calls"] += 1
    _cost_tracker["tts_chars"] += char_count
    # TTS preview = besplatno, ali pratimo za kad krene naplaćivati
    _cost_tracker["tts_cost_usd"] += char_count * _PRICING["tts"][0]

def _track_llm(model: str, input_tokens: int, output_tokens: int):
    key = _model_key(model)
    p = _PRICING.get(key, (0, 0))
    cost = (input_tokens * p[0] + output_tokens * p[1]) / 1_000_000
    _cost_tracker["llm_calls"][key] += 1
    _cost_tracker["llm_input_tokens"][key] += input_tokens
    _cost_tracker["llm_output_tokens"][key] += output_tokens
    _cost_tracker["llm_cost_usd"][key] += cost

def _track_veo():
    _cost_tracker["veo_calls"] += 1
    _cost_tracker["veo_cost_usd"] += _PRICING["veo3"][0]

def _track_imagen():
    _cost_tracker["imagen_calls"] += 1
    _cost_tracker["imagen_cost_usd"] += _PRICING["imagen3"][0]

def _track_quota_error(service: str):
    _cost_tracker["quota_errors"][service] += 1
    _cost_tracker["quota_errors_last"][service] = _time.time()

LIVE_SYSTEM_PROMPT = (
    "Ti si glasovna asistentica integrirana u Google Workspace poslovnu platformu. "
    "Odgovaraj kratko i jasno — razgovaramo glasom, ne pišemo. "
    "Ako te pitaju o emailovima, kalendarima, dokumentima ili zadacima, reci da to nije dostupno "
    "u glasovnom načinu rada — korisnik mora upisati poruku za agente. "
    "Govori prirodno, u jednoj ili dvije rečenice. Izbjegavaj nabrajanje i dugačke liste. "
    "Uvijek govori o sebi u ženskom rodu."
)


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
    app.mount("/static", StaticFiles(directory=static_dir, html=False), name="static")

    # --- Dashboard ---
    @app.get("/")
    async def dashboard():
        return FileResponse(
            os.path.join(static_dir, "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

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
                # Track 429/quota errors for monitoring
                if "429" in str(data) or "RESOURCE_EXHAUSTED" in str(data):
                    _track_quota_error("vertex_ai")
                yield {"event": event_type, "data": data}

        return EventSourceResponse(event_generator())

    # --- Gemini TTS endpoint ---
    @app.post("/api/tts")
    async def tts(request: Request):
        """Convert text to speech using Gemini 2.5 Flash TTS. Returns PCM16 audio @ 24kHz."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY not set")

        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="No text provided")

        # Strip markdown before TTS
        import re
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\n{2,}', '. ', text)
        text = re.sub(r'\n', ' ', text)
        text = text.strip()[:4000]  # Gemini TTS limit

        if not text:
            raise HTTPException(status_code=400, detail="Text is empty after cleanup")

        try:
            from google import genai as _genai
            from google.genai import types as _types
            _vkeys = ['GOOGLE_GENAI_USE_VERTEXAI', 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION']
            _backup = {k: os.environ.pop(k) for k in _vkeys if k in os.environ}
            try:
                _client = _genai.Client(api_key=api_key)
            finally:
                os.environ.update(_backup)

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _client.models.generate_content(
                    model='gemini-2.5-flash-preview-tts',
                    contents=text,
                    config=_types.GenerateContentConfig(
                        response_modalities=['AUDIO'],
                        speech_config=_types.SpeechConfig(
                            voice_config=_types.VoiceConfig(
                                prebuilt_voice_config=_types.PrebuiltVoiceConfig(voice_name='Aoede')
                            )
                        )
                    )
                )
            )
            pcm_data = response.candidates[0].content.parts[0].inline_data.data
            _track_tts(len(text))
            from fastapi.responses import Response
            return Response(content=pcm_data, media_type="audio/L16;codec=pcm;rate=24000")
        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- Gemini Live Voice WebSocket ---
    @app.websocket("/api/live")
    async def live_voice(websocket: WebSocket):
        """Real-time voice via Gemini 3.1 Flash Live API (PCM16 audio streaming)."""
        # Token auth via query param (WebSocket doesn't support custom headers in browsers)
        api_token = os.environ.get("API_TOKEN", "")
        if api_token:
            token = websocket.query_params.get("token", "")
            if token != api_token:
                await websocket.close(code=4001)
                return

        api_key = os.environ.get("GEMINI_API_KEY", "")

        await websocket.accept()

        if not api_key:
            logger.error("GEMINI_API_KEY not set — Live voice unavailable")
            await websocket.send_json({"type": "error", "message": "GEMINI_API_KEY nije postavljen na serveru"})
            await websocket.close(code=4002)
            return
        logger.info("Live voice session started")

        try:
            from google import genai
            from google.genai import types
            from google.genai.types import (
                LiveConnectConfig, SpeechConfig, VoiceConfig,
                PrebuiltVoiceConfig, Content, Part
            )

            # Gemini Live API requires Gemini API endpoint (not Vertex AI).
            # Temporarily remove Vertex AI env vars for client creation only.
            # Safe in single-threaded asyncio — no await between pop and restore.
            _vertex_keys = ['GOOGLE_GENAI_USE_VERTEXAI', 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION']
            _vertex_backup = {k: os.environ.pop(k) for k in _vertex_keys if k in os.environ}
            try:
                client = genai.Client(api_key=api_key)
            finally:
                os.environ.update(_vertex_backup)

            config = LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=Content(parts=[Part(text=LIVE_SYSTEM_PROMPT)]),
                speech_config=SpeechConfig(
                    voice_config=VoiceConfig(
                        prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Aoede")
                    )
                )
            )

            async with client.aio.live.connect(
                model="gemini-3.1-flash-live-preview",
                config=config
            ) as session:

                async def send_audio():
                    chunks_sent = 0
                    try:
                        while True:
                            data = await websocket.receive_bytes()
                            await session.send_realtime_input(
                                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                            )
                            chunks_sent += 1
                            if chunks_sent % 50 == 0:
                                logger.debug(f"Live: sent {chunks_sent} audio chunks")
                    except Exception as e:
                        logger.info(f"Live send_audio ended ({chunks_sent} chunks sent): {type(e).__name__}: {e}")

                async def receive_audio():
                    # PCM16 @ 24kHz = 48000 bytes/sec
                    # Buffer min 100ms (4800 bytes) to avoid choppy 2-byte micro-chunks
                    MIN_SEND_BYTES = 4800
                    audio_buf = bytearray()
                    responses_received = 0
                    audio_bytes_total = 0

                    async def _flush(force: bool = False):
                        nonlocal audio_buf
                        if not audio_buf:
                            return
                        if force or len(audio_buf) >= MIN_SEND_BYTES:
                            await websocket.send_bytes(bytes(audio_buf))
                            audio_buf = bytearray()

                    try:
                        # Outer while loop: re-enter session.receive() after each
                        # turn_complete so multi-turn conversation works.
                        while True:
                            turn_done = False
                            async for response in session.receive():
                                responses_received += 1

                                raw: bytes | None = None
                                if response.data:
                                    raw = response.data

                                sc = getattr(response, 'server_content', None)
                                if sc:
                                    mt = getattr(sc, 'model_turn', None)
                                    if mt:
                                        for part in getattr(mt, 'parts', []):
                                            inline = getattr(part, 'inline_data', None)
                                            if inline and getattr(inline, 'data', None):
                                                raw = inline.data
                                            txt = getattr(part, 'text', None)
                                            if txt:
                                                await websocket.send_json({"type": "transcript", "text": txt})
                                    ot = getattr(sc, 'output_transcription', None)
                                    if ot and getattr(ot, 'text', None):
                                        await websocket.send_json({"type": "transcript", "text": ot.text})
                                    if getattr(sc, 'turn_complete', False):
                                        if raw:
                                            audio_buf.extend(raw)
                                            audio_bytes_total += len(raw)
                                            raw = None
                                        await _flush(force=True)
                                        turn_done = True
                                        continue

                                txt = getattr(response, 'text', None)
                                if txt:
                                    await websocket.send_json({"type": "transcript", "text": txt})

                                if raw:
                                    audio_buf.extend(raw)
                                    audio_bytes_total += len(raw)
                                    await _flush()

                            # session.receive() generator exhausted — either turn_complete
                            # fired (keep going) or session truly closed (break).
                            if not turn_done:
                                break  # session closed by Gemini, stop looping
                            # else: turn finished normally, loop back to receive next turn

                    except Exception as e:
                        logger.error(f"Live receive error ({responses_received} resp, {audio_bytes_total}B): {type(e).__name__}: {e}")
                    finally:
                        await _flush(force=True)
                        logger.info(f"Live receive_audio done: {responses_received} responses, {audio_bytes_total} audio bytes")

                await asyncio.gather(send_audio(), receive_audio())

        except Exception as e:
            logger.error(f"Live voice session error: {e}")
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
            logger.info("Live voice session ended")

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

    # --- Cost & Quota monitoring ---
    @app.get("/api/costs")
    async def get_costs():
        uptime_h = (_time.time() - _cost_tracker["start_time"]) / 3600

        # LLM breakdown po modelu
        llm_breakdown = []
        for key in _cost_tracker["llm_calls"]:
            llm_breakdown.append({
                "model": key,
                "calls": _cost_tracker["llm_calls"][key],
                "input_tokens": _cost_tracker["llm_input_tokens"][key],
                "output_tokens": _cost_tracker["llm_output_tokens"][key],
                "cost_usd": round(_cost_tracker["llm_cost_usd"][key], 4),
            })
        llm_breakdown.sort(key=lambda x: x["cost_usd"], reverse=True)

        total_llm = sum(_cost_tracker["llm_cost_usd"].values())
        total_cost = total_llm + _cost_tracker["veo_cost_usd"] + _cost_tracker["imagen_cost_usd"]

        # 429 info
        quota_errors = dict(_cost_tracker["quota_errors"])
        last_errors = {}
        for svc, ts in _cost_tracker["quota_errors_last"].items():
            mins_ago = (_time.time() - ts) / 60
            last_errors[svc] = f"{mins_ago:.0f}m ago" if mins_ago < 60 else f"{mins_ago/60:.1f}h ago"

        return {
            "uptime_hours": round(uptime_h, 2),
            "total_cost_usd": round(total_cost, 4),
            "total_cost_eur": round(total_cost * 0.92, 4),
            "llm": {
                "total_usd": round(total_llm, 4),
                "breakdown": llm_breakdown,
            },
            "tts": {
                "calls": _cost_tracker["tts_calls"],
                "chars": _cost_tracker["tts_chars"],
                "cost_usd": round(_cost_tracker["tts_cost_usd"], 5),
                "note": "preview - trenutno besplatno",
            },
            "veo": {
                "calls": _cost_tracker["veo_calls"],
                "cost_usd": round(_cost_tracker["veo_cost_usd"], 2),
                "cost_per_video": 0.40,
            },
            "imagen": {
                "calls": _cost_tracker["imagen_calls"],
                "cost_usd": round(_cost_tracker["imagen_cost_usd"], 3),
                "cost_per_image": 0.04,
            },
            "quota_errors": quota_errors,
            "quota_errors_last": last_errors,
            "total_quota_errors": sum(quota_errors.values()),
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
    from config.deployment_config import ENABLE_ERP
    if ENABLE_ERP:
        from web.erp_routes import router as erp_router
        app.include_router(erp_router)

        # --- ERP UI (serves HTML, not under /api/erp prefix) ---
        @app.get("/erp")
        async def erp_dashboard():
            return FileResponse(os.path.join(static_dir, "erp.html"))

    return app

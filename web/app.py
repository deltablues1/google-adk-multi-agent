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
    PaymentRequest, VendorInvoiceCreate, StockAdjustRequest,
    CustomerCreate, ProductCreate,
)
from config.agent_registry import get_agent_config, get_worker_agent_names
from services.erp.errors import BusinessError
from services.erp.repositories.base import InvoiceReference

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
    # ERP Routes
    # =======================================================================

    _MAX_LIMIT = 500  # Hard cap for all list endpoints

    def _clamp_limit(limit: int, default: int = 50) -> int:
        return max(1, min(limit, _MAX_LIMIT))

    # Helper: build a system-level context for dev/demo (no real auth yet)
    def _get_dev_ctx(company_id: str = "default-company"):
        import uuid as _uuid
        from services.erp.request_context import ERPRequestContext
        return ERPRequestContext(
            user_id="web-user",
            company_id=os.environ.get("ERP_COMPANY_ID", company_id),
            role="owner",
            grants=["*"],
            denies=[],
            request_id=str(_uuid.uuid4()),
        )

    # --- ERP UI ---
    @app.get("/erp")
    async def erp_dashboard():
        return FileResponse(os.path.join(static_dir, "erp.html"))

    # --- ERP /me ---
    @app.get("/api/erp/me")
    async def erp_me():
        ctx = _get_dev_ctx()
        return {"user_id": ctx.user_id, "company_id": ctx.company_id, "role": ctx.role}

    # ── Customers ───────────────────────────────────────────────────────────
    @app.get("/api/erp/customers")
    async def erp_list_customers(
        search: str = "", party_type: str = "", limit: int = 50, offset: int = 0
    ):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        filters = {}
        if search:
            filters["search"] = search
        if party_type:
            filters["party_type"] = party_type
        return await get_customer_service().list_customers(ctx, filters, _clamp_limit(limit), offset)

    @app.get("/api/erp/customers/{customer_id}")
    async def erp_get_customer(customer_id: str):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        return await get_customer_service().get_customer(customer_id, ctx)

    @app.post("/api/erp/customers")
    async def erp_create_customer(req: CustomerCreate):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        return await get_customer_service().create_customer(req.model_dump(), ctx)

    @app.put("/api/erp/customers/{customer_id}")
    async def erp_update_customer(customer_id: str, data: dict):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        return await get_customer_service().update_customer(customer_id, data, ctx)

    @app.delete("/api/erp/customers/{customer_id}")
    async def erp_delete_customer(customer_id: str):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        await get_customer_service().delete_customer(customer_id, ctx)
        return {"deleted": True, "customer_id": customer_id}

    @app.get("/api/erp/customers/{customer_id}/balance")
    async def erp_customer_balance(customer_id: str):
        from services.erp.customer_service import get_customer_service
        ctx = _get_dev_ctx()
        return await get_customer_service().get_customer_balance(customer_id, ctx)

    # ── Products ────────────────────────────────────────────────────────────
    @app.get("/api/erp/products")
    async def erp_list_products(
        search: str = "", low_stock_only: bool = False, limit: int = 100, offset: int = 0
    ):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        filters = {}
        if search:
            filters["search"] = search
        if low_stock_only:
            filters["low_stock_only"] = True
        return await get_product_service().list_products(ctx, filters, _clamp_limit(limit), offset)

    @app.get("/api/erp/products/{product_id}")
    async def erp_get_product(product_id: str):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        return await get_product_service().get_product(product_id, ctx)

    @app.post("/api/erp/products")
    async def erp_create_product(req: ProductCreate):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        return await get_product_service().create_product(req.model_dump(), ctx)

    @app.put("/api/erp/products/{product_id}")
    async def erp_update_product(product_id: str, data: dict):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        return await get_product_service().update_product(product_id, data, ctx)

    @app.post("/api/erp/products/{product_id}/adjust")
    async def erp_adjust_stock(product_id: str, req: StockAdjustRequest):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        return await get_product_service().adjust_stock(
            product_id, req.new_quantity, req.reason, ctx
        )

    @app.get("/api/erp/products/{product_id}/movements")
    async def erp_get_stock_movements(product_id: str, limit: int = 100):
        from services.erp.product_service import get_product_service
        ctx = _get_dev_ctx()
        return await get_product_service().get_stock_movements(product_id, ctx, _clamp_limit(limit))

    # ── Outgoing Invoices ────────────────────────────────────────────────────
    @app.get("/api/erp/invoices")
    async def erp_list_invoices(
        invoice_type: str = "", customer_id: str = "", payment_status: str = "",
        date_from: str = "", date_to: str = "", limit: int = 50, offset: int = 0
    ):
        from services.erp.invoice_service import get_invoice_service
        ctx = _get_dev_ctx()
        filters = {}
        if invoice_type:
            filters["invoice_type"] = invoice_type
        if customer_id:
            filters["customer_id"] = customer_id
        if payment_status:
            filters["payment_status"] = payment_status
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to
        return await get_invoice_service().list_invoices(ctx, filters=filters, limit=_clamp_limit(limit), offset=offset)

    @app.get("/api/erp/invoices/{invoice_type}/{invoice_id}")
    async def erp_get_invoice(invoice_type: str, invoice_id: str, display_id: str = ""):
        from services.erp.invoice_service import get_invoice_service
        ctx = _get_dev_ctx()
        ref = InvoiceReference(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            display_id=display_id or invoice_id,
        )
        return await get_invoice_service().get_invoice(ref, ctx)

    @app.post("/api/erp/invoices/{invoice_type}/{invoice_id}/payment")
    async def erp_record_payment(invoice_type: str, invoice_id: str, req: PaymentRequest):
        from services.erp.invoice_service import get_invoice_service
        ctx = _get_dev_ctx()
        invoice_svc = get_invoice_service()
        # Fetch the invoice to get the real human-readable display_id (invoice_number)
        ref_tmp = InvoiceReference(invoice_id=invoice_id, invoice_type=invoice_type, display_id=invoice_id)
        invoice_doc = await invoice_svc.get_invoice(ref_tmp, ctx)
        real_display_id = (
            invoice_doc.get("invoice_number") or invoice_doc.get("display_id") or invoice_id
        )
        ref = InvoiceReference(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            display_id=real_display_id,
        )
        return await invoice_svc.record_payment(
            invoice_ref=ref,
            amount=req.amount,
            payment_date=req.payment_date.isoformat(),
            payment_method=req.payment_method,
            reference=req.reference,
            ctx=ctx,
            idempotency_key=req.idempotency_key,
            notes=req.notes,
        )

    @app.get("/api/erp/receivables")
    async def erp_receivables(as_of_date: str = ""):
        from services.erp.invoice_service import get_invoice_service
        ctx = _get_dev_ctx()
        return await get_invoice_service().get_open_receivables(ctx, as_of_date or None)

    # ── Vendor Invoices (URA) ────────────────────────────────────────────────
    @app.get("/api/erp/vendor-invoices")
    async def erp_list_vendor_invoices(
        document_status: str = "", payment_status: str = "",
        vendor_id: str = "", limit: int = 50, offset: int = 0
    ):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        filters = {}
        if document_status:
            filters["document_status"] = document_status
        if payment_status:
            filters["payment_status"] = payment_status
        if vendor_id:
            filters["vendor_id"] = vendor_id
        return await get_vendor_invoice_service().list_vendor_invoices(ctx, filters, _clamp_limit(limit), offset)

    @app.get("/api/erp/vendor-invoices/{vendor_invoice_id}")
    async def erp_get_vendor_invoice(vendor_invoice_id: str):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        return await get_vendor_invoice_service().get_vendor_invoice(vendor_invoice_id, ctx)

    @app.post("/api/erp/vendor-invoices")
    async def erp_create_vendor_invoice(req: VendorInvoiceCreate):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        data = req.model_dump()
        if data.get("issue_date"):
            data["issue_date"] = data["issue_date"].isoformat()
        if data.get("due_date"):
            data["due_date"] = data["due_date"].isoformat()
        data["total_gross"] = float(data["total_gross"])
        data["vat_amount"] = float(data["vat_amount"])
        return await get_vendor_invoice_service().create_vendor_invoice(data, ctx)

    @app.post("/api/erp/vendor-invoices/{vendor_invoice_id}/receive")
    async def erp_receive_vendor_invoice(vendor_invoice_id: str):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        return await get_vendor_invoice_service().mark_received(vendor_invoice_id, ctx)

    @app.post("/api/erp/vendor-invoices/{vendor_invoice_id}/approve")
    async def erp_approve_vendor_invoice(vendor_invoice_id: str):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        return await get_vendor_invoice_service().approve_vendor_invoice(vendor_invoice_id, ctx)

    @app.post("/api/erp/vendor-invoices/{vendor_invoice_id}/payment")
    async def erp_vendor_record_payment(vendor_invoice_id: str, req: PaymentRequest):
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        return await get_vendor_invoice_service().record_payment(
            vendor_invoice_id=vendor_invoice_id,
            amount=req.amount,
            payment_date=req.payment_date.isoformat(),
            payment_method=req.payment_method,
            reference=req.reference,
            ctx=ctx,
            idempotency_key=req.idempotency_key,
            notes=req.notes,
        )

    @app.get("/api/erp/payables")
    async def erp_payables():
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _get_dev_ctx()
        return await get_vendor_invoice_service().get_open_payables(ctx)

    # ── Payments ────────────────────────────────────────────────────────────
    @app.get("/api/erp/payments")
    async def erp_list_payments(
        type: str = "", party_id: str = "", limit: int = 50, offset: int = 0
    ):
        from services.erp.payment_service import get_payment_service
        ctx = _get_dev_ctx()
        filters = {}
        if type:
            filters["type"] = type
        if party_id:
            filters["party_id"] = party_id
        return await get_payment_service().list_payments(ctx, filters, _clamp_limit(limit), offset)

    @app.get("/api/erp/payments/{payment_id}")
    async def erp_get_payment(payment_id: str):
        from services.erp.payment_service import get_payment_service
        ctx = _get_dev_ctx()
        return await get_payment_service().get_payment(payment_id, ctx)

    @app.get("/api/erp/payments/{payment_id}/allocations")
    async def erp_payment_allocations(payment_id: str):
        from services.erp.payment_service import get_payment_service
        ctx = _get_dev_ctx()
        return await get_payment_service().get_allocations_for_payment(payment_id, ctx)

    @app.get("/api/erp/invoices/{invoice_type}/{invoice_id}/allocations")
    async def erp_invoice_allocations(invoice_type: str, invoice_id: str):
        from services.erp.payment_service import get_payment_service
        ctx = _get_dev_ctx()
        return await get_payment_service().get_allocations_for_invoice(invoice_id, ctx)

    # ── Reports ─────────────────────────────────────────────────────────────
    @app.get("/api/erp/reports/vat")
    async def erp_vat_report(year: int = 2026, month: int = 1):
        from services.erp.reporting_service import get_reporting_service
        ctx = _get_dev_ctx()
        return await get_reporting_service().get_vat_summary(ctx, year, month)

    @app.get("/api/erp/reports/cashflow")
    async def erp_cashflow(start: str = "", end: str = ""):
        from services.erp.payment_service import get_payment_service
        from datetime import date
        ctx = _get_dev_ctx()
        today = date.today()
        date_from = start or f"{today.year}-{today.month:02d}-01"
        date_to = end or today.isoformat()
        return await get_payment_service().get_cashflow_summary(ctx, date_from, date_to)

    @app.get("/api/erp/reports/receivables-aging")
    async def erp_receivables_aging(as_of_date: str = ""):
        from services.erp.reporting_service import get_reporting_service
        ctx = _get_dev_ctx()
        return await get_reporting_service().get_receivables_aging(ctx, as_of_date or None)

    @app.get("/api/erp/reports/payables-aging")
    async def erp_payables_aging():
        from services.erp.reporting_service import get_reporting_service
        ctx = _get_dev_ctx()
        return await get_reporting_service().get_payables_aging(ctx)

    @app.get("/api/erp/reports/financial-summary")
    async def erp_financial_summary(start: str = "", end: str = ""):
        from services.erp.reporting_service import get_reporting_service
        from datetime import date
        ctx = _get_dev_ctx()
        today = date.today()
        date_from = start or f"{today.year}-01-01"
        date_to = end or today.isoformat()
        return await get_reporting_service().get_financial_summary(ctx, date_from, date_to)

    @app.get("/api/erp/reports/top-customers")
    async def erp_top_customers(limit: int = 10, start: str = "", end: str = ""):
        from datetime import date
        from services.erp.invoice_service import get_invoice_service
        ctx = _get_dev_ctx()
        today = date.today()
        date_from = start or f"{today.year}-01-01"
        date_to = end or today.isoformat()
        docs = await get_invoice_service().list_invoices(
            ctx, filters={"date_from": date_from, "date_to": date_to}, limit=1000
        )
        # Aggregate by customer
        customer_totals: dict = {}
        for d in docs:
            cid = d.get("customer_id") or d.get("buyer_oib") or "unknown"
            cname = d.get("customer_name") or d.get("buyer_name") or cid
            total = float(d.get("grand_total") or d.get("total_gross") or 0)
            if cid not in customer_totals:
                customer_totals[cid] = {"customer_id": cid, "name": cname, "total_revenue": 0.0, "invoice_count": 0}
            customer_totals[cid]["total_revenue"] = round(customer_totals[cid]["total_revenue"] + total, 2)
            customer_totals[cid]["invoice_count"] += 1
        sorted_customers = sorted(customer_totals.values(), key=lambda x: x["total_revenue"], reverse=True)
        return sorted_customers[:limit]

    # ── Activity Feed ────────────────────────────────────────────────────────
    @app.get("/api/erp/activity")
    async def erp_activity_feed(limit: int = 50):
        """Chronological feed of ERP business actions from the audit log."""
        from services.erp.base_erp_service import get_firestore_db
        ctx = _get_dev_ctx()
        db = get_firestore_db()
        query = (
            db.collection("audit_log")
            .where("company_id", "==", ctx.company_id)
            .where("target_service", "==", "erp")
            .order_by("timestamp", direction="DESCENDING")
            .limit(_clamp_limit(limit))
        )
        events = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            events.append({
                "id": snap.id,
                "timestamp": doc.get("timestamp"),
                "action": doc.get("action_type"),
                "description": doc.get("action_description"),
                "entity_type": doc.get("entity_type"),
                "display_id": doc.get("display_id"),
                "user_id": doc.get("user_id"),
            })
        return events

    return app

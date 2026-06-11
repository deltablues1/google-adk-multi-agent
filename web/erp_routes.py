"""
ERP API Routes
==============
All /api/erp/* endpoints as an APIRouter.
Mounted by create_app() in web/app.py.
Tests can include this router directly without duplicating route definitions.
"""

import os
import logging
import uuid as _uuid
from decimal import Decimal
from datetime import datetime, timezone
from html import escape as esc
from typing import Tuple

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse

from services.erp.request_context import ERPRequestContext, build_context
from services.erp.repositories.base import InvoiceReference
from web.models import (
    PaymentRequest, VendorInvoiceCreate, StockAdjustRequest,
    CustomerCreate, ProductCreate,
    QuoteCreate, QuoteUpdate, QuoteConvertRequest, QuoteCreateInvoiceRequest,
    OutboundB2BCreate, OutboundB2BSendRequest, OutboundB2BRejectRequest,
    OutboundB2GCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp")

_MAX_LIMIT = 500

# ERP_DEV_MODE grants an owner-role fallback when identity headers are absent.
# That is a deliberate dev-only shortcut — it must never be active in a
# production-like environment. Fail fast at import rather than at the first
# request, so a misconfigured deploy can't come up at all.
_ENV = os.environ.get("ENVIRONMENT", "development").lower()
_DEV_MODE = os.environ.get("ERP_DEV_MODE", "").lower() in ("1", "true", "yes")
if _DEV_MODE and _ENV in ("production", "prod", "staging"):
    raise RuntimeError(
        f"ERP_DEV_MODE is enabled in ENVIRONMENT={_ENV!r}. "
        "Refusing to start — the dev identity fallback grants owner access "
        "without authentication. Unset ERP_DEV_MODE or change ENVIRONMENT."
    )


def _clamp_limit(limit: int, default: int = 50) -> int:
    return max(1, min(limit, _MAX_LIMIT))


# ---------------------------------------------------------------------------
# Identity extraction — the ONLY part that changes when moving to Firebase Auth
# ---------------------------------------------------------------------------

def _extract_identity(request: Request) -> Tuple[str, str]:
    """Extract (user_id, company_id) from the request.

    Dev bridge:  X-ERP-User-Id + X-ERP-Company-Id headers.
    Production:  Replace this function body with JWT verification
                 (e.g. firebase_admin.auth.verify_id_token) — the rest
                 of get_erp_ctx stays unchanged.

    Returns:
        (user_id, company_id) or raises HTTPException 401.
    """
    user_id = request.headers.get("X-ERP-User-Id", "").strip()
    company_id = request.headers.get("X-ERP-Company-Id", "").strip()
    if user_id and company_id:
        return user_id, company_id
    raise HTTPException(status_code=401, detail="Missing X-ERP-User-Id or X-ERP-Company-Id header")


# ---------------------------------------------------------------------------
# Context dependency — resolves identity → erp_users membership → context
# ---------------------------------------------------------------------------

async def get_erp_ctx(request: Request) -> ERPRequestContext:
    """Resolve ERPRequestContext from the incoming request.

    Flow:
      1. _extract_identity(request) → (user_id, company_id)
      2. Query erp_users for membership doc (user_id + company_id)
      3. build_context(user_doc) → ERPRequestContext

    Dev fallback (ERP_DEV_MODE=1):
      If no identity headers are present, returns owner context for
      ERP_COMPANY_ID. Logs a warning so it's never silent.

    In tests, override via ``app.dependency_overrides[get_erp_ctx]``.
    """
    # --- Dev fallback (explicit flag only) ---
    # Hardened: never engage the owner fallback in production, and require an
    # explicitly configured ERP_COMPANY_ID (no silent "default-company"). This
    # prevents an accidental ERP_DEV_MODE in prod from granting owner access.
    _env = os.environ.get("ENVIRONMENT", "").lower()
    _is_prod = _env in ("prod", "production")
    if _DEV_MODE and not _is_prod:
        try:
            user_id, company_id = _extract_identity(request)
        except HTTPException:
            dev_company = os.environ.get("ERP_COMPANY_ID", "").strip()
            if not dev_company:
                raise HTTPException(
                    status_code=401,
                    detail="ERP_DEV_MODE is on but ERP_COMPANY_ID is not set; "
                           "send X-ERP-User-Id/X-ERP-Company-Id headers.",
                )
            logger.warning(
                "ERP_DEV_MODE: no identity headers — using owner fallback for "
                "company '%s' (dev only)", dev_company,
            )
            return ERPRequestContext(
                user_id="dev-user",
                company_id=dev_company,
                role="owner",
                grants=["*"],
                denies=[],
                request_id=str(_uuid.uuid4()),
            )
    else:
        user_id, company_id = _extract_identity(request)

    # --- Membership lookup ---
    from services.erp.base_erp_service import get_firestore_db
    from google.cloud.firestore_v1.base_query import FieldFilter
    db = get_firestore_db()
    query = (
        db.collection("erp_users")
        .where(filter=FieldFilter("user_id", "==", user_id))
        .where(filter=FieldFilter("company_id", "==", company_id))
        .where(filter=FieldFilter("active", "==", True))
        .limit(1)
    )
    user_doc = None
    async for snap in query.stream():
        user_doc = snap.to_dict()
        break

    if not user_doc:
        raise HTTPException(
            status_code=403,
            detail=f"No active ERP membership for user '{user_id}' in company '{company_id}'",
        )

    ctx = build_context(user_doc)
    ctx.request_id = str(_uuid.uuid4())
    return ctx


# ── Dev: list available memberships (no auth required) ────────────────────────

@router.get("/dev/memberships")
async def erp_dev_memberships():
    """List all active erp_users docs for the dev identity picker.

    Available only with ERP_DEV_MODE=1 outside production — returns 404 otherwise,
    so user/email data is never exposed on a real deployment.
    """
    _env = os.environ.get("ENVIRONMENT", "").lower()
    if not _DEV_MODE or _env in ("prod", "production"):
        raise HTTPException(status_code=404, detail="Not found")
    from services.erp.base_erp_service import get_firestore_db
    from google.cloud.firestore_v1.base_query import FieldFilter
    db = get_firestore_db()
    query = (
        db.collection("erp_users")
        .where(filter=FieldFilter("active", "==", True))
        .limit(100)
    )
    results = []
    async for snap in query.stream():
        doc = snap.to_dict() or {}
        results.append({
            "user_id": doc.get("user_id", ""),
            "company_id": doc.get("company_id", ""),
            "role": doc.get("role", "viewer"),
            "display_name": doc.get("display_name", ""),
            "email": doc.get("email", ""),
        })
    return results


# ── ERP /me ──────────────────────────────────────────────────────────────────

@router.get("/me")
async def erp_me(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    return {"user_id": ctx.user_id, "company_id": ctx.company_id, "role": ctx.role}


# ── Company Settings (Sprint C0) ──────────────────────────────────────────────

@router.get("/company/settings")
async def erp_get_company_settings(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Return this company's ERP settings (OIB, name, IBAN, fiscalization codes)."""
    from services.erp.company_service import get_company_service
    return await get_company_service().get(ctx)


@router.put("/company/settings")
async def erp_upsert_company_settings(req: Request, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Create or fully replace company settings."""
    from services.erp.company_service import get_company_service
    data = await req.json()
    return await get_company_service().upsert(data, ctx)


@router.patch("/company/settings")
async def erp_patch_company_settings(req: Request, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Partial update — only provided keys are written."""
    from services.erp.company_service import get_company_service
    data = await req.json()
    return await get_company_service().patch(data, ctx)


# ── Customers ────────────────────────────────────────────────────────────────

@router.get("/customers")
async def erp_list_customers(
    search: str = "", party_type: str = "", limit: int = 50, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.customer_service import get_customer_service
    filters = {}
    if search:
        filters["search"] = search
    if party_type:
        filters["party_type"] = party_type
    return await get_customer_service().list_customers(ctx, filters, _clamp_limit(limit), offset)


@router.get("/customers/{customer_id}")
async def erp_get_customer(customer_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.customer_service import get_customer_service
    return await get_customer_service().get_customer(customer_id, ctx)


@router.post("/customers")
async def erp_create_customer(req: CustomerCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.customer_service import get_customer_service
    return await get_customer_service().create_customer(req.model_dump(), ctx)


@router.put("/customers/{customer_id}")
async def erp_update_customer(customer_id: str, data: dict, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.customer_service import get_customer_service
    return await get_customer_service().update_customer(customer_id, data, ctx)


@router.delete("/customers/{customer_id}")
async def erp_delete_customer(customer_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.customer_service import get_customer_service
    await get_customer_service().delete_customer(customer_id, ctx)
    return {"deleted": True, "customer_id": customer_id}


@router.get("/customers/{customer_id}/balance")
async def erp_customer_balance(customer_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.customer_service import get_customer_service
    return await get_customer_service().get_customer_balance(customer_id, ctx)


# ── Products ─────────────────────────────────────────────────────────────────

@router.get("/products")
async def erp_list_products(
    search: str = "", low_stock_only: bool = False, limit: int = 100, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.product_service import get_product_service
    filters = {}
    if search:
        filters["search"] = search
    if low_stock_only:
        filters["low_stock_only"] = True
    return await get_product_service().list_products(ctx, filters, _clamp_limit(limit), offset)


@router.get("/products/{product_id}")
async def erp_get_product(product_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.product_service import get_product_service
    return await get_product_service().get_product(product_id, ctx)


@router.post("/products")
async def erp_create_product(req: ProductCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.product_service import get_product_service
    return await get_product_service().create_product(req.model_dump(), ctx)


@router.put("/products/{product_id}")
async def erp_update_product(product_id: str, data: dict, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.product_service import get_product_service
    return await get_product_service().update_product(product_id, data, ctx)


@router.post("/products/{product_id}/adjust")
async def erp_adjust_stock(product_id: str, req: StockAdjustRequest, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.product_service import get_product_service
    return await get_product_service().adjust_stock(
        product_id, req.new_quantity, req.reason, ctx
    )


@router.get("/products/{product_id}/movements")
async def erp_get_stock_movements(product_id: str, limit: int = 100, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.product_service import get_product_service
    return await get_product_service().get_stock_movements(product_id, ctx, _clamp_limit(limit))


# ── Outgoing Invoices ────────────────────────────────────────────────────────

@router.get("/invoices")
async def erp_list_invoices(
    invoice_type: str = "", customer_id: str = "", payment_status: str = "",
    date_from: str = "", date_to: str = "", limit: int = 500, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.invoice_service import get_invoice_service
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
    docs = await get_invoice_service().list_invoices(ctx, filters=filters, limit=_clamp_limit(limit), offset=offset)
    _STRIP = {"ocr_data", "items", "scan_file_id"}
    return [{k: v for k, v in d.items() if k not in _STRIP} for d in docs]


@router.get("/invoices/{invoice_type}/{invoice_id}")
async def erp_get_invoice(invoice_type: str, invoice_id: str, display_id: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.invoice_service import get_invoice_service
    ref = InvoiceReference(
        invoice_id=invoice_id,
        invoice_type=invoice_type,
        display_id=display_id or invoice_id,
    )
    return await get_invoice_service().get_invoice(ref, ctx)


@router.post("/invoices/{invoice_type}/{invoice_id}/payment")
async def erp_record_payment(invoice_type: str, invoice_id: str, req: PaymentRequest, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.invoice_service import get_invoice_service
    invoice_svc = get_invoice_service()
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


@router.get("/receivables")
async def erp_receivables(as_of_date: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.invoice_service import get_invoice_service
    return await get_invoice_service().get_open_receivables(ctx, as_of_date or None)


# ── B2C Fiscalization (Sprint C1.1) ──────────────────────────────────────────

@router.post("/invoices/b2c/{invoice_id}/fiscalize")
async def erp_fiscalize_b2c(
    invoice_id: str,
    payment_method: str = "T",
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Trigger fiscalization for a B2C invoice (fiscalization_status == pending).

    The API call is the user's explicit confirmation — HITL is skipped.
    Idempotent: returns cached JIR/ZKI if already fiscalized.

    Query param:
        payment_method: G=gotovina, K=kartica, T=transakcijski (default T)
    """
    from services.erp.fiscalization_bridge_service import fiscalize_b2c_invoice
    return await fiscalize_b2c_invoice(invoice_id, ctx, payment_method=payment_method)


@router.get("/invoices/b2c/{invoice_id}/fiscalization-status")
async def erp_b2c_fiscalization_status(
    invoice_id: str,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Return fiscalization tracking fields for a B2C invoice (non-blocking read).

    Returns {} if the invoice does not exist.
    """
    from services.erp.base_erp_service import check_permission
    check_permission(ctx, "invoice:read")
    from services.erp.fiscalization_bridge_service import get_fiscalization_status
    return await get_fiscalization_status(invoice_id)


# ── Vendor Invoices (URA) ────────────────────────────────────────────────────

@router.get("/vendor-invoices")
async def erp_list_vendor_invoices(
    document_status: str = "", payment_status: str = "",
    vendor_id: str = "", limit: int = 500, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    filters = {}
    if document_status:
        filters["document_status"] = document_status
    if payment_status:
        filters["payment_status"] = payment_status
    if vendor_id:
        filters["vendor_id"] = vendor_id
    docs = await get_vendor_invoice_service().list_vendor_invoices(ctx, filters, _clamp_limit(limit), offset)
    # Strip heavy fields (ocr_data, items) from list response for speed
    _STRIP = {"ocr_data", "items", "scan_file_id"}
    return [{k: v for k, v in d.items() if k not in _STRIP} for d in docs]


@router.get("/vendor-invoices/overdue-fiscalizations")
async def erp_vendor_overdue_fisc_a(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Get vendor invoices that exceeded 5-business-day fiscalization deadline."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().get_overdue_fiscalizations(ctx)


@router.get("/vendor-invoices/pending-archive")
async def erp_vendor_pending_archive(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """List vendor invoices with Drive files that are not yet archived (not_archived or failed)."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().list_pending_archive(ctx)


@router.post("/vendor-invoices/retry-archive")
async def erp_vendor_retry_archive(
    max_retries: int = 3, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Re-attempt Drive archiving for all pending/failed invoices. Returns summary."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().retry_pending_archives(ctx, max_retries=max_retries)


@router.get("/vendor-invoices/rejected")
async def erp_vendor_rejected(limit: int = 100, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """List rejected inbound vendor invoices."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().list_rejected_invoices(ctx, limit=_clamp_limit(limit))


@router.get("/vendor-invoices/inbound-compliance-report")
async def erp_vendor_inbound_report_a(
    year: int = None, month: int = None,
    format: str = "json",
    save_to_drive: bool = False,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """Monthly inbound compliance summary. format=json (default) or csv. save_to_drive=true uploads to Reports_Output/ERP/."""
    from fastapi.responses import PlainTextResponse
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    svc = get_vendor_invoice_service()
    report = await svc.get_inbound_compliance_report(
        year, month, ctx, save_to_drive=save_to_drive
    )
    if format == "csv":
        csv_text, filename = svc.compliance_report_to_csv(report)
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return report


@router.get("/vendor-invoices/{vendor_invoice_id}")
async def erp_get_vendor_invoice(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().get_vendor_invoice(vendor_invoice_id, ctx)


@router.post("/vendor-invoices")
async def erp_create_vendor_invoice(req: VendorInvoiceCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    data = req.model_dump()
    for date_field in ("issue_date", "due_date", "received_date"):
        if data.get(date_field):
            data[date_field] = data[date_field].isoformat()
    data["total_gross"] = float(data["total_gross"])
    data["vat_amount"] = float(data["vat_amount"])
    if data.get("subtotal_net") is not None:
        data["subtotal_net"] = float(data["subtotal_net"])
    return await get_vendor_invoice_service().create_vendor_invoice(data, ctx)


@router.patch("/vendor-invoices/{vendor_invoice_id}")
async def erp_patch_vendor_invoice(vendor_invoice_id: str, req: Request, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    body = await req.json()
    # Only allow updating safe fields
    allowed = {"vendor_name", "vendor_oib", "vendor_invoice_no", "issue_date", "due_date",
               "total_gross", "vat_amount", "subtotal_net", "category", "notes"}
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    svc = get_vendor_invoice_service()
    return await svc.update_vendor_invoice(vendor_invoice_id, ctx, update_data)


@router.post("/vendor-invoices/{vendor_invoice_id}/receive")
async def erp_receive_vendor_invoice(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().mark_received(vendor_invoice_id, ctx)


@router.post("/vendor-invoices/{vendor_invoice_id}/approve")
async def erp_approve_vendor_invoice(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().approve_vendor_invoice(vendor_invoice_id, ctx)


@router.post("/vendor-invoices/{vendor_invoice_id}/fisc-report")
async def erp_vendor_fisc_report(
    vendor_invoice_id: str,
    req: dict = None,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """Mark vendor invoice as fiscally reported to Porezna Uprava.

    Optional body: {"fisc_confirmation_ref": "CIS-2026-XXXXXXX"}
    """
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    fisc_ref = (req or {}).get("fisc_confirmation_ref", "")
    return await get_vendor_invoice_service().mark_fisc_reported(vendor_invoice_id, ctx, fisc_ref)


@router.post("/vendor-invoices/{vendor_invoice_id}/accept")
async def erp_vendor_accept(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Accept a fiscally reported vendor invoice."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().accept_vendor_invoice(vendor_invoice_id, ctx)


@router.post("/vendor-invoices/{vendor_invoice_id}/reject")
async def erp_vendor_reject(vendor_invoice_id: str, req: dict, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Reject a vendor invoice with mandatory reason."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().reject_vendor_invoice(
        vendor_invoice_id, req.get("rejection_reason", ""), ctx
    )


@router.post("/vendor-invoices/{vendor_invoice_id}/archive-original")
async def erp_vendor_archive_original(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Move original Drive document into Invoices_Archive/IN/YYYY/MM/ and update archive metadata."""
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().archive_original_document(vendor_invoice_id, ctx)


@router.post("/vendor-invoices/{vendor_invoice_id}/payment")
async def erp_vendor_record_payment(vendor_invoice_id: str, req: PaymentRequest, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
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


@router.get("/payables")
async def erp_payables(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().get_open_payables(ctx)


# ── Outbound B2B eRačun ──────────────────────────────────────────────────────
#
# IMPORTANT: Static sub-paths MUST be declared before /{invoice_id}.
#
# Lifecycle:
#   POST   /outbound-b2b                       — create (draft)
#   GET    /outbound-b2b                       — list
#   GET    /outbound-b2b/pending-ack           — awaiting buyer ack
#   GET    /outbound-b2b/send-failures         — issued with failed send attempts
#   POST   /outbound-b2b/retry-send-failures   — scheduler retry
#   GET    /outbound-b2b/capabilities          — adapter capability map (2D)
#   GET    /outbound-b2b/pending-archive       — issued/sent/etc not yet archived (2C)
#   POST   /outbound-b2b/retry-archive         — scheduler archive retry (2C)
#   POST   /outbound-b2b/peppol/webhook        — AP delivery webhook (C2.2)
#   POST   /outbound-b2b/poll-peppol-status    — scheduler AP status poll (C2.2)
#   GET    /outbound-b2b/pending-peppol-sync   — stale AP status dashboard (C2.2)
#   GET    /outbound-b2b/{id}                  — get single
#   POST   /outbound-b2b/{id}/approve
#   POST   /outbound-b2b/{id}/issue            — UBL generated
#   POST   /outbound-b2b/{id}/send             — real transport dispatch
#   POST   /outbound-b2b/{id}/resend           — retry failed/re-send
#   POST   /outbound-b2b/{id}/sync-status      — external status update
#   POST   /outbound-b2b/{id}/delivered
#   POST   /outbound-b2b/{id}/accept
#   POST   /outbound-b2b/{id}/reject
#   POST   /outbound-b2b/{id}/cancel
#   POST   /outbound-b2b/{id}/archive


# ── Static collection-level routes (BEFORE /{invoice_id}) ────────────────────

@router.get("/outbound-b2b/pending-ack")
async def erp_outbound_b2b_pending_ack(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """List B2B invoices in eracun_sent or delivered status awaiting buyer acknowledgement."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().list_pending_ack(ctx)


@router.get("/outbound-b2b/send-failures")
async def erp_outbound_b2b_send_failures(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """List issued B2B invoices where dispatch has failed at least once."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().list_send_failures(ctx)


@router.post("/outbound-b2b/retry-send-failures")
async def erp_outbound_b2b_retry_send(
    max_attempts: int = 5, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Re-attempt dispatch for all send-failed invoices. Returns {attempted, succeeded, failed, skipped}."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().retry_send_failures(ctx, max_attempts=max_attempts)


# ── 2D: Capability discovery route (BEFORE /{invoice_id}) ────────────────────

@router.get("/outbound-b2b/capabilities")
async def erp_outbound_b2b_capabilities():
    """Return the delivery adapter capability map (no auth required — static config)."""
    from services.erp.outbound_capabilities import ADAPTER_CAPABILITIES
    return ADAPTER_CAPABILITIES


# ── 2C: Archive collection-level routes (BEFORE /{invoice_id}) ────────────────

@router.get("/outbound-b2b/pending-archive")
async def erp_outbound_b2b_pending_archive(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    List issued/eracun_sent/delivered/accepted/rejected invoices with ubl_xml
    that have not yet been archived to Drive.
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().list_pending_archive(ctx)


@router.post("/outbound-b2b/retry-archive")
async def erp_outbound_b2b_retry_archive(
    max_attempts: int = 3, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Retry Drive archiving for all pending-archive invoices. Returns {attempted, succeeded, failed, skipped}."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().retry_archive(ctx, max_attempts=max_attempts)


# ── Inbound Peppol e-račun (Sprint Inbound B) ─────────────────────────────────
# System-to-system — no ERP user identity required.
# Same pattern as outbound Peppol webhook but for INCOMING documents from AP.
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/inbound-eracun/peppol/webhook")
async def erp_peppol_inbound_webhook(request: Request):
    """
    Receive an inbound e-račun document from a Peppol AP.

    This is a system-to-system endpoint — no ERP user headers required.
    The AP pushes UBL/XML documents to this URL when it receives an invoice
    addressed to one of our registered Peppol participant IDs.

    Authentication:
      HMAC-SHA256 via PEPPOL_AP_INBOUND_WEBHOOK_SECRET (falls back to
      PEPPOL_AP_WEBHOOK_SECRET, then no-auth in dev mode).

    Payload (JSON):
      {
        "submissionId":   "<AP submission ID>",           required
        "receiverId":     "0190:<OIB>",                   required for routing
        "senderId":       "0190:<supplier OIB>",          optional
        "documentId":     "<invoice ID from sender>",     optional
        "documentBase64": "<base64 UBL XML>",             one of these
        "documentUrl":    "<URL to fetch the UBL XML>",   is required
        "filename":       "invoice.xml",                  optional
        "receivedAt":     "<ISO timestamp>",              optional
      }

    Returns:
      200 {"ok": True, "status": "imported"|"duplicate"|"failed",
           "vendor_invoice_id": "...", "display_id": "..."}
      400 on missing/invalid payload
      403 on signature failure
      404 if receiver participant_id not registered
      500 on unexpected error
    """
    import json as _json
    from services.erp.inbound_peppol_transport_service import (
        verify_inbound_webhook,
        parse_inbound_payload,
        resolve_company_from_participant_id,
        fetch_xml_bytes,
        _make_system_ctx,
        InboundPeppolTransportService,
    )

    body_bytes = await request.body()

    if not verify_inbound_webhook(dict(request.headers), body_bytes):
        raise HTTPException(status_code=403, detail="Invalid or missing Peppol inbound webhook signature")

    try:
        body = _json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in webhook body")

    parsed = parse_inbound_payload(body)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Could not parse inbound Peppol payload — missing submissionId",
        )

    # Resolve receiver company
    receiver_id = parsed.get("receiver_participant_id", "")
    company_id  = await resolve_company_from_participant_id(receiver_id)
    if not company_id:
        raise HTTPException(
            status_code=404,
            detail=f"No registered company for Peppol participant {receiver_id!r}",
        )

    # Fetch XML bytes
    xml_bytes = await fetch_xml_bytes(parsed)
    if not xml_bytes:
        raise HTTPException(
            status_code=400,
            detail="Inbound Peppol payload contains no XML document (no documentBase64 or documentUrl)",
        )

    ctx    = _make_system_ctx(company_id)
    result = await InboundPeppolTransportService().process(
        parsed, xml_bytes, ctx, archive=True
    )

    return {
        "ok":                True,
        "status":            result.get("status"),
        "vendor_invoice_id": result.get("vendor_invoice_id", ""),
        "display_id":        result.get("display_id", ""),
        "ap_submission_id":  result.get("ap_submission_id", ""),
        "archive_status":    result.get("archive_status", "skipped"),
    }


# ── Peppol feedback loop (C2.2 / C2.2.1) — must be BEFORE /{invoice_id} routes
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/outbound-b2b/peppol/webhook")
async def erp_peppol_webhook(request: Request):
    """
    Receive a delivery/acknowledgement callback from the Peppol AP.

    This endpoint requires NO user identity — it is a system-to-system endpoint
    called by the AP, not by an ERP user.  Authentication is handled via:
      1. HMAC-SHA256 signature (``X-Peppol-Signature`` header + ``PEPPOL_AP_WEBHOOK_SECRET``)
      2. When secret is not set: any call is accepted (dev/sandbox only — log warning)

    The AP posts JSON with at least:
      { "submissionId": "...", "status": "delivered|accepted|rejected|failed|pending" }

    The endpoint finds the invoice by submission_id across all companies (no
    company_id needed from the caller).

    Returns: {"ok": True, "invoice_id": "...", "new_status": "..."} on success.
    """
    import json as _json
    from services.erp.peppol_status_service import verify_webhook_request, parse_webhook_payload
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    from services.erp.errors import NotFoundError
    from services.erp.outbound_b2g_service import get_outbound_b2g_service

    body_bytes = await request.body()
    if not verify_webhook_request(dict(request.headers), body_bytes):
        raise HTTPException(status_code=403, detail="Invalid or missing Peppol webhook signature")

    try:
        body = _json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in webhook body")

    parsed = parse_webhook_payload(body)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Could not parse webhook payload — missing submissionId or status",
        )

    # Cross-collection lookup: B2B invoices first, then B2G.
    # The AP sends a submission_id without knowing the invoice type,
    # so we try both collections and apply to whichever finds it.
    kwargs = dict(
        status=parsed["status"],
        raw_status=parsed.get("raw_status", ""),
        buyer_message=parsed.get("buyer_message", ""),
        receiver_participant_id=parsed.get("receiver_participant_id", ""),
        sender_participant_id=parsed.get("sender_participant_id", ""),
    )
    updated = None
    for svc in (get_outbound_b2b_service(), get_outbound_b2g_service()):
        try:
            updated = await svc.apply_peppol_status_from_webhook(
                parsed["submission_id"], **kwargs
            )
            break
        except NotFoundError:
            continue

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"No outbound invoice found for submission_id={parsed['submission_id']!r}",
        )
    return {"ok": True, "invoice_id": updated.get("invoice_id"), "new_status": updated.get("document_status")}


@router.post("/outbound-b2b/poll-peppol-status")
async def erp_poll_peppol_status(
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Trigger an immediate AP status poll for all in-flight Peppol invoices.

    Intended for:
      - Scheduler (periodic job every N minutes)
      - Operator "sync now" button in the dashboard

    Returns: {"polled": N, "updated": N, "errors": N, "skipped": N, "_stub": bool}
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().poll_pending_peppol_status(ctx)


@router.get("/outbound-b2b/pending-peppol-sync")
async def erp_pending_peppol_sync(
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Return all outbound B2B Peppol invoices in eracun_sent or delivered state
    whose last AP status check is older than 30 minutes (or never checked).
    PEPPOL-STUB-* submission IDs are excluded.
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().list_pending_peppol_sync(ctx)


# ── End Peppol feedback routes ─────────────────────────────────────────────────

@router.post("/outbound-b2b")
async def erp_create_outbound_b2b(req: OutboundB2BCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Create a new outgoing B2B invoice (eRačun) in draft status."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    data = req.model_dump()
    # Serialize dates to ISO strings for Firestore
    for field in ("issue_date", "due_date"):
        if data.get(field):
            data[field] = data[field].isoformat()
    # Serialize items
    data["items"] = [
        {**item, "unit_price": float(item["unit_price"]), "quantity": float(item["quantity"])}
        for item in data.get("items", [])
    ]
    return await get_outbound_b2b_service().create(data, ctx)


@router.get("/outbound-b2b")
async def erp_list_outbound_b2b(
    document_status: str = "", customer_id: str = "",
    date_from: str = "", date_to: str = "",
    limit: int = 50, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """List outgoing B2B invoices with optional filters."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    filters = {}
    if document_status:
        filters["document_status"] = document_status
    if customer_id:
        filters["customer_id"] = customer_id
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    return await get_outbound_b2b_service().list(ctx, filters, _clamp_limit(limit), offset)


@router.get("/outbound-b2b/{invoice_id}")
async def erp_get_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Fetch a single outgoing B2B invoice by ID."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().get(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/approve")
async def erp_approve_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Approve a draft B2B invoice (draft → approved)."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().approve(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/issue")
async def erp_issue_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Issue a B2B invoice (approved → issued).
    Generates UBL 2.1 XML and stores it on the document.
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().issue(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/send")
async def erp_send_outbound_b2b(
    invoice_id: str, req: OutboundB2BSendRequest,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Send an issued B2B invoice to the buyer (issued → eracun_sent).
    Delivery methods: email | peppol | manual
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().send(
        invoice_id, ctx,
        delivery_method=req.delivery_method,
        delivery_target=req.delivery_target,
        delivery_ref=req.delivery_ref,
    )


@router.post("/outbound-b2b/{invoice_id}/delivered")
async def erp_delivered_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Confirm delivery to buyer (eracun_sent → delivered)."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().mark_delivered(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/accept")
async def erp_accept_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Buyer confirmed receipt (delivered → accepted)."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().accept(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/reject")
async def erp_reject_outbound_b2b(
    invoice_id: str, req: OutboundB2BRejectRequest,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """Buyer rejected the invoice. Mandatory rejection_reason required."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().reject(invoice_id, ctx, req.rejection_reason)


@router.post("/outbound-b2b/{invoice_id}/cancel")
async def erp_cancel_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Cancel a B2B invoice (allowed from draft/approved/issued/eracun_sent)."""
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().cancel(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/archive")
async def erp_archive_outbound_b2b(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Upload UBL XML to Drive and move it into Invoices_Archive/OUT/b2b/YYYY/MM/.
    Requires UBL to have been generated (document_status >= issued).
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().archive_outbound(invoice_id, ctx)


@router.post("/outbound-b2b/{invoice_id}/resend")
async def erp_resend_outbound_b2b(
    invoice_id: str, req: OutboundB2BSendRequest = None,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Retry dispatch for an issued invoice (send failed) or re-send eracun_sent.
    If delivery_method/target are omitted in body, uses values already on the doc.
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    method = (req.delivery_method if req else None) or None
    target = (req.delivery_target if req else None) or None
    return await get_outbound_b2b_service().resend(invoice_id, ctx, method, target)


@router.post("/outbound-b2b/{invoice_id}/sync-status")
async def erp_sync_status_outbound_b2b(
    invoice_id: str, req: dict, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """
    Record an external delivery/acknowledgement status update from an AP or operator.

    Body: {"external_status": "delivered|accepted|pending|failed", "external_ref": "..."}
    Auto-transitions: delivered→mark_delivered(), accepted→accept() if SM allows.
    """
    from services.erp.outbound_b2b_service import get_outbound_b2b_service
    return await get_outbound_b2b_service().sync_external_status(
        invoice_id, ctx,
        external_status=req.get("external_status", ""),
        external_ref=req.get("external_ref", ""),
    )


# ── Outbound B2G eRačun (javna nabava — FINA Peppol) ─────────────────────────
#
# Full lifecycle mirrors B2B but targets the public-sector via FINA Peppol.
# Collection: invoices_b2g  |  Archive: Invoices_Archive/OUT/b2g/YYYY/MM/
#
#   POST   /outbound-b2g                       — create (draft)
#   GET    /outbound-b2g                       — list
#   GET    /outbound-b2g/pending-ack           — awaiting buyer ack
#   GET    /outbound-b2g/send-failures         — issued with failed sends
#   POST   /outbound-b2g/retry-send-failures   — scheduler retry
#   GET    /outbound-b2g/pending-archive       — not yet archived
#   POST   /outbound-b2g/retry-archive         — scheduler archive retry
#   POST   /outbound-b2g/poll-peppol-status    — AP status poll (scheduler)
#   GET    /outbound-b2g/pending-peppol-sync   — stale AP status dashboard
#   GET    /outbound-b2g/{id}
#   POST   /outbound-b2g/{id}/approve
#   POST   /outbound-b2g/{id}/issue            — UBL + BuyerReference generated
#   POST   /outbound-b2g/{id}/send             — real transport dispatch (Peppol/email/manual)
#   POST   /outbound-b2g/{id}/resend
#   POST   /outbound-b2g/{id}/sync-status
#   POST   /outbound-b2g/{id}/delivered
#   POST   /outbound-b2g/{id}/accept
#   POST   /outbound-b2g/{id}/reject
#   POST   /outbound-b2g/{id}/cancel
#   POST   /outbound-b2g/{id}/archive
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/outbound-b2g/poll-peppol-status")
async def erp_b2g_poll_peppol_status(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Poll the AP for status of all in-flight B2G Peppol invoices (eracun_sent/delivered).
    Intended for the scheduler and the operator 'sync now' button.
    Returns {"polled": N, "updated": N, "errors": N, "skipped": N}.
    """
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().poll_pending_peppol_status(ctx)


@router.get("/outbound-b2g/pending-peppol-sync")
async def erp_b2g_pending_peppol_sync(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Return B2G Peppol invoices in eracun_sent/delivered whose last AP status check
    is older than 30 minutes (or never checked). PEPPOL-STUB-* excluded.
    """
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().list_pending_peppol_sync(ctx)


@router.get("/outbound-b2g/pending-ack")
async def erp_outbound_b2g_pending_ack(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """B2G invoices in eracun_sent/delivered awaiting buyer acknowledgement."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().list_pending_ack(ctx)


@router.get("/outbound-b2g/send-failures")
async def erp_outbound_b2g_send_failures(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """B2G invoices in issued status with a failed send attempt."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().list_send_failures(ctx)


@router.post("/outbound-b2g/retry-send-failures")
async def erp_outbound_b2g_retry_send_failures(
    max_attempts: int = 5, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Retry B2G send failures (scheduler). Returns {attempted, succeeded, failed, skipped}."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().retry_send_failures(ctx, max_attempts=max_attempts)


@router.get("/outbound-b2g/pending-archive")
async def erp_outbound_b2g_pending_archive(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """B2G invoices with UBL not yet archived to Drive."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().list_pending_archive(ctx)


@router.post("/outbound-b2g/retry-archive")
async def erp_outbound_b2g_retry_archive(
    max_attempts: int = 3, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Retry Drive archiving for B2G pending-archive invoices."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().retry_archive(ctx, max_attempts=max_attempts)


@router.post("/outbound-b2g")
async def erp_create_outbound_b2g(req: OutboundB2GCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Create a new outgoing B2G invoice (eRačun for public sector) in draft status."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    data = req.model_dump()
    for field in ("issue_date", "due_date"):
        if data.get(field):
            data[field] = data[field].isoformat()
    data["items"] = [
        {**item, "unit_price": float(item["unit_price"]), "quantity": float(item["quantity"])}
        for item in data.get("items", [])
    ]
    return await get_outbound_b2g_service().create(data, ctx)


@router.get("/outbound-b2g")
async def erp_list_outbound_b2g(
    document_status: str = "", customer_id: str = "",
    date_from: str = "", date_to: str = "",
    limit: int = 50, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """List outgoing B2G invoices with optional filters."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    filters = {}
    if document_status:
        filters["document_status"] = document_status
    if customer_id:
        filters["customer_id"] = customer_id
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    return await get_outbound_b2g_service().list(ctx, filters, _clamp_limit(limit), offset)


@router.get("/outbound-b2g/{invoice_id}")
async def erp_get_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Fetch a single outgoing B2G invoice by ID."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().get(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/approve")
async def erp_approve_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Approve a draft B2G invoice (draft → approved)."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().approve(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/issue")
async def erp_issue_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Issue a B2G invoice (approved → issued).
    Generates UBL 2.1 XML with BuyerReference (EN 16931 BT-10) if provided.
    """
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().issue(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/send")
async def erp_send_outbound_b2g(
    invoice_id: str, req: OutboundB2BSendRequest,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Send an issued B2G invoice to the buyer (issued → eracun_sent).
    Recommended delivery method: peppol (FINA Peppol network).
    """
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().send(
        invoice_id, ctx,
        delivery_method=req.delivery_method,
        delivery_target=req.delivery_target,
        delivery_ref=req.delivery_ref,
    )


@router.post("/outbound-b2g/{invoice_id}/delivered")
async def erp_delivered_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Confirm delivery (eracun_sent → delivered)."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().mark_delivered(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/accept")
async def erp_accept_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Buyer (public sector) confirmed receipt (delivered → accepted)."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().accept(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/reject")
async def erp_reject_outbound_b2g(
    invoice_id: str, req: OutboundB2BRejectRequest,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """Buyer (public sector) rejected the invoice. Mandatory rejection_reason required."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().reject(invoice_id, ctx, req.rejection_reason)


@router.post("/outbound-b2g/{invoice_id}/cancel")
async def erp_cancel_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Cancel a B2G invoice (allowed from draft/approved/issued/eracun_sent)."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().cancel(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/archive")
async def erp_archive_outbound_b2g(invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """
    Upload UBL XML to Drive (Invoices_Archive/OUT/b2g/YYYY/MM/).
    Requires UBL to have been generated (document_status >= issued).
    """
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().archive_outbound(invoice_id, ctx)


@router.post("/outbound-b2g/{invoice_id}/resend")
async def erp_resend_outbound_b2g(
    invoice_id: str, req: OutboundB2BSendRequest = None,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """Retry dispatch or re-send a B2G invoice."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    method = (req.delivery_method if req else None) or None
    target = (req.delivery_target if req else None) or None
    return await get_outbound_b2g_service().resend(invoice_id, ctx, method, target)


@router.post("/outbound-b2g/{invoice_id}/sync-status")
async def erp_sync_status_outbound_b2g(
    invoice_id: str, req: dict, ctx: ERPRequestContext = Depends(get_erp_ctx)
):
    """Record an external delivery/acknowledgement status update for a B2G invoice."""
    from services.erp.outbound_b2g_service import get_outbound_b2g_service
    return await get_outbound_b2g_service().sync_external_status(
        invoice_id, ctx,
        external_status=req.get("external_status", ""),
        external_ref=req.get("external_ref", ""),
    )



# ── Payments ─────────────────────────────────────────────────────────────────

@router.get("/payments")
async def erp_list_payments(
    type: str = "", party_id: str = "", limit: int = 50, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.payment_service import get_payment_service
    filters = {}
    if type:
        filters["type"] = type
    if party_id:
        filters["party_id"] = party_id
    return await get_payment_service().list_payments(ctx, filters, _clamp_limit(limit), offset)


@router.get("/payments/{payment_id}")
async def erp_get_payment(payment_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.payment_service import get_payment_service
    return await get_payment_service().get_payment(payment_id, ctx)


@router.get("/payments/{payment_id}/allocations")
async def erp_payment_allocations(payment_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.payment_service import get_payment_service
    return await get_payment_service().get_allocations_for_payment(payment_id, ctx)


@router.get("/invoices/{invoice_type}/{invoice_id}/allocations")
async def erp_invoice_allocations(invoice_type: str, invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.payment_service import get_payment_service
    return await get_payment_service().get_allocations_for_invoice(invoice_id, ctx)


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("/reports/vat")
async def erp_vat_report(year: int = 2026, month: int = 1, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.reporting_service import get_reporting_service
    return await get_reporting_service().get_vat_summary(ctx, year, month)


@router.get("/reports/cashflow")
async def erp_cashflow(start: str = "", end: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.payment_service import get_payment_service
    from datetime import date
    today = date.today()
    date_from = start or f"{today.year}-{today.month:02d}-01"
    date_to = end or today.isoformat()
    try:
        return await get_payment_service().get_cashflow_summary(ctx, date_from, date_to)
    except Exception as e:
        # Firestore index may still be building — return empty until ready
        if "index" in str(e).lower() or "400" in str(e):
            return {"incoming": 0.0, "outgoing": 0.0, "net": 0.0,
                    "date_from": date_from, "date_to": date_to, "_index_building": True}
        raise


@router.get("/reports/receivables-aging")
async def erp_receivables_aging(as_of_date: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.reporting_service import get_reporting_service
    return await get_reporting_service().get_receivables_aging(ctx, as_of_date or None)


@router.get("/reports/payables-aging")
async def erp_payables_aging(ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.reporting_service import get_reporting_service
    return await get_reporting_service().get_payables_aging(ctx)


@router.get("/reports/financial-summary")
async def erp_financial_summary(start: str = "", end: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.reporting_service import get_reporting_service
    from datetime import date
    today = date.today()
    date_from = start or f"{today.year}-01-01"
    date_to = end or today.isoformat()
    return await get_reporting_service().get_financial_summary(ctx, date_from, date_to)


@router.get("/reports/top-customers")
async def erp_top_customers(limit: int = 10, start: str = "", end: str = "", ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from datetime import date
    from services.erp.invoice_service import get_invoice_service
    today = date.today()
    date_from = start or f"{today.year}-01-01"
    date_to = end or today.isoformat()
    docs = await get_invoice_service().list_invoices(
        ctx, filters={"date_from": date_from, "date_to": date_to}, limit=1000
    )
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


# ── Quotes (Ponude) ──────────────────────────────────────────────────────────

@router.get("/quotes")
async def erp_list_quotes(
    document_status: str = "", customer_id: str = "",
    customer_name: str = "",
    limit: int = 50, offset: int = 0,
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    from services.erp.quote_service import get_quote_service
    filters = {}
    if document_status:
        filters["document_status"] = document_status
    if customer_id:
        filters["customer_id"] = customer_id
    if customer_name:
        filters["customer_name"] = customer_name
    return await get_quote_service().list_quotes(ctx, filters, _clamp_limit(limit), offset)


@router.get("/quotes/{quote_id}")
async def erp_get_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().get_quote(quote_id, ctx)


@router.post("/quotes")
async def erp_create_quote(req: QuoteCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    data = req.model_dump()
    data["valid_until"] = data["valid_until"].isoformat()
    data["items"] = [
        {k: (float(v) if isinstance(v, Decimal) else v) for k, v in item.items()}
        for item in data["items"]
    ]
    return await get_quote_service().create_quote(data, ctx)


@router.patch("/quotes/{quote_id}")
async def erp_update_quote(quote_id: str, req: QuoteUpdate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "valid_until" in data:
        data["valid_until"] = data["valid_until"].isoformat()
    if "items" in data:
        data["items"] = [
            {k: (float(v) if isinstance(v, Decimal) else v) for k, v in item.items()}
            for item in data["items"]
        ]
    return await get_quote_service().update_quote(quote_id, data, ctx)


@router.post("/quotes/{quote_id}/send")
async def erp_send_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().mark_sent(quote_id, ctx)


@router.post("/quotes/{quote_id}/accept")
async def erp_accept_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().accept_quote(quote_id, ctx)


@router.post("/quotes/{quote_id}/reject")
async def erp_reject_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().reject_quote(quote_id, ctx)


@router.post("/quotes/{quote_id}/expire")
async def erp_expire_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().expire_quote(quote_id, ctx)


@router.post("/quotes/{quote_id}/cancel")
async def erp_cancel_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().cancel_quote(quote_id, ctx)


@router.post("/quotes/{quote_id}/convert")
async def erp_convert_quote(quote_id: str, req: QuoteConvertRequest, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.quote_service import get_quote_service
    return await get_quote_service().convert_to_invoice(quote_id, req.invoice_type, ctx)


@router.post("/quotes/{quote_id}/create-invoice")
async def erp_create_invoice_from_quote(
    quote_id: str,
    req: QuoteCreateInvoiceRequest = QuoteCreateInvoiceRequest(),
    ctx: ERPRequestContext = Depends(get_erp_ctx),
):
    """
    Create a fully-structured outbound invoice from an accepted quote.

    invoice_type (default "b2b"):
      "b2b" — domestic B2B eRačun via OutboundB2BService
      "b2g" — public-sector B2G eRačun via FINA Peppol / OutboundB2GService

    The quote must be in 'accepted' status.
    Idempotent: a second call returns the already-created invoice without creating a duplicate.
    Returns 201 for new invoices, 200 for already-existing ones.
    """
    from fastapi.responses import JSONResponse
    from services.erp.quote_service import get_quote_service

    overrides = req.model_dump(exclude_none=True)
    # Remove invoice_type from overrides dict; it's routing metadata, not a payload field
    invoice_type = overrides.pop("invoice_type", "b2b")
    if "due_date" in overrides and overrides["due_date"]:
        overrides["due_date"] = str(overrides["due_date"])

    svc = get_quote_service()
    if invoice_type == "b2b":
        invoice = await svc.create_outbound_b2b_from_quote(quote_id, ctx, overrides)
    elif invoice_type == "b2g":
        invoice = await svc.create_outbound_b2g_from_quote(quote_id, ctx, overrides)
    else:
        # Pydantic pattern validation should catch this first; belt-and-suspenders.
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unsupported invoice_type: {invoice_type!r}")

    already_exists = invoice.pop("_already_exists", False)
    status_code = 200 if already_exists else 201
    return JSONResponse(content=invoice, status_code=status_code)


@router.get("/quotes/{quote_id}/print")
async def erp_print_quote(quote_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Return print-friendly HTML for a quote."""
    from services.erp.quote_service import get_quote_service
    q = await get_quote_service().get_quote(quote_id, ctx)
    items_html = ""
    for item in (q.get("items") or []):
        items_html += (
            f"<tr><td>{esc(str(item.get('description','')))}</td>"
            f"<td style='text-align:right'>{float(item.get('quantity',1))}</td>"
            f"<td style='text-align:right'>{float(item.get('unit_price',0)):.2f}</td>"
            f"<td style='text-align:right'>{int(item.get('vat_rate',25))}%</td>"
            f"<td style='text-align:right'>{float(item.get('line_gross',0)):.2f}</td></tr>"
        )
    display_id = esc(str(q.get('display_id', '')))
    customer_name = esc(str(q.get('customer_name', '—')))
    customer_oib = esc(str(q.get('customer_oib', '—')))
    issue_date = esc(str(q.get('issue_date', ''))[:10])
    valid_until = esc(str(q.get('valid_until', ''))[:10])
    currency = esc(str(q.get('currency', 'EUR')))
    status = esc(str(q.get('document_status', 'draft')))
    notes_raw = q.get('notes', '')
    notes_html = f"<div class='notes'>{esc(str(notes_raw))}</div>" if notes_raw else ""
    html = f"""<!DOCTYPE html>
<html lang="hr"><head><meta charset="UTF-8"/><title>Ponuda {display_id}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 700px; margin: 2rem auto; color: #222; font-size: 14px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem 2rem; margin: 1.5rem 0; font-size: 0.9rem; }}
  .meta dt {{ color: #888; font-size: 0.8rem; }}
  .meta dd {{ margin: 0 0 0.5rem; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
  th {{ text-align: left; border-bottom: 2px solid #333; padding: 0.5rem 0.4rem; font-size: 0.8rem; text-transform: uppercase; color: #555; }}
  td {{ padding: 0.45rem 0.4rem; border-bottom: 1px solid #ddd; }}
  .totals {{ text-align: right; margin-top: 1rem; font-size: 0.95rem; }}
  .totals .gross {{ font-size: 1.2rem; font-weight: 700; }}
  .notes {{ margin-top: 1.5rem; padding: 0.75rem; background: #f5f5f5; border-radius: 4px; font-size: 0.85rem; color: #555; }}
  .footer {{ margin-top: 2rem; font-size: 0.78rem; color: #999; border-top: 1px solid #ddd; padding-top: 0.75rem; }}
  @media print {{ body {{ margin: 0; }} }}
</style></head><body>
<h1>PONUDA {display_id}</h1>
<dl class="meta">
  <dt>Kupac</dt><dd>{customer_name}</dd>
  <dt>OIB</dt><dd>{customer_oib}</dd>
  <dt>Datum izdavanja</dt><dd>{issue_date}</dd>
  <dt>Rok valjanosti</dt><dd>{valid_until}</dd>
  <dt>Valuta</dt><dd>{currency}</dd>
  <dt>Status</dt><dd>{status}</dd>
</dl>
<table><thead><tr><th>Opis</th><th style="text-align:right">Kol.</th><th style="text-align:right">Cijena</th><th style="text-align:right">PDV</th><th style="text-align:right">Ukupno</th></tr></thead>
<tbody>{items_html}</tbody></table>
<div class="totals">
  Neto: {float(q.get('subtotal_net',0)):.2f} EUR<br/>
  PDV: {float(q.get('vat_total',0)):.2f} EUR<br/>
  <span class="gross">Ukupno: {float(q.get('total_gross',0)):.2f} EUR</span>
</div>
{notes_html}
<div class="footer">Ponuda vrijedi do {valid_until}. Plaćanje po dogovoru.</div>
</body></html>"""
    return HTMLResponse(content=html)


# ── Activity Feed ────────────────────────────────────────────────────────────

@router.get("/activity")
async def erp_activity_feed(limit: int = 50, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    """Chronological feed of ERP business actions from the audit log."""
    from services.erp.base_erp_service import get_firestore_db
    from google.cloud.firestore_v1.base_query import FieldFilter
    db = get_firestore_db()
    query = (
        db.collection("audit_log")
        .where(filter=FieldFilter("company_id", "==", ctx.company_id))
        .where(filter=FieldFilter("target_service", "==", "erp"))
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

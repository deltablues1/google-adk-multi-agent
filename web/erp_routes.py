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
from html import escape as esc
from typing import Tuple

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse

from services.erp.request_context import ERPRequestContext, build_context
from services.erp.repositories.base import InvoiceReference
from web.models import (
    PaymentRequest, VendorInvoiceCreate, StockAdjustRequest,
    CustomerCreate, ProductCreate,
    QuoteCreate, QuoteUpdate, QuoteConvertRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp")

_MAX_LIMIT = 500
_DEV_MODE = os.environ.get("ERP_DEV_MODE", "").lower() in ("1", "true", "yes")


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
    if _DEV_MODE:
        try:
            user_id, company_id = _extract_identity(request)
        except HTTPException:
            # No headers → dev owner fallback
            logger.debug("ERP_DEV_MODE: no identity headers, using owner fallback")
            return ERPRequestContext(
                user_id="dev-user",
                company_id=os.environ.get("ERP_COMPANY_ID", "default-company"),
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

    NOT a production endpoint — disable or protect when real auth is in place.
    """
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


@router.get("/vendor-invoices/{vendor_invoice_id}")
async def erp_get_vendor_invoice(vendor_invoice_id: str, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    return await get_vendor_invoice_service().get_vendor_invoice(vendor_invoice_id, ctx)


@router.post("/vendor-invoices")
async def erp_create_vendor_invoice(req: VendorInvoiceCreate, ctx: ERPRequestContext = Depends(get_erp_ctx)):
    from services.erp.vendor_invoice_service import get_vendor_invoice_service
    data = req.model_dump()
    if data.get("issue_date"):
        data["issue_date"] = data["issue_date"].isoformat()
    if data.get("due_date"):
        data["due_date"] = data["due_date"].isoformat()
    data["total_gross"] = float(data["total_gross"])
    data["vat_amount"] = float(data["vat_amount"])
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

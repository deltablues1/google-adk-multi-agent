"""
ERP ADK Tools
=============
Thin async wrappers that bridge ADK agents → ERP service layer.
Each function receives flat typed parameters (ADK requirement),
builds an ERPRequestContext from session state or defaults,
and delegates to the appropriate ERP service.

17 tools total. Context is built explicitly — no magic session state lookups.
"""

import logging
import os
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context helper — builds ERPRequestContext for ADK tool calls
# ---------------------------------------------------------------------------

def _build_ctx(
    company_id: Optional[str] = None,
    user_id: str = "agent",
    role: str = "employee",
) -> "ERPRequestContext":
    """Build ERPRequestContext with explicit values (no magic)."""
    from services.erp.request_context import ERPRequestContext
    return ERPRequestContext(
        user_id=user_id,
        company_id=company_id or os.environ.get("ERP_COMPANY_ID", "default-company"),
        role=role,
        grants=[],
        denies=[],
        request_id=str(uuid4()),
    )


# ---------------------------------------------------------------------------
# Tool: erp_create_vendor_invoice_from_ocr
# ---------------------------------------------------------------------------

async def erp_create_vendor_invoice_from_ocr(
    merchant_name: str,
    total_amount: float,
    transaction_date: str,
    vat_amount: float = 0.0,
    invoice_number: str = "",
    vendor_oib: str = "",
    expense_category: str = "Ostalo",
    confidence_score: float = 0.0,
    scan_file_id: str = "",
    items: Optional[list] = None,
    extraction_notes: str = "",
) -> dict:
    """
    Create a DRAFT vendor invoice (URA) in the ERP system from OCR-extracted data.

    Call this after extract_receipt_data() when the scanned document is a
    SUPPLIER INVOICE (not a simple cash receipt). The draft is created in the
    ERP with document_status='draft' — an accountant must review, assign the
    vendor, and approve via the ERP UI.

    Args:
        merchant_name: Vendor/supplier name from OCR (e.g. "T-HT d.d.")
        total_amount: Total gross amount including VAT (e.g. 1250.00)
        transaction_date: Invoice date in YYYY-MM-DD format
        vat_amount: VAT amount extracted from invoice (0 if not found)
        invoice_number: Vendor's own invoice number (e.g. "INV-2026-001")
        vendor_oib: Vendor OIB (11 digits), if extracted
        expense_category: OCR category: Hrana|Prijevoz|Ured|Režije|Ostalo
        confidence_score: OCR confidence 0.0–1.0 (logged, not enforced)
        scan_file_id: Google Drive file ID of the scanned invoice image
        items: Line items list from OCR [{"description": ..., "amount": ...}]
        extraction_notes: Any notes from OCR extraction process

    Returns:
        dict with keys:
          - success: bool
          - vendor_invoice_id: str (UUID, for reference)
          - display_id: str (e.g. "URA-2026-000003")
          - document_status: "draft"
          - message: str (human-readable result)
          - requires_review: bool (always True for OCR drafts)

    Example:
        # After extract_receipt_data() returns:
        ocr = result["data"]
        erp_result = await erp_create_vendor_invoice_from_ocr(
            merchant_name=ocr["merchant_name"],
            total_amount=ocr["total_amount"],
            transaction_date=ocr["transaction_date"],
            vat_amount=ocr.get("vat_amount", 0),
            invoice_number=ocr.get("invoice_number", ""),
            vendor_oib=ocr.get("tax_id", ""),
            expense_category=ocr.get("expense_category", "Ostalo"),
            confidence_score=ocr.get("confidence_score", 0),
            scan_file_id=ocr.get("drive_file_id", ""),
            items=ocr.get("items", []),
        )
    """
    try:
        from services.erp.vendor_invoice_service import get_vendor_invoice_service

        svc = get_vendor_invoice_service()
        # Employee role can create OCR drafts; approval requires accountant/owner
        ctx = _build_ctx(role="employee", user_id="expense-agent")

        ocr_data = {
            "merchant_name": merchant_name,
            "total_amount": total_amount,
            "transaction_date": transaction_date,
            "vat_amount": vat_amount,
            "invoice_number": invoice_number,
            "tax_id": vendor_oib,
            "expense_category": expense_category,
            "confidence_score": confidence_score,
            "drive_file_id": scan_file_id,
            "items": items or [],
            "extraction_notes": extraction_notes,
        }

        doc = await svc.create_from_ocr(
            ocr_data=ocr_data,
            scan_file_id=scan_file_id,
            ctx=ctx,
        )

        logger.info(
            f"ERP vendor invoice draft created: {doc['display_id']} "
            f"({merchant_name}, {total_amount} EUR, confidence={confidence_score:.0%})"
        )

        return {
            "success": True,
            "vendor_invoice_id": doc["vendor_invoice_id"],
            "display_id": doc["display_id"],
            "document_status": doc["document_status"],
            "vendor_name": merchant_name,
            "total_gross": total_amount,
            "requires_review": True,
            "message": (
                f"Ulazni račun {doc['display_id']} kreiran kao DRAFT. "
                f"Dobavljač: {merchant_name}, iznos: {total_amount:.2f} EUR. "
                f"Pouzdanost OCR-a: {confidence_score:.0%}. "
                f"Molite accountanta da pregleda i odobri u ERP UI-u."
            ),
        }

    except Exception as e:
        logger.error(f"erp_create_vendor_invoice_from_ocr failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Greška pri kreiranju URA drafta: {e}",
        }


# ---------------------------------------------------------------------------
# Rolodex tools — customer:read
# ---------------------------------------------------------------------------

async def erp_search_customers(
    search: str = "",
    party_type: str = "",
    limit: int = 20,
) -> dict:
    """
    Search customers and suppliers in the ERP system.

    Use this to find a customer/supplier by name, OIB, or type before
    creating an invoice, quote, or vendor invoice.

    Args:
        search: Name or OIB fragment to search for (case-insensitive)
        party_type: Filter by type: "customer" | "supplier" | "both" | "" (all)
        limit: Max results to return (default 20)

    Returns:
        dict with "customers" list, each item has:
          _id, name, oib, party_type, category, email, phone,
          payment_terms, credit_limit, iban, city, country
    """
    try:
        from services.erp.customer_service import get_customer_service
        ctx = _build_ctx(role="viewer", user_id="rolodex-agent")
        filters = {}
        if search:
            filters["search"] = search
        if party_type:
            filters["party_type"] = party_type
        results = await get_customer_service().list_customers(ctx, filters, limit=limit, offset=0)
        return {"success": True, "customers": results, "count": len(results)}
    except Exception as e:
        logger.error(f"erp_search_customers failed: {e}")
        return {"success": False, "error": str(e), "customers": []}


async def erp_get_customer_balance(customer_id: str) -> dict:
    """
    Get the current balance (open receivables) for a specific customer.

    Returns total amount owed, number of open invoices, and oldest unpaid invoice.
    Use this when a customer asks about their balance or before extending credit.

    Args:
        customer_id: Internal customer UUID (from erp_search_customers result)

    Returns:
        dict with: customer_name, total_open_eur, invoice_count,
                   oldest_invoice_date, credit_limit, payment_terms
    """
    try:
        from services.erp.customer_service import get_customer_service
        ctx = _build_ctx(role="viewer", user_id="rolodex-agent")
        result = await get_customer_service().get_customer_balance(customer_id, ctx)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_get_customer_balance failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Analyst tools — report:read
# ---------------------------------------------------------------------------

async def erp_get_vat_summary(year: int, month: int) -> dict:
    """
    Get VAT (PDV) summary for a specific month.

    Returns output VAT (izlazni PDV) by rate, input VAT (ulazni PDV / pretporez),
    and net VAT payable to Tax Authority (Porezna uprava).

    Use this when asked about: PDV za mjesec, porezna obveza, pretporez,
    prijava PDV-a, obrasci PDV.

    Args:
        year: Year (e.g. 2026)
        month: Month 1-12

    Returns:
        dict with output_vat breakdown by rate, input_vat total,
        net_vat_payable, period (YYYY-MM)
    """
    try:
        from services.erp.reporting_service import get_reporting_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        result = await get_reporting_service().get_vat_summary(ctx, year=year, month=month)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_get_vat_summary failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_receivables_aging(as_of_date: str = "") -> dict:
    """
    Get receivables aging report — who owes money and how overdue.

    Groups open customer invoices into buckets:
    current (not yet due), 1-30 days, 31-60 days, 61-90 days, 90+ days.

    Use this when asked about: tko duguje, zaostala potraživanja, aging,
    neplaćeni računi, potraživanja po kupcima.

    Args:
        as_of_date: Reference date YYYY-MM-DD (default: today)

    Returns:
        dict with total_open_eur, buckets (current/1_30/31_60/61_90/over_90),
        each bucket has invoices list and total EUR
    """
    try:
        from services.erp.invoice_service import get_invoice_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        result = await get_invoice_service().get_open_receivables(ctx, as_of_date=as_of_date or None)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_get_receivables_aging failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_financial_summary(date_from: str, date_to: str) -> dict:
    """
    Get financial summary for a date range: revenue, expenses, gross profit.

    Aggregates issued invoices (revenue) and vendor invoices (expenses)
    for the given period. No LLM, pure arithmetic.

    Use this when asked about: prihodi, rashodi, dobit, financijski pregled,
    P&L, profit and loss, poslovni rezultat.

    Args:
        date_from: Start date YYYY-MM-DD (e.g. "2026-01-01")
        date_to: End date YYYY-MM-DD (e.g. "2026-03-31")

    Returns:
        dict with total_revenue, total_expenses, gross_profit,
        invoice_count, vendor_invoice_count, period
    """
    try:
        from services.erp.reporting_service import get_reporting_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        result = await get_reporting_service().get_financial_summary(ctx, date_from=date_from, date_to=date_to)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_get_financial_summary failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_stock_levels(low_stock_only: bool = False) -> dict:
    """
    Get current product stock levels.

    Returns all products with current stock quantity.
    Optionally filter to only products below minimum stock threshold.

    Use this when asked about: zalihe, stanje skladišta, niska zaliha,
    što nedostaje na skladištu, inventura.

    Args:
        low_stock_only: If True, return only products below min_stock

    Returns:
        dict with "products" list, each has: sku, name, stock_quantity,
        min_stock, unit, price — sorted by stock_quantity ascending
    """
    try:
        from services.erp.product_service import get_product_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        filters = {"low_stock_only": low_stock_only} if low_stock_only else {}
        products = await get_product_service().list_products(ctx, filters, limit=200, offset=0)
        if low_stock_only:
            products = [p for p in products
                        if p.get("min_stock") and float(p.get("stock_quantity", 0)) < float(p["min_stock"])]
        products.sort(key=lambda p: float(p.get("stock_quantity", 0)))
        return {"success": True, "products": products, "count": len(products)}
    except Exception as e:
        logger.error(f"erp_get_stock_levels failed: {e}")
        return {"success": False, "error": str(e), "products": []}


# ---------------------------------------------------------------------------
# Tracker tools — payment:record
# ---------------------------------------------------------------------------

async def erp_list_open_invoices(
    invoice_type: str = "",
    customer_name: str = "",
    limit: int = 30,
) -> dict:
    """
    List open (unpaid or partially paid) customer invoices.

    Use this before recording a payment, or when asked about:
    koji računi nisu plaćeni, otvoreni računi, neplaćene fakture.

    Args:
        invoice_type: Filter by type: "b2c"|"b2b"|"b2g"|"eu"|"int"|"" (all)
        customer_name: Filter by customer name fragment
        limit: Max results (default 30)

    Returns:
        dict with "invoices" list, each has: display_id, invoice_type,
        customer_name, total_gross, amount_paid, amount_due,
        payment_status, due_date, is_overdue
    """
    try:
        from services.erp.invoice_service import get_invoice_service
        ctx = _build_ctx(role="viewer", user_id="tracker-agent")
        filters: dict = {"payment_status_ne": "paid"}
        if invoice_type:
            filters["invoice_type"] = invoice_type
        invoices = await get_invoice_service().list_invoices(
            ctx, invoice_type=invoice_type or None, filters=filters, limit=limit, offset=0
        )
        # Post-filter: exclude paid (by erp_payment_status field written by repo)
        open_invoices = [i for i in invoices if i.get("erp_payment_status") != "paid"]
        # Post-filter: customer name search (Firestore has no text search)
        if customer_name:
            cn = customer_name.lower()
            open_invoices = [
                i for i in open_invoices
                if cn in (i.get("customer_name") or i.get("buyer_name", "")).lower()
            ]
        return {"success": True, "invoices": open_invoices, "count": len(open_invoices)}
    except Exception as e:
        logger.error(f"erp_list_open_invoices failed: {e}")
        return {"success": False, "error": str(e), "invoices": []}


async def erp_record_payment(
    invoice_type: str,
    invoice_id: str,
    invoice_display_id: str,
    amount: float,
    payment_date: str,
    payment_method: str,
    reference: str = "",
    notes: str = "",
    idempotency_key: str = "",
) -> dict:
    """
    Record a payment against a customer invoice.

    IMPORTANT: This writes to the database. Only call this after the user
    has explicitly confirmed the payment details (amount, date, method).
    Never call this autonomously without user confirmation.

    Args:
        invoice_type: Invoice collection type: "b2c"|"b2b"|"b2g"|"eu"|"int"
        invoice_id: Internal invoice UUID
        invoice_display_id: Human-readable ID (e.g. "RAC-2026-000042") for audit
        amount: Payment amount in EUR (must be > 0 and <= amount_due)
        payment_date: Payment date YYYY-MM-DD
        payment_method: "transfer"|"cash"|"card"|"direct_debit"
        reference: Bank reference / poziv na broj (optional)
        notes: Additional notes (optional)
        idempotency_key: Unique key to prevent duplicate payments (generate with uuid if not provided)

    Returns:
        dict with: success, payment_id, display_id, new_payment_status, amount_due_after
    """
    try:
        from services.erp.invoice_service import get_invoice_service
        from services.erp.repositories.base import InvoiceReference
        if not idempotency_key:
            idempotency_key = str(uuid4())
        ctx = _build_ctx(role="accountant", user_id="tracker-agent")
        invoice_ref = InvoiceReference(
            invoice_id=invoice_id,
            invoice_type=invoice_type,
            display_id=invoice_display_id,
        )
        from decimal import Decimal
        result = await get_invoice_service().record_payment(
            invoice_ref=invoice_ref,
            amount=Decimal(str(amount)),
            payment_date=payment_date,
            payment_method=payment_method,
            reference=reference,
            ctx=ctx,
            idempotency_key=idempotency_key,
            notes=notes,
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_record_payment failed: {e}")
        return {"success": False, "error": str(e), "message": str(e)}


async def erp_get_open_payables(as_of_date: str = "") -> dict:
    """
    Get open vendor invoices (payables) — what the company owes to suppliers.

    Groups by aging bucket and flags overdue items.
    Use this when asked about: što dugujemo, obaveze prema dobavljačima,
    neplaćeni URA, plaćanja prema dobavljačima.

    Args:
        as_of_date: Reference date YYYY-MM-DD (default: today)

    Returns:
        dict with total_due_eur, buckets, overdue items list
    """
    try:
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _build_ctx(role="viewer", user_id="tracker-agent")
        result = await get_vendor_invoice_service().get_open_payables(ctx)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"erp_get_open_payables failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Fiskalizacija tools — invoice:read, customer:read, product:read
# ---------------------------------------------------------------------------

async def erp_get_invoice(invoice_type: str, invoice_id: str) -> dict:
    """
    Get a single invoice by type and ID from the ERP system.

    Use this when fiscalization agent needs to look up invoice details
    before issuing JIR/ZKI or UBL XML for B2B/B2G.

    Args:
        invoice_type: "b2c"|"b2b"|"b2g"|"eu"|"int"
        invoice_id: Internal UUID of the invoice document

    Returns:
        Full invoice dict with all fields, or error if not found
    """
    try:
        from services.erp.invoice_service import get_invoice_service
        from services.erp.repositories.base import InvoiceReference
        ctx = _build_ctx(role="viewer", user_id="fiskalizacija-agent")
        ref = InvoiceReference(invoice_id=invoice_id, invoice_type=invoice_type, display_id="")
        result = await get_invoice_service().get_invoice(ref, ctx)
        return {"success": True, "invoice": result}
    except Exception as e:
        logger.error(f"erp_get_invoice failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_product(product_id: str) -> dict:
    """
    Get a single product/service from the ERP catalog.

    Use this when fiscalization agent needs product details (KPD code,
    VAT rate, price) for generating UBL line items.

    Args:
        product_id: Internal product UUID

    Returns:
        Product dict with: sku, name, kpd_code, unit, price, vat_rate, stock_quantity
    """
    try:
        from services.erp.product_service import get_product_service
        ctx = _build_ctx(role="viewer", user_id="fiskalizacija-agent")
        result = await get_product_service().get_product(product_id, ctx)
        return {"success": True, "product": result}
    except Exception as e:
        logger.error(f"erp_get_product failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Activity & Inventory read-only tools
# ---------------------------------------------------------------------------

async def erp_get_activity_feed(limit: int = 20) -> dict:
    """
    Return the latest ERP activity events from the audit log.

    Use this when the user asks "what happened recently?", "show me recent
    ERP activity", or when analyst/tracker agents need a chronological
    overview of business actions (payments, invoices, stock changes).

    Args:
        limit: Max number of events to return (1-100, default 20)

    Returns:
        Dict with success, count, events list, and message if empty.
        Each event: id, timestamp, action, description, entity_type,
        display_id, user_id.
    """
    try:
        from services.erp.base_erp_service import get_firestore_db
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        db = get_firestore_db()
        clamped = max(1, min(limit, 100))
        query = (
            db.collection("audit_log")
            .where("company_id", "==", ctx.company_id)
            .where("target_service", "==", "erp")
            .order_by("timestamp", direction="DESCENDING")
            .limit(clamped)
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
        if not events:
            return {"success": True, "count": 0, "events": [], "message": "Nema nedavnih ERP aktivnosti."}
        return {"success": True, "count": len(events), "events": events}
    except Exception as e:
        logger.error(f"erp_get_activity_feed failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_inventory_movements(product_id: str, limit: int = 20) -> dict:
    """
    Return inventory movement history for a specific product.

    Use this when the user asks about stock changes, "what happened to
    inventory for product X?", or when tracker agent needs to verify
    stock adjustments and their reasons.

    Args:
        product_id: Internal product UUID
        limit: Max number of movements to return (1-100, default 20)

    Returns:
        Dict with success, count, movements list, and message if empty.
        Each movement: id, product_id, product_sku, movement_type,
        quantity_delta, quantity_after, reason, reference_id, created_at,
        created_by.
    """
    try:
        from services.erp.product_service import get_product_service
        ctx = _build_ctx(role="viewer", user_id="tracker-agent")
        clamped = max(1, min(limit, 100))
        movements = await get_product_service().get_stock_movements(product_id, ctx, clamped)
        if not movements:
            return {"success": True, "count": 0, "movements": [], "message": f"Nema kretanja zaliha za proizvod {product_id}."}
        return {"success": True, "count": len(movements), "movements": movements}
    except Exception as e:
        logger.error(f"erp_get_inventory_movements failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_list_quotes(
    status: str = "",
    customer_name: str = "",
    limit: int = 50,
) -> dict:
    """
    List quotes (ponude) with optional filters.

    Use this when the user asks about quotes, offers, ponude — e.g. "show me
    all sent quotes", "pending ponude", "quotes for customer X".

    Args:
        status: Filter by document_status (draft|sent|accepted|rejected|expired|converted|cancelled)
        customer_name: Filter by customer name (case-insensitive substring match)
        limit: Max results (1-100, default 50)

    Returns:
        Dict with success, count, quotes list.
    """
    try:
        from services.erp.quote_service import get_quote_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        clamped = max(1, min(limit, 100))
        filters = {}
        if status:
            filters["document_status"] = status
        quotes = await get_quote_service().list_quotes(ctx, filters=filters, limit=clamped)
        if customer_name:
            q = customer_name.lower()
            quotes = [r for r in quotes if q in (r.get("customer_name") or "").lower()]
        return {"success": True, "count": len(quotes), "quotes": quotes}
    except Exception as e:
        logger.error(f"erp_list_quotes failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_quote(quote_id: str) -> dict:
    """
    Get a single quote (ponuda) by its ID.

    Use this when the user asks about a specific quote — details, items,
    status, validity date, total amount.

    Args:
        quote_id: Internal quote UUID

    Returns:
        Dict with success and quote document including items, totals, status.
    """
    try:
        from services.erp.quote_service import get_quote_service
        ctx = _build_ctx(role="viewer", user_id="analyst-agent")
        result = await get_quote_service().get_quote(quote_id, ctx)
        return {"success": True, "quote": result}
    except Exception as e:
        logger.error(f"erp_get_quote failed: {e}")
        return {"success": False, "error": str(e)}


async def erp_get_vendor_invoice(vendor_invoice_id: str) -> dict:
    """
    Get a single vendor invoice (URA) by its ID.

    Use this when the expense agent needs to check vendor invoice details,
    approval status, or payment status for a specific URA document.

    Args:
        vendor_invoice_id: Internal vendor invoice UUID

    Returns:
        Dict with success and vendor_invoice document.
    """
    try:
        from services.erp.vendor_invoice_service import get_vendor_invoice_service
        ctx = _build_ctx(role="viewer", user_id="expense-agent")
        result = await get_vendor_invoice_service().get_vendor_invoice(vendor_invoice_id, ctx)
        return {"success": True, "vendor_invoice": result}
    except Exception as e:
        logger.error(f"erp_get_vendor_invoice failed: {e}")
        return {"success": False, "error": str(e)}

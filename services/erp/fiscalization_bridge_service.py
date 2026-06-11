"""
ERP–Fiscalization Bridge Service (Sprint C1)
=============================================
Canonical write-back layer between the Croatian fiscalization pipeline
(DeterministicFiscalExecutor / fiskalizacija_adk_tools) and the ERP invoice
collections.

After a successful (or failed) CIS/SOAP call, this module writes the
fiscalization result back to the originating ERP document so that:
  - The ERP invoice is the single source of truth for JIR, ZKI, and status.
  - No separate "ledger" is needed for downstream ERP queries.
  - The audit trail in audit_log includes the fiscalization event.

Fiscalization fields written to invoice documents
-------------------------------------------------
  fiscalization_status  : "pending" | "fiscalized" | "fiscalization_failed" | "not_required"
  fiscalized_at         : ISO timestamp of the CIS success response
  jir                   : Jedinstveni Identifikator Računa (UUID from FINA)
  zki                   : Zaštitni Kod Izdavatelja (hex hash)
  verification_url      : https://porezna.gov.hr/rn?jir=...
  qr_code_base64        : Base64-encoded QR PNG (if PDF renderer produced one)
  fiscalization_error   : error message if status == "fiscalization_failed"

Collection routing
------------------
  B2C invoices  → invoices_b2c   (fiscalization_status = "pending" at create time)
  B2B invoices  → invoices_b2b   (fiscalization_status = "not_required")
  B2G invoices  → invoices_b2g   (fiscalization_status = "not_required")

Public API
----------
  write_back_b2c(erp_invoice_id, fiskalizacija_result)  → None
  write_back_failure_b2c(erp_invoice_id, error_msg)    → None
  get_fiscalization_status(erp_invoice_id, collection)  → dict

Non-blocking: write failures are logged as warnings, never raised to caller.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_B2C_COL = "invoices_b2c"


def _db():
    from services.erp.base_erp_service import get_firestore_db
    return get_firestore_db()


async def write_back_b2c(
    erp_invoice_id: str,
    fiskalizacija_result: dict,
    *,
    company_id: Optional[str] = None,
) -> None:
    """
    Write a successful (or already-fiscalized idempotent) fiscalization result
    back to the invoices_b2c ERP document.

    Non-blocking: exceptions are caught and logged; the caller's fiscalization
    result is unaffected.

    Args:
        erp_invoice_id:        Firestore document ID in invoices_b2c.
        fiskalizacija_result:  Dict returned by execute_fiscalization() or
                               DeterministicFiscalExecutor.execute().to_dict().
                               Must contain: success, jir, zki.
        company_id:            Optional — used only for audit trail.
    """
    if not erp_invoice_id:
        return

    now = datetime.now(timezone.utc).isoformat()
    jir = fiskalizacija_result.get("jir") or ""
    zki = fiskalizacija_result.get("zki") or ""

    if not fiskalizacija_result.get("success"):
        await write_back_failure_b2c(
            erp_invoice_id,
            error_msg=fiskalizacija_result.get("error_message") or "Fiscalization failed",
        )
        return

    update = {
        "fiscalization_status": "fiscalized",
        "fiscalized_at":        now,
        "jir":                  jir,
        "zki":                  zki,
        "verification_url":     fiskalizacija_result.get("verification_url"),
        "qr_code_base64":       fiskalizacija_result.get("qr_code_base64"),
        "fiscalization_error":  None,
        "updated_at":           now,
    }
    # Persist fiscal_invoice_number if the caller provides it (Sprint C1.2)
    fiscal_inv_no = fiskalizacija_result.get("fiscal_invoice_number")
    if fiscal_inv_no:
        update["fiscal_invoice_number"] = fiscal_inv_no

    try:
        db = _db()
        await db.collection(_B2C_COL).document(erp_invoice_id).update(update)
        logger.info(
            f"[FiscBridge] B2C write-back OK: invoice={erp_invoice_id} "
            f"jir={jir[:8] if jir else 'none'}... zki={zki[:8] if zki else 'none'}..."
        )

        # Write audit entry (best-effort — no ctx available here)
        try:
            snap = await db.collection(_B2C_COL).document(erp_invoice_id).get(
                field_paths=["company_id", "display_id"]
            )
            doc_meta = snap.to_dict() or {} if snap.exists else {}
            cid = company_id or doc_meta.get("company_id", "unknown")
            display_id = doc_meta.get("display_id", erp_invoice_id)

            from services.erp.request_context import ERPRequestContext
            system_ctx = ERPRequestContext(
                user_id="system:fiscalization_bridge",
                company_id=cid,
                role="system",
                grants=set(),
                denies=set(),
                request_id=f"fisc-bridge-{erp_invoice_id[:8]}",
            )
            from services.erp.base_erp_service import write_audit
            await write_audit(
                "invoice_fiscalized", "invoice_b2c", erp_invoice_id,
                display_id, system_ctx,
                data={"jir": jir, "zki": zki[:16] if zki else ""},
                db=db,
            )
        except Exception as audit_exc:
            logger.warning(f"[FiscBridge] Audit write failed (non-blocking): {audit_exc}")

    except Exception as exc:
        logger.error(
            f"[FiscBridge] B2C write-back FAILED for invoice {erp_invoice_id}: {exc}. "
            "Fiscalization succeeded — ERP document not updated."
        )


async def write_back_failure_b2c(
    erp_invoice_id: str,
    error_msg: str,
) -> None:
    """
    Write a fiscalization failure back to the invoices_b2c ERP document.

    Non-blocking: exceptions are logged, never raised.
    """
    if not erp_invoice_id:
        return

    now = datetime.now(timezone.utc).isoformat()
    update = {
        "fiscalization_status": "fiscalization_failed",
        "fiscalization_error":  error_msg[:1000],
        "updated_at":           now,
    }

    try:
        await _db().collection(_B2C_COL).document(erp_invoice_id).update(update)
        logger.warning(
            f"[FiscBridge] B2C failure written for invoice {erp_invoice_id}: "
            f"{error_msg[:80]}"
        )
    except Exception as exc:
        logger.error(
            f"[FiscBridge] Failed to write fiscalization failure for {erp_invoice_id}: {exc}"
        )


async def fiscalize_b2c_invoice(
    invoice_id: str,
    ctx,  # ERPRequestContext — imported lazily to avoid circular import
    *,
    payment_method: str = "T",
) -> dict:
    """
    Trigger fiscalization for a B2C ERP invoice via the ERP API.

    The API call itself is the user's explicit confirmation, so HITL is
    bypassed (skip_hitl=True).  The bridge write-back happens inside
    execute_fiscalization() because erp_invoice_id is included in the payload.

    Fiscal invoice number (Sprint C1.2):
    - The ERP `display_id` (RA-...) is the INTERNAL ERP identifier.
    - FINA requires `XXX/PP/NU` format (Croatian fiscal invoice number).
    - These are DIFFERENT numbers that serve different purposes.
    - On first fiscalization: a new FINA number is generated from the ledger
      counter and stored as `fiscal_invoice_number` on the ERP document.
    - On retry (fiscalization_failed): the same `fiscal_invoice_number` is
      reused so the FINA sequence stays consistent.

    Args:
        invoice_id:     Firestore document ID in invoices_b2c.
        ctx:            ERPRequestContext (for permission check + company_id).
        payment_method: "G"=gotovina, "K"=kartica, "T"=transakcijski račun
                        (default "T" — most B2C online invoices).

    Returns:
        dict with fiscalization result keys:
            success, status, jir, zki, verification_url, error_message,
            already_fiscalized (bool — True if idempotent return),
            fiscal_invoice_number (str — the FINA XXX/PP/NU number used)

    Raises:
        NotFoundError       — invoice not found
        ValidationError     — wrong fiscalization_status
        InsufficientPermissionError — caller lacks invoice:fiscalize
    """
    from services.erp.base_erp_service import check_permission
    from services.erp.errors import NotFoundError, ValidationError

    check_permission(ctx, "invoice:fiscalize")

    db = _db()
    snap = await db.collection(_B2C_COL).document(invoice_id).get()
    if not snap.exists:
        raise NotFoundError(
            code="NOT_FOUND",
            message=f"B2C račun '{invoice_id}' nije pronađen.",
        )

    doc = snap.to_dict() or {}
    fisc_status = doc.get("fiscalization_status", "pending")

    # Idempotency: already fiscalized → return cached result
    if fisc_status == "fiscalized":
        return {
            "already_fiscalized":    True,
            "fiscalization_status":  "fiscalized",
            "jir":                   doc.get("jir"),
            "zki":                   doc.get("zki"),
            "fiscalized_at":         doc.get("fiscalized_at"),
            "verification_url":      doc.get("verification_url"),
            "fiscal_invoice_number": doc.get("fiscal_invoice_number"),
            "success":               True,
        }

    # Only allow triggering from pending or fiscalization_failed (retry)
    if fisc_status not in ("pending", "fiscalization_failed"):
        raise ValidationError(
            code="INVALID_FISCALIZATION_STATE",
            message=(
                f"Račun nije u stanju 'pending' ili 'fiscalization_failed'. "
                f"Trenutno stanje: {fisc_status}"
            ),
        )

    # ── Supplier identity: company_settings first, then company_config ────
    from tools.adk_tools.fiskalizacija_adk_tools import get_supplier_data
    supplier_result = await get_supplier_data(company_id=ctx.company_id)
    if supplier_result.get("success"):
        supplier      = supplier_result["supplier"]
        supplier_oib  = supplier["oib"]
        supplier_name = supplier["name"]
        business_unit = supplier["business_unit"]  # vu_code
        device_number = supplier["device_number"]   # nu_code
        supplier_addr = supplier.get("address", "")
        supplier_city = supplier.get("city", "")
    else:
        # Last-resort fallback — read partial data from the ERP doc itself
        supplier_oib  = doc.get("seller_oib", "")
        supplier_name = doc.get("seller_name", "")
        business_unit = "1"
        device_number = "1"
        supplier_addr = ""
        supplier_city = ""

    # ── Fiscal invoice number: reuse existing or generate new ─────────────
    # On retry the same FINA number must be reused (Croatian law requires
    # one FINA number per invoice).
    fiscal_invoice_number = doc.get("fiscal_invoice_number")

    if not fiscal_invoice_number:
        # Generate new sequential FINA invoice number
        try:
            import os
            from tools.api_implementations.fiskalizacija_ledger import get_ledger_service
            use_firestore = os.environ.get("USE_FIRESTORE", "true").lower() == "true"
            ledger = get_ledger_service(use_firestore=use_firestore)
            seq = ledger.get_next_invoice_number(
                supplier_oib=supplier_oib,
                business_unit=business_unit,
                device_number=device_number,
            )
            fiscal_invoice_number = f"{seq}/{business_unit}/{device_number}"
        except Exception as ledger_exc:
            logger.warning(
                f"[FiscBridge] Ledger unavailable for {invoice_id}: {ledger_exc}. "
                "Using fallback fiscal number."
            )
            from datetime import datetime as _dt
            fiscal_invoice_number = f"1/{business_unit}/{device_number}"

        # Persist fiscal_invoice_number + business/device codes BEFORE calling FINA
        # so that a retry can recover the same number even if the write-back fails.
        try:
            now_pre = datetime.now(timezone.utc).isoformat()
            await db.collection(_B2C_COL).document(invoice_id).update({
                "fiscal_invoice_number": fiscal_invoice_number,
                "business_unit":         business_unit,
                "device_number":         device_number,
                "updated_at":            now_pre,
            })
        except Exception as pre_exc:
            logger.warning(
                f"[FiscBridge] Could not persist fiscal_invoice_number "
                f"for {invoice_id}: {pre_exc} (continuing)"
            )

    # ── Map ERP invoice items → FINA fiscalization item format ────────────
    items = [
        {
            "description": it.get("name") or it.get("description", ""),
            "quantity":    float(it.get("quantity", 1)),
            "unit_price":  float(it.get("unit_price", 0)),
            "vat_rate":    float(it.get("vat_rate", 25)),
        }
        for it in (doc.get("items") or [])
    ]

    # invoice_datetime: use doc's created_at (ISO) or fallback to now
    invoice_datetime = doc.get("created_at") or datetime.now(timezone.utc).isoformat()

    invoice_payload = {
        # Bridge write-back key
        "erp_invoice_id":   invoice_id,
        "company_id":       ctx.company_id,
        # FINA-required fiscal number — NOT the ERP display_id
        "invoice_number":   fiscal_invoice_number,
        "supplier_oib":     supplier_oib,
        "supplier_name":    supplier_name,
        "supplier_address": supplier_addr,
        "supplier_city":    supplier_city,
        "customer_oib":     doc.get("customer_oib", ""),
        "customer_name":    doc.get("customer_name", ""),
        "payment_method":   payment_method,
        "invoice_datetime": invoice_datetime,
        "items":            items,
    }

    try:
        from tools.adk_tools.fiskalizacija_adk_tools import execute_fiscalization
        result = await execute_fiscalization(invoice_payload, skip_hitl=True)
    except Exception as exc:
        logger.error(
            f"[FiscBridge] fiscalize_b2c_invoice({invoice_id}) failed: {exc}"
        )
        result = {
            "success":       False,
            "status":        "execution_failed",
            "error_message": str(exc),
            "jir":           None,
            "zki":           None,
        }

    result["already_fiscalized"]    = False
    result["fiscal_invoice_number"] = fiscal_invoice_number
    return result


async def get_fiscalization_status(
    erp_invoice_id: str,
    collection: str = _B2C_COL,
) -> dict:
    """
    Return the fiscalization tracking fields for a single invoice.

    Returns {} if the document does not exist or a read error occurs.
    """
    try:
        snap = await _db().collection(collection).document(erp_invoice_id).get(
            field_paths=[
                "fiscalization_status", "fiscalized_at", "jir", "zki",
                "verification_url", "qr_code_base64", "fiscalization_error",
            ]
        )
        if not snap.exists:
            return {}
        return snap.to_dict() or {}
    except Exception as exc:
        logger.warning(f"[FiscBridge] get_fiscalization_status({erp_invoice_id}): {exc}")
        return {}

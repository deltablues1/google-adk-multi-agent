"""
ERP Vendor Invoice Service (Ulazni računi — URA)
=================================================
Manages incoming invoices from vendors with state machine enforcement.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit
)
from .errors import ValidationError, NotFoundError, DuplicateError
from .request_context import ERPRequestContext
from .state_machines import (
    VENDOR_INVOICE_DOC_TRANSITIONS, validate_transition, compute_payment_status,
    compute_fiscalization_deadline, is_fiscalization_overdue,
)
from .repositories.firestore.vendor_invoice_repo import FirestoreVendorInvoiceRepository
from .repositories.firestore.payment_repo import FirestorePaymentRepository
from .repositories.firestore.customer_repo import FirestoreCustomerRepository

logger = logging.getLogger(__name__)


class VendorInvoiceService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreVendorInvoiceRepository] = None
        self._payment_repo: Optional[FirestorePaymentRepository] = None

    def _get_repo(self) -> FirestoreVendorInvoiceRepository:
        if self._repo is None:
            self._repo = FirestoreVendorInvoiceRepository(db=self._get_db())
        return self._repo

    def _get_payment_repo(self) -> FirestorePaymentRepository:
        if self._payment_repo is None:
            self._payment_repo = FirestorePaymentRepository(db=self._get_db())
        return self._payment_repo

    async def _try_match_vendor(self, vendor_oib: str, vendor_name: str, company_id: str) -> Optional[dict]:
        """Return customer doc if vendor can be matched by OIB (exact) or name (fuzzy)."""
        repo = FirestoreCustomerRepository(db=self._get_db())
        match = await repo.find_by_oib(vendor_oib, company_id)
        if match:
            return match
        return await repo.find_by_name_fuzzy(vendor_name, company_id)

    async def get_vendor_invoice(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "vendor_invoice:read")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ulazni račun '{vendor_invoice_id}' nije pronađen."
            )
        return doc

    async def list_vendor_invoices(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 50, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "vendor_invoice:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def get_open_payables(self, ctx: ERPRequestContext) -> dict:
        """Open payables with aging."""
        from datetime import date
        check_permission(ctx, "vendor_invoice:read")
        docs = await self._get_repo().list_open_payables(ctx)
        today = date.today()
        buckets = {"current": [], "1_30": [], "31_60": [], "61_90": [], "over_90": []}
        total_due = Decimal("0")

        for doc in docs:
            amount_due = Decimal(str(doc.get("amount_due") or 0))
            total_due += amount_due
            due_str = doc.get("due_date")
            if not due_str:
                buckets["current"].append(doc)
                continue
            try:
                dd = date.fromisoformat(str(due_str)[:10])
                days = (today - dd).days
                if days <= 0:
                    buckets["current"].append(doc)
                elif days <= 30:
                    buckets["1_30"].append(doc)
                elif days <= 60:
                    buckets["31_60"].append(doc)
                elif days <= 90:
                    buckets["61_90"].append(doc)
                else:
                    buckets["over_90"].append(doc)
            except (ValueError, TypeError):
                buckets["current"].append(doc)

        return {
            "total_due_eur": float(total_due),
            "total_count": len(docs),
            "buckets": {k: {"invoices": v, "total": float(sum(
                Decimal(str(d.get("amount_due") or 0)) for d in v
            ))} for k, v in buckets.items()},
        }

    async def update_vendor_invoice(
        self, vendor_invoice_id: str, ctx: ERPRequestContext, update_data: dict
    ) -> dict:
        """Update safe fields on a vendor invoice."""
        check_permission(ctx, "vendor_invoice:create")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ulazni racun '{vendor_invoice_id}' nije pronaden."
            )
        return await self._get_repo().update(vendor_invoice_id, ctx, update_data)

    async def create_vendor_invoice(self, data: dict, ctx: ERPRequestContext) -> dict:
        """Create a new vendor invoice (manual entry or from OCR)."""
        check_permission(ctx, "vendor_invoice:create")
        # vendor_id is optional for OCR and UBL drafts — accountant assigns it via UI
        if not data.get("from_ocr") and not data.get("from_ubl") and not data.get("vendor_id"):
            raise ValidationError(code="REQUIRED_FIELD", message="vendor_id je obavezan.", field="vendor_id")
        if not data.get("total_gross") or float(data["total_gross"]) <= 0:
            raise ValidationError(code="REQUIRED_FIELD", message="total_gross mora biti > 0.", field="total_gross")

        # Dedup check: block exact duplicate invoices (same vendor + invoice_no + date + amount)
        vendor_oib = data.get("vendor_oib", "")
        vendor_invoice_no = data.get("vendor_invoice_no", "")
        if vendor_oib and vendor_invoice_no:
            dedup_hash = self._get_repo().compute_dedup_hash(
                ctx.company_id, vendor_oib, vendor_invoice_no,
                data.get("issue_date", ""), float(data.get("total_gross", 0))
            )
            existing = await self._get_repo().find_by_dedup_hash(dedup_hash, ctx.company_id)
            if existing:
                raise DuplicateError(
                    code="DUPLICATE_VENDOR_INVOICE",
                    message=(
                        f"Ulazni račun '{vendor_invoice_no}' od dobavljača OIB {vendor_oib} "
                        f"već postoji (ID: {existing['_id']})."
                    ),
                )
            data["_dedup_hash"] = dedup_hash

        display_id = await generate_display_id(ctx.company_id, "URA", self._get_db())
        data["display_id"] = display_id
        data["created_by"] = ctx.user_id

        doc = await self._get_repo().create(data, ctx)
        await write_audit("vendor_invoice_created", "vendor_invoice", doc["vendor_invoice_id"],
                          display_id, ctx, db=self._get_db())
        return doc

    async def create_from_ocr(
        self, ocr_data: dict, scan_file_id: str, ctx: ERPRequestContext
    ) -> dict:
        """
        Create a DRAFT vendor invoice from OCR output.
        AI populates fields, human confirms via UI.
        """
        check_permission(ctx, "vendor_invoice:create")
        # Map OCR category to ERP category
        cat_map = {
            "Hrana": "materials", "Prijevoz": "services",
            "Ured": "services", "Režije": "utilities", "Ostalo": "other",
        }
        erp_category = cat_map.get(ocr_data.get("expense_category", ""), "other")
        vat_raw = ocr_data.get("vat_amount") or ocr_data.get("tax_amount") or 0
        gross = float(ocr_data.get("total_amount", 0))
        vat = float(vat_raw)
        net = round(gross - vat, 2)

        vendor_oib = ocr_data.get("tax_id") or ocr_data.get("vendor_oib", "")
        vendor_name_ocr = ocr_data.get("merchant_name", "")

        # Auto-match vendor from customers collection (OIB exact → name fuzzy)
        matched = await self._try_match_vendor(vendor_oib, vendor_name_ocr, ctx.company_id)
        vendor_id = matched["_id"] if matched else ""
        vendor_name = (matched.get("name") if matched else None) or vendor_name_ocr
        vendor_match_status = "matched" if matched else "no_match"

        notes_base = (
            f"Kreirano automatski iz OCR skeniranja "
            f"(pouzdanost: {ocr_data.get('confidence_score', 0):.0%}). "
        )
        if matched:
            notes_base += f"Dobavljač automatski prepoznat: {vendor_name}."
        else:
            notes_base += "Molimo provjerite i dodijelite dobavljača."

        data = {
            "from_ocr": True,
            "document_status": "draft",
            "scan_file_id": scan_file_id,
            "ocr_data": {**ocr_data, "vendor_match": vendor_match_status},
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "vendor_oib": vendor_oib,
            "vendor_invoice_no": ocr_data.get("invoice_number") or ocr_data.get("receipt_number", ""),
            "issue_date": ocr_data.get("transaction_date", ""),
            "total_gross": gross,
            "vat_amount": vat,
            "subtotal_net": net,
            "category": erp_category,
            "due_date": ocr_data.get("due_date", ""),
            "items": ocr_data.get("items", []),
            "notes": notes_base,
        }
        return await self.create_vendor_invoice(data, ctx)

    async def create_from_ubl(
        self,
        xml_input: "str | bytes",
        ctx: ERPRequestContext,
        drive_file_id: str = "",
        drive_folder_id: str = "",
    ) -> dict:
        """
        Create a DRAFT vendor invoice from a UBL 2.1 inbound XML document.
        Runs the parser, validates buyer identity, matches vendor, deduplicates.

        Args:
            xml_input:       Raw XML string or bytes of the inbound eRačun.
            ctx:             ERP request context (company_id, user_id, …).
            drive_file_id:   Drive file_id of the original XML (for archive reference).
            drive_folder_id: Drive folder_id where the document lives.

        Returns:
            The created vendor_invoice dict (document_status='draft').
        """
        from .ubl_inbound_parser import parse_ubl_invoice

        check_permission(ctx, "vendor_invoice:create")

        # ── Sprint C0: Buyer OIB resolution from company_settings store ──
        # Uses the canonical CompanyService as the primary source.
        # Falls back to the legacy agent_registry helper (kept for backward compat).
        buyer_oib = ""
        buyer_oib_source = "not_resolved"
        try:
            from services.erp.company_service import get_company_oib as _company_get_oib
            buyer_oib = await _company_get_oib(ctx.company_id)
            if buyer_oib:
                buyer_oib_source = "company_settings"
        except Exception:
            pass

        if not buyer_oib:
            # Fallback: legacy helper (may not exist — exception is silently swallowed)
            try:
                from config.agent_registry import get_company_oib as _reg_get_oib  # noqa
                buyer_oib = _reg_get_oib(ctx.company_id)
                if buyer_oib:
                    buyer_oib_source = "agent_registry"
            except Exception:
                pass

        result = parse_ubl_invoice(xml_input, buyer_oib=buyer_oib)
        if not result["ok"]:
            raise ValidationError(
                code="UBL_PARSE_ERROR",
                message=f"UBL parser: {result['error']}",
            )

        data = result["data"]

        # Explicit buyer validation status (Sprint A.2):
        #   "validated"        — our OIB was known and matched the XML's AccountingCustomerParty
        #   "oib_not_resolved" — we could not determine our company OIB; no check performed
        #   "oib_mismatch"     — our OIB was known but did NOT match the XML (parse already
        #                         rejected this case above, so this value can't appear here;
        #                         included in the enum for completeness)
        if not buyer_oib:
            data["buyer_validation_status"] = "oib_not_resolved"
        else:
            # If we reached here with a known OIB, the parser accepted it (match OK)
            data["buyer_validation_status"] = "validated"

        # Mark as UBL draft so create_vendor_invoice() treats it like an OCR draft
        # (vendor_id is optional — accountant assigns it via UI after review).
        data["from_ubl"] = True

        # Auto-match vendor
        matched = await self._try_match_vendor(data["vendor_oib"], data["vendor_name"], ctx.company_id)
        if matched:
            data["vendor_id"] = matched["_id"]
            data["vendor_name"] = matched.get("name") or data["vendor_name"]
            data["vendor_match_status"] = "matched"
        else:
            data["vendor_id"] = ""   # accountant assigns via UI
            data["vendor_match_status"] = "no_match"

        # Archive references
        if drive_file_id:
            data["drive_original_file_id"] = drive_file_id
        if drive_folder_id:
            data["drive_folder_id"] = drive_folder_id
        data["archive_status"] = "not_archived"

        # Store original XML (truncated to 1 MB to stay within Firestore limits)
        raw = xml_input if isinstance(xml_input, str) else xml_input.decode("utf-8", errors="replace")
        data["source_ubl_xml"] = raw[:1_000_000]

        notes_parts = ["Kreirano automatski iz UBL 2.1 inbound eRačuna."]
        if matched:
            notes_parts.append(f"Dobavljač automatski prepoznat: {data['vendor_name']}.")
        else:
            notes_parts.append("Molimo provjerite i dodijelite dobavljača.")
        if data["buyer_validation_status"] == "oib_not_resolved":
            notes_parts.append("Upozorenje: OIB kupca nije provjeren — ID tvrtke nije dostupan.")
        data["notes"] = (data.get("notes") or "") + " " + " ".join(notes_parts)

        return await self.create_vendor_invoice(data, ctx)

    async def mark_received(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Transition vendor invoice from 'draft' to 'received'.
        Computes the 5-business-day fiscalization deadline per NN 89/2025."""
        check_permission(ctx, "vendor_invoice:create")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")
        validate_transition(doc["document_status"], "received", VENDOR_INVOICE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc)
        received_date = now.date()
        fiscal_deadline = compute_fiscalization_deadline(received_date)
        await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update({
            "document_status": "received",
            "received_date": now.isoformat(),
            "fiscalization_deadline": fiscal_deadline.isoformat(),
            "updated_at": now.isoformat(),
        })
        await write_audit("vendor_invoice_received", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id", ""), ctx, db=self._get_db())
        doc["document_status"] = "received"
        doc["received_date"] = now.isoformat()
        doc["fiscalization_deadline"] = fiscal_deadline.isoformat()
        return doc

    async def approve_vendor_invoice(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Transition vendor invoice from 'received' to 'approved'."""
        check_permission(ctx, "vendor_invoice:approve")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")

        validate_transition(
            doc["document_status"], "approved", VENDOR_INVOICE_DOC_TRANSITIONS
        )
        # Required fields for approval
        if not doc.get("due_date"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Datum dospijeća (due_date) mora biti postavljen prije odobravanja.",
                field="due_date"
            )

        updated = await self._get_repo().update(vendor_invoice_id, ctx, {
            "document_status": "approved",
            "approved_by": ctx.user_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })
        await write_audit("vendor_invoice_approved", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, db=self._get_db())
        return updated

    async def mark_fisc_reported(
        self, vendor_invoice_id: str, ctx: ERPRequestContext,
        fisc_confirmation_ref: str = "",
    ) -> dict:
        """
        Mark vendor invoice as fiscally reported to Porezna Uprava.
        Transition: approved -> fisc_reported.
        Per NN 89/2025, this must happen within 5 business days of received_date.
        """
        check_permission(ctx, "vendor_invoice:approve")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")
        validate_transition(doc["document_status"], "fisc_reported", VENDOR_INVOICE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "document_status": "fisc_reported",
            "fiscalization_status": "fiscalized",
            "fisc_reported_at": now,
            "fisc_reported_by": ctx.user_id,
            "updated_at": now,
        }
        if fisc_confirmation_ref:
            update_data["fisc_confirmation_ref"] = fisc_confirmation_ref
        await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update(update_data)
        await write_audit("vendor_invoice_fisc_reported", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, {"ref": fisc_confirmation_ref}, db=self._get_db())
        doc.update(update_data)
        return doc

    async def accept_vendor_invoice(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        """
        Accept a fiscally reported vendor invoice.
        Transition: fisc_reported -> accepted.
        """
        check_permission(ctx, "vendor_invoice:approve")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")
        validate_transition(doc["document_status"], "accepted", VENDOR_INVOICE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update({
            "document_status": "accepted",
            "acceptance_status": "accepted",
            "accepted_at": now,
            "accepted_by": ctx.user_id,
            "updated_at": now,
        })
        await write_audit("vendor_invoice_accepted", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, db=self._get_db())
        doc["document_status"] = "accepted"
        doc["acceptance_status"] = "accepted"
        return doc

    async def reject_vendor_invoice(
        self, vendor_invoice_id: str, rejection_reason: str, ctx: ERPRequestContext
    ) -> dict:
        """
        Reject a fiscally reported vendor invoice.
        Transition: fisc_reported -> rejected.
        rejection_reason is MANDATORY per NN 89/2025.
        """
        check_permission(ctx, "vendor_invoice:approve")
        if not rejection_reason or not rejection_reason.strip():
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Razlog odbijanja (rejection_reason) je obavezan.",
                field="rejection_reason",
            )
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")
        validate_transition(doc["document_status"], "rejected", VENDOR_INVOICE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update({
            "document_status": "rejected",
            "acceptance_status": "rejected",
            "rejection_reason": rejection_reason.strip(),
            "rejected_at": now,
            "rejected_by": ctx.user_id,
            "updated_at": now,
        })
        await write_audit("vendor_invoice_rejected", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, {"reason": rejection_reason}, db=self._get_db())
        doc["document_status"] = "rejected"
        doc["acceptance_status"] = "rejected"
        doc["rejection_reason"] = rejection_reason
        return doc

    async def archive_original_document(
        self, vendor_invoice_id: str, ctx: ERPRequestContext
    ) -> dict:
        """
        Move the original Drive document (XML or scan) into Invoices_Archive/IN/YYYY/MM/.
        Updates archive_status, archived_at, drive_folder_id on the vendor invoice.

        Safe to call multiple times — if already archived, returns current state.
        """
        from .drive_archive_service import archive_inbound_document

        check_permission(ctx, "vendor_invoice:create")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")

        if doc.get("archive_status") == "archived":
            return {"vendor_invoice_id": vendor_invoice_id, "archive_status": "archived",
                    "archived_at": doc.get("archived_at"), "drive_folder_id": doc.get("drive_folder_id"),
                    "note": "Already archived"}

        drive_file_id = doc.get("drive_original_file_id") or doc.get("scan_file_id", "")
        source_ubl_xml = doc.get("source_ubl_xml", "")

        if not drive_file_id and not source_ubl_xml:
            raise ValidationError(
                code="NO_DRIVE_FILE",
                message=(
                    "Vendor invoice nema referencu na Drive fajl niti pohranjeni UBL XML "
                    "(drive_original_file_id / scan_file_id / source_ubl_xml)."
                ),
            )

        attempts = int(doc.get("archive_attempts") or 0) + 1
        now = datetime.now(timezone.utc).isoformat()

        if drive_file_id:
            # Original path: move an existing Drive file into the archive folder
            result = await archive_inbound_document(drive_file_id, issue_date=doc.get("issue_date"))
        else:
            # Byte re-upload path: Gmail/Peppol inbound docs without a Drive source file.
            # Re-upload the stored UBL XML bytes directly into Invoices_Archive/IN/YYYY/MM/.
            from .drive_archive_service import archive_inbound_bytes
            xml_bytes = source_ubl_xml.encode("utf-8") if isinstance(source_ubl_xml, str) else source_ubl_xml
            filename = (
                doc.get("source_email_attachment_name")
                or doc.get("source_filename")
                or f"eracun_{vendor_invoice_id[:8]}.xml"
            )
            result = await archive_inbound_bytes(
                content=xml_bytes,
                filename=filename,
                issue_date=doc.get("issue_date"),
                mime_type="application/xml",
            )
            if result.get("ok"):
                # Backpatch drive_original_file_id so future calls use the move path
                await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update({
                    "drive_original_file_id": result.get("drive_file_id", ""),
                })

        # Shared handling below (original path code continues)
        now = datetime.now(timezone.utc).isoformat()

        if not result["ok"]:
            # Record failure for retry scheduler — do NOT raise so best-effort callers can continue
            await self._get_repo().update(vendor_invoice_id, ctx, {
                "archive_status": "failed",
                "archive_attempts": attempts,
                "last_archive_attempt_at": now,
                "archive_error": result["error"][:500],
            })
            raise ValidationError(code="ARCHIVE_FAILED", message=f"Drive archive neuspješan: {result['error']}")

        update = {
            "archive_status": "archived",
            "archived_at": result["archived_at"],
            "drive_folder_id": result["drive_folder_id"],
            "archive_attempts": attempts,
            "last_archive_attempt_at": now,
            "archive_error": "",
        }
        await self._get_repo().update(vendor_invoice_id, ctx, update)
        await write_audit(
            "vendor_invoice_archived", "vendor_invoice", vendor_invoice_id,
            doc.get("display_id"), ctx, {"drive_folder_id": result["drive_folder_id"]},
            db=self._get_db(),
        )
        return {"vendor_invoice_id": vendor_invoice_id, **update}

    async def retry_pending_archives(self, ctx: ERPRequestContext, max_retries: int = 3) -> dict:
        """
        Re-attempt archiving for invoices with archive_status in (not_archived, failed).
        Called by the daily archive-retry scheduler job.

        Args:
            max_retries: Skip invoices that have already failed this many times.
        Returns:
            Summary dict: {attempted, succeeded, failed, skipped}.
        """
        check_permission(ctx, "vendor_invoice:create")
        pending = await self._get_repo().list_pending_archive(ctx, limit=200)
        summary = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}

        for doc in pending:
            vid = doc.get("vendor_invoice_id") or doc.get("_id")
            attempts_so_far = int(doc.get("archive_attempts") or 0)
            if attempts_so_far >= max_retries:
                summary["skipped"] += 1
                logger.warning(f"Archive retry skipped {vid}: already {attempts_so_far} attempts")
                continue
            summary["attempted"] += 1
            try:
                await self.archive_original_document(vid, ctx)
                summary["succeeded"] += 1
            except Exception as exc:
                summary["failed"] += 1
                logger.warning(f"Archive retry failed for {vid}: {exc}")

        logger.info(f"retry_pending_archives: {summary}")
        return summary

    async def list_pending_archive(self, ctx: ERPRequestContext) -> List[dict]:
        """List invoices with a Drive file that still need archiving (archive_status failed/not_archived)."""
        check_permission(ctx, "vendor_invoice:read")
        return await self._get_repo().list_pending_archive(ctx)

    async def list_rejected_invoices(self, ctx: ERPRequestContext, limit: int = 200) -> List[dict]:
        """List rejected inbound vendor invoices (document_status=rejected)."""
        check_permission(ctx, "vendor_invoice:read")
        return await self._get_repo().list(ctx, {"document_status": "rejected"}, limit=limit)

    async def get_overdue_fiscalizations(self, ctx: ERPRequestContext) -> List[dict]:
        """
        Find vendor invoices that have exceeded their 5-business-day
        fiscalization deadline. Used for SLA monitoring/alerts.
        """
        from datetime import date as date_type
        check_permission(ctx, "vendor_invoice:read")
        # Get all approved but not yet fisc_reported invoices
        docs = await self._get_repo().list(ctx, {"document_status": "approved"}, limit=200)
        overdue = []
        today = date_type.today()
        for doc in docs:
            received_str = doc.get("received_date")
            if not received_str:
                continue
            try:
                received = date_type.fromisoformat(str(received_str)[:10])
            except (ValueError, TypeError):
                continue
            if is_fiscalization_overdue(received, doc.get("document_status", ""), today):
                doc["is_fisc_overdue"] = True
                doc["fisc_deadline"] = compute_fiscalization_deadline(received).isoformat()
                doc["days_overdue"] = (today - compute_fiscalization_deadline(received)).days
                overdue.append(doc)
        return overdue

    async def get_inbound_compliance_report(
        self, year: Optional[int], month: Optional[int], ctx: ERPRequestContext,
        export_format: str = "json",
        save_to_drive: bool = False,
    ) -> dict:
        """
        Monthly SLA compliance summary for inbound vendor invoices per NN 89/2025.

        Primary dimension: received_date (SLA clock starts on physical receipt).
        Secondary dimension: fisc_reported_at (regulatory reporting date).

        If year/month are None, defaults to current month.
        """
        import calendar
        from datetime import date as date_type

        check_permission(ctx, "vendor_invoice:read")
        today = date_type.today()
        y = year  or today.year
        m = month or today.month

        last_day = calendar.monthrange(y, m)[1]
        received_from = f"{y:04d}-{m:02d}-01"
        received_to   = f"{y:04d}-{m:02d}-{last_day:02d}"

        # Fetch all recent invoices and filter by received_date in Python.
        # Using Firestore range filter on received_date + order_by(issue_date) requires
        # a composite index. Filtering in Python avoids that index dependency and is
        # acceptable for monthly reports (≤ 500 docs per company per report run).
        all_docs = await self._get_repo().list(ctx, {}, limit=500)
        docs = [
            d for d in all_docs
            if received_from <= str(d.get("received_date") or "")[:10] <= received_to
        ]

        statuses = ["draft", "received", "approved", "fisc_reported", "accepted", "rejected", "disputed", "cancelled"]
        counts: dict[str, int] = {s: 0 for s in statuses}
        totals: dict[str, float] = {s: 0.0 for s in statuses}
        overdue_count = 0
        archived_count = 0
        fisc_reported_in_month = 0

        for doc in docs:
            st = doc.get("document_status", "draft")
            counts[st] = counts.get(st, 0) + 1
            totals[st] = totals.get(st, 0.0) + float(doc.get("total_gross") or 0)
            if doc.get("archive_status") == "archived":
                archived_count += 1
            # SLA: did this invoice miss the 5-business-day fiscalization window?
            received_str = doc.get("received_date")
            if received_str:
                try:
                    received = date_type.fromisoformat(str(received_str)[:10])
                    if is_fiscalization_overdue(received, st, today):
                        overdue_count += 1
                except (ValueError, TypeError):
                    pass
            # Regulatory: how many were fiscally reported this month?
            fisc_at = doc.get("fisc_reported_at", "")
            if fisc_at and fisc_at[:7] == f"{y:04d}-{m:02d}":
                fisc_reported_in_month += 1

        report = {
            "period": f"{y:04d}-{m:02d}",
            "period_basis": "received_date",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_invoices_received": len(docs),
            "total_gross_eur": round(sum(totals.values()), 2),
            "by_status": {
                s: {"count": counts[s], "total_gross_eur": round(totals[s], 2)}
                for s in statuses if counts[s] > 0
            },
            # SLA metrics (NN 89/2025: 5 business days from received_date)
            "overdue_fiscalization_count": overdue_count,
            "sla_compliant": overdue_count == 0,
            # Regulatory metrics
            "fisc_reported_this_period": fisc_reported_in_month,
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            # Archive
            "archived_count": archived_count,
            "not_archived_count": len(docs) - archived_count,
        }

        # Drive upload always happens first (before any format conversion)
        if save_to_drive:
            drive_file_id = await self._save_compliance_report_to_drive(report, ctx)
            if drive_file_id:
                report["drive_file_id"] = drive_file_id

        if export_format == "csv":
            return self._compliance_report_to_csv_response(report)

        return report

    @staticmethod
    def _compliance_report_to_csv_response(report: dict):
        """Convert compliance report dict to CSV plain-text response."""
        import io, csv
        from fastapi.responses import PlainTextResponse

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["period", "period_basis", "generated_at",
                    "total_invoices_received", "total_gross_eur",
                    "overdue_fiscalization_count", "sla_compliant",
                    "fisc_reported_this_period",
                    "accepted_count", "rejected_count",
                    "archived_count", "not_archived_count"])
        w.writerow([
            report["period"], report["period_basis"], report["generated_at"],
            report["total_invoices_received"], report["total_gross_eur"],
            report["overdue_fiscalization_count"], report["sla_compliant"],
            report["fisc_reported_this_period"],
            report["accepted_count"], report["rejected_count"],
            report["archived_count"], report["not_archived_count"],
        ])
        # Append by_status breakdown
        w.writerow([])
        w.writerow(["status", "count", "total_gross_eur"])
        for status, vals in report.get("by_status", {}).items():
            w.writerow([status, vals["count"], vals["total_gross_eur"]])

        csv_text = buf.getvalue()
        filename = f"inbound_compliance_{report['period']}.csv"
        return PlainTextResponse(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def _save_compliance_report_to_drive(self, report: dict, ctx: ERPRequestContext) -> Optional[str]:
        """Upload JSON compliance report to Reports_Output/ERP/ on Drive. Returns Drive file_id or None."""
        import json
        try:
            from tools.drive_navigator import get_drive_navigator
            from tools.api_implementations.drive_api import drive_upload_file
            from tools.google_api_client import create_api_client_auto

            nav = await get_drive_navigator()
            folder_id = nav.get_folder_id("reports_erp")
            if not folder_id:
                logger.warning("reports_erp folder not resolved — skipping Drive export")
                return None

            credentials = create_api_client_auto().credentials
            period = report["period"]
            filename = f"inbound_compliance_{period}.json"
            content = json.dumps(report, ensure_ascii=False, indent=2)

            result = await drive_upload_file(
                credentials=credentials,
                file_name=filename,
                content=content,
                mime_type="application/json",
                parent_folder_id=folder_id,
            )
            file_id = result.get("id", "")
            logger.info(f"Compliance report uploaded to Drive: {filename} ({file_id})")
            return file_id
        except Exception as exc:
            logger.warning(f"Drive compliance report upload failed: {exc}")
            return None

    async def record_payment(
        self,
        vendor_invoice_id: str,
        amount: Decimal,
        payment_date: str,
        payment_method: str,
        reference: str,
        ctx: ERPRequestContext,
        idempotency_key: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """Record outgoing payment for a vendor invoice."""
        check_permission(ctx, "payment:record")

        idem_key = idempotency_key or str(uuid4())
        payment_repo = self._get_payment_repo()

        if await payment_repo.key_exists(idem_key, ctx.company_id):
            raise DuplicateError(code="DUPLICATE", message="Duplikat uplate odbijen.")

        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message="URA nije pronađen.")
        if doc["document_status"] not in ("approved", "partial_paid", "fisc_reported", "accepted"):
            raise ValidationError(
                code="WRONG_STATUS",
                message=f"Plaćanje moguće samo za odobren ili fiskaliz. prijavljeni račun. Trenutni status: {doc['document_status']}.",
            )

        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amount_due = Decimal(str(doc.get("amount_due") or 0))
        if amount > amount_due:
            raise ValidationError(
                code="OVERPAYMENT",
                message=f"Iznos {amount} EUR premašuje dugovanje {amount_due:.2f} EUR.",
                field="amount",
            )

        total_gross = Decimal(str(doc.get("total_gross") or 0))
        new_amount_paid = Decimal(str(doc.get("amount_paid") or 0)) + amount
        new_amount_due = total_gross - new_amount_paid
        new_payment_status = compute_payment_status(new_amount_paid, total_gross)

        payment_id = str(uuid4())
        from .base_erp_service import generate_display_id
        display_id = await generate_display_id(ctx.company_id, "PAY", self._get_db())

        db = self._get_db()
        batch = db.batch()

        payment_doc = {
            "payment_id": payment_id, "display_id": display_id,
            "company_id": ctx.company_id, "type": "outgoing",
            "party_id": doc.get("vendor_id", ""),
            "party_name": doc.get("vendor_name", ""),
            "invoice_ref_id": vendor_invoice_id,
            "invoice_ref_type": "vendor",
            "invoice_ref_display": doc.get("display_id", ""),
            "amount": float(amount), "currency": "EUR",
            "payment_date": payment_date, "payment_method": payment_method,
            "reference": reference, "status": "confirmed", "notes": notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": ctx.user_id, "reconciled": False, "reconciled_at": None,
            "idempotency_key": idem_key,
        }
        batch.set(db.collection("payments").document(payment_id), payment_doc)

        alloc_id = str(uuid4())
        batch.set(db.collection("payment_allocations").document(alloc_id), {
            "allocation_id": alloc_id, "company_id": ctx.company_id,
            "payment_id": payment_id, "invoice_id": vendor_invoice_id,
            "invoice_type": "vendor", "display_id": doc.get("display_id", ""),
            "amount": float(amount),
            "allocated_at": datetime.now(timezone.utc).isoformat(),
            "allocated_by": ctx.user_id,
        })

        batch.update(db.collection("vendor_invoices").document(vendor_invoice_id), {
            "amount_paid": float(new_amount_paid),
            "amount_due": float(new_amount_due),
            "payment_status": new_payment_status,
        })
        await batch.commit()

        await write_audit("vendor_payment_recorded", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, {"amount": float(amount)}, db)
        return {
            "payment_id": payment_id, "display_id": display_id,
            "amount": float(amount), "new_payment_status": new_payment_status,
            "amount_due_after": float(new_amount_due),
        }


_vendor_invoice_service_instance: Optional[VendorInvoiceService] = None


def get_vendor_invoice_service() -> VendorInvoiceService:
    global _vendor_invoice_service_instance
    if _vendor_invoice_service_instance is None:
        _vendor_invoice_service_instance = VendorInvoiceService()
    return _vendor_invoice_service_instance

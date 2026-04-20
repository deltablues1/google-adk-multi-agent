"""
Company Settings Service (Sprint C0)
=====================================
Manages per-company configuration stored in the Firestore `company_settings` collection.

This is the canonical source of truth for company identity data (OIB, name, IBAN, etc.)
used across the ERP and fiscalization subsystems.

Collection: company_settings
Document ID: company_id (same as ERPRequestContext.company_id)

Schema (all optional except company_id):
    company_id             str   — Firestore document key (mirrors field)
    oib                    str   — 11-digit Croatian OIB of the company (issuer)
    name                   str   — Legal company name
    address                str   — Street address
    city                   str   — City
    postal_code            str   — Croatian postal code (5 digits)
    country                str   — ISO 3166-1 alpha-2 (default "HR")
    iban                   str   — IBAN for payment instructions on invoices
    vat_registered         bool  — True if company is in VAT system
    vu_code                str   — Poslovni prostor code for fiscalization
    nu_code                str   — Naplatni uređaj code for fiscalization
    peppol_participant_id  str   — Peppol endpoint ID (e.g. "0190:47034854402")
    peppol_scheme          str   — Peppol scheme code (default "0190" = HR OIB)
    created_at             str   — ISO timestamp
    updated_at             str   — ISO timestamp
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from services.erp.base_erp_service import check_permission, write_audit, get_firestore_db
from services.erp.errors import NotFoundError, ValidationError
from services.erp.request_context import ERPRequestContext

logger = logging.getLogger(__name__)

_COL = "company_settings"


def _validate_iban(iban: str) -> bool:
    """
    Validate IBAN format.

    For Croatian IBANs: must be "HR" + 19 digits (21 chars total).
    For other EU IBANs: must be 2 alpha + 2 check digits + alphanumeric BBAN,
    total 15-34 chars.  Performs MOD-97 check digit validation.
    """
    if not iban or len(iban) < 5:
        return False
    country = iban[:2]
    if not country.isalpha():
        return False
    if not iban[2:].isalnum():
        return False
    if country == "HR" and len(iban) != 21:
        return False
    if len(iban) > 34:
        return False
    # MOD-97 check
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1


# ---------------------------------------------------------------------------
# Public helpers (used by other services without a full request context)
# ---------------------------------------------------------------------------

async def get_company_oib(company_id: str) -> str:
    """
    Return the OIB for company_id, or empty string if not configured.

    This is the canonical source used by:
    - VendorInvoiceService.create_from_ubl() for buyer OIB validation
    - Fiscalization tools for supplier_oib resolution
    """
    try:
        db = get_firestore_db()
        snap = await db.collection(_COL).document(company_id).get(field_paths=["oib"])
        if not snap.exists:
            return ""
        return (snap.to_dict() or {}).get("oib", "")
    except Exception as exc:
        logger.warning(f"[CompanyService] get_company_oib({company_id}) failed: {exc}")
        return ""


async def get_company_settings(company_id: str) -> dict:
    """
    Return all settings for company_id.  Returns {} if not found.
    Does NOT raise — callers must handle the empty-dict case.
    """
    try:
        db = get_firestore_db()
        snap = await db.collection(_COL).document(company_id).get()
        if not snap.exists:
            return {}
        d = snap.to_dict() or {}
        d["_id"] = snap.id
        return d
    except Exception as exc:
        logger.warning(f"[CompanyService] get_company_settings({company_id}) failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Service class (used by ERP routes)
# ---------------------------------------------------------------------------

class CompanyService:
    """CRUD for company_settings collection."""

    def _get_db(self):
        return get_firestore_db()

    async def _assert_peppol_id_unique(self, peppol_participant_id: str, exclude_company_id: str) -> None:
        """
        Raise ValidationError if ``peppol_participant_id`` is already registered
        by a different company.  Empty string is always allowed (means "not set").
        """
        if not peppol_participant_id:
            return
        db = self._get_db()
        query = (
            db.collection(_COL)
            .where(filter=FieldFilter("peppol_participant_id", "==", peppol_participant_id))
            .limit(2)
        )
        async for snap in query.stream():
            if snap.id != exclude_company_id:
                raise ValidationError(
                    code="PEPPOL_ID_CONFLICT",
                    message=(
                        f"Peppol participant ID '{peppol_participant_id}' već je registriran "
                        "za drugu tvrtku. Svaka tvrtka mora imati jedinstven Peppol ID."
                    ),
                    field="peppol_participant_id",
                )

    async def get(self, ctx: ERPRequestContext) -> dict:
        """Return this company's settings.  404 if not configured yet."""
        check_permission(ctx, "company:read")
        snap = await self._get_db().collection(_COL).document(ctx.company_id).get()
        if not snap.exists:
            raise NotFoundError(
                code="COMPANY_NOT_CONFIGURED",
                message="Postavke tvrtke još nisu konfigurirane. Koristite PUT za inicijalizaciju.",
            )
        d = snap.to_dict() or {}
        d["_id"] = snap.id
        return d

    async def upsert(self, data: dict, ctx: ERPRequestContext) -> dict:
        """
        Create or fully replace company settings.

        Validates OIB format if provided.  Sets company_id, created_at/updated_at.
        """
        check_permission(ctx, "company:write")

        oib = (data.get("oib") or "").strip()
        if oib and (not oib.isdigit() or len(oib) != 11):
            raise ValidationError(
                code="INVALID_OIB",
                message="OIB mora biti točno 11 znamenki.",
                field="oib",
            )

        iban = (data.get("iban") or "").strip().upper().replace(" ", "")
        if iban and not _validate_iban(iban):
            raise ValidationError(
                code="INVALID_IBAN",
                message="IBAN nije u ispravnom formatu. Hrvatski IBAN: HR + 19 znamenki (ukupno 21 znak).",
                field="iban",
            )
        if iban:
            data["iban"] = iban  # store normalized (uppercase, no spaces)

        peppol_id = (data.get("peppol_participant_id") or "").strip()
        await self._assert_peppol_id_unique(peppol_id, exclude_company_id=ctx.company_id)

        now = datetime.now(timezone.utc).isoformat()
        db = self._get_db()

        snap = await db.collection(_COL).document(ctx.company_id).get(field_paths=["created_at"])
        existing_created_at = (snap.to_dict() or {}).get("created_at") if snap.exists else None

        doc = {
            "company_id":            ctx.company_id,
            "oib":                   oib,
            "name":                  (data.get("name") or "").strip(),
            "address":               (data.get("address") or "").strip(),
            "city":                  (data.get("city") or "").strip(),
            "postal_code":           (data.get("postal_code") or "").strip(),
            "country":               (data.get("country") or "HR").strip(),
            "iban":                  (data.get("iban") or "").strip(),
            "vat_registered":        bool(data.get("vat_registered", True)),
            "vu_code":               (data.get("vu_code") or "").strip(),
            "nu_code":               (data.get("nu_code") or "").strip(),
            "peppol_participant_id": (data.get("peppol_participant_id") or "").strip(),
            "peppol_scheme":         (data.get("peppol_scheme") or "0190").strip(),
            "created_at":            existing_created_at or now,
            "updated_at":            now,
        }

        await db.collection(_COL).document(ctx.company_id).set(doc)
        await write_audit(
            "company_settings_upserted", "company_settings", ctx.company_id,
            doc.get("name") or ctx.company_id, ctx, db=db,
        )
        doc["_id"] = ctx.company_id
        return doc

    async def patch(self, data: dict, ctx: ERPRequestContext) -> dict:
        """
        Partial update — only provided keys are written.
        OIB is validated if included.
        """
        check_permission(ctx, "company:write")

        if "oib" in data:
            oib = (data["oib"] or "").strip()
            if oib and (not oib.isdigit() or len(oib) != 11):
                raise ValidationError(
                    code="INVALID_OIB",
                    message="OIB mora biti točno 11 znamenki.",
                    field="oib",
                )
            data["oib"] = oib

        if "iban" in data:
            iban = (data["iban"] or "").strip().upper().replace(" ", "")
            if iban and not _validate_iban(iban):
                raise ValidationError(
                    code="INVALID_IBAN",
                    message="IBAN nije u ispravnom formatu. Hrvatski IBAN: HR + 19 znamenki (ukupno 21 znak).",
                    field="iban",
                )
            data["iban"] = iban

        if "peppol_participant_id" in data:
            peppol_id = (data["peppol_participant_id"] or "").strip()
            data["peppol_participant_id"] = peppol_id
            await self._assert_peppol_id_unique(peppol_id, exclude_company_id=ctx.company_id)

        now = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = now

        db = self._get_db()
        snap = await db.collection(_COL).document(ctx.company_id).get()
        if not snap.exists:
            raise NotFoundError(
                code="COMPANY_NOT_CONFIGURED",
                message="Postavke tvrtke nisu pronađene. Koristite PUT za inicijalizaciju.",
            )

        await db.collection(_COL).document(ctx.company_id).update(data)
        await write_audit(
            "company_settings_patched", "company_settings", ctx.company_id,
            ctx.company_id, ctx, data={"fields": list(data.keys())}, db=db,
        )
        return await self.get(ctx)


_company_service_instance: Optional[CompanyService] = None


def get_company_service() -> CompanyService:
    global _company_service_instance
    if _company_service_instance is None:
        _company_service_instance = CompanyService()
    return _company_service_instance

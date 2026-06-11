"""
Outbound B2B Archive Service (Faza 2C)
=======================================
Stateless module for archiving outbound B2B invoices to Google Drive.

Archive path  : Invoices_Archive/OUT/b2b/YYYY/MM/   (Drive alias: archive_out_b2b)
Archive files :
  {display_id}_ubl.xml    — UBL 2.1 XML (from Firestore doc["ubl_xml"])
  {display_id}_meta.json  — status snapshot at archive time
  {display_id}_render.pdf — human-readable PDF (best-effort; PDF failure does not block archive)

Firestore collection: invoices_b2b

Public API
----------
  archive_outbound_document(invoice_id, ctx)   → dict (full doc after archive)
  list_pending_outbound_archive(ctx, limit=200) → List[dict]
  retry_outbound_archive(ctx, max_attempts=3)  → dict summary
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

from services.erp.base_erp_service import (
    check_permission, write_audit, get_firestore_db,
)
from services.erp.errors import ValidationError, NotFoundError
from services.erp.request_context import ERPRequestContext

logger = logging.getLogger(__name__)

_COL = "invoices_b2b"

# Statuses that are eligible for archiving (must have a generated UBL)
_ARCHIVE_ELIGIBLE_STATUSES = {"issued", "eracun_sent", "delivered", "accepted", "rejected"}


# ---------------------------------------------------------------------------
# Meta JSON builder
# ---------------------------------------------------------------------------

def _build_meta_json(doc: dict, archived_at: str, pdf_file_id: str | None = None) -> bytes:
    """
    Build a status-snapshot JSON for Drive archive.

    Schema version 2 — adds archive_pdf_file_id (None when PDF render failed).
    """
    meta = {
        "schema_version":        2,
        "invoice_id":            doc.get("invoice_id"),
        "display_id":            doc.get("display_id"),
        "document_status":       doc.get("document_status"),
        "delivery_method":       doc.get("delivery_method"),
        "delivery_target":       doc.get("delivery_target"),
        "external_submission_id": doc.get("external_submission_id"),
        "external_status":       doc.get("external_status"),
        "sent_at":               doc.get("sent_at"),
        "delivered_at":          doc.get("delivered_at"),
        "accepted_at":           doc.get("accepted_at"),
        "rejected_at":           doc.get("rejected_at"),
        "archived_at":           archived_at,
        "send_attempts":         doc.get("send_attempts", 0),
        "archive_pdf_file_id":   pdf_file_id,
    }
    return json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Drive helpers (module-level, mockable in tests)
# ---------------------------------------------------------------------------

async def _get_or_create_folder(credentials, name: str, parent_id: str) -> str:
    """Find a Drive folder by name + parent, or create it."""
    from tools.api_implementations.drive_api import drive_search_files, drive_create_folder
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
        f" and trashed = false and '{parent_id}' in parents"
    )
    result = await drive_search_files(credentials, query)
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    folder = await drive_create_folder(credentials, name, parent_folder_id=parent_id)
    return folder["id"]


async def _upload_bytes_to_drive(
    credentials,
    filename: str,
    content: bytes,
    folder_id: str,
    mimetype: str = "application/octet-stream",
) -> dict:
    """Upload raw bytes to Drive as a new file. Returns {"id": ..., "name": ..., ...}."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaInMemoryUpload
    import asyncio

    def _sync_upload():
        service = build("drive", "v3", credentials=credentials)
        metadata = {
            "name":     filename,
            "parents":  [folder_id],
            "mimeType": mimetype,
        }
        media = MediaInMemoryUpload(content, mimetype=mimetype, resumable=False)
        return service.files().create(
            body=metadata, media_body=media, fields="id,name,webViewLink"
        ).execute()

    return await asyncio.get_event_loop().run_in_executor(None, _sync_upload)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

async def archive_outbound_document(
    invoice_id: str,
    ctx: ERPRequestContext,
) -> dict:
    """
    Archive an outbound B2B invoice to Google Drive.

    Steps:
      1. Load doc from Firestore.
      2. Idempotent: if already archived, return current doc.
      3. Validate ubl_xml present.
      4. Resolve Drive folder Invoices_Archive/OUT/b2b/YYYY/MM/.
      5. Upload {display_id}_ubl.xml and {display_id}_meta.json.
      6. Update Firestore with archive tracking fields.
      7. Write audit.

    On Drive/network failure: sets archive_status="failed", raises ValidationError.
    """
    check_permission(ctx, "outbound:archive")
    db = get_firestore_db()

    snap = await db.collection(_COL).document(invoice_id).get()
    if not snap.exists:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    doc = snap.to_dict() or {}
    doc["_id"] = invoice_id

    if doc.get("company_id") != ctx.company_id:
        raise NotFoundError(f"Invoice {invoice_id} not found")

    # Idempotent — return current state (minus heavy ubl_xml blob)
    if doc.get("archive_status") == "archived":
        doc.pop("ubl_xml", None)
        return doc

    # Must have UBL XML to archive
    if not doc.get("ubl_xml"):
        raise ValidationError(
            code="UBL_NOT_GENERATED",
            message="UBL XML nije generiran — pozovite /issue prije arhiviranja.",
        )

    now       = datetime.now(timezone.utc).isoformat()
    attempts  = int(doc.get("archive_attempts") or 0) + 1
    display_id = doc.get("display_id") or invoice_id

    ubl_bytes     = (doc.get("ubl_xml") or "").encode("utf-8")
    ubl_filename  = f"{display_id}_ubl.xml"
    meta_filename = f"{display_id}_meta.json"

    try:
        from tools.drive_navigator import get_drive_navigator
        from tools.google_api_client import create_api_client_auto

        nav = await get_drive_navigator()
        b2b_root_id = nav.get_folder_id("archive_out_b2b")
        if not b2b_root_id:
            raise RuntimeError(
                "archive_out_b2b folder not resolved — run ensure_structure() first"
            )

        # YYYY/MM subfolder from issue_date
        issue_date_str = doc.get("issue_date", "")
        try:
            dt = datetime.strptime(issue_date_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)

        year_str  = str(dt.year)
        month_str = f"{dt.month:02d}"

        credentials = create_api_client_auto().credentials

        year_folder_id  = await _get_or_create_folder(credentials, year_str,  b2b_root_id)
        month_folder_id = await _get_or_create_folder(credentials, month_str, year_folder_id)

        ubl_file  = await _upload_bytes_to_drive(
            credentials, ubl_filename,  ubl_bytes,  month_folder_id, "text/xml"
        )

        # Best-effort PDF render — failure does NOT block archive
        pdf_file_id: str | None = None
        try:
            from services.erp.outbound_pdf_renderer import render_invoice_pdf
            pdf_bytes = render_invoice_pdf(doc)
            pdf_file  = await _upload_bytes_to_drive(
                credentials,
                f"{display_id}_render.pdf",
                pdf_bytes,
                month_folder_id,
                "application/pdf",
            )
            pdf_file_id = pdf_file.get("id") or None
        except Exception as pdf_exc:
            logger.warning(
                f"[OutboundArchive] PDF render/upload failed for {display_id} "
                f"(non-blocking): {pdf_exc}"
            )

        meta_bytes = _build_meta_json(doc, archived_at=now, pdf_file_id=pdf_file_id)
        meta_file = await _upload_bytes_to_drive(
            credentials, meta_filename, meta_bytes, month_folder_id, "application/json"
        )

        ubl_file_id  = ubl_file.get("id", "")
        meta_file_id = meta_file.get("id", "")

        update = {
            "archive_status":          "archived",
            "archive_attempts":        attempts,
            "last_archive_attempt_at": now,
            "archived_at":             now,
            "archive_folder_id":       month_folder_id,
            "archive_drive_file_id":   ubl_file_id,   # backward-compat alias
            "archive_ubl_file_id":     ubl_file_id,
            "archive_meta_file_id":    meta_file_id,
            "archive_pdf_file_id":     pdf_file_id,
            "archive_error":           None,
            "updated_at":              now,
        }

        await db.collection(_COL).document(invoice_id).update(update)
        await write_audit(
            "outbound_b2b.archived", "outbound_b2b", invoice_id, display_id, ctx,
            data={
                "archive_folder_id": month_folder_id,
                "ubl_file_id":       ubl_file_id,
                "meta_file_id":      meta_file_id,
                "pdf_file_id":       pdf_file_id,
            },
            db=db,
        )

        logger.info(
            f"[OutboundArchive] Archived {display_id} → "
            f"archive_out_b2b/{year_str}/{month_str} "
            f"(ubl={ubl_file_id}, meta={meta_file_id}, pdf={pdf_file_id or 'none'})"
        )

        # Return doc with updated archive fields (no ubl_xml blob)
        result = {**doc, **update, "invoice_id": invoice_id}
        result.pop("ubl_xml", None)
        return result

    except ValidationError:
        raise
    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.error(f"[OutboundArchive] Failed to archive {display_id}: {exc}")

        fail_update = {
            "archive_status":          "failed",
            "archive_attempts":        attempts,
            "last_archive_attempt_at": now,
            "archive_error":           error_msg,
            "updated_at":              now,
        }
        await db.collection(_COL).document(invoice_id).update(fail_update)

        raise ValidationError(
            code="ARCHIVE_FAILED",
            message=f"Arhiviranje nije uspjelo: {error_msg}",
        )


async def list_pending_outbound_archive(
    ctx: ERPRequestContext,
    limit: int = 200,
) -> List[dict]:
    """
    Return outbound B2B invoices that:
      - are in an archive-eligible status (issued/eracun_sent/delivered/accepted/rejected)
      - have ubl_xml present
      - have archive_status != "archived"

    ubl_xml is stripped from the response.
    """
    check_permission(ctx, "outbound:read")
    from google.cloud.firestore_v1.base_query import FieldFilter

    db = get_firestore_db()
    query = (
        db.collection(_COL)
        .where(filter=FieldFilter("company_id", "==", ctx.company_id))
        .where(filter=FieldFilter("deleted",    "==", False))
        .limit(limit)
    )

    docs = []
    async for snap in query.stream():
        doc = snap.to_dict() or {}
        # Python-side filters (avoid composite Firestore indexes)
        if doc.get("document_status") not in _ARCHIVE_ELIGIBLE_STATUSES:
            continue
        if doc.get("archive_status") == "archived":
            continue
        if not doc.get("ubl_xml"):
            continue
        doc["_id"] = snap.id
        doc.pop("ubl_xml", None)
        docs.append(doc)

    docs.sort(key=lambda d: d.get("issue_date") or "", reverse=True)
    return docs


async def retry_outbound_archive(
    ctx: ERPRequestContext,
    max_attempts: int = 3,
) -> dict:
    """
    Retry archiving for all pending-archive invoices where
    archive_attempts < max_attempts.

    Returns {"attempted": N, "succeeded": N, "failed": N, "skipped": N}.
    """
    check_permission(ctx, "outbound:archive")
    candidates = await list_pending_outbound_archive(ctx)

    attempted = succeeded = failed = skipped = 0
    for doc in candidates:
        if int(doc.get("archive_attempts") or 0) >= max_attempts:
            skipped += 1
            continue

        attempted += 1
        invoice_id = doc.get("invoice_id") or doc.get("_id")
        try:
            await archive_outbound_document(invoice_id, ctx)
            succeeded += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                f"[OutboundArchive] retry failed for {doc.get('display_id')}: {exc}"
            )

    return {"attempted": attempted, "succeeded": succeeded, "failed": failed, "skipped": skipped}

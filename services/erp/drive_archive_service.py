"""
Drive Archive Service
=====================
Handles moving inbound vendor invoice source documents (XML, PDF scans) from
the intake folder (Vendor_Invoices_Input) into the canonical archive hierarchy:

    Invoices_Archive/IN/YYYY/MM/

After a successful move:
  - vendor_invoice.archive_status  → "archived"
  - vendor_invoice.archived_at     → ISO timestamp
  - vendor_invoice.drive_folder_id → target archive folder ID

Used by VendorInvoiceService.archive_original_document() and called from
monitor_drive_invoices after a successful UBL or OCR inbound save.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from tools.google_api_client import create_api_client_auto
from tools.api_implementations.drive_api import drive_move_file, drive_create_folder, drive_search_files

logger = logging.getLogger(__name__)

# Alias for the root of inbound archive (Invoices_Archive/IN)
_ARCHIVE_IN_ALIAS = "archive_in"


async def _get_or_create_folder(credentials, name: str, parent_id: str) -> str:
    """Find folder by name+parent or create it."""
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


async def archive_inbound_document(
    drive_file_id: str,
    issue_date: Optional[str] = None,
) -> dict:
    """
    Move a Drive file into Invoices_Archive/IN/YYYY/MM/ and return archive metadata.

    Args:
        drive_file_id:  Drive file_id of the document to archive.
        issue_date:     YYYY-MM-DD string used to determine the YYYY/MM subfolder.
                        Falls back to today's date if not provided or invalid.

    Returns:
        {
            "ok": True,
            "drive_folder_id": "<target folder id>",
            "archived_at": "<ISO timestamp>",
        }
        or
        {
            "ok": False,
            "error": "<message>",
        }
    """
    from tools.drive_navigator import get_drive_navigator

    try:
        # Resolve archive_in root
        nav = await get_drive_navigator()
        archive_in_id = nav.get_folder_id(_ARCHIVE_IN_ALIAS)
        if not archive_in_id:
            return {"ok": False, "error": "archive_in folder not resolved — run ensure_structure() first"}

        # Determine YYYY/MM from issue_date
        try:
            dt = datetime.strptime(issue_date[:10], "%Y-%m-%d") if issue_date else None
        except (ValueError, TypeError):
            dt = None
        if dt is None:
            dt = datetime.now(timezone.utc)

        year_str  = str(dt.year)
        month_str = f"{dt.month:02d}"

        credentials = create_api_client_auto().credentials

        # Get or create YYYY subfolder under archive_in
        year_folder_id  = await _get_or_create_folder(credentials, year_str, archive_in_id)
        # Get or create MM subfolder under YYYY
        month_folder_id = await _get_or_create_folder(credentials, month_str, year_folder_id)

        # Move the file
        await drive_move_file(credentials, drive_file_id, month_folder_id)

        archived_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"Archived Drive file {drive_file_id} → archive_in/{year_str}/{month_str} "
            f"(folder {month_folder_id})"
        )
        return {
            "ok": True,
            "drive_folder_id": month_folder_id,
            "archived_at": archived_at,
        }

    except Exception as exc:
        logger.error(f"archive_inbound_document failed for {drive_file_id}: {exc}")
        return {"ok": False, "error": str(exc)}

"""End-to-end smoke test for all Google Workspace integrations.

Touches every service with a minimal real operation and prints PASS/FAIL
per service. Read-only everywhere except Docs (creates one doc, then
deletes it via Drive).

Also exercises the aexecute() async layer end-to-end, and reports OAuth
token health (refresh-token expiry is the #1 silent killer when the OAuth
consent screen is in "Testing" mode — tokens then die after 7 days).

Usage:
    python scripts/google_smoke_test.py
"""

import asyncio
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

RESULTS: list[tuple[str, str, str]] = []  # (service, status, detail)


def record(service: str, status: str, detail: str = ""):
    RESULTS.append((service, status, detail))
    mark = {"PASS": "[OK]  ", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print(f"  {mark} {service:<12} {detail[:100]}")


async def run_check(service: str, coro_factory):
    start = time.monotonic()
    try:
        detail = await coro_factory()
        elapsed = time.monotonic() - start
        record(service, "PASS", f"({elapsed:.1f}s) {detail}")
    except Exception as e:
        record(service, "FAIL", f"{type(e).__name__}: {str(e)[:150]}")


async def main():
    print("=== Google Workspace Smoke Test ===\n")

    # --- OAuth health -------------------------------------------------------
    from auth.oauth_manager import get_oauth_manager
    manager = get_oauth_manager()
    health = manager.get_auth_health_status()
    creds = manager.get_credentials()
    print(f"OAuth status : {health.get('status')} ({health.get('reason', '-')})")
    print(f"Token path   : {health.get('token_path')}")
    if creds is None:
        print("\nNo valid credentials — run: python scripts/force_oauth_login.py")
        record("oauth", "FAIL", health.get("reason", "no credentials"))
        return
    record("oauth", "PASS", f"status={health.get('status')}")
    print()

    from tools.api_implementations.gmail_api import gmail_search_threads
    from tools.api_implementations.drive_api import (
        drive_search_files, drive_delete_file,
    )
    from tools.api_implementations.docs_api import docs_create_document
    from tools.api_implementations.sheets_api import sheets_get_spreadsheet
    from tools.api_implementations.calendar_api import calendar_list_events
    from tools.api_implementations.tasks_api import tasks_list_task_lists
    from tools.api_implementations.contacts_api import contacts_list_contacts

    # --- Gmail --------------------------------------------------------------
    async def check_gmail():
        result = await gmail_search_threads(creds, query="in:inbox", max_results=1)
        n = result.get("result_size_estimate", 0)
        return f"inbox reachable, ~{n} threads"
    await run_check("gmail", check_gmail)

    # --- Drive --------------------------------------------------------------
    async def check_drive():
        result = await drive_search_files(creds, query="trashed = false", max_results=3)
        files = result.get("files", result if isinstance(result, list) else [])
        return f"{len(files)} files listed"
    await run_check("drive", check_drive)

    # --- Docs (create + cleanup) ---------------------------------------------
    async def check_docs():
        doc = await docs_create_document(creds, title="__smoke_test_delete_me__")
        doc_id = doc.get("document_id") or doc.get("documentId") or doc.get("id")
        if not doc_id:
            raise RuntimeError(f"create returned no id: {str(doc)[:120]}")
        await drive_delete_file(creds, file_id=doc_id)
        return f"created + deleted doc {doc_id[:12]}…"
    await run_check("docs", check_docs)

    # --- Sheets (read an existing spreadsheet if any) -------------------------
    async def check_sheets():
        found = await drive_search_files(
            creds,
            query="mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false",
            max_results=1,
        )
        files = found.get("files", found if isinstance(found, list) else [])
        if not files:
            return "no spreadsheets in Drive (nothing to read) — API reachable"
        sid = files[0].get("id")
        meta = await sheets_get_spreadsheet(creds, spreadsheet_id=sid)
        title = (meta.get("properties") or {}).get("title") or meta.get("title", "?")
        return f"read spreadsheet '{title}'"
    await run_check("sheets", check_sheets)

    # --- Calendar -------------------------------------------------------------
    async def check_calendar():
        result = await calendar_list_events(creds, calendar_id="primary", max_results=3)
        events = result.get("events", result if isinstance(result, list) else [])
        return f"{len(events)} upcoming events"
    await run_check("calendar", check_calendar)

    # --- Tasks ----------------------------------------------------------------
    async def check_tasks():
        result = await tasks_list_task_lists(creds, max_results=5)
        lists_ = result.get("task_lists", result.get("items", []))
        return f"{len(lists_)} task lists"
    await run_check("tasks", check_tasks)

    # --- Contacts ---------------------------------------------------------------
    async def check_contacts():
        result = await contacts_list_contacts(creds, page_size=3)
        people = result.get("contacts", result.get("connections", []))
        return f"{len(people)} contacts listed"
    await run_check("contacts", check_contacts)

    # --- Firestore ---------------------------------------------------------------
    async def check_firestore():
        from services.erp.base_erp_service import get_firestore_db
        db = get_firestore_db()
        docs = await db.collection("erp_users").limit(1).get()
        return f"project={db.project}, read ok"
    await run_check("firestore", check_firestore)

    # --- Gemini API key (TTS / Live voice) ----------------------------------------
    if os.environ.get("GEMINI_API_KEY"):
        record("gemini-key", "PASS", "GEMINI_API_KEY set (TTS/Live voice available)")
    else:
        record("gemini-key", "FAIL", "GEMINI_API_KEY missing — TTS i Live voice NE rade")

    # --- Summary --------------------------------------------------------------------
    print("\n=== Summary ===")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    for service, status, _ in RESULTS:
        if status == "FAIL":
            print(f"  FAIL: {service}")
    print(f"\n{passed} PASS / {failed} FAIL / {len(RESULTS)} total")

    expiry = getattr(creds, "expiry", None)
    if expiry:
        print(f"\nAccess token expiry: {expiry} UTC (auto-refreshes via refresh token)")
    print(
        "\nNOTE: ako OAuth consent screen u GCP konzoli stoji na 'Testing',\n"
        "refresh token istjece nakon 7 dana i sve gore pada na re-login.\n"
        "Provjeri: https://console.cloud.google.com/apis/credentials/consent\n"
        "-> Publishing status mora biti 'In production'."
    )

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        sys.exit(2)

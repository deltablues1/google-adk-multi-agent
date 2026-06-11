"""Create composite Firestore indexes needed by ERP queries.

Uses google-cloud-firestore Admin API via google-auth.
Run once after setup_firestore.py.
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env so google.auth.default() picks up GOOGLE_APPLICATION_CREDENTIALS
# (service account) instead of falling back to user ADC without permissions.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


INDEXES = [
    # ── customers ────────────────────────────────────────────────────────────
    {
        "collection": "customers",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("name", "ASCENDING"),
        ],
    },
    {
        "collection": "customers",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("party_type", "ASCENDING"),
            ("name", "ASCENDING"),
        ],
    },
    # ── products ─────────────────────────────────────────────────────────────
    {
        "collection": "products",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("name", "ASCENDING"),
        ],
    },
    {
        "collection": "products",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("active", "ASCENDING"),
            ("name", "ASCENDING"),
        ],
    },
    {
        "collection": "products",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("stock_quantity", "ASCENDING"),
        ],
    },
    # ── invoices_b2c ─────────────────────────────────────────────────────────
    *[
        {
            "collection": col,
            "fields": [
                ("company_id", "ASCENDING"),
                ("deleted", "ASCENDING"),
                ("date", "DESCENDING"),
            ],
        }
        for col in ["invoices_b2c", "invoices_b2b", "invoices_b2g", "invoices_eu", "invoices_int"]
    ],
    *[
        {
            "collection": col,
            "fields": [
                ("company_id", "ASCENDING"),
                ("payment_status", "ASCENDING"),
                ("date", "DESCENDING"),
            ],
        }
        for col in ["invoices_b2c", "invoices_b2b", "invoices_b2g", "invoices_eu", "invoices_int"]
    ],
    *[
        {
            "collection": col,
            "fields": [
                ("company_id", "ASCENDING"),
                ("document_status", "ASCENDING"),
                ("date", "DESCENDING"),
            ],
        }
        for col in ["invoices_b2c", "invoices_b2b", "invoices_b2g", "invoices_eu", "invoices_int"]
    ],
    # ── payments ─────────────────────────────────────────────────────────────
    {
        "collection": "payments",
        "fields": [
            ("company_id", "ASCENDING"),
            ("payment_date", "DESCENDING"),
        ],
    },
    {
        "collection": "payments",
        "fields": [
            ("company_id", "ASCENDING"),
            ("idempotency_key", "ASCENDING"),
        ],
    },
    # ── payment_allocations ──────────────────────────────────────────────────
    {
        "collection": "payment_allocations",
        "fields": [
            ("company_id", "ASCENDING"),
            ("invoice_id", "ASCENDING"),
        ],
    },
    {
        "collection": "payment_allocations",
        "fields": [
            ("company_id", "ASCENDING"),
            ("payment_id", "ASCENDING"),
        ],
    },
    # ── vendor_invoices ──────────────────────────────────────────────────────
    {
        "collection": "vendor_invoices",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("issue_date", "DESCENDING"),
        ],
    },
    {
        "collection": "vendor_invoices",
        "fields": [
            ("company_id", "ASCENDING"),
            ("payment_status", "ASCENDING"),
            ("issue_date", "DESCENDING"),
        ],
    },
    {
        "collection": "vendor_invoices",
        "fields": [
            ("company_id", "ASCENDING"),
            ("document_status", "ASCENDING"),
            ("issue_date", "DESCENDING"),
        ],
    },
    # ── quotes ───────────────────────────────────────────────────────────────
    {
        "collection": "quotes",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("created_at", "DESCENDING"),
        ],
    },
    {
        "collection": "quotes",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("document_status", "ASCENDING"),
            ("created_at", "DESCENDING"),
        ],
    },
    {
        "collection": "quotes",
        "fields": [
            ("company_id", "ASCENDING"),
            ("deleted", "ASCENDING"),
            ("customer_id", "ASCENDING"),
            ("created_at", "DESCENDING"),
        ],
    },
    # ── audit_log (activity feed) ────────────────────────────────────────────
    {
        "collection": "audit_log",
        "fields": [
            ("company_id", "ASCENDING"),
            ("target_service", "ASCENDING"),
            ("timestamp", "DESCENDING"),
        ],
    },
    # ── inventory_movements ──────────────────────────────────────────────────
    {
        "collection": "inventory_movements",
        "fields": [
            ("company_id", "ASCENDING"),
            ("product_id", "ASCENDING"),
            ("created_at", "DESCENDING"),
        ],
    },
]


def build_index_body(index_def: dict) -> dict:
    return {
        "queryScope": "COLLECTION",
        "fields": [
            {"fieldPath": fp, "order": order}
            for fp, order in index_def["fields"]
        ],
    }


def create_indexes_rest(project_id: str, database_id: str = "(default)"):
    """Create composite indexes via Firestore Admin REST API."""
    import google.auth
    import google.auth.transport.requests
    import urllib.request

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    req = google.auth.transport.requests.Request()
    credentials.refresh(req)
    token = credentials.token

    base_url = (
        f"https://firestore.googleapis.com/v1/projects/{project_id}"
        f"/databases/{database_id}/collectionGroups"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    created = 0
    skipped = 0
    errors = 0

    for idx_def in INDEXES:
        col = idx_def["collection"]
        body = build_index_body(idx_def)
        url = f"{base_url}/{col}/indexes"
        data = json.dumps(body).encode()

        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request) as resp:
                result = json.loads(resp.read())
                state = result.get("state", "?")
                name_short = result.get("name", "").split("/")[-1]
                fields_str = ", ".join(f"{f['fieldPath']}:{f['order'][:3]}" for f in body["fields"])
                print(f"  + {col} [{fields_str}] -> {state} ({name_short})")
                created += 1
        except urllib.error.HTTPError as e:
            body_resp = e.read().decode()
            if "ALREADY_EXISTS" in body_resp or e.code == 409:
                fields_str = ", ".join(f[0] for f in idx_def["fields"])
                print(f"  = {col} [{fields_str}] already exists")
                skipped += 1
            else:
                print(f"  ! {col} ERROR {e.code}: {body_resp[:200]}")
                errors += 1

    print(f"\nDone: {created} created, {skipped} already existed, {errors} errors")
    if created > 0:
        print("Note: Indexes build in background (1-5 min). Check Firebase Console for status.")


if __name__ == "__main__":
    import google.auth as _gauth
    _, project_id = _gauth.default()
    project_id = project_id or "lyrical-star-497817-m3"
    print(f"Creating ERP composite indexes for project: {project_id}")
    print(f"Total indexes to create: {len(INDEXES)}\n")
    create_indexes_rest(project_id)

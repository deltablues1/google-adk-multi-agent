"""
Firestore Collection Setup Script
==================================
Creates all collections with seed/schema documents and composite indexes.

Collections:
  - conversations          Chat sessions + messages (subcollection)
  - invoices_b2c           B2C fiscal invoices (JIR/ZKI required)
  - invoices_b2b           B2B e-invoices (UBL 2.1, CTC dual reporting)
  - invoices_b2g           B2G e-invoices (Peppol/FINA, UBL 2.1)
  - invoices_eu            EU intra-community (reverse charge, e-Reporting)
  - invoices_int           International/export (zero-rate, e-Reporting)
  - products               Product catalog with KPD codes
  - customers              Customer/vendor master data
  - quotes                 Sales quotes/offers
  - expense_records        Receipts and expense tracking
  - scheduled_jobs         Scheduler job definitions + execution history
  - user_preferences       Per-user settings and learning
  - agent_learning         Agent adaptation patterns from conversations
  - audit_log              All agent actions for compliance

ERP Module (new collections):
  - payments               Incoming/outgoing payment records
  - payment_allocations    Payment → invoice allocation (1 payment : N invoices)
  - vendor_invoices        Incoming invoices (URA) from vendors
  - erp_companies          Multi-tenant company registry
  - erp_users              ERP user profiles with roles and permissions
  - erp_counters           Sequential display ID counters

Usage:
    python scripts/setup_firestore.py
    python scripts/setup_firestore.py --dry-run    # Preview without writing
"""

import os
import sys
import argparse
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from google.cloud import firestore


def get_db():
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', 'lyrical-star-497817-m3')
    return firestore.Client(project=project)


def setup_conversations(db, dry_run=False):
    """Chat sessions with messages subcollection."""
    print("\n[1/14] conversations")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Chat session metadata. Messages stored in subcollection.",
        "_fields": {
            "user_id": "string - owner of this session",
            "title": "string - auto-generated from first message",
            "status": "string - active|archived",
            "created_at": "timestamp",
            "updated_at": "timestamp",
            "message_count": "integer",
            "agents_used": "array[string] - which agents participated",
            "summary": "string - AI-generated session summary",
        },
        "_subcollections": {
            "messages": {
                "role": "string - user|assistant|system",
                "content": "string - message text",
                "timestamp": "timestamp",
                "agent_name": "string|null - which agent responded",
                "media_urls": "array[string] - attached images/videos/files",
                "tool_calls": "array[object] - tool invocations in this turn",
                "tokens_used": "integer - token count for this message",
            }
        },
        "user_id": "_schema",
        "title": "Schema Definition",
        "status": "archived",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "message_count": 0,
        "agents_used": [],
        "summary": "",
    }

    if not dry_run:
        doc_ref = db.collection("conversations").document("_schema")
        doc_ref.set(schema_doc)
        # Add schema message to subcollection
        doc_ref.collection("messages").document("_schema").set({
            "role": "system",
            "content": "Schema definition document",
            "timestamp": firestore.SERVER_TIMESTAMP,
            "agent_name": None,
            "media_urls": [],
            "tool_calls": [],
            "tokens_used": 0,
        })
    print("  OK - conversations + messages subcollection")


def setup_invoices_b2c(db, dry_run=False):
    """B2C invoices - full fiscalization with JIR/ZKI."""
    print("\n[2/14] invoices_b2c")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "B2C fiscal invoices. JIR and ZKI required. QR code mandatory from 2026.",
        "_legal_basis": "Zakon o fiskalizaciji (NN 89/25), Fiskalizacija 2.0",
        "_retention_years": 11,
        "_fields": {
            "invoice_number": "string - sequential (e.g., 1/URED/1)",
            "date": "timestamp - invoice date/time",
            "seller_oib": "string(11) - seller tax ID",
            "seller_name": "string",
            "business_premise": "string - poslovni prostor code",
            "cash_register": "string - naplatni uredjaj code",
            "payment_method": "string - G(gotovina)/K(kartica)/T(transakcija)/O(ostalo)",
            "items": "array[object] - line items with KPD codes",
            "total_without_vat": "number(decimal)",
            "vat_breakdown": "map - per-rate VAT amounts {rate: {base, amount}}",
            "total_vat": "number(decimal)",
            "grand_total": "number(decimal)",
            "currency": "string - EUR",
            "zki": "string(32) - Zastitni Kod Izdavatelja (generated locally)",
            "jir": "string(36) - Jedinstveni Identifikator Racuna (from CIS)",
            "qr_code_data": "string - QR code payload",
            "fiscalization_status": "string - pending|submitted|confirmed|failed|retry",
            "fiscalization_timestamp": "timestamp - when CIS confirmed",
            "fiscalization_attempts": "integer",
            "error_log": "array[object] - {timestamp, error, attempt}",
            "xml_request": "string - SOAP XML sent to CIS",
            "xml_response": "string - SOAP XML response from CIS",
            "voided": "boolean - storno",
            "void_reference": "string - reference to void invoice if applicable",
        },
        "invoice_number": "_schema/URED/1",
        "date": firestore.SERVER_TIMESTAMP,
        "seller_oib": "00000000000",
        "seller_name": "Schema Definition",
        "business_premise": "URED",
        "cash_register": "1",
        "payment_method": "G",
        "items": [],
        "total_without_vat": 0,
        "vat_breakdown": {},
        "total_vat": 0,
        "grand_total": 0,
        "currency": "EUR",
        "zki": "",
        "jir": "",
        "qr_code_data": "",
        "fiscalization_status": "schema",
        "fiscalization_timestamp": None,
        "fiscalization_attempts": 0,
        "error_log": [],
        "xml_request": "",
        "xml_response": "",
        "voided": False,
        "void_reference": "",
    }

    if not dry_run:
        db.collection("invoices_b2c").document("_schema").set(schema_doc)
    print("  OK - B2C invoices (JIR/ZKI, QR code, CIS SOAP/XML)")


def setup_invoices_b2b(db, dry_run=False):
    """B2B e-invoices - UBL 2.1 with HR-FISK 2.0 CIUS."""
    print("\n[3/14] invoices_b2b")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "B2B e-invoices. UBL 2.1 + HR-FISK 2.0 CIUS. CTC dual reporting.",
        "_legal_basis": "Fiskalizacija 2.0, EN 16931, mandatory from 01.01.2026 for VAT-registered",
        "_retention_years": 11,
        "_fields": {
            "invoice_number": "string - unique invoice number",
            "date": "timestamp",
            "due_date": "timestamp - payment due date",
            "seller_oib": "string(11)",
            "seller_name": "string",
            "seller_iban": "string - bank account",
            "buyer_oib": "string(11) - REQUIRED for B2B",
            "buyer_name": "string",
            "buyer_address": "string",
            "buyer_iban": "string",
            "items": "array[object] - with CPA 6-digit product codes",
            "total_without_vat": "number(decimal)",
            "vat_breakdown": "map",
            "total_vat": "number(decimal)",
            "grand_total": "number(decimal)",
            "currency": "string - EUR",
            "payment_terms": "string",
            "payment_reference": "string - model+poziv na broj",
            "ubl_xml": "string - full UBL 2.1 XML document",
            "digital_signature": "string - qualified electronic signature",
            "ctc_status": "string - pending|reported_outbound|reported_inbound|confirmed",
            "ctc_outbound_timestamp": "timestamp - when seller reported",
            "ctc_inbound_timestamp": "timestamp - when buyer confirmed (within 5 days)",
            "as4_message_id": "string - AS4 access point message ID",
            "as4_access_point": "string - which access point delivered",
            "error_log": "array[object]",
            "voided": "boolean",
            "credit_note_reference": "string - if this is a credit note",
        },
        "invoice_number": "_schema",
        "date": firestore.SERVER_TIMESTAMP,
        "seller_oib": "00000000000",
        "buyer_oib": "00000000000",
        "seller_name": "Schema Definition",
        "buyer_name": "Schema Definition",
        "items": [],
        "total_without_vat": 0,
        "vat_breakdown": {},
        "total_vat": 0,
        "grand_total": 0,
        "currency": "EUR",
        "ubl_xml": "",
        "digital_signature": "",
        "ctc_status": "schema",
        "voided": False,
    }

    if not dry_run:
        db.collection("invoices_b2b").document("_schema").set(schema_doc)
    print("  OK - B2B e-invoices (UBL 2.1, HR-FISK 2.0, CTC dual)")


def setup_invoices_b2g(db, dry_run=False):
    """B2G e-invoices - via FINA Servis eRacun."""
    print("\n[4/14] invoices_b2g")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "B2G e-invoices. Mandatory since 01.07.2019. Via FINA Peppol access point.",
        "_legal_basis": "Act on eInvoicing in Public Procurement (OJ 94/2018), EU Directive 2014/55/EU",
        "_retention_years": 11,
        "_fields": {
            "invoice_number": "string",
            "date": "timestamp",
            "due_date": "timestamp",
            "seller_oib": "string(11)",
            "seller_name": "string",
            "buyer_oib": "string(11) - government entity OIB",
            "buyer_name": "string - government entity name",
            "buyer_department": "string - specific department/unit",
            "contract_reference": "string - public procurement contract number",
            "order_reference": "string - purchase order number",
            "items": "array[object] - with CPA codes, Peppol BIS 3.0 compliant",
            "total_without_vat": "number(decimal)",
            "vat_breakdown": "map",
            "total_vat": "number(decimal)",
            "grand_total": "number(decimal)",
            "currency": "string - EUR",
            "ubl_xml": "string - UBL 2.1 XML (Peppol BIS 3.0)",
            "peppol_participant_id": "string - buyer Peppol ID",
            "fina_submission_id": "string - FINA eRacun submission ID",
            "fina_status": "string - pending|submitted|accepted|rejected",
            "fina_timestamp": "timestamp",
            "ctc_status": "string - CTC dual reporting status",
            "digital_signature": "string",
            "error_log": "array[object]",
            "voided": "boolean",
        },
        "invoice_number": "_schema",
        "date": firestore.SERVER_TIMESTAMP,
        "seller_oib": "00000000000",
        "buyer_oib": "00000000000",
        "seller_name": "Schema Definition",
        "buyer_name": "Schema Definition",
        "items": [],
        "grand_total": 0,
        "currency": "EUR",
        "fina_status": "schema",
        "voided": False,
    }

    if not dry_run:
        db.collection("invoices_b2g").document("_schema").set(schema_doc)
    print("  OK - B2G e-invoices (FINA eRacun, Peppol BIS 3.0)")


def setup_invoices_eu(db, dry_run=False):
    """EU intra-community invoices - reverse charge."""
    print("\n[5/14] invoices_eu")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "EU intra-community invoices. Reverse charge. e-Reporting required.",
        "_legal_basis": "EU VAT Directive Art. 138, ViDA from 01.07.2030",
        "_retention_years": 11,
        "_fields": {
            "invoice_number": "string",
            "date": "timestamp",
            "due_date": "timestamp",
            "seller_oib": "string(11)",
            "seller_name": "string",
            "seller_vat_id": "string - HR + OIB",
            "buyer_name": "string",
            "buyer_country": "string - ISO 3166-1 alpha-2",
            "buyer_vat_id": "string - EU VAT ID (validated via VIES)",
            "buyer_address": "string",
            "vies_validated": "boolean - buyer VAT ID confirmed via VIES",
            "vies_validation_date": "timestamp",
            "items": "array[object] - line items",
            "total_amount": "number(decimal) - no VAT (reverse charge)",
            "currency": "string - EUR or other",
            "exchange_rate": "number - ECB rate if non-EUR",
            "reverse_charge_note": "string - 'Prijenos porezne obveze / Reverse charge'",
            "intrastat_required": "boolean - if goods exceed threshold",
            "intrastat_data": "map - commodity codes, weight, transport mode",
            "e_reporting_status": "string - pending|reported|confirmed",
            "e_reporting_timestamp": "timestamp",
            "delivery_terms": "string - Incoterms",
            "transport_document": "string - CMR/AWB reference",
            "error_log": "array[object]",
            "voided": "boolean",
        },
        "invoice_number": "_schema",
        "date": firestore.SERVER_TIMESTAMP,
        "seller_oib": "00000000000",
        "seller_name": "Schema Definition",
        "buyer_name": "Schema Definition",
        "buyer_vat_id": "",
        "vies_validated": False,
        "total_amount": 0,
        "currency": "EUR",
        "reverse_charge_note": "Prijenos porezne obveze / Reverse charge Art. 138 VAT Directive",
        "e_reporting_status": "schema",
        "voided": False,
    }

    if not dry_run:
        db.collection("invoices_eu").document("_schema").set(schema_doc)
    print("  OK - EU invoices (reverse charge, VIES, e-Reporting)")


def setup_invoices_int(db, dry_run=False):
    """International (non-EU) export invoices."""
    print("\n[6/14] invoices_int")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "International export invoices (non-EU). Zero-rate VAT. e-Reporting required.",
        "_legal_basis": "Zakon o PDV-u Art. 45, export exemption",
        "_retention_years": 11,
        "_fields": {
            "invoice_number": "string",
            "date": "timestamp",
            "due_date": "timestamp",
            "seller_oib": "string(11)",
            "seller_name": "string",
            "buyer_name": "string",
            "buyer_country": "string - ISO 3166-1 alpha-2",
            "buyer_tax_id": "string - foreign tax ID if applicable",
            "buyer_address": "string",
            "items": "array[object]",
            "total_amount": "number(decimal) - zero-rate VAT",
            "currency": "string",
            "exchange_rate": "number - HNB/ECB rate",
            "vat_exemption_reason": "string - Art. 45 reference",
            "export_declaration_number": "string - customs MRN",
            "customs_status": "string - declared|cleared|released",
            "proof_of_export": "map - {type, reference, date}",
            "delivery_terms": "string - Incoterms (EXW, FOB, CIF, etc.)",
            "transport_document": "string - CMR/BL/AWB reference",
            "letter_of_credit": "string - L/C reference if applicable",
            "e_reporting_status": "string - pending|reported|confirmed",
            "e_reporting_timestamp": "timestamp",
            "sanctions_check": "boolean - sanctions screening done",
            "error_log": "array[object]",
            "voided": "boolean",
        },
        "invoice_number": "_schema",
        "date": firestore.SERVER_TIMESTAMP,
        "seller_oib": "00000000000",
        "seller_name": "Schema Definition",
        "buyer_name": "Schema Definition",
        "buyer_country": "",
        "total_amount": 0,
        "currency": "EUR",
        "vat_exemption_reason": "Izvoz - oslobodeno PDV-a sukladno cl. 45 Zakona o PDV-u",
        "e_reporting_status": "schema",
        "voided": False,
    }

    if not dry_run:
        db.collection("invoices_int").document("_schema").set(schema_doc)
    print("  OK - INT invoices (export, zero-rate, customs)")


def setup_products(db, dry_run=False):
    """Product catalog."""
    print("\n[7/14] products")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Product/service catalog with KPD classification codes.",
        "sku": "_schema",
        "name": "Schema Definition",
        "description": "",
        "category": "",
        "kpd_code": "string - 6-digit CPA/KPD product classification",
        "unit": "string - kom/kg/l/h/m2/etc",
        "price": 0,
        "vat_rate": "25",
        "currency": "EUR",
        "stock_quantity": 0,
        "supplier": "",
        "active": True,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if not dry_run:
        db.collection("products").document("_schema").set(schema_doc)
    print("  OK - products")


def setup_customers(db, dry_run=False):
    """Customer/vendor master data."""
    print("\n[8/14] customers")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Customer and vendor master data with OIB validation.",
        "name": "Schema Definition",
        "oib": "string(11) - Croatian tax ID",
        "vat_id": "string - EU VAT ID (HR+OIB for Croatian)",
        "type": "string - customer|vendor|both",
        "category": "string - B2B|B2C|B2G|EU|INT",
        "email": "",
        "phone": "",
        "address": "",
        "city": "",
        "postal_code": "",
        "country": "HR",
        "iban": "",
        "contact_person": "",
        "vies_validated": False,
        "vies_validation_date": None,
        "payment_terms_days": 30,
        "credit_limit": 0,
        "notes": "",
        "active": True,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if not dry_run:
        db.collection("customers").document("_schema").set(schema_doc)
    print("  OK - customers")


def setup_quotes(db, dry_run=False):
    """Sales quotes/offers."""
    print("\n[9/14] quotes")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Sales quotes and offers. Can be converted to invoices.",
        "quote_number": "_schema",
        "date": firestore.SERVER_TIMESTAMP,
        "valid_until": None,
        "customer_id": "string - reference to customers collection",
        "customer_name": "",
        "items": [],
        "total_without_vat": 0,
        "total_vat": 0,
        "grand_total": 0,
        "currency": "EUR",
        "status": "string - draft|sent|accepted|rejected|expired|invoiced",
        "converted_to_invoice": "string|null - invoice ID if converted",
        "notes": "",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if not dry_run:
        db.collection("quotes").document("_schema").set(schema_doc)
    print("  OK - quotes")


def setup_expense_records(db, dry_run=False):
    """Expense/receipt tracking."""
    print("\n[10/14] expense_records")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Expense records from OCR-scanned receipts and manual entries.",
        "merchant_name": "Schema Definition",
        "transaction_date": firestore.SERVER_TIMESTAMP,
        "total_amount": 0,
        "currency": "EUR",
        "category": "string - Hrana|Prijevoz|Ured|Rezije|Reprezentacija|IT|Ostalo",
        "subcategory": "",
        "payment_method": "string - gotovina|kartica|transakcija",
        "items": [],
        "vat_amount": 0,
        "receipt_image_url": "string - Drive file URL or Cloud Storage URL",
        "receipt_drive_id": "string - Google Drive file ID",
        "ocr_confidence": 0.0,
        "ocr_model": "string - gemini-2.5-flash",
        "vendor_oib": "",
        "deductible": True,
        "deduction_percentage": 100,
        "notes": "",
        "approved": False,
        "approved_by": "",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if not dry_run:
        db.collection("expense_records").document("_schema").set(schema_doc)
    print("  OK - expense_records")


def setup_scheduled_jobs(db, dry_run=False):
    """Scheduler job definitions + execution history."""
    print("\n[11/14] scheduled_jobs")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Scheduled job definitions and execution history.",
        "name": "Schema Definition",
        "agent_request": "string - natural language request for agent",
        "trigger_type": "string - cron|interval|date",
        "cron_expression": "",
        "interval_seconds": 0,
        "run_date": None,
        "timezone": "Europe/Zagreb",
        "enabled": False,
        "max_retries": 3,
        "description": "",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "last_run": None,
        "last_status": "string - never|success|failed",
        "run_count": 0,
        "execution_history": "subcollection - {timestamp, status, result_preview, error, elapsed_seconds, attempt}",
    }

    if not dry_run:
        db.collection("scheduled_jobs").document("_schema").set(schema_doc)
    print("  OK - scheduled_jobs")


def setup_user_preferences(db, dry_run=False):
    """Per-user settings and preferences."""
    print("\n[12/14] user_preferences")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "User preferences for personalized agent behavior.",
        "user_id": "_schema",
        "display_name": "",
        "language": "hr",
        "timezone": "Europe/Zagreb",
        "preferred_agents": [],
        "communication_style": "string - formal|casual|concise|detailed",
        "email_signature": "",
        "default_calendar": "primary",
        "default_drive_folder": "",
        "notification_preferences": {
            "email": True,
            "web": True,
        },
        "theme": "dark",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if not dry_run:
        db.collection("user_preferences").document("_schema").set(schema_doc)
    print("  OK - user_preferences")


def setup_agent_learning(db, dry_run=False):
    """Agent adaptation patterns from conversations."""
    print("\n[13/14] agent_learning")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Patterns learned from user interactions for agent personalization.",
        "_examples": [
            "User always wants emails in formal Croatian",
            "User prefers calendar events with 15-min reminders",
            "User's most common expense category is 'Reprezentacija'",
            "User frequently asks about invoices for company X",
        ],
        "user_id": "_schema",
        "pattern_type": "string - preference|habit|correction|shortcut|contact_alias",
        "category": "string - email|calendar|drive|invoicing|expenses|general",
        "pattern": "string - description of the learned pattern",
        "context": "string - conversation context where pattern was observed",
        "confidence": 0.0,
        "frequency": 0,
        "last_observed": firestore.SERVER_TIMESTAMP,
        "first_observed": firestore.SERVER_TIMESTAMP,
        "active": True,
        "source_session_ids": [],
    }

    if not dry_run:
        db.collection("agent_learning").document("_schema").set(schema_doc)
    print("  OK - agent_learning")


def setup_audit_log(db, dry_run=False):
    """Audit log for all agent actions."""
    print("\n[14/14] audit_log")

    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Immutable audit trail of all agent actions. For compliance and debugging.",
        "_retention_years": 7,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "user_id": "_schema",
        "session_id": "",
        "agent_name": "string - which agent performed the action",
        "action_type": "string - email_sent|file_created|invoice_submitted|calendar_event|etc",
        "action_description": "string - human-readable description",
        "target_resource": "string - email ID, file ID, invoice number, etc",
        "target_service": "string - gmail|drive|calendar|sheets|fina|etc",
        "input_summary": "string - what was requested (truncated)",
        "output_summary": "string - what was done (truncated)",
        "status": "string - success|failed|partial",
        "error": "",
        "ip_address": "",
        "metadata": {},
    }

    if not dry_run:
        db.collection("audit_log").document("_schema").set(schema_doc)
    print("  OK - audit_log")


def setup_erp_payments(db, dry_run=False):
    """ERP payment records (incoming and outgoing)."""
    print("\n[15/20] payments (ERP)")
    schema_doc = {
        "_schema_version": "1.0",
        "_description": "ERP payment records. UUID internal ID, display_id for humans.",
        "_fields": {
            "payment_id": "string - UUID (internal)",
            "display_id": "string - PAY-2026-000001 (human-readable)",
            "company_id": "string - multi-tenant isolation key",
            "type": "string - incoming|outgoing",
            "party_id": "string - FK → customers",
            "party_name": "string - denormalized",
            "invoice_ref_id": "string - FK → invoice document",
            "invoice_ref_type": "string - b2c|b2b|b2g|eu|int|vendor",
            "invoice_ref_display": "string - invoice display_id",
            "amount": "decimal - EUR",
            "currency": "string - EUR",
            "payment_date": "date - YYYY-MM-DD",
            "payment_method": "string - transfer|cash|card|direct_debit",
            "reference": "string - poziv na broj",
            "bank_account": "string - IBAN",
            "status": "string - confirmed|pending|returned",
            "notes": "string",
            "created_at": "timestamp",
            "created_by": "string",
            "reconciled": "boolean",
            "reconciled_at": "timestamp|null",
            "idempotency_key": "string - SHA256 hash, prevents duplicates",
        },
        "_retention": "7 years",
    }
    if not dry_run:
        db.collection("payments").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def setup_erp_payment_allocations(db, dry_run=False):
    """Payment allocations — 1 payment can cover N invoices."""
    print("\n[16/20] payment_allocations (ERP)")
    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Maps payments to invoices. One payment can partially cover multiple invoices.",
        "_fields": {
            "allocation_id": "string - UUID",
            "company_id": "string",
            "payment_id": "string - FK → payments",
            "invoice_id": "string - FK → invoice document (UUID)",
            "invoice_type": "string - b2c|b2b|b2g|eu|int|vendor",
            "display_id": "string - invoice display_id for UI without join",
            "amount": "decimal - portion of payment allocated to this invoice",
            "allocated_at": "timestamp",
            "allocated_by": "string - user_id",
        },
    }
    if not dry_run:
        db.collection("payment_allocations").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def setup_erp_vendor_invoices(db, dry_run=False):
    """Vendor invoices — ulazni računi od dobavljača."""
    print("\n[17/20] vendor_invoices (ERP)")
    schema_doc = {
        "_schema_version": "2.0",
        "_description": (
            "Incoming invoices (URA) from vendors. Separate from outgoing fiscal invoices. "
            "Extended for eRačun compliance (NN 89/2025): inbound UBL 2.1 support, "
            "fiscalization lifecycle, buyer acceptance tracking, Drive archive references."
        ),
        "_fields": {
            # Core identity
            "vendor_invoice_id": "string - UUID",
            "display_id": "string - URA-2026-000001",
            "company_id": "string",
            # Vendor
            "vendor_id": "string - FK → customers (party_type=supplier|both)",
            "vendor_name": "string - denormalized",
            "vendor_oib": "string",
            # Dates
            "issue_date": "date - YYYY-MM-DD",
            "due_date": "date - YYYY-MM-DD",
            "received_date": "date - when physically received (triggers 5-day SLA)",
            "fiscalization_deadline": "date - received_date + 5 business days per NN 89/2025",
            # Financials
            "items": "array[{description, quantity, unit_price, vat_rate, line_total}]",
            "subtotal_net": "decimal",
            "vat_amount": "decimal",
            "total_gross": "decimal",
            "currency": "string - EUR",
            "vat_deductible": "boolean - can we reclaim input VAT?",
            # Document lifecycle (state machine enforced)
            "document_status": (
                "string - draft|received|approved|disputed|cancelled|"
                "fisc_reported|accepted|rejected"
            ),
            "payment_status": "string - unpaid|partial|paid (denormalized)",
            "amount_paid": "decimal - running total of payments received",
            "amount_due": "decimal - total_gross - amount_paid",
            # Fiscalization compliance
            "fiscalization_status": "string - pending|fiscalized|not_required",
            "fisc_reported_at": "timestamp - when reported to Porezna Uprava",
            "fisc_reported_by": "string - user_id",
            "fisc_confirmation_ref": "string - CIS confirmation reference number",
            # Buyer acceptance (eRačun)
            "acceptance_status": "string - pending|accepted|rejected",
            "accepted_at": "timestamp",
            "accepted_by": "string - user_id",
            "rejected_at": "timestamp",
            "rejected_by": "string - user_id",
            "rejection_reason": "string - mandatory when rejected",
            # Approval
            "approved_by": "string - user_id",
            "approved_at": "timestamp",
            # Source tracing
            "source_type": "string - ubl_xml|ocr_scan|manual",
            "parsed_from_ubl": "boolean - True if created from UBL 2.1 inbound parser",
            "source_ubl_xml": "string - original UBL XML content (stored on UBL-sourced invoices)",
            "scan_file_id": "string - Drive file_id of scanned PDF/image",
            "ocr_data": "map - raw OCR output if scanned",
            # Drive archive references
            "drive_original_file_id": "string - Drive file_id of the original inbound document",
            "drive_folder_id": "string - Drive folder_id where document is archived",
            "archive_status": "string - not_archived|pending|archived",
            "archived_at": "timestamp",
            # Classification
            "category": "string - materials|services|utilities|equipment|other",
            "vendor_invoice_no": "string - supplier's invoice number",
            "notes": "string",
            "_dedup_hash": "string - sha256(company_id:vendor_oib:invoice_no:date:amount)",
            # Audit
            "created_at": "timestamp",
            "updated_at": "timestamp",
            "created_by": "string",
            "deleted": "boolean - soft delete",
            "deleted_at": "timestamp|null",
            "deleted_by": "string|null",
            "idempotency_key": "string",
        },
        "_retention": "11 years",
        "_state_machine": "VENDOR_INVOICE_DOC_TRANSITIONS (services/erp/state_machines.py)",
        "_sla": "5 business days from received_date for fiscalization (NN 89/2025)",
    }
    if not dry_run:
        db.collection("vendor_invoices").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def setup_erp_companies(db, dry_run=False):
    """ERP multi-tenant company registry."""
    print("\n[18/20] erp_companies (ERP)")
    schema_doc = {
        "_schema_version": "1.0",
        "_description": "Multi-tenant company registry for ERP module.",
        "_fields": {
            "company_id": "string - UUID",
            "name": "string",
            "oib": "string - Croatian OIB (11 digits)",
            "plan": "string - free|pro|enterprise",
            "created_at": "timestamp",
            "active": "boolean",
        },
    }
    if not dry_run:
        db.collection("erp_companies").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def setup_erp_users(db, dry_run=False):
    """ERP user profiles with roles and explicit permissions."""
    print("\n[19/20] erp_users (ERP)")
    schema_doc = {
        "_schema_version": "1.0",
        "_description": "ERP user profiles. Role defaults + explicit permission grants/denies.",
        "_fields": {
            "user_id": "string - FK (Firebase Auth or custom)",
            "company_id": "string - FK → erp_companies",
            "role": "string - owner|accountant|employee|viewer",
            "email": "string",
            "display_name": "string",
            "active": "boolean",
            "permissions": "map - {grants: [string], denies: [string]}",
        },
        "_permission_precedence": (
            "1. explicit deny (denies[]) beats everything. "
            "2. explicit grant (grants[]) beats role default. "
            "3. role default from ROLE_PERMISSIONS. "
            "4. wildcard '*' in role grants all. "
            "5. default: deny."
        ),
        "_role_defaults": {
            "owner": ["*"],
            "accountant": ["invoice:read", "invoice:create", "payment:record",
                           "vendor_invoice:read", "vendor_invoice:approve",
                           "customer:read", "customer:create", "customer:update",
                           "product:read", "report:read"],
            "employee": ["invoice:read", "vendor_invoice:read", "vendor_invoice:create",
                         "expense:create", "customer:read", "product:read"],
            "viewer": ["invoice:read", "vendor_invoice:read", "report:read",
                       "customer:read", "product:read"],
        },
    }
    if not dry_run:
        db.collection("erp_users").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def setup_erp_counters(db, dry_run=False):
    """Sequential display ID counters."""
    print("\n[20/20] erp_counters (ERP)")
    schema_doc = {
        "_schema_version": "1.0",
        "_description": (
            "Sequential counters for human-readable display IDs. "
            "Document key: {company_id}-{prefix}-{year}. "
            "Incremented atomically via Firestore Increment(1). "
            "Internal doc IDs are always UUID — this is only for display."
        ),
        "_example_key": "default-company-PAY-2026",
        "_example_value": {"counter": 42},
        "_prefixes": ["PAY", "URA", "QUOT", "ADJ"],
    }
    if not dry_run:
        db.collection("erp_counters").document("_schema").set(schema_doc)
        print("  OK - Schema doc written")
    else:
        print("  [DRY RUN] Would write schema doc")


def create_composite_indexes(db, dry_run=False):
    """Print required composite indexes (must be created via gcloud or Console)."""
    print("\n" + "=" * 60)
    print("COMPOSITE INDEXES (create manually or via gcloud)")
    print("=" * 60)

    indexes = [
        {
            "collection": "invoices_b2c",
            "fields": "seller_oib ASC, date DESC",
            "purpose": "Query invoices by seller, sorted by date",
        },
        {
            "collection": "invoices_b2c",
            "fields": "fiscalization_status ASC, date DESC",
            "purpose": "Find pending/failed fiscalizations",
        },
        {
            "collection": "invoices_b2b",
            "fields": "buyer_oib ASC, date DESC",
            "purpose": "Query invoices by buyer",
        },
        {
            "collection": "invoices_b2b",
            "fields": "ctc_status ASC, date DESC",
            "purpose": "Find pending CTC reports",
        },
        {
            "collection": "expense_records",
            "fields": "category ASC, transaction_date DESC",
            "purpose": "Expenses by category sorted by date",
        },
        {
            "collection": "conversations",
            "fields": "user_id ASC, updated_at DESC",
            "purpose": "User sessions sorted by last activity",
        },
        {
            "collection": "audit_log",
            "fields": "user_id ASC, timestamp DESC",
            "purpose": "User audit trail",
        },
        {
            "collection": "audit_log",
            "fields": "agent_name ASC, timestamp DESC",
            "purpose": "Agent activity trail",
        },
        {
            "collection": "agent_learning",
            "fields": "user_id ASC, category ASC, confidence DESC",
            "purpose": "Top patterns per user per category",
        },
    ]

    for idx in indexes:
        print(f"\n  Collection: {idx['collection']}")
        print(f"  Fields:     {idx['fields']}")
        print(f"  Purpose:    {idx['purpose']}")

    print(f"\n  Total: {len(indexes)} composite indexes needed")
    print("  Note: Single-field indexes are auto-created by Firestore")
    print("  Indexes will be auto-created on first query that needs them,")
    print("  or create them proactively via Firebase Console > Firestore > Indexes")


def main():
    parser = argparse.ArgumentParser(description="Setup Firestore collections")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    print("=" * 60)
    print("  Firestore Collection Setup")
    print("=" * 60)

    if args.dry_run:
        print("  MODE: DRY RUN (no writes)")

    db = get_db()
    print(f"  Project: {db.project}")

    # Check existing collections
    existing = [c.id for c in db.collections()]
    print(f"  Existing collections: {existing or '(none)'}")
    print()

    # Create all collections
    setup_conversations(db, args.dry_run)
    setup_invoices_b2c(db, args.dry_run)
    setup_invoices_b2b(db, args.dry_run)
    setup_invoices_b2g(db, args.dry_run)
    setup_invoices_eu(db, args.dry_run)
    setup_invoices_int(db, args.dry_run)
    setup_products(db, args.dry_run)
    setup_customers(db, args.dry_run)
    setup_quotes(db, args.dry_run)
    setup_expense_records(db, args.dry_run)
    setup_scheduled_jobs(db, args.dry_run)
    setup_user_preferences(db, args.dry_run)
    setup_agent_learning(db, args.dry_run)
    setup_audit_log(db, args.dry_run)

    # ERP module collections
    setup_erp_payments(db, args.dry_run)
    setup_erp_payment_allocations(db, args.dry_run)
    setup_erp_vendor_invoices(db, args.dry_run)
    setup_erp_companies(db, args.dry_run)
    setup_erp_users(db, args.dry_run)
    setup_erp_counters(db, args.dry_run)

    create_composite_indexes(db, args.dry_run)

    # Verify
    print("\n" + "=" * 60)
    print("  VERIFICATION")
    print("=" * 60)

    if not args.dry_run:
        collections = sorted([c.id for c in db.collections()])
        print(f"\n  Total collections created: {len(collections)}")
        for c in collections:
            doc_count = len(list(db.collection(c).limit(10).stream()))
            print(f"    {c}: {doc_count} doc(s)")
    else:
        print("  (skipped - dry run mode)")

    print("\n  Setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

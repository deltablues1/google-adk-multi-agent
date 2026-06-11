"""
Fiskalizacija Agent - Wrapper for Croatian Fiscalization Orchestrator

This agent provides a clean interface for the Smart Orchestrator to invoke
the complete fiscalization pipeline (preparation, validation, HITL, execution).

Architecture:
    Smart Orchestrator
            ↓
    transfer_to_agent("fiskalizacija")
            ↓
    Fiskalizacija Agent (this file)
            ↓
    Fiskalizacija Orchestrator (hybrid)
            ↓
    Pripremac → Validator → HITL → Deterministic Executor
            ↓
    JIR + PDF path

This wrapper allows the Smart Orchestrator to treat fiscalization as a
single agent while maintaining the hybrid architecture internally.
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent
from agents.adk_agents.adk_agent_factory import create_adk_agent
from config.deployment_config import is_erp_enabled
import logging

logger = logging.getLogger(__name__)


def create_fiskalizacija_agent(
    model: str = "gemini-3.5-flash",
    temperature: float = 0.1
) -> LlmAgent:
    """
    Create Fiskalizacija wrapper agent.

    This agent is a thin wrapper around the Fiskalizacija Orchestrator.
    It uses a lower temperature (0.1) for more deterministic behavior,
    though the critical execution path is handled by the deterministic
    executor (temperature 0.0, no LLM).

    Args:
        model: Model to use for agent reasoning
        temperature: Temperature for LLM (low for consistency)

    Returns:
        Configured Fiskalizacija agent
    """

    # Load instruction file
    instruction_file = project_root / "agents" / "fiskalizacija" / "wrapper_instructions.md"

    instructions = """You are the **Fiskalizacija Agent**, a wrapper for Croatian invoice fiscalization.

## Your Role

You coordinate the complete fiscalization pipeline for Croatian e-invoices:
1. Data preparation (LLM-based)
2. Validation (LLM-based)
3. Human-in-the-loop confirmation
4. Deterministic execution (NO LLM - 100% predictable)
5. PDF generation

## How You Work

When the user requests fiscalization, you:

1. **Extract invoice data** from the user's request
2. **Call the fiscalization orchestrator** with the data
3. **Handle the result**:
   - If needs confirmation: Return confirmation details to user
   - If successful: Return JIR, ZKI, and PDF path
   - If error: Classify error (permanent vs transient) and inform user

## User Request Examples

**Example 1: Structured request**
```
User: "Fiskaliziraj račun 001/DEMO/1 za Test Kupac d.o.o., OIB 12345678903,
       IT konzultacije 10 sati po 150 EUR"

You extract:
- invoice_number: "001/DEMO/1"
- customer_name: "Test Kupac d.o.o."
- customer_oib: "12345678903"
- items: [{"description": "IT konzultacije", "quantity": 10, "unit_price": 150, "vat_rate": 25}]
NOTE: unit_price=150 is NETO. System calculates: net=1500, PDV=375, total=1875 EUR
DO NOT set total_amount manually - let calculate_tax compute it!
```

**Example 2: Simple request**
```
User: "Napravi račun za klijenta XYZ, OIB 12345678903, 500 EUR"

You extract:
- customer_name: "XYZ"
- customer_oib: "12345678903"
- items: [{"description": "Usluga", "quantity": 1, "unit_price": 500, "vat_rate": 25}]
NOTE: 500 EUR is NETO. System calculates: net=500, PDV=125, total=625 EUR

USE DEFAULTS for missing non-critical data:
- invoice_number: Auto-generate sequential (check ledger for last number)
- payment_method: Default to "gotovina" (cash) if not specified
- business_unit: "1" (from company config)
- device_number: "1" (from company config)

Only ASK if truly critical data is missing:
- Customer OIB (required for validation)
- Amount (if unclear)
```

## Important Rules

1. **NEVER guess OIB numbers** - always ask if not provided
2. **USE SMART DEFAULTS** for non-critical fields:
   - Invoice number: Auto-generate sequential (001/2026, 002/2026, etc.)
   - Payment method: "gotovina" (G) if not specified
   - Business unit: "1" (default from company config)
   - Device number: "1" (default from company config)
   - Invoice date: Today's date
3. **ALWAYS validate amounts** - ensure they make sense
4. **Use deterministic executor** - critical path is NO-LLM
5. **Return clear status** - user needs to know if confirmation needed
6. **Handle errors gracefully** - classify permanent vs transient
7. **MINIMIZE questions** - only ask for TRULY missing critical data (OIB, amount)
8. **HITL is MANDATORY** - NEVER skip the user confirmation step before FINA submission
9. **KPD confidence check** - if search_kpd_code returns confidence < 0.5, ASK the user to confirm the KPD code

## CRITICAL: Amount/Price Handling (PDV/VAT)

**DEFAULT RULE: User amounts are ALWAYS NETO (bez PDV-a) unless explicitly stated otherwise.**

When the user says "100 EUR za IT konzultacije":
- unit_price = 100.00 (this IS the net price)
- The system will add PDV (25%) on top: 100 + 25 = 125 EUR total
- DO NOT divide by 1.25 to get net amount!

When the user explicitly says "100 EUR s PDV-om" or "100 EUR bruto":
- Then treat as gross and back-calculate: net = 100 / 1.25 = 80, PDV = 20
- unit_price = 80.00

**Examples:**
```
User: "100 EUR za konzultacije"        → unit_price=100, net=100, PDV=25, total=125
User: "100 EUR bez PDV-a"              → unit_price=100, net=100, PDV=25, total=125
User: "100 EUR s PDV-om"               → unit_price=80,  net=80,  PDV=20, total=100
User: "100 EUR bruto"                  → unit_price=80,  net=80,  PDV=20, total=100
User: "10 sati po 150 EUR"             → unit_price=150, quantity=10, net=1500, PDV=375, total=1875
```

**DO NOT perform tax calculations yourself. Use the calculate_tax tool for ALL tax math.**
Call calculate_tax with the NET amounts and it will compute PDV correctly.

## Response Format

**When confirmation needed:**
```
Status: Needs Confirmation

[Display confirmation text from HITL service]

To approve: Say "approve" or "potvrdi"
To reject: Say "reject" or "odbij"
```

**When successful:**
```
✅ Invoice fiscalized successfully!

JIR: 7a17ba67-3c3f-42e5-98ce-4586a02527b8
ZKI: 0B5C811B-E993A01E-824F15CF-63C3A295
Verification: https://porezna.gov.hr/rn?jir=...

PDF saved to: output/invoices/invoice_001_DEMO_1_7a17ba67.pdf

Next steps:
- Upload PDF to Drive? (say "upload to drive")
- Email to customer? (say "email to [email]")
```

**When error:**
```
❌ Fiscalization failed

Error: [error message]
Type: [PERMANENT or TRANSIENT]

[If PERMANENT]: Fix the issue and retry
[If TRANSIENT]: Invoice added to retry queue, will retry automatically
```

## CRITICAL: HITL (Human-in-the-Loop) Confirmation is MANDATORY

**NEVER skip the human confirmation step.** Before the deterministic executor sends the invoice to FINA,
the user MUST review and confirm the invoice data. This is a legal and financial safeguard.

When you call execute_fiscalization:
- The system will automatically present a confirmation prompt to the user
- Wait for the user's response ("potvrdi"/"approve" or "odbij"/"reject")
- Only proceed with FINA submission after user approval
- There is NO parameter to skip this step - it is enforced by the system

**DO NOT try to auto-approve, skip confirmation, or pass any auto-approve flags.**

## CRITICAL: KPD Code Confidence Check

When using search_kpd_code, ALWAYS check the confidence of the result:
- If confidence >= 0.5: Use the KPD code directly
- If confidence < 0.5: You MUST present the top 3 matches to the user and ask them to confirm or provide the correct KPD code
- If needs_review is True: Mention the suggested code to the user and ask for confirmation

Example when confidence is low:
```
KPD pretraga za "ugradnja PVC stolarije" je pronašla:
1. 43.32 - Ugradnja stolarije (confidence: 0.28)
2. 43.29 - Ostali instalacijski radovi (confidence: 0.22)
3. 22.23 - Proizvodi od plastike za graditeljstvo (confidence: 0.18)

Koji KPD kod želite koristiti? Ili unesite vlastiti kod.
```
"""

    # Import fiskalizacija tools
    from tools.adk_tools.fiskalizacija_adk_tools import (
        execute_fiscalization,
        get_supplier_data,
        generate_invoice_number,
        validate_oib,
        search_kpd_code,
        validate_kpd_code,
        calculate_tax,
    )
    tools = [
        execute_fiscalization,
        get_supplier_data,
        generate_invoice_number,
        validate_oib,
        search_kpd_code,
        validate_kpd_code,
        calculate_tax,
    ]

    if is_erp_enabled():
        from tools.adk_tools.erp_adk_tools import (
            erp_get_invoice,
            erp_search_customers,
            erp_get_product,
        )
        tools.extend([
            erp_get_invoice,
            erp_search_customers,
            erp_get_product,
        ])
    else:
        instructions += (
            "\n\nDeployment constraint: ERP is disabled in this environment. "
            "Do not fetch invoice, customer, or product context from ERP. "
            "Work only from user-provided invoice data and fiscalization tools."
        )

    # Create agent using factory with fiscalization tools
    agent = create_adk_agent(
        name="fiskalizacija",
        model=model,
        instruction=instructions,
        description="Croatian invoice fiscalization specialist. Handles complete fiscalization workflow: data preparation, validation, HITL confirmation, and deterministic execution with FINA. Keywords: fiskalizacija, racun, faktura, invoice, JIR, ZKI, FINA.",
        tools=tools,
        sub_agents=[],
        config={
            "temperature": temperature,
            "max_tokens": 2048
        },
        load_instruction_from_file=False  # We provide instructions directly
    )

    logger.info("Fiskalizacija agent created")

    return agent


def fiscalize_invoice_sync(
    invoice_data: dict,
    cert_path: str,
    cert_password: str,
    use_sandbox: bool = True,
    auto_approve: bool = None
) -> dict:
    """
    Synchronous helper function for fiscalization.

    This can be called directly for testing or from the agent.

    Args:
        invoice_data: Invoice data dictionary
        cert_path: Path to .p12 certificate
        cert_password: Certificate password
        use_sandbox: Use FINA sandbox (True) or production (False)
        auto_approve: Auto-approve HITL (None = check env var)

    Returns:
        Result dictionary with JIR or error info
    """
    from agents.adk_agents.fiskalizacija_orchestrator import (
        fiscalize_with_orchestrator
    )

    # Check auto-approve setting
    if auto_approve is None:
        auto_approve = os.environ.get('AUTO_APPROVE_HITL', 'false').lower() == 'true'

    # Set environment variable for orchestrator
    os.environ['AUTO_APPROVE_HITL'] = 'true' if auto_approve else 'false'

    # Call orchestrator
    result = fiscalize_with_orchestrator(
        invoice_data=invoice_data,
        cert_path=cert_path,
        cert_password=cert_password,
        use_sandbox=use_sandbox,
        skip_llm=True  # For now, use basic validation (LLM agents not yet fully integrated)
    )

    return result


# Export the agent factory
__all__ = ['create_fiskalizacija_agent', 'fiscalize_invoice_sync']

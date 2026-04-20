"""
Fiskalizacija Orchestrator - Hybrid Architecture (Proposal C)

This orchestrator implements the recommended hybrid integration pattern:
- LLM agents for preparation and validation (where "thinking" is needed)
- Deterministic executor for critical path (no LLM = no hallucinations)

Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                    FISKALIZACIJA ORCHESTRATOR                           │
    └─────────────────────────────────────────────────────────────────────────┘
                                      │
           ┌──────────────────────────┼──────────────────────────┐
           ▼                          ▼                          ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────────┐
    │  PRIPREMAC      │      │  VALIDATOR      │      │  DETERMINISTIC      │
    │    (LLM)        │ ───▶ │    (LLM)        │ ───▶ │  EXECUTOR           │
    │                 │      │                 │      │  (NO LLM!)          │
    │ • NKD classify  │      │ • Quality gate  │      │                     │
    │ • Tax help      │      │ • Format check  │      │ • sign_fina_xml()   │
    │ • Data enrich   │      │ • Decision      │      │ • send_to_fina()    │
    │ • OIB lookup    │      │ • Validation    │      │ • generate_qr()     │
    └─────────────────┘      └─────────────────┘      │ • save_ledger()     │
                                                      └─────────────────────┘

Key Design Principles:
1. LLM only where "intelligence" is genuinely needed
2. Critical cryptographic operations are 100% deterministic
3. Clear boundary between "thinking" and "executing"
4. Comprehensive audit trail at every step

Version: 1.0
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

logger = logging.getLogger(__name__)


# ============================================================================
# ORCHESTRATOR STATUS TYPES
# ============================================================================

class OrchestratorStatus(Enum):
    """Overall orchestration status."""
    SUCCESS = "success"
    NEEDS_REVIEW = "needs_review"  # Human-in-loop required
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    RETRY_QUEUED = "retry_queued"


class ValidationStatus(Enum):
    """Validator agent output status."""
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class InvoiceInput:
    """Input data for orchestrator - can be unstructured."""
    raw_text: str = ""  # Free-form text description
    structured_data: Dict[str, Any] = field(default_factory=dict)  # Pre-structured data

    # Certificate info
    cert_path: str = ""
    cert_password: str = ""

    # Environment
    use_sandbox: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PreparedData:
    """Output from Pripremac agent."""
    invoice_number: str
    supplier_oib: str
    supplier_name: str

    invoice_datetime: datetime
    total_amount: Decimal
    payment_method: str

    # VAT breakdown
    pdv_breakdown: List[Dict[str, str]]

    # Optional fields
    customer_oib: str = None
    customer_name: str = None
    operator_oib: str = None
    is_late_delivery: bool = False

    # Metadata from preparation
    nkd_codes: List[str] = None
    kpd_codes: List[Dict[str, Any]] = None  # With confidence scores
    preparation_notes: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        # Convert datetime to ISO format
        if isinstance(result.get('invoice_datetime'), datetime):
            result['invoice_datetime'] = result['invoice_datetime'].isoformat()
        # Convert Decimal to string
        if isinstance(result.get('total_amount'), Decimal):
            result['total_amount'] = str(result['total_amount'])
        return result


@dataclass
class ValidationResult:
    """Output from Validator agent."""
    status: ValidationStatus
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)

    # Items needing review
    needs_human_review: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OrchestratorResult:
    """Final result from orchestrator."""
    status: OrchestratorStatus
    success: bool

    # Fiscalization identifiers
    jir: Optional[str] = None
    zki: Optional[str] = None

    # QR code
    qr_code_base64: Optional[str] = None
    qr_code_svg: Optional[str] = None
    verification_url: Optional[str] = None

    # PDF
    pdf_path: Optional[str] = None

    # Error info
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # Audit trail
    preparation_notes: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)
    execution_notes: List[str] = field(default_factory=list)

    # Timing
    total_time_ms: int = 0
    preparation_time_ms: int = 0
    validation_time_ms: int = 0
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['status'] = self.status.value
        return result


# ============================================================================
# FISKALIZACIJA ORCHESTRATOR
# ============================================================================

class FiskalizacijaOrchestrator:
    """
    Main orchestrator for Croatian fiscalization.

    Implements Proposal C (Hybrid Integration):
    - LLM agents for preparation and validation
    - Deterministic executor for critical path
    """

    def __init__(
        self,
        cert_path: str,
        cert_password: str,
        use_sandbox: bool = True,
        use_ledger: bool = True,
        skip_llm: bool = False  # For testing - skip LLM agents
    ):
        """
        Initialize orchestrator.

        Args:
            cert_path: Path to .p12 certificate
            cert_password: Certificate password
            use_sandbox: Use FINA sandbox (True) or production (False)
            use_ledger: Enable idempotency checking
            skip_llm: Skip LLM agents (for testing with pre-prepared data)
        """
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.use_sandbox = use_sandbox
        self.use_ledger = use_ledger
        self.skip_llm = skip_llm

        # Initialize LLM agents (lazy loading)
        self._pripremac_agent = None
        self._validator_agent = None

        logger.info(f"Orchestrator initialized (sandbox={use_sandbox}, ledger={use_ledger})")

    def _get_pripremac_agent(self):
        """Lazy load Pripremac agent."""
        if self._pripremac_agent is None:
            from agents.adk_agents.fiskalni_pripremac_adk import create_fiskalni_pripremac_agent
            self._pripremac_agent = create_fiskalni_pripremac_agent()
        return self._pripremac_agent

    def _get_validator_agent(self):
        """Lazy load Validator agent."""
        if self._validator_agent is None:
            from agents.adk_agents.fiskalni_validator_adk import create_fiskalni_validator_agent
            self._validator_agent = create_fiskalni_validator_agent()
        return self._validator_agent

    async def process_invoice(
        self,
        input_data: InvoiceInput
    ) -> OrchestratorResult:
        """
        Process invoice through the complete pipeline.

        Steps:
        1. Preparation (LLM) - Transform unstructured data
        2. Validation (LLM) - Quality gate
        3. Execution (Deterministic) - Sign and send to FINA

        Args:
            input_data: Invoice input (structured or unstructured)

        Returns:
            OrchestratorResult with JIR/ZKI or error info
        """
        import time
        start_time = time.time()

        result = OrchestratorResult(
            status=OrchestratorStatus.SUCCESS,
            success=False
        )

        try:
            # ============================================================
            # STEP 1: PREPARATION (LLM)
            # ============================================================
            prep_start = time.time()

            if self.skip_llm and input_data.structured_data:
                # Use pre-structured data (for testing)
                prepared_data = self._convert_structured_input(input_data.structured_data)
                result.preparation_notes.append("Used pre-structured data (skip_llm=True)")
            else:
                # Use LLM agent to prepare data
                prepared_data = await self._run_preparation(input_data)
                result.preparation_notes.extend(prepared_data.preparation_notes or [])

            result.preparation_time_ms = int((time.time() - prep_start) * 1000)
            logger.info(f"Preparation completed in {result.preparation_time_ms}ms")

            # ============================================================
            # STEP 2: VALIDATION (LLM)
            # ============================================================
            val_start = time.time()

            if self.skip_llm:
                # Basic validation only
                validation_result = self._basic_validation(prepared_data)
                result.validation_notes.append("Used basic validation (skip_llm=True)")
            else:
                # Use LLM agent for comprehensive validation
                validation_result = await self._run_validation(prepared_data)
                result.validation_notes.extend(validation_result.validation_notes)

            result.validation_time_ms = int((time.time() - val_start) * 1000)
            logger.info(f"Validation completed in {result.validation_time_ms}ms")

            # Check validation result
            if validation_result.status == ValidationStatus.INVALID:
                result.status = OrchestratorStatus.VALIDATION_FAILED
                result.error_message = "; ".join(validation_result.errors)
                result.total_time_ms = int((time.time() - start_time) * 1000)
                return result

            if validation_result.status == ValidationStatus.NEEDS_REVIEW:
                result.status = OrchestratorStatus.NEEDS_REVIEW
                result.error_message = "Human review required"
                result.validation_notes.extend([
                    f"Review needed: {item}" for item in validation_result.needs_human_review
                ])
                result.total_time_ms = int((time.time() - start_time) * 1000)
                return result

            # ============================================================
            # STEP 3: HUMAN-IN-THE-LOOP CONFIRMATION
            # ============================================================
            hitl_start = time.time()

            # Check if HITL is enabled
            enable_hitl = os.environ.get('ENABLE_HITL', 'true').lower() == 'true'

            if enable_hitl:
                logger.info("Running HITL confirmation...")

                # Normalize data to nested format expected by HITL
                # (flat keys like supplier_oib -> nested supplier: {oib: ...})
                if input_data.structured_data:
                    invoice_data_for_hitl = self._normalize_for_hitl(input_data.structured_data)
                    logger.info("Normalized structured_data for HITL confirmation")
                else:
                    invoice_data_for_hitl = self._prepared_data_to_invoice_dict(prepared_data)
                    logger.info("Converting PreparedData for HITL confirmation")

                # Create confirmation
                from tools.api_implementations.hitl_confirmation import create_fiscalization_confirmation
                confirmation_result = create_fiscalization_confirmation(
                    invoice_data=invoice_data_for_hitl,
                    nkd_service=None  # TODO: Add NKD service when available
                )

                # Check if auto-approve
                auto_approve = os.environ.get('AUTO_APPROVE_HITL', 'false').lower() == 'true'

                if auto_approve:
                    # Auto-approve (for testing)
                    logger.info("Auto-approving HITL confirmation (AUTO_APPROVE_HITL=true)")
                    result.validation_notes.append("HITL confirmation: AUTO-APPROVED")
                else:
                    # Manual approval required
                    print("\n" + "="*80)
                    print(confirmation_result['display_text'])
                    print("="*80)

                    # Check for critical warnings
                    if confirmation_result.get('has_critical_warnings'):
                        result.status = OrchestratorStatus.VALIDATION_FAILED
                        result.error_message = "Critical warnings in HITL confirmation - cannot proceed"
                        result.total_time_ms = int((time.time() - start_time) * 1000)
                        return result

                    # Prompt user — terminal ili web approval flow
                    hitl_interface = os.environ.get('HITL_INTERFACE', 'terminal')

                    if hitl_interface == 'terminal':
                        user_input = input("\nŽelite li poslati račun na fiskalizaciju? (y/n): ")
                    elif hitl_interface == 'web':
                        # Web approval: write pending request to Firestore, poll for decision
                        from services.hitl_firestore_service import (
                            HITLFirestoreService, generate_confirmation_id
                        )
                        session_id = os.environ.get('CURRENT_SESSION_ID', 'unknown')
                        user_id = os.environ.get('CURRENT_USER_ID', 'web-user')
                        conf_id = generate_confirmation_id(session_id)

                        # Build a compact invoice summary for the dashboard card
                        invoice_summary = {
                            k: confirmation_result.get(k)
                            for k in (
                                'invoice_number', 'supplier_name', 'customer_name',
                                'total_amount', 'invoice_type', 'invoice_date'
                            )
                            if confirmation_result.get(k) is not None
                        }

                        hitl_svc = HITLFirestoreService()
                        await hitl_svc.create_pending(
                            confirmation_id=conf_id,
                            session_id=session_id,
                            user_id=user_id,
                            display_text=confirmation_result.get('display_text', ''),
                            invoice_summary=invoice_summary,
                            has_warnings=bool(confirmation_result.get('warnings')),
                        )
                        logger.info(
                            f"HITL: pending approval created '{conf_id}' — "
                            "waiting for web decision (max 5 min)"
                        )

                        decision = await hitl_svc.wait_for_decision(conf_id, timeout_seconds=300)

                        if decision['status'] == 'approved':
                            user_input = 'y'
                        elif decision['status'] == 'rejected':
                            user_input = 'n'
                        else:  # timeout
                            result.status = OrchestratorStatus.VALIDATION_FAILED
                            result.error_message = (
                                f"HITL approval timed out after 5 minutes. "
                                "Confirmation ID: " + conf_id
                            )
                            result.total_time_ms = int((time.time() - start_time) * 1000)
                            return result
                    else:
                        # scheduler or unknown — cannot block, fail with clear message
                        logger.warning(
                            f"HITL: interface '{hitl_interface}' ne podržava interaktivno odobrenje. "
                            "Postavite AUTO_APPROVE_HITL=true za scheduler kontekst."
                        )
                        result.status = OrchestratorStatus.VALIDATION_FAILED
                        result.error_message = (
                            f"HITL approval nije dostupan u '{hitl_interface}' modu. "
                            "Koristite AUTO_APPROVE_HITL=true za automatsko odobrenje."
                        )
                        result.total_time_ms = int((time.time() - start_time) * 1000)
                        return result

                    if user_input.lower() not in ['y', 'yes', 'da']:
                        result.status = OrchestratorStatus.VALIDATION_FAILED
                        result.error_message = "User rejected fiscalization"
                        result.validation_notes.append("HITL confirmation: REJECTED by user")
                        result.total_time_ms = int((time.time() - start_time) * 1000)
                        return result

                    result.validation_notes.append("HITL confirmation: APPROVED by user")

                hitl_time = int((time.time() - hitl_start) * 1000)
                logger.info(f"HITL confirmation completed in {hitl_time}ms")
            else:
                logger.info("HITL confirmation disabled (ENABLE_HITL=false)")
                result.validation_notes.append("HITL confirmation: DISABLED")

            # ============================================================
            # STEP 4: EXECUTION (DETERMINISTIC - NO LLM!)
            # ============================================================
            exec_start = time.time()

            execution_result = self._run_deterministic_execution(
                prepared_data=prepared_data,
                cert_path=input_data.cert_path or self.cert_path,
                cert_password=input_data.cert_password or self.cert_password
            )

            result.execution_time_ms = int((time.time() - exec_start) * 1000)
            logger.info(f"Execution completed in {result.execution_time_ms}ms")

            # Process execution result
            if execution_result.success:
                result.success = True
                result.status = OrchestratorStatus.SUCCESS
                result.jir = execution_result.jir
                result.zki = execution_result.zki
                result.qr_code_base64 = execution_result.qr_code_base64
                result.qr_code_svg = execution_result.qr_code_svg
                result.verification_url = execution_result.verification_url
                result.execution_notes.append(f"JIR received: {execution_result.jir}")
            else:
                # Check if error is transient (should retry)
                if execution_result.error_type == "transient":
                    result.status = OrchestratorStatus.RETRY_QUEUED
                    result.execution_notes.append(
                        f"Added to retry queue: {execution_result.error_message}"
                    )
                else:
                    result.status = OrchestratorStatus.EXECUTION_FAILED

                result.error_code = execution_result.error_code
                result.error_message = execution_result.error_message
                result.zki = execution_result.zki  # ZKI is generated before sending

        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            result.status = OrchestratorStatus.EXECUTION_FAILED
            result.error_message = str(e)

        result.total_time_ms = int((time.time() - start_time) * 1000)
        return result

    def _convert_structured_input(self, data: Dict[str, Any]) -> PreparedData:
        """Convert structured input dict to PreparedData."""
        # Parse datetime if string
        invoice_dt = data.get('invoice_datetime')
        if isinstance(invoice_dt, str):
            if 'T' in invoice_dt:
                invoice_dt = datetime.fromisoformat(invoice_dt)
            else:
                invoice_dt = datetime.strptime(invoice_dt, '%d.%m.%Y %H:%M:%S')
        elif invoice_dt is None:
            invoice_dt = datetime.now()

        # Parse amount
        total = data.get('total_amount', '0')
        if isinstance(total, str):
            total = Decimal(total)
        elif isinstance(total, (int, float)):
            total = Decimal(str(total))

        return PreparedData(
            invoice_number=data.get('invoice_number', ''),
            supplier_oib=data.get('supplier_oib', ''),
            supplier_name=data.get('supplier_name', ''),
            invoice_datetime=invoice_dt,
            total_amount=total,
            payment_method=data.get('payment_method', 'G'),
            pdv_breakdown=data.get('pdv_breakdown', []),
            customer_oib=data.get('customer_oib'),
            customer_name=data.get('customer_name'),
            operator_oib=data.get('operator_oib'),
            is_late_delivery=data.get('is_late_delivery', False),
            preparation_notes=["Converted from structured input"]
        )

    def _normalize_for_hitl(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize flat invoice_data dict into the nested format expected by HITL.

        execute_fiscalization uses flat keys (supplier_oib, customer_name, etc.)
        but HITL expects nested dicts (supplier: {oib, name}, customer: {oib, name}).
        Also calculates line_total and vat_amount for items.
        """
        from datetime import datetime as dt

        normalized = dict(data)

        # --- Supplier (flat -> nested) ---
        if 'supplier' not in normalized or not isinstance(normalized.get('supplier'), dict):
            normalized['supplier'] = {
                'name': data.get('supplier_name', ''),
                'oib': data.get('supplier_oib', ''),
                'address': data.get('supplier_address', 'Leskovački brijeg 2'),
                'city': data.get('supplier_city', 'Hrvatski Leskovac'),
                'postal_code': data.get('supplier_postal_code', '10257'),
            }

        # --- Customer (flat -> nested) ---
        if 'customer' not in normalized or not isinstance(normalized.get('customer'), dict):
            normalized['customer'] = {
                'name': data.get('customer_name', ''),
                'oib': data.get('customer_oib', ''),
                'address': data.get('customer_address', ''),
                'city': data.get('customer_city', ''),
                'postal_code': data.get('customer_postal_code', ''),
            }

        # --- Business unit & device from invoice_number ---
        invoice_number = normalized.get('invoice_number', '1/1/1')
        parts = invoice_number.split('/')
        if not normalized.get('business_unit'):
            normalized['business_unit'] = parts[1] if len(parts) > 1 else '1'
        if not normalized.get('device_number'):
            normalized['device_number'] = parts[2] if len(parts) > 2 else '1'

        # --- Dates ---
        if not normalized.get('invoice_date'):
            invoice_dt = data.get('invoice_datetime')
            if invoice_dt:
                if isinstance(invoice_dt, str):
                    try:
                        parsed = dt.fromisoformat(invoice_dt.replace('Z', '+00:00'))
                        normalized['invoice_date'] = parsed.strftime('%Y-%m-%d')
                        normalized['invoice_time'] = parsed.strftime('%H:%M:%S')
                    except ValueError:
                        normalized['invoice_date'] = dt.now().strftime('%Y-%m-%d')
                        normalized['invoice_time'] = dt.now().strftime('%H:%M:%S')
                elif isinstance(invoice_dt, dt):
                    normalized['invoice_date'] = invoice_dt.strftime('%Y-%m-%d')
                    normalized['invoice_time'] = invoice_dt.strftime('%H:%M:%S')
            else:
                normalized['invoice_date'] = dt.now().strftime('%Y-%m-%d')
                normalized['invoice_time'] = dt.now().strftime('%H:%M:%S')

        # --- Items: calculate line_total and vat_amount ---
        items = normalized.get('items', [])
        for item in items:
            quantity = float(item.get('quantity', 1))
            unit_price = float(item.get('unit_price', 0))
            vat_rate = float(item.get('vat_rate', 25))

            line_total = quantity * unit_price
            vat_amount = line_total * (vat_rate / 100)

            item['line_total'] = str(line_total)
            item['vat_amount'] = str(vat_amount)
            if not item.get('unit'):
                item['unit'] = item.get('unit_code', 'kom')
            # Map kpd_code to nkd_code for HITL display
            if item.get('kpd_code') and not item.get('nkd_code'):
                item['nkd_code'] = item['kpd_code']

        normalized['items'] = items

        return normalized

    def _prepared_data_to_invoice_dict(self, data: PreparedData) -> Dict[str, Any]:
        """
        Convert PreparedData back to invoice_data dict for HITL confirmation.

        HITL confirmation expects a specific format with supplier/customer objects.
        """
        # Parse invoice number for business_unit and device_number
        # Format: XXX/PP/NU where PP=business_unit, NU=device_number
        parts = data.invoice_number.split('/')
        business_unit = parts[1] if len(parts) > 1 else "1"
        device_number = parts[2] if len(parts) > 2 else "1"

        # Format datetime
        if isinstance(data.invoice_datetime, datetime):
            invoice_date = data.invoice_datetime.strftime('%Y-%m-%d')
            invoice_time = data.invoice_datetime.strftime('%H:%M:%S')
        else:
            invoice_date = "2026-01-01"
            invoice_time = "12:00:00"

        # Build invoice_data dict
        invoice_data = {
            "invoice_number": data.invoice_number,
            "invoice_date": invoice_date,
            "invoice_time": invoice_time,
            "business_unit": business_unit,
            "device_number": device_number,
            "supplier": {
                "name": data.supplier_name or "Unknown Supplier",
                "oib": data.supplier_oib,
                "address": "",  # Not in PreparedData
                "city": "",
                "postal_code": ""
            },
            "customer": {
                "name": data.customer_name or "Unknown Customer",
                "oib": data.customer_oib or "",
                "address": "",
                "city": "",
                "postal_code": ""
            },
            "items": [],  # Would be populated from pdv_breakdown
            "tax_breakdown": {
                "total_net": str(data.total_amount),
                "total_gross": str(data.total_amount),
                "subtotals": []
            }
        }

        # Add VAT breakdown if available
        if data.pdv_breakdown:
            for pdv_item in data.pdv_breakdown:
                invoice_data["tax_breakdown"]["subtotals"].append({
                    "vat_rate": pdv_item.get("stopa", "25"),
                    "taxable_amount": pdv_item.get("osnovica", "0"),
                    "tax_amount": pdv_item.get("iznos", "0")
                })

        return invoice_data

    async def _run_preparation(self, input_data: InvoiceInput) -> PreparedData:
        """Run LLM-based preparation."""
        # TODO: Implement actual LLM agent call
        # For now, return converted structured data if available
        if input_data.structured_data:
            return self._convert_structured_input(input_data.structured_data)

        raise NotImplementedError("LLM preparation from raw text not yet implemented")

    async def _run_validation(self, prepared_data: PreparedData) -> ValidationResult:
        """Run LLM-based validation."""
        # TODO: Implement actual LLM agent call
        # For now, use basic validation
        return self._basic_validation(prepared_data)

    def _basic_validation(self, data: PreparedData) -> ValidationResult:
        """Basic validation without LLM."""
        errors = []
        warnings = []

        # Check OIB format
        if not data.supplier_oib or len(data.supplier_oib) != 11:
            errors.append(f"Invalid supplier OIB: {data.supplier_oib}")

        # Check invoice number format
        if not data.invoice_number or '/' not in data.invoice_number:
            errors.append(f"Invalid invoice number format: {data.invoice_number}")

        # Check amount
        if data.total_amount <= 0:
            errors.append(f"Invalid amount: {data.total_amount}")

        # Check payment method
        if data.payment_method not in ['G', 'K', 'T', 'O']:
            errors.append(f"Invalid payment method: {data.payment_method}")

        if errors:
            return ValidationResult(
                status=ValidationStatus.INVALID,
                is_valid=False,
                errors=errors,
                warnings=warnings,
                validation_notes=["Basic validation failed"]
            )

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            errors=[],
            warnings=warnings,
            validation_notes=["Basic validation passed"]
        )

    def _run_deterministic_execution(
        self,
        prepared_data: PreparedData,
        cert_path: str,
        cert_password: str
    ):
        """
        Run DETERMINISTIC execution - NO LLM INVOLVEMENT.

        This is the critical path where we need 100% predictability.
        """
        from tools.api_implementations.deterministic_executor import (
            DeterministicFiscalExecutor,
            ExecutorInput
        )

        # Convert PreparedData to ExecutorInput
        input_data = ExecutorInput(
            invoice_number=prepared_data.invoice_number,
            supplier_oib=prepared_data.supplier_oib,
            cert_path=cert_path,
            cert_password=cert_password,
            invoice_datetime=prepared_data.invoice_datetime,
            total_amount=prepared_data.total_amount,
            payment_method=prepared_data.payment_method,
            pdv_breakdown=prepared_data.pdv_breakdown,
            operator_oib=prepared_data.operator_oib,
            is_late_delivery=prepared_data.is_late_delivery,
            use_sandbox=self.use_sandbox
        )

        # Execute deterministically with Firestore persistence
        use_firestore = os.environ.get('USE_FIRESTORE', 'true').lower() == 'true'
        executor = DeterministicFiscalExecutor(
            use_ledger=self.use_ledger,
            use_firestore=use_firestore
        )
        return executor.execute(input_data)


# ============================================================================
# SYNCHRONOUS WRAPPER
# ============================================================================

def fiscalize_with_orchestrator(
    invoice_data: Dict[str, Any],
    cert_path: str,
    cert_password: str,
    use_sandbox: bool = True,
    skip_llm: bool = True
) -> Dict[str, Any]:
    """
    Synchronous convenience function for fiscalization.

    Args:
        invoice_data: Invoice data dictionary
        cert_path: Path to certificate
        cert_password: Certificate password
        use_sandbox: Use FINA sandbox
        skip_llm: Skip LLM agents (use basic validation only)

    Returns:
        Dictionary with results

    Example:
        result = fiscalize_with_orchestrator(
            invoice_data={
                "invoice_number": "001/1/1",
                "supplier_oib": "12345678901",
                "supplier_name": "Test Company",
                "total_amount": "125.00",
                "payment_method": "G",
                "pdv_breakdown": [{"stopa": "25.00", "osnovica": "100.00", "iznos": "25.00"}]
            },
            cert_path="company.p12",
            cert_password="password"
        )
    """
    import asyncio

    orchestrator = FiskalizacijaOrchestrator(
        cert_path=cert_path,
        cert_password=cert_password,
        use_sandbox=use_sandbox,
        skip_llm=skip_llm
    )

    input_data = InvoiceInput(
        structured_data=invoice_data,
        cert_path=cert_path,
        cert_password=cert_password,
        use_sandbox=use_sandbox
    )

    # Run async in sync context
    result = asyncio.run(orchestrator.process_invoice(input_data))

    # Generate PDF if fiscalization was successful
    if result.success and result.jir:
        try:
            from tools.adk_tools.fiskalizacija_adk_tools import generate_invoice_pdf

            # Run PDF generation in async context
            pdf_result = asyncio.run(generate_invoice_pdf(
                invoice_data=invoice_data,
                jir=result.jir,
                zki=result.zki,
                qr_code_base64=result.qr_code_base64
            ))

            if pdf_result.get('success'):
                result.pdf_path = pdf_result.get('pdf_path')
                logger.info(f"PDF generated: {result.pdf_path}")
            else:
                logger.warning(f"PDF generation failed: {pdf_result.get('error')}")

        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            # Don't fail entire fiscalization if PDF generation fails

    return result.to_dict()


# ============================================================================
# MAIN (Testing)
# ============================================================================

if __name__ == "__main__":
    from pathlib import Path

    # Test configuration
    project_root = Path(__file__).parent.parent.parent
    CERT_PATH = os.environ.get("FINA_CERT_PATH") or str(project_root / "47034854402.F1.1.p12")
    CERT_PASSWORD = os.environ.get("FINA_CERT_PASSWORD")
    if not CERT_PASSWORD:
        raise SystemExit(
            "FINA_CERT_PASSWORD is not set. "
            "Export it in your shell (or .env) before running this demo."
        )

    # Test invoice
    test_invoice = {
        "invoice_number": f"TEST{datetime.now().strftime('%H%M%S')}/1/1",
        "supplier_oib": "47034854402",
        "supplier_name": "LUX TECH D.O.O.",
        "invoice_datetime": datetime.now().isoformat(),
        "total_amount": "125.00",
        "payment_method": "G",
        "pdv_breakdown": [
            {"stopa": "25.00", "osnovica": "100.00", "iznos": "25.00"}
        ]
    }

    print("=" * 70)
    print("   FISKALIZACIJA ORCHESTRATOR TEST")
    print("=" * 70)
    print(f"Invoice: {test_invoice['invoice_number']}")
    print(f"Amount: {test_invoice['total_amount']} EUR")
    print()

    result = fiscalize_with_orchestrator(
        invoice_data=test_invoice,
        cert_path=CERT_PATH,
        cert_password=CERT_PASSWORD,
        use_sandbox=True,
        skip_llm=True  # Use basic validation
    )

    print("RESULT:")
    print(f"  Status: {result['status']}")
    print(f"  Success: {result['success']}")

    if result['success']:
        print(f"  JIR: {result['jir']}")
        print(f"  ZKI: {result['zki']}")
        print(f"  QR URL: {result['verification_url']}")
    else:
        print(f"  Error: {result.get('error_message')}")

    print(f"\nTiming:")
    print(f"  Preparation: {result['preparation_time_ms']}ms")
    print(f"  Validation: {result['validation_time_ms']}ms")
    print(f"  Execution: {result['execution_time_ms']}ms")
    print(f"  Total: {result['total_time_ms']}ms")

"""
Deterministic Fiscal Executor - NO LLM INVOLVEMENT

This is the critical path executor for Croatian Fiskalizacija 2.0.
All operations are deterministic - same input ALWAYS produces same output.

IMPORTANT: This module should NEVER involve LLM calls.
All "thinking" is done by LLM agents BEFORE this executor runs.

Architecture (Proposal C - Hybrid Integration):
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐
    │ pripremac_agent │───▶│ validator_agent │───▶│ DeterministicFiscal │
    │     (LLM)       │    │     (LLM)       │    │ Executor (NO LLM!)  │
    └─────────────────┘    └─────────────────┘    └─────────────────────┘

Functions (all deterministic):
    1. build_racun_zahtjev() - XML generation
    2. calculate_zki() - Cryptographic ZKI calculation
    3. sign_fina_xml() - RSA-SHA1 digital signature
    4. send_to_fina() - SOAP communication
    5. generate_verification_qr() - QR code generation
    6. save_to_ledger() - Audit trail

Error Categories:
    - PERMANENT: Bad OIB, schema error, invalid cert - don't retry
    - TRANSIENT: Network timeout, server busy - add to retry queue

Version: 1.0
Author: Fiskalizacija 2.0 Implementation
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import tempfile
import os

# Cryptography
try:
    from cryptography.hazmat.primitives import serialization
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

# HTTP
try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================================
# ERROR CLASSIFICATION
# ============================================================================

class ErrorType(Enum):
    """Error type for retry logic."""
    PERMANENT = "permanent"  # Don't retry - bad data, invalid cert, etc.
    TRANSIENT = "transient"  # Retry - network, server busy, timeout


# FINA error codes classification
FINA_ERROR_CODES = {
    # Permanent errors - don't retry
    "s001": (ErrorType.PERMANENT, "Schema validation error"),
    "s002": (ErrorType.PERMANENT, "Invalid OIB"),
    "s003": (ErrorType.PERMANENT, "Invalid certificate"),
    "s004": (ErrorType.PERMANENT, "Invalid digital signature"),
    "s005": (ErrorType.PERMANENT, "Invalid ZKI"),
    "s006": (ErrorType.PERMANENT, "Invalid invoice number format"),
    "s007": (ErrorType.PERMANENT, "Invalid business premises"),
    "s008": (ErrorType.PERMANENT, "Invalid date/time format"),
    "s009": (ErrorType.PERMANENT, "Invalid amount format"),
    "s010": (ErrorType.PERMANENT, "Invalid payment method"),
    "s011": (ErrorType.PERMANENT, "Certificate not authorized for OIB"),
    "s012": (ErrorType.PERMANENT, "Duplicate invoice (already fiscalized)"),

    # Transient errors - retry
    "p001": (ErrorType.TRANSIENT, "Service temporarily unavailable"),
    "p002": (ErrorType.TRANSIENT, "Server busy"),
    "p003": (ErrorType.TRANSIENT, "Request timeout"),
    "p004": (ErrorType.TRANSIENT, "Database temporarily unavailable"),
}


def classify_fina_error(error_code: str) -> tuple:
    """
    Classify FINA error code for retry logic.

    Returns:
        Tuple of (ErrorType, description)
    """
    error_code_lower = error_code.lower() if error_code else ""

    if error_code_lower in FINA_ERROR_CODES:
        return FINA_ERROR_CODES[error_code_lower]

    # Default: assume transient if unknown
    if error_code_lower.startswith('p'):
        return (ErrorType.TRANSIENT, f"Unknown processing error: {error_code}")

    return (ErrorType.PERMANENT, f"Unknown schema/validation error: {error_code}")


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ExecutorInput:
    """Input data for DeterministicFiscalExecutor."""
    # Invoice identification
    invoice_number: str  # Format: XXX/PP/NU
    supplier_oib: str

    # Certificate
    cert_path: str
    cert_password: str

    # Invoice data
    invoice_datetime: datetime
    total_amount: Decimal
    payment_method: str  # G=cash, K=card, T=transfer, O=other

    # VAT breakdown (optional)
    pdv_breakdown: list = None  # List of {"stopa": "25.00", "osnovica": "100.00", "iznos": "25.00"}

    # Operator
    operator_oib: str = None  # Defaults to supplier_oib

    # Options
    is_late_delivery: bool = False  # Naknadna dostava
    use_sandbox: bool = True

    def __post_init__(self):
        if self.operator_oib is None:
            self.operator_oib = self.supplier_oib


@dataclass
class ExecutorResult:
    """Result from DeterministicFiscalExecutor."""
    success: bool

    # Identifiers
    jir: Optional[str] = None
    zki: Optional[str] = None

    # Generated artifacts
    signed_xml: Optional[str] = None
    qr_code_base64: Optional[str] = None
    qr_code_svg: Optional[str] = None
    verification_url: Optional[str] = None

    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # "permanent" or "transient"

    # FINA response
    fina_response: Optional[str] = None
    http_status: Optional[int] = None

    # Timing
    execution_time_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# DETERMINISTIC FISCAL EXECUTOR
# ============================================================================

class DeterministicFiscalExecutor:
    """
    Executes fiscalization without any LLM involvement.

    All operations are deterministic:
    - Same input = same output (for signing, ZKI, XML)
    - Network operations may fail transiently

    This class should be called ONLY after LLM agents have:
    1. Prepared the data (fiskalni_pripremac)
    2. Validated the data (fiskalni_validator)

    Usage:
        executor = DeterministicFiscalExecutor()
        result = executor.execute(input_data)

        if result.success:
            print(f"JIR: {result.jir}")
        elif result.error_type == "transient":
            # Add to retry queue
            pass
        else:
            # Permanent error - notify user
            pass
    """

    SANDBOX_URL = "https://cistest.apis-it.hr:8449/FiskalizacijaServiceTest"
    PRODUCTION_URL = "https://cis.porezna-uprava.hr:8449/FiskalizacijaService"

    def __init__(self, use_ledger: bool = True, use_firestore: bool = False):
        """
        Initialize executor.

        Args:
            use_ledger: Enable idempotency checking and audit logging
            use_firestore: Use Firestore (True) or in-memory ledger (False)
        """
        self.use_ledger = use_ledger
        self.use_firestore = use_firestore
        self._cert_info = None

    def execute(self, input_data: ExecutorInput) -> ExecutorResult:
        """
        Execute complete fiscalization flow.

        Steps:
            1. Check idempotency (already fiscalized?)
            2. Load certificate
            3. Build RacunZahtjev XML
            4. Calculate ZKI
            5. Sign XML
            6. Send to FINA
            7. Parse response
            8. Generate QR code
            9. Save to ledger

        Args:
            input_data: ExecutorInput with all required data

        Returns:
            ExecutorResult with JIR/ZKI or error info
        """
        import time
        start_time = time.time()

        try:
            # Step 0: Idempotency check
            if self.use_ledger:
                existing = self._check_idempotency(input_data)
                if existing:
                    logger.info(f"Invoice {input_data.invoice_number} already fiscalized")

                    # Regenerate QR code for the existing invoice
                    existing_jir = existing.get("jir")
                    existing_zki = existing.get("zki")
                    qr_code_base64 = None
                    qr_code_svg = None
                    verification_url = None

                    try:
                        from tools.api_implementations.fina_soap_client import generate_verification_qr
                        qr_result = generate_verification_qr(
                            jir=existing_jir,
                            zki=existing_zki,
                            invoice_datetime=input_data.invoice_datetime.strftime("%d.%m.%YT%H:%M:%S"),
                            total_amount=str(input_data.total_amount),
                            oib=input_data.supplier_oib,
                            use_jir=True
                        )
                        qr_code_base64 = qr_result.get("qr_code_base64")
                        qr_code_svg = qr_result.get("qr_code_svg")
                        verification_url = qr_result.get("verification_url")
                    except Exception as qr_err:
                        logger.warning(f"QR regeneration for idempotent return failed: {qr_err}")

                    return ExecutorResult(
                        success=True,
                        jir=existing_jir,
                        zki=existing_zki,
                        qr_code_base64=qr_code_base64,
                        qr_code_svg=qr_code_svg,
                        verification_url=verification_url,
                        error_message="Already fiscalized (idempotent return)"
                    )

            # Step 1: Load certificate
            cert_info = self._load_certificate(input_data.cert_path, input_data.cert_password)

            # Step 2: Parse invoice number
            parts = input_data.invoice_number.split("/")
            if len(parts) != 3:
                return ExecutorResult(
                    success=False,
                    error_code="E001",
                    error_message=f"Invalid invoice number format: {input_data.invoice_number}. Expected: XXX/PP/NU",
                    error_type=ErrorType.PERMANENT.value
                )

            broj_racuna, oznaka_pp, oznaka_nu = parts

            # Step 3: Calculate ZKI
            from tools.api_implementations.xades_signer import calculate_zki

            zki = calculate_zki(
                oib=input_data.supplier_oib,
                invoice_datetime=input_data.invoice_datetime,
                invoice_number=broj_racuna,
                business_unit=oznaka_pp,
                device_number=oznaka_nu,
                total_amount=input_data.total_amount,
                private_key=cert_info.private_key
            )

            logger.info(f"ZKI calculated: {zki}")

            # Step 4: Build RacunZahtjev XML
            from tools.api_implementations.fina_xml_builder import build_racun_zahtjev

            racun_xml = build_racun_zahtjev(
                oib=input_data.supplier_oib,
                u_sustavu_pdv=True,
                datum_vrijeme=input_data.invoice_datetime,
                oznaka_slijednosti="P",  # Paragon (real-time)
                broj_racuna=broj_racuna,
                oznaka_poslovnog_prostora=oznaka_pp,
                oznaka_naplatnog_uredaja=oznaka_nu,
                ukupan_iznos=str(input_data.total_amount),
                nacin_placanja=input_data.payment_method,
                oib_operatera=input_data.operator_oib,
                zki=zki,
                pdv=input_data.pdv_breakdown,
                naknadna_dostava=input_data.is_late_delivery
            )

            logger.info(f"RacunZahtjev XML built ({len(racun_xml)} bytes)")

            # Step 5: Sign XML
            from tools.api_implementations.xades_signer import sign_fina_xml

            signed_xml = sign_fina_xml(
                racun_xml,
                cert_info.private_key,
                cert_info.certificate
            )

            logger.info(f"XML signed ({len(signed_xml)} bytes)")

            # Step 6: Send to FINA
            fina_url = self.SANDBOX_URL if input_data.use_sandbox else self.PRODUCTION_URL

            result = self._send_to_fina(
                signed_xml=signed_xml,
                cert_info=cert_info,
                url=fina_url
            )

            execution_time = int((time.time() - start_time) * 1000)

            # Step 7: Process result
            if result.get("success"):
                jir = result.get("jir")

                # Step 8: Generate QR code
                from tools.api_implementations.fina_soap_client import generate_verification_qr

                qr_result = generate_verification_qr(
                    jir=jir,
                    zki=zki,
                    invoice_datetime=input_data.invoice_datetime.strftime("%d.%m.%YT%H:%M:%S"),
                    total_amount=str(input_data.total_amount),
                    oib=input_data.supplier_oib,
                    use_jir=True
                )

                if not qr_result.get("success"):
                    logger.warning(f"QR code generation failed: {qr_result.get('error', 'unknown')}")
                else:
                    logger.info(f"QR code generated: {len(qr_result.get('qr_code_base64', '') or '')} chars base64")

                # Step 9: Save to ledger
                if self.use_ledger:
                    self._save_to_ledger(
                        input_data=input_data,
                        jir=jir,
                        zki=zki,
                        signed_xml=signed_xml,
                        fina_response=result.get("raw_response", "")
                    )

                return ExecutorResult(
                    success=True,
                    jir=jir,
                    zki=zki,
                    signed_xml=signed_xml,
                    qr_code_base64=qr_result.get("qr_code_base64"),
                    qr_code_svg=qr_result.get("qr_code_svg"),
                    verification_url=qr_result.get("verification_url"),
                    fina_response=result.get("raw_response"),
                    http_status=result.get("http_status"),
                    execution_time_ms=execution_time
                )
            else:
                # Handle FINA error
                error_code = result.get("error_code", "UNKNOWN")
                error_type, error_desc = classify_fina_error(error_code)

                error_message = result.get("error_message", error_desc)

                # Add to retry queue if transient
                if self.use_ledger and error_type == ErrorType.TRANSIENT:
                    self._add_to_retry_queue(
                        input_data=input_data,
                        signed_xml=signed_xml,
                        zki=zki,
                        error_message=error_message
                    )

                return ExecutorResult(
                    success=False,
                    zki=zki,
                    signed_xml=signed_xml,
                    error_code=error_code,
                    error_message=error_message,
                    error_type=error_type.value,
                    fina_response=result.get("raw_response"),
                    http_status=result.get("http_status"),
                    execution_time_ms=execution_time
                )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Executor error: {e}")

            return ExecutorResult(
                success=False,
                error_code="E999",
                error_message=str(e),
                error_type=ErrorType.PERMANENT.value,
                execution_time_ms=execution_time
            )

    def _load_certificate(self, cert_path: str, cert_password: str):
        """Load certificate from .p12 file."""
        from tools.api_implementations.xades_signer import load_certificate_from_file
        return load_certificate_from_file(cert_path, cert_password)

    def _send_to_fina(
        self,
        signed_xml: str,
        cert_info,
        url: str
    ) -> Dict[str, Any]:
        """Send signed XML to FINA."""
        from tools.api_implementations.fina_soap_client import (
            build_fiscalization_request,
            parse_fina_response
        )

        if not REQUESTS_AVAILABLE:
            return {
                "success": False,
                "error_code": "E002",
                "error_message": "requests library not available"
            }

        try:
            # Build SOAP envelope
            soap_message = build_fiscalization_request(signed_xml)

            # Create temp PEM file for mTLS
            key_pem = cert_info.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
            cert_pem = cert_info.certificate.public_bytes(serialization.Encoding.PEM)

            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                f.write(key_pem)
                combined_pem = f.name

            try:
                session = requests.Session()
                session.cert = combined_pem
                session.verify = False  # FINA uses self-signed cert in sandbox

                response = session.post(
                    url,
                    data=soap_message.encode('utf-8'),
                    headers={'Content-Type': 'text/xml; charset=utf-8'},
                    timeout=30
                )

                logger.info(f"FINA response: HTTP {response.status_code}")

                # Parse response
                result = parse_fina_response(response.text)
                result["http_status"] = response.status_code
                result["raw_response"] = response.text

                return result

            finally:
                os.unlink(combined_pem)

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error_code": "p003",
                "error_message": "Request timeout"
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "error_code": "p001",
                "error_message": f"Connection error: {e}"
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": "E003",
                "error_message": str(e)
            }

    def _check_idempotency(self, input_data: ExecutorInput) -> Optional[Dict[str, Any]]:
        """Check if invoice already fiscalized."""
        from tools.api_implementations.fiskalizacija_ledger import check_invoice_ledger

        result = check_invoice_ledger(
            invoice_number=input_data.invoice_number,
            supplier_oib=input_data.supplier_oib,
            use_firestore=self.use_firestore
        )

        if result.get("exists") and result.get("jir"):
            return result

        return None

    def _save_to_ledger(
        self,
        input_data: ExecutorInput,
        jir: str,
        zki: str,
        signed_xml: str,
        fina_response: str
    ) -> None:
        """Save successful fiscalization to ledger."""
        from tools.api_implementations.fiskalizacija_ledger import save_to_ledger

        save_to_ledger(
            invoice_number=input_data.invoice_number,
            supplier_oib=input_data.supplier_oib,
            jir=jir,
            zki=zki,
            signed_xml=signed_xml,
            fina_response=fina_response,
            total_amount=str(input_data.total_amount),
            use_firestore=self.use_firestore
        )

    def _add_to_retry_queue(
        self,
        input_data: ExecutorInput,
        signed_xml: str,
        zki: str,
        error_message: str
    ) -> None:
        """Add failed fiscalization to retry queue."""
        from tools.api_implementations.fiskalizacija_ledger import add_to_retry

        add_to_retry(
            invoice_number=input_data.invoice_number,
            supplier_oib=input_data.supplier_oib,
            signed_xml=signed_xml,
            zki=zki,
            error_message=error_message,
            use_firestore=self.use_firestore
        )


# ============================================================================
# CONVENIENCE FUNCTION FOR SIMPLE USAGE
# ============================================================================

def fiscalize_invoice(
    invoice_number: str,
    supplier_oib: str,
    invoice_datetime: datetime,
    total_amount: Decimal,
    payment_method: str,
    cert_path: str,
    cert_password: str,
    pdv_breakdown: list = None,
    operator_oib: str = None,
    is_late_delivery: bool = False,
    use_sandbox: bool = True,
    use_ledger: bool = True
) -> Dict[str, Any]:
    """
    Fiscalize an invoice with minimal parameters.

    This is a convenience function that wraps DeterministicFiscalExecutor.

    Args:
        invoice_number: Invoice number in format XXX/PP/NU
        supplier_oib: Company OIB (11 digits)
        invoice_datetime: Invoice date and time
        total_amount: Total invoice amount in EUR
        payment_method: Payment method (G=cash, K=card, T=transfer, O=other)
        cert_path: Path to .p12 certificate file
        cert_password: Certificate password
        pdv_breakdown: Optional VAT breakdown list
        operator_oib: Optional operator OIB (defaults to supplier_oib)
        is_late_delivery: Is this a late delivery (naknadna dostava)
        use_sandbox: Use FINA sandbox (True) or production (False)
        use_ledger: Enable idempotency and audit logging

    Returns:
        Dictionary with:
            - success: bool
            - jir: JIR from FINA (if successful)
            - zki: ZKI code
            - qr_code_base64: QR code as base64 PNG
            - verification_url: URL for QR code
            - error_code: Error code (if failed)
            - error_message: Error message (if failed)
            - error_type: "permanent" or "transient"

    Example:
        result = fiscalize_invoice(
            invoice_number="001/1/1",
            supplier_oib="12345678901",
            invoice_datetime=datetime.now(),
            total_amount=Decimal("125.00"),
            payment_method="G",
            cert_path="company.p12",
            cert_password="password"
        )

        if result["success"]:
            print(f"JIR: {result['jir']}")
        else:
            print(f"Error: {result['error_message']}")
    """
    input_data = ExecutorInput(
        invoice_number=invoice_number,
        supplier_oib=supplier_oib,
        cert_path=cert_path,
        cert_password=cert_password,
        invoice_datetime=invoice_datetime,
        total_amount=total_amount,
        payment_method=payment_method,
        pdv_breakdown=pdv_breakdown,
        operator_oib=operator_oib,
        is_late_delivery=is_late_delivery,
        use_sandbox=use_sandbox
    )

    executor = DeterministicFiscalExecutor(use_ledger=use_ledger)
    result = executor.execute(input_data)

    return result.to_dict()


# ============================================================================
# RETRY PROCESSOR
# ============================================================================

class RetryProcessor:
    """
    Processes retry queue for failed fiscalizations.

    Should be run periodically (e.g., via cron or Cloud Scheduler).
    Respects 48h deadline per Croatian law.
    """

    def __init__(self, cert_path: str, cert_password: str, use_sandbox: bool = True):
        """
        Initialize retry processor.

        Args:
            cert_path: Path to certificate file
            cert_password: Certificate password
            use_sandbox: Use FINA sandbox or production
        """
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.use_sandbox = use_sandbox
        self.executor = DeterministicFiscalExecutor(use_ledger=True)

    def process_pending_retries(self) -> Dict[str, Any]:
        """
        Process all pending retries.

        Returns:
            Dictionary with:
                - processed: Number of retries processed
                - successful: Number that succeeded
                - failed: Number that failed again
                - expired: Number past 48h deadline
        """
        from tools.api_implementations.fiskalizacija_ledger import get_ledger_service

        service = get_ledger_service()
        pending = service.get_pending_retries()

        stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "expired": 0,
            "details": []
        }

        for entry in pending:
            stats["processed"] += 1

            # Check deadline
            deadline = datetime.fromisoformat(entry["deadline"].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) >= deadline:
                stats["expired"] += 1
                stats["details"].append({
                    "invoice": entry["invoice_number"],
                    "status": "expired",
                    "message": "48h deadline exceeded"
                })
                continue

            # Retry with stored signed_xml
            # Note: For retry, we already have signed XML, so we just re-send
            result = self._retry_send(entry)

            if result.get("success"):
                stats["successful"] += 1
                stats["details"].append({
                    "invoice": entry["invoice_number"],
                    "status": "success",
                    "jir": result.get("jir")
                })
            else:
                stats["failed"] += 1
                stats["details"].append({
                    "invoice": entry["invoice_number"],
                    "status": "failed",
                    "error": result.get("error_message")
                })

        logger.info(
            f"Retry processing complete: {stats['successful']} successful, "
            f"{stats['failed']} failed, {stats['expired']} expired"
        )

        return stats

    def _retry_send(self, entry: dict) -> Dict[str, Any]:
        """Retry sending a stored signed XML."""
        from tools.api_implementations.xades_signer import load_certificate_from_file
        from tools.api_implementations.fina_soap_client import (
            build_fiscalization_request,
            parse_fina_response
        )
        from tools.api_implementations.fiskalizacija_ledger import (
            save_to_ledger,
            add_to_retry
        )

        try:
            cert_info = load_certificate_from_file(self.cert_path, self.cert_password)

            url = (
                DeterministicFiscalExecutor.SANDBOX_URL
                if self.use_sandbox
                else DeterministicFiscalExecutor.PRODUCTION_URL
            )

            result = self.executor._send_to_fina(
                signed_xml=entry["signed_xml"],
                cert_info=cert_info,
                url=url
            )

            if result.get("success"):
                # Save to ledger
                save_to_ledger(
                    invoice_number=entry["invoice_number"],
                    supplier_oib=entry["supplier_oib"],
                    jir=result["jir"],
                    zki=entry["zki"],
                    signed_xml=entry["signed_xml"],
                    fina_response=result.get("raw_response", "")
                )
            else:
                # Update retry queue
                error_type, _ = classify_fina_error(result.get("error_code", ""))

                if error_type == ErrorType.TRANSIENT:
                    add_to_retry(
                        invoice_number=entry["invoice_number"],
                        supplier_oib=entry["supplier_oib"],
                        signed_xml=entry["signed_xml"],
                        zki=entry["zki"],
                        error_message=result.get("error_message", "Unknown error")
                    )

            return result

        except Exception as e:
            logger.error(f"Retry failed for {entry['invoice_number']}: {e}")
            return {
                "success": False,
                "error_code": "E999",
                "error_message": str(e)
            }

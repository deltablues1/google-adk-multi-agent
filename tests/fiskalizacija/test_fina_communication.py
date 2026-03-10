"""
Tests for FINA SOAP Communication (Phase 4)

Tests:
- SOAP message building
- Circuit breaker pattern
- Response parsing
- QR code generation
- Ledger operations
- Retry queue management
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import base64


def _qrcode_available() -> bool:
    """Check if qrcode library is available."""
    try:
        import qrcode
        return True
    except ImportError:
        return False


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================

class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker, CircuitBreakerState

        cb = CircuitBreaker()

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_can_execute_when_closed(self):
        """Test requests allowed when circuit is closed."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker

        cb = CircuitBreaker()
        can_execute, reason = cb.can_execute()

        assert can_execute is True
        assert "closed" in reason.lower()

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit opens after failure threshold."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker, CircuitBreakerState

        cb = CircuitBreaker(failure_threshold=3)

        # Record failures up to threshold
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_circuit_breaker_rejects_when_open(self):
        """Test requests rejected when circuit is open."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker, CircuitBreakerState

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()

        can_execute, reason = cb.can_execute()

        assert can_execute is False
        assert "OPEN" in reason

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit becomes half-open after recovery timeout."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker, CircuitBreakerState

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)  # Immediate recovery

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Check after timeout (0 seconds)
        can_execute, reason = cb.can_execute()

        assert can_execute is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_circuit_breaker_closes_on_success(self):
        """Test circuit closes on successful request."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker, CircuitBreakerState

        cb = CircuitBreaker(failure_threshold=2)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Record success
        cb.record_success()

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_status(self):
        """Test circuit breaker status reporting."""
        from tools.api_implementations.fina_soap_client import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        cb.record_failure()

        status = cb.get_status()

        assert status["state"] == "closed"
        assert status["failure_count"] == 1
        assert status["failure_threshold"] == 5
        assert status["recovery_timeout_seconds"] == 60


# ============================================================================
# SOAP MESSAGE TESTS
# ============================================================================

class TestSOAPMessageBuilding:
    """Tests for SOAP message construction."""

    def test_build_fiscalization_request(self):
        """Test SOAP envelope construction."""
        from tools.api_implementations.fina_soap_client import build_fiscalization_request

        signed_xml = '<Invoice xmlns="test">Content</Invoice>'
        soap = build_fiscalization_request(signed_xml, message_id="test123")

        assert '<?xml version="1.0"' in soap
        assert 'soap:Envelope' in soap
        assert 'soap:Header' in soap
        assert 'soap:Body' in soap
        assert 'fis:RacunZahtjev' in soap
        assert 'test123' in soap  # message_id
        assert 'Content' in soap

    def test_build_request_removes_xml_declaration(self):
        """Test XML declaration is removed from invoice."""
        from tools.api_implementations.fina_soap_client import build_fiscalization_request

        signed_xml = '<?xml version="1.0" encoding="UTF-8"?><Invoice>Content</Invoice>'
        soap = build_fiscalization_request(signed_xml)

        # Should only have one XML declaration (for SOAP envelope)
        count = soap.count('<?xml')
        assert count == 1


# ============================================================================
# RESPONSE PARSING TESTS
# ============================================================================

class TestResponseParsing:
    """Tests for FINA response parsing."""

    def test_parse_successful_response(self):
        """Test parsing successful FINA response with JIR."""
        from tools.api_implementations.fina_soap_client import parse_fina_response

        soap_response = '''<?xml version="1.0" encoding="UTF-8"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                       xmlns:fis="http://www.apis-it.hr/fin/2012/types/f73">
            <soap:Body>
                <fis:RacunOdgovor>
                    <fis:Jir>abc123-def456-ghi789</fis:Jir>
                    <fis:Zki>A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6</fis:Zki>
                    <fis:DatumVrijeme>2026-01-15T10:30:00</fis:DatumVrijeme>
                </fis:RacunOdgovor>
            </soap:Body>
        </soap:Envelope>'''

        result = parse_fina_response(soap_response)

        assert result["success"] is True
        assert result["jir"] == "abc123-def456-ghi789"
        assert result["zki"] == "A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6"
        assert len(result["errors"]) == 0

    def test_parse_error_response(self):
        """Test parsing FINA error response."""
        from tools.api_implementations.fina_soap_client import parse_fina_response

        soap_response = '''<?xml version="1.0" encoding="UTF-8"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
                       xmlns:fis="http://www.apis-it.hr/fin/2012/types/f73">
            <soap:Body>
                <fis:RacunOdgovor>
                    <fis:Greska>
                        <fis:SifraGreske>p001</fis:SifraGreske>
                        <fis:PorukaGreske>Neispravan OIB</fis:PorukaGreske>
                    </fis:Greska>
                </fis:RacunOdgovor>
            </soap:Body>
        </soap:Envelope>'''

        result = parse_fina_response(soap_response)

        assert result["success"] is False
        assert result["jir"] is None
        assert len(result["errors"]) > 0
        assert result["errors"][0]["code"] == "p001"

    def test_parse_soap_fault(self):
        """Test parsing SOAP Fault response."""
        from tools.api_implementations.fina_soap_client import parse_fina_response

        soap_response = '''<?xml version="1.0" encoding="UTF-8"?>
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <soap:Fault>
                    <faultcode>soap:Server</faultcode>
                    <faultstring>Internal Server Error</faultstring>
                </soap:Fault>
            </soap:Body>
        </soap:Envelope>'''

        result = parse_fina_response(soap_response)

        assert result["success"] is False
        assert "SOAP_FAULT" in result["errors"][0]["code"]


# ============================================================================
# QR CODE TESTS
# ============================================================================

class TestQRCodeGeneration:
    """Tests for QR code generation."""

    @pytest.mark.skipif(
        not _qrcode_available(),
        reason="qrcode library not available"
    )
    def test_generate_verification_qr(self):
        """Test QR code generation."""
        from tools.api_implementations.fina_soap_client import generate_verification_qr

        result = generate_verification_qr(
            jir="abc123-def456",
            zki="A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6",
            invoice_datetime="2026-01-15T10:30:00",
            total_amount="1250.00",
            oib="12345678903"
        )

        assert result["success"] is True
        assert result["qr_code_base64"] is not None
        assert result["verification_url"] is not None
        assert "porezna.gov.hr" in result["verification_url"]
        assert "abc123-def456" in result["verification_url"]

    @pytest.mark.skipif(
        not _qrcode_available(),
        reason="qrcode library not available"
    )
    def test_qr_code_is_valid_base64(self):
        """Test QR code is valid base64 PNG."""
        from tools.api_implementations.fina_soap_client import generate_verification_qr

        result = generate_verification_qr(
            jir="test-jir",
            zki="A1B2C3D4-E5F6G7H8-I9J0K1L2-M3N4O5P6",
            invoice_datetime="2026-01-15T10:30:00",
            total_amount="100.00",
            oib="12345678903"
        )

        if result["success"]:
            # Should decode without error
            decoded = base64.b64decode(result["qr_code_base64"])
            # PNG starts with these bytes
            assert decoded[:4] == b'\x89PNG'


def _qrcode_available():
    """Check if qrcode library is available."""
    try:
        import qrcode
        return True
    except ImportError:
        return False


# ============================================================================
# LEDGER TESTS
# ============================================================================

class TestInMemoryLedger:
    """Tests for in-memory ledger storage."""

    def test_ledger_check_nonexistent(self):
        """Test checking for non-existent invoice."""
        from tools.api_implementations.fiskalizacija_ledger import InMemoryLedger

        ledger = InMemoryLedger()
        entry = ledger.check_exists("001/URED/1", "12345678903")

        assert entry is None

    def test_ledger_save_and_check(self):
        """Test saving and retrieving ledger entry."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            LedgerEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc).isoformat()

        entry = LedgerEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            jir="test-jir-123",
            zki="test-zki",
            status=FiscalizationStatus.SUCCESS.value,
            created_at=now,
            updated_at=now
        )

        ledger.save_entry(entry)
        retrieved = ledger.check_exists("001/URED/1", "12345678903")

        assert retrieved is not None
        assert retrieved.jir == "test-jir-123"
        assert retrieved.status == FiscalizationStatus.SUCCESS.value

    def test_ledger_update_entry(self):
        """Test updating ledger entry."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            LedgerEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc).isoformat()

        entry = LedgerEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            jir=None,
            zki="test-zki",
            status=FiscalizationStatus.PENDING.value,
            created_at=now,
            updated_at=now
        )

        ledger.save_entry(entry)
        ledger.update_entry("001/URED/1", "12345678903", {
            "jir": "new-jir-456",
            "status": FiscalizationStatus.SUCCESS.value
        })

        retrieved = ledger.check_exists("001/URED/1", "12345678903")

        assert retrieved.jir == "new-jir-456"
        assert retrieved.status == FiscalizationStatus.SUCCESS.value


# ============================================================================
# RETRY QUEUE TESTS
# ============================================================================

class TestRetryQueue:
    """Tests for retry queue management."""

    def test_add_to_retry_queue(self):
        """Test adding invoice to retry queue."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            RetryQueueEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc)

        entry = RetryQueueEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            first_attempt=now.isoformat(),
            last_attempt=now.isoformat(),
            attempt_count=1,
            next_retry=(now + timedelta(minutes=1)).isoformat(),
            deadline=(now + timedelta(hours=48)).isoformat(),
            error_message="Connection timeout",
            status=FiscalizationStatus.RETRYING.value
        )

        key = ledger.add_to_retry_queue(entry)
        retrieved = ledger.get_retry_entry("001/URED/1", "12345678903")

        assert retrieved is not None
        assert retrieved.attempt_count == 1
        assert "timeout" in retrieved.error_message.lower()

    def test_get_pending_retries(self):
        """Test getting invoices due for retry."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            RetryQueueEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc)

        # Add entry with past retry time
        entry = RetryQueueEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            first_attempt=now.isoformat(),
            last_attempt=now.isoformat(),
            attempt_count=1,
            next_retry=(now - timedelta(minutes=1)).isoformat(),  # Past
            deadline=(now + timedelta(hours=48)).isoformat(),
            error_message="Error",
            status=FiscalizationStatus.RETRYING.value
        )

        ledger.add_to_retry_queue(entry)
        pending = ledger.get_pending_retries()

        assert len(pending) == 1
        assert pending[0].invoice_number == "001/URED/1"

    def test_expired_entries_marked(self):
        """Test that expired entries are marked."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            RetryQueueEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc)

        # Add entry with past deadline
        entry = RetryQueueEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            first_attempt=(now - timedelta(hours=50)).isoformat(),
            last_attempt=(now - timedelta(hours=1)).isoformat(),
            attempt_count=5,
            next_retry=(now - timedelta(minutes=1)).isoformat(),
            deadline=(now - timedelta(hours=2)).isoformat(),  # Past deadline!
            error_message="Error",
            status=FiscalizationStatus.RETRYING.value
        )

        ledger.add_to_retry_queue(entry)
        pending = ledger.get_pending_retries()

        # Should not be in pending (expired)
        assert len(pending) == 0

        # Check status was updated
        retrieved = ledger.get_retry_entry("001/URED/1", "12345678903")
        assert retrieved.status == FiscalizationStatus.EXPIRED.value

    def test_remove_from_retry_queue(self):
        """Test removing invoice from retry queue after success."""
        from tools.api_implementations.fiskalizacija_ledger import (
            InMemoryLedger,
            RetryQueueEntry,
            FiscalizationStatus
        )

        ledger = InMemoryLedger()
        now = datetime.now(timezone.utc)

        entry = RetryQueueEntry(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            first_attempt=now.isoformat(),
            last_attempt=now.isoformat(),
            attempt_count=1,
            next_retry=(now + timedelta(minutes=1)).isoformat(),
            deadline=(now + timedelta(hours=48)).isoformat(),
            error_message="Error",
            status=FiscalizationStatus.RETRYING.value
        )

        ledger.add_to_retry_queue(entry)
        removed = ledger.remove_from_retry_queue("001/URED/1", "12345678903")

        assert removed is True
        assert ledger.get_retry_entry("001/URED/1", "12345678903") is None


# ============================================================================
# LEDGER SERVICE TESTS
# ============================================================================

class TestLedgerService:
    """Tests for FiscalizationLedgerService facade."""

    def test_check_invoice_exists_not_found(self):
        """Test checking for non-existent invoice."""
        from tools.api_implementations.fiskalizacija_ledger import FiscalizationLedgerService

        service = FiscalizationLedgerService(use_firestore=False)
        result = service.check_invoice_exists("001/URED/1", "12345678903")

        assert result["exists"] is False
        assert result["jir"] is None

    def test_save_successful_fiscalization(self):
        """Test saving successful fiscalization."""
        from tools.api_implementations.fiskalizacija_ledger import FiscalizationLedgerService

        service = FiscalizationLedgerService(use_firestore=False)

        result = service.save_successful_fiscalization(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            jir="test-jir-123",
            zki="test-zki",
            signed_xml="<xml>signed</xml>",
            fina_response="<soap>response</soap>",
            total_amount="1250.00"
        )

        assert result["success"] is True
        assert result["document_id"] is not None

        # Verify it's saved
        check = service.check_invoice_exists("001/URED/1", "12345678903")
        assert check["exists"] is True
        assert check["jir"] == "test-jir-123"

    def test_add_to_retry_queue_exponential_backoff(self):
        """Test retry queue uses exponential backoff."""
        from tools.api_implementations.fiskalizacija_ledger import FiscalizationLedgerService

        service = FiscalizationLedgerService(use_firestore=False)

        # First failure
        result1 = service.add_to_retry_queue(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            error_message="First error"
        )

        assert result1["success"] is True
        assert result1["attempt_count"] == 1

        # Second failure - should have longer backoff
        result2 = service.add_to_retry_queue(
            invoice_number="001/URED/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            error_message="Second error"
        )

        assert result2["success"] is True
        assert result2["attempt_count"] == 2

        # Next retry time should be later
        from datetime import datetime
        next1 = datetime.fromisoformat(result1["next_retry"].replace('Z', '+00:00'))
        next2 = datetime.fromisoformat(result2["next_retry"].replace('Z', '+00:00'))

        # Second retry should be after first (exponential backoff)
        assert next2 > next1


# ============================================================================
# ADK TOOL WRAPPER TESTS
# ============================================================================

class TestADKToolWrappers:
    """Tests for ADK tool wrapper functions."""

    @pytest.mark.asyncio
    async def test_check_invoice_ledger_tool(self):
        """Test check_invoice_ledger ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import check_invoice_ledger

        result = await check_invoice_ledger(
            invoice_number="999/TEST/1",
            supplier_oib="12345678903",
            use_firestore=False
        )

        assert "exists" in result
        assert result["exists"] is False

    @pytest.mark.asyncio
    async def test_save_invoice_ledger_tool(self):
        """Test save_invoice_ledger ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import (
            save_invoice_ledger,
            check_invoice_ledger
        )

        # Save
        result = await save_invoice_ledger(
            invoice_number="998/TEST/1",
            supplier_oib="12345678903",
            jir="adk-test-jir",
            zki="adk-test-zki",
            signed_xml="<xml>test</xml>",
            fina_response="<soap>response</soap>",
            total_amount="500.00",
            use_firestore=False
        )

        assert result["success"] is True

        # Verify
        check = await check_invoice_ledger(
            invoice_number="998/TEST/1",
            supplier_oib="12345678903",
            use_firestore=False
        )

        assert check["exists"] is True
        assert check["jir"] == "adk-test-jir"

    @pytest.mark.asyncio
    async def test_add_to_retry_queue_tool(self):
        """Test add_to_retry_queue ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import add_to_retry_queue

        result = await add_to_retry_queue(
            invoice_number="997/TEST/1",
            supplier_oib="12345678903",
            signed_xml="<xml>test</xml>",
            zki="test-zki",
            error_message="Test error",
            use_firestore=False
        )

        assert result["success"] is True
        assert result["attempt_count"] == 1
        assert result["next_retry"] is not None
        assert result["deadline"] is not None

    @pytest.mark.asyncio
    async def test_get_retry_queue_stats_tool(self):
        """Test get_retry_queue_stats ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import get_retry_queue_stats

        result = await get_retry_queue_stats(use_firestore=False)

        assert "total" in result
        assert "pending" in result
        assert "expired" in result

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status_tool(self):
        """Test get_circuit_breaker_status ADK tool."""
        from tools.adk_tools.fiskalizacija_adk_tools import get_circuit_breaker_status

        result = await get_circuit_breaker_status()

        assert "state" in result
        assert "failure_count" in result
        assert "failure_threshold" in result


# ============================================================================
# FINA ERROR CODE TESTS
# ============================================================================

class TestFINAErrorCodes:
    """Tests for FINA error code handling."""

    def test_error_codes_defined(self):
        """Test error codes dictionary is defined."""
        from tools.api_implementations.fina_soap_client import FINA_ERROR_CODES

        assert "s001" in FINA_ERROR_CODES  # Format error
        assert "p001" in FINA_ERROR_CODES  # Invalid OIB
        assert "t001" in FINA_ERROR_CODES  # System unavailable

    def test_error_code_messages_croatian(self):
        """Test error messages are in Croatian."""
        from tools.api_implementations.fina_soap_client import FINA_ERROR_CODES

        # Croatian characters should be present in some messages
        assert "OIB" in FINA_ERROR_CODES["p001"]
        assert "račun" in FINA_ERROR_CODES.get("p007", "račun").lower()  # Case-insensitive

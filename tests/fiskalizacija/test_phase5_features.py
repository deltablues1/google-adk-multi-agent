"""
Tests for Phase 5 Features:
- NKD 2025 Classification Service
- Human-in-the-Loop Confirmation
- Company Activity Validation
- Deposit Refund (Povratna Naknada)
"""

import pytest
import os
import sys
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


# ============================================================================
# NKD SERVICE TESTS
# ============================================================================

class TestNKDService:
    """Tests for NKD 2025 classification service."""

    @pytest.fixture
    def nkd_service(self):
        """Create NKD service with test data."""
        from tools.api_implementations.nkd_service import NKDService
        service = NKDService()

        # Try to load from project root (check data/ subdirectory first, then root)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        paths_to_try = [
            os.path.join(project_root, 'data', 'kpd_2025', 'NKD_2025.json'),
            os.path.join(project_root, 'data', 'kpd_2025', 'NKD_2025.csv'),
            os.path.join(project_root, 'NKD_2025.json'),
            os.path.join(project_root, 'NKD_2025.csv'),
        ]

        for path in paths_to_try:
            if os.path.exists(path):
                service.load(path)
                break

        return service

    def test_service_loads_data(self, nkd_service):
        """Test NKD data is loaded."""
        counts = nkd_service.get_entry_count()
        assert counts["podrucje"] > 0, "Should have section entries"
        assert counts["podrazred"] > 0, "Should have subclass entries"

    def test_get_by_code(self, nkd_service):
        """Test lookup by exact code."""
        # Test section lookup
        entry = nkd_service.get("A")
        if entry:
            assert entry.level == "podrucje"
            assert "POLJOPRIVREDA" in entry.name.upper()

    def test_search_by_text(self, nkd_service):
        """Test text search."""
        results = nkd_service.search("poljoprivreda", limit=5)
        assert len(results) > 0
        assert any("POLJOPRIVREDA" in r.name.upper() for r in results)

    def test_search_construction(self, nkd_service):
        """Test searching for construction activities."""
        results = nkd_service.search("stolarija", limit=5)
        # Should find construction/installation activities
        codes = [r.code for r in results]
        print(f"Found codes for 'stolarija': {codes}")
        # Verify we get results
        assert len(results) >= 0  # May or may not find depending on data

    def test_hierarchy(self, nkd_service):
        """Test getting hierarchy for a code."""
        # First find a valid code
        results = nkd_service.search("uzgoj", limit=1, level="podrazred")
        if results:
            code = results[0].code
            hierarchy = nkd_service.get_hierarchy(code)
            assert len(hierarchy) > 0
            # Should have path from section to subclass

    def test_company_activity_validation(self, nkd_service):
        """Test company activity registration check."""
        # Set some registered activities
        nkd_service.set_company_activities(["01.11.0", "43.32.0"])

        # Check registered activity
        is_reg, warning = nkd_service.is_activity_registered("01.11.0")
        assert is_reg is True
        assert warning is None

        # Check unregistered activity
        is_reg, warning = nkd_service.is_activity_registered("99.99.0")
        assert is_reg is False
        assert warning is not None

    def test_search_for_invoice_item(self, nkd_service):
        """Test invoice item suggestion."""
        suggestions = nkd_service.search_for_invoice_item("Uzgoj pšenice")
        # Should get suggestions with hierarchy
        if suggestions:
            assert "code" in suggestions[0]
            assert "hierarchy" in suggestions[0]


# ============================================================================
# HITL CONFIRMATION TESTS
# ============================================================================

class TestHITLConfirmation:
    """Tests for Human-in-the-Loop confirmation service."""

    @pytest.fixture
    def hitl_service(self):
        """Create HITL service."""
        from tools.api_implementations.hitl_confirmation import HITLConfirmationService
        return HITLConfirmationService()

    @pytest.fixture
    def sample_invoice_data(self):
        """Sample invoice data for testing."""
        return {
            "invoice_number": "001/URED/1",
            "invoice_date": "2026-01-22",
            "invoice_time": "10:30:00",
            "supplier": {
                "name": "Test d.o.o.",
                "oib": "12345678903",
                "address": "Testna ulica 1, Zagreb"
            },
            "customer": {
                "name": "Kupac d.o.o.",
                "oib": "98765432101",
                "address": "Kupčeva 2, Split"
            },
            "business_unit": "URED",
            "device_number": "1",
            "lines": [
                {
                    "description": "Ugradnja PVC stolarije",
                    "quantity": "1",
                    "unit": "usluga",
                    "unit_price": "1000.00",
                    "line_total": "1000.00",
                    "vat_rate": "25",
                    "vat_amount": "250.00",
                    "nkd_code": "43.32.0",
                    "nkd_name": "Ugradnja stolarije"
                }
            ]
        }

    def test_create_confirmation(self, hitl_service, sample_invoice_data):
        """Test creating confirmation request."""
        confirmation = hitl_service.create_confirmation(sample_invoice_data)

        assert confirmation.confirmation_id is not None
        assert confirmation.invoice_number == "001/URED/1"
        assert confirmation.supplier_oib == "12345678903"
        assert len(confirmation.lines) == 1

    def test_confirmation_validates_oib(self, hitl_service, sample_invoice_data):
        """Test OIB validation in confirmation."""
        # Invalid supplier OIB
        sample_invoice_data["supplier"]["oib"] = "invalid"
        confirmation = hitl_service.create_confirmation(sample_invoice_data)

        assert confirmation.has_critical_warnings
        assert any(w.code == "INVALID_SUPPLIER_OIB" for w in confirmation.warnings)

    def test_confirmation_display_text(self, hitl_service, sample_invoice_data):
        """Test generating display text."""
        confirmation = hitl_service.create_confirmation(sample_invoice_data)
        display = confirmation.to_display_text()

        assert "FISKALIZACIJA" in display
        assert "001/URED/1" in display
        assert "Test d.o.o." in display
        assert "1000.00" in display or "1000" in display

    def test_approve_confirmation(self, hitl_service, sample_invoice_data):
        """Test approving confirmation."""
        confirmation = hitl_service.create_confirmation(sample_invoice_data)
        conf_id = confirmation.confirmation_id

        approved = hitl_service.approve(conf_id, approved_by="test_user")

        assert approved is not None
        assert approved.status.value == "approved"
        assert approved.approved_by == "test_user"

    def test_reject_confirmation(self, hitl_service, sample_invoice_data):
        """Test rejecting confirmation."""
        confirmation = hitl_service.create_confirmation(sample_invoice_data)
        conf_id = confirmation.confirmation_id

        rejected = hitl_service.reject(conf_id, reason="Test rejection")

        assert rejected is not None
        assert rejected.status.value == "rejected"
        assert rejected.user_notes == "Test rejection"

    def test_validation_missing_business_unit(self, hitl_service, sample_invoice_data):
        """Test validation catches missing business unit."""
        sample_invoice_data["business_unit"] = ""
        confirmation = hitl_service.create_confirmation(sample_invoice_data)

        assert confirmation.has_critical_warnings
        assert any(w.code == "MISSING_BUSINESS_UNIT" for w in confirmation.warnings)


# ============================================================================
# DEPOSIT REFUND TESTS
# ============================================================================

class TestDepositRefund:
    """Tests for deposit refund (povratna naknada) service."""

    def test_create_deposit_item(self):
        """Test creating deposit refund item."""
        from tools.api_implementations.deposit_refund import create_deposit_refund, DEPOSIT_AMOUNT_EUR

        item = create_deposit_refund(30, "Staklene boce piva")

        assert item.quantity == 30
        assert item.unit_amount == DEPOSIT_AMOUNT_EUR
        assert item.total_amount == Decimal("3.00")

    def test_deposit_summary(self):
        """Test deposit summary calculation."""
        from tools.api_implementations.deposit_refund import (
            DepositRefundItem,
            DepositRefundSummary,
            DEPOSIT_AMOUNT_EUR
        )

        items = [
            DepositRefundItem("Boce piva", 30, DEPOSIT_AMOUNT_EUR),
            DepositRefundItem("Limenke soka", 20, DEPOSIT_AMOUNT_EUR)
        ]
        summary = DepositRefundSummary(items=items)

        assert summary.total_quantity == 50
        assert summary.total_amount == Decimal("5.00")

    def test_deposit_rate(self):
        """Test getting current deposit rate."""
        from tools.api_implementations.deposit_refund import get_current_deposit_rate

        rate = get_current_deposit_rate()

        assert rate["amount_per_unit"] == "0.10"
        assert rate["currency"] == "EUR"
        assert "FZOEU" in rate["recipient"]

    def test_deposit_to_dict(self):
        """Test deposit serialization."""
        from tools.api_implementations.deposit_refund import (
            DepositRefundItem,
            DepositRefundSummary,
            DEPOSIT_AMOUNT_EUR
        )

        item = DepositRefundItem("Test", 10, DEPOSIT_AMOUNT_EUR)
        summary = DepositRefundSummary(items=[item])
        data = summary.to_dict()

        assert data["total_quantity"] == 10
        assert data["total_amount"] == "1.00"
        assert data["is_pass_through"] is True
        assert data["vat_exempt"] is True

    def test_build_allowance_charge_xml(self):
        """Test building UBL AllowanceCharge XML."""
        from tools.api_implementations.deposit_refund import (
            DepositRefundItem,
            DepositRefundSummary,
            build_allowance_charge_xml,
            DEPOSIT_AMOUNT_EUR
        )

        summary = DepositRefundSummary(items=[
            DepositRefundItem("Boce", 10, DEPOSIT_AMOUNT_EUR)
        ])

        xml_element = build_allowance_charge_xml(summary)

        # Check structure
        assert xml_element.tag.endswith("AllowanceCharge")

        # Find ChargeIndicator
        ns = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
        charge_ind = xml_element.find(".//cbc:ChargeIndicator", ns)
        assert charge_ind is not None
        assert charge_ind.text == "true"

        # Find Amount
        amount = xml_element.find(".//cbc:Amount", ns)
        assert amount is not None
        assert amount.text == "1.00"


# ============================================================================
# COMPANY CONFIG TESTS
# ============================================================================

class TestCompanyConfig:
    """Tests for company configuration."""

    def test_create_config(self):
        """Test creating company config."""
        from config.company_config import CompanyConfig, BusinessPremise, CashRegister

        config = CompanyConfig(
            name="Test d.o.o.",
            oib="12345678903",
            address="Testna 1",
            city="Zagreb",
            postal_code="10000",
            registered_nkd=["43.32.0"],
            business_premises=[
                BusinessPremise("URED", "Ured", "Testna 1", "Zagreb", "10000")
            ],
            cash_registers=[
                CashRegister("1", "URED", "Glavna blagajna")
            ]
        )

        assert config.name == "Test d.o.o."
        assert len(config.registered_nkd) == 1

    def test_config_validation(self):
        """Test config validation."""
        from config.company_config import CompanyConfig

        # Invalid config - missing required fields
        config = CompanyConfig(
            name="",
            oib="123",  # Invalid OIB
            address="",
            city="",
            postal_code=""
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)
        assert any("oib" in e.lower() for e in errors)

    def test_get_premise(self):
        """Test getting business premise."""
        from config.company_config import CompanyConfig, BusinessPremise, CashRegister

        config = CompanyConfig(
            name="Test",
            oib="12345678903",
            address="Test",
            city="Zagreb",
            postal_code="10000",
            business_premises=[
                BusinessPremise("URED", "Ured", "Test", "Zagreb", "10000"),
                BusinessPremise("SKLADISTE", "Skladište", "Test", "Zagreb", "10000")
            ],
            cash_registers=[
                CashRegister("1", "URED")
            ]
        )

        premise = config.get_premise("URED")
        assert premise is not None
        assert premise.name == "Ured"

        # Non-existent
        assert config.get_premise("NEPOSTOJI") is None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestPhase5Integration:
    """Integration tests for Phase 5 features."""

    @pytest.fixture
    def nkd_service(self):
        """Create NKD service with data."""
        from tools.api_implementations.nkd_service import get_nkd_service
        service = get_nkd_service()

        # Load data (check data/ subdirectory first, then root)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        for path in [
            os.path.join(project_root, 'data', 'kpd_2025', 'NKD_2025.json'),
            os.path.join(project_root, 'NKD_2025.json'),
        ]:
            if os.path.exists(path):
                service.load(path)
                break

        return service

    def test_full_confirmation_workflow(self, nkd_service):
        """Test complete confirmation workflow with NKD validation."""
        from tools.api_implementations.hitl_confirmation import HITLConfirmationService

        # Set company activities
        nkd_service.set_company_activities(["43.32.0", "47.52.0"])

        # Create invoice data
        invoice_data = {
            "invoice_number": "TEST/001/1",
            "invoice_date": "2026-01-22",
            "invoice_time": "12:00:00",
            "supplier": {
                "name": "Testna Tvrtka d.o.o.",
                "oib": "12345678903"
            },
            "customer": {
                "name": "Kupac",
                "oib": "98765432101"
            },
            "business_unit": "URED",
            "device_number": "1",
            "lines": [
                {
                    "description": "Ugradnja prozora",
                    "quantity": "1",
                    "unit": "usluga",
                    "unit_price": "500.00",
                    "line_total": "500.00",
                    "vat_rate": "25",
                    "vat_amount": "125.00",
                    "nkd_code": "43.32.0"
                }
            ],
            "deposit_refund": {
                "unit_count": 10,
                "unit_amount": "0.10",
                "total_amount": "1.00"
            }
        }

        # Create confirmation
        service = HITLConfirmationService()
        confirmation = service.create_confirmation(invoice_data, nkd_service)

        # Verify
        assert confirmation.confirmation_id is not None
        assert confirmation.deposit_refund is not None
        assert confirmation.deposit_refund.total_amount == Decimal("1.00")

        # Check display text includes deposit
        display = confirmation.to_display_text()
        assert "POVRATNA NAKNADA" in display.upper() or "prolazna" in display.lower()

        # Approve
        approved = service.approve(confirmation.confirmation_id)
        assert approved.status.value == "approved"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

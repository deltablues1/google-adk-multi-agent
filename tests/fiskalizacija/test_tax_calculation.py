"""
Unit Tests for Tax Calculation

Tests the deterministic VAT calculation tool with Decimal precision.
Croatian VAT rates: 25% (standard), 13% (reduced), 5% (super-reduced), 0% (exempt)

Run with: pytest tests/fiskalizacija/test_tax_calculation.py -v
"""

import pytest
import asyncio
from decimal import Decimal

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.adk_tools.fiskalizacija_adk_tools import calculate_tax, verify_tax_calculation


# ============================================================================
# BASIC CALCULATION TESTS
# ============================================================================

class TestBasicTaxCalculation:
    """Test basic tax calculations"""

    @pytest.mark.asyncio
    async def test_single_item_25_percent(self):
        """Test single item with 25% VAT"""
        result = await calculate_tax([
            {"net_amount": "1000.00", "vat_rate": "25"}
        ])

        assert result["total_net"] == "1000.00"
        assert result["total_tax"] == "250.00"
        assert result["total_gross"] == "1250.00"
        assert result["currency"] == "EUR"

    @pytest.mark.asyncio
    async def test_single_item_13_percent(self):
        """Test single item with 13% VAT (food service, accommodation)"""
        result = await calculate_tax([
            {"net_amount": "1000.00", "vat_rate": "13"}
        ])

        assert result["total_net"] == "1000.00"
        assert result["total_tax"] == "130.00"
        assert result["total_gross"] == "1130.00"

    @pytest.mark.asyncio
    async def test_single_item_5_percent(self):
        """Test single item with 5% VAT (bread, milk, books)"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "5"}
        ])

        assert result["total_net"] == "100.00"
        assert result["total_tax"] == "5.00"
        assert result["total_gross"] == "105.00"

    @pytest.mark.asyncio
    async def test_single_item_zero_percent(self):
        """Test single item with 0% VAT (exports, exempt)"""
        result = await calculate_tax([
            {"net_amount": "500.00", "vat_rate": "0"}
        ])

        assert result["total_net"] == "500.00"
        assert result["total_tax"] == "0.00"
        assert result["total_gross"] == "500.00"

    @pytest.mark.asyncio
    async def test_empty_items(self):
        """Test with empty items list"""
        result = await calculate_tax([])

        assert result["total_net"] == "0.00"
        assert result["total_tax"] == "0.00"
        assert result["total_gross"] == "0.00"
        assert "error" in result


# ============================================================================
# MULTI-ITEM AND MULTI-RATE TESTS
# ============================================================================

class TestMultiItemCalculation:
    """Test calculations with multiple items and rates"""

    @pytest.mark.asyncio
    async def test_multiple_items_same_rate(self):
        """Test multiple items with same VAT rate"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"},
            {"net_amount": "200.00", "vat_rate": "25"},
            {"net_amount": "300.00", "vat_rate": "25"},
        ])

        assert result["total_net"] == "600.00"
        assert result["total_tax"] == "150.00"  # 600 * 0.25
        assert result["total_gross"] == "750.00"

        # Check subtotals
        assert len(result["subtotals"]) == 1
        assert result["subtotals"][0]["vat_rate"] == "25"
        assert result["subtotals"][0]["taxable_amount"] == "600.00"

    @pytest.mark.asyncio
    async def test_multiple_items_different_rates(self):
        """Test multiple items with different VAT rates"""
        result = await calculate_tax([
            {"net_amount": "1000.00", "vat_rate": "25"},
            {"net_amount": "500.00", "vat_rate": "13"},
            {"net_amount": "100.00", "vat_rate": "5"},
        ])

        assert result["total_net"] == "1600.00"
        # Tax: 250 + 65 + 5 = 320
        assert result["total_tax"] == "320.00"
        assert result["total_gross"] == "1920.00"

        # Check subtotals (should be sorted by rate descending)
        assert len(result["subtotals"]) == 3

    @pytest.mark.asyncio
    async def test_mixed_rates_aggregation(self):
        """Test that items with same rate are aggregated"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"},
            {"net_amount": "50.00", "vat_rate": "13"},
            {"net_amount": "150.00", "vat_rate": "25"},
            {"net_amount": "30.00", "vat_rate": "13"},
        ])

        # 25% items: 100 + 150 = 250, tax = 62.50
        # 13% items: 50 + 30 = 80, tax = 10.40
        assert result["total_net"] == "330.00"
        assert result["total_tax"] == "72.90"
        assert result["total_gross"] == "402.90"


# ============================================================================
# DECIMAL PRECISION TESTS
# ============================================================================

class TestDecimalPrecision:
    """Test Decimal precision for financial calculations"""

    @pytest.mark.asyncio
    async def test_rounding_half_up(self):
        """Test that rounding uses ROUND_HALF_UP"""
        # 33.33 * 0.25 = 8.3325, should round to 8.33
        result = await calculate_tax([
            {"net_amount": "33.33", "vat_rate": "25"}
        ])

        assert result["total_net"] == "33.33"
        assert result["total_tax"] == "8.33"
        assert result["total_gross"] == "41.66"

    @pytest.mark.asyncio
    async def test_rounding_edge_case(self):
        """Test rounding edge case (exactly .5)"""
        # 10.02 * 0.25 = 2.505, should round to 2.51 (half up)
        result = await calculate_tax([
            {"net_amount": "10.02", "vat_rate": "25"}
        ])

        assert result["total_tax"] == "2.51"

    @pytest.mark.asyncio
    async def test_small_amounts(self):
        """Test with very small amounts"""
        result = await calculate_tax([
            {"net_amount": "0.01", "vat_rate": "25"}
        ])

        assert result["total_net"] == "0.01"
        assert result["total_tax"] == "0.00"  # 0.0025 rounds to 0.00
        assert result["total_gross"] == "0.01"

    @pytest.mark.asyncio
    async def test_large_amounts(self):
        """Test with large amounts"""
        result = await calculate_tax([
            {"net_amount": "999999.99", "vat_rate": "25"}
        ])

        assert result["total_net"] == "999999.99"
        assert result["total_tax"] == "250000.00"  # 999999.99 * 0.25 = 249999.9975
        assert result["total_gross"] == "1249999.99"

    @pytest.mark.asyncio
    async def test_no_floating_point_errors(self):
        """Test that we don't have floating point errors"""
        # Classic floating point problem: 0.1 + 0.2 != 0.3 in float
        result = await calculate_tax([
            {"net_amount": "0.10", "vat_rate": "25"},
            {"net_amount": "0.20", "vat_rate": "25"},
        ])

        # With Decimal, 0.10 + 0.20 should exactly equal 0.30
        assert result["total_net"] == "0.30"


# ============================================================================
# INPUT FORMAT TESTS
# ============================================================================

class TestInputFormats:
    """Test various input formats"""

    @pytest.mark.asyncio
    async def test_string_amounts(self):
        """Test string amount inputs"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"}
        ])
        assert result["total_net"] == "100.00"

    @pytest.mark.asyncio
    async def test_integer_amounts(self):
        """Test integer amount inputs"""
        result = await calculate_tax([
            {"net_amount": 100, "vat_rate": "25"}
        ])
        assert result["total_net"] == "100.00"

    @pytest.mark.asyncio
    async def test_float_amounts(self):
        """Test float amount inputs (converted to Decimal)"""
        result = await calculate_tax([
            {"net_amount": 100.50, "vat_rate": "25"}
        ])
        assert result["total_net"] == "100.50"

    @pytest.mark.asyncio
    async def test_rate_as_string(self):
        """Test VAT rate as string"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"}
        ])
        assert result["total_tax"] == "25.00"

    @pytest.mark.asyncio
    async def test_invalid_rate_defaults_to_25(self):
        """Test that invalid rate defaults to 25%"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "99"}
        ])
        # Should default to 25%
        assert result["total_tax"] == "25.00"


# ============================================================================
# TAX VERIFICATION TESTS
# ============================================================================

class TestTaxVerification:
    """Test the verification function that compares calculations"""

    @pytest.mark.asyncio
    async def test_correct_calculation_passes(self):
        """Test that correct calculations pass verification"""
        items = [
            {"net_amount": "1000.00", "vat_rate": "25"},
            {"net_amount": "500.00", "vat_rate": "13"}
        ]

        result = await verify_tax_calculation(
            items=items,
            claimed_total_net="1500.00",
            claimed_total_tax="315.00",  # 250 + 65
            claimed_total_gross="1815.00"
        )

        assert result["valid"] is True
        assert len(result["discrepancies"]) == 0

    @pytest.mark.asyncio
    async def test_wrong_net_fails(self):
        """Test that wrong net total fails verification"""
        items = [{"net_amount": "1000.00", "vat_rate": "25"}]

        result = await verify_tax_calculation(
            items=items,
            claimed_total_net="999.00",  # Wrong!
            claimed_total_tax="250.00",
            claimed_total_gross="1250.00"
        )

        assert result["valid"] is False
        assert any(d["field"] == "total_net" for d in result["discrepancies"])

    @pytest.mark.asyncio
    async def test_wrong_tax_fails(self):
        """Test that wrong tax total fails verification"""
        items = [{"net_amount": "1000.00", "vat_rate": "25"}]

        result = await verify_tax_calculation(
            items=items,
            claimed_total_net="1000.00",
            claimed_total_tax="249.00",  # Wrong!
            claimed_total_gross="1250.00"
        )

        assert result["valid"] is False
        assert any(d["field"] == "total_tax" for d in result["discrepancies"])

    @pytest.mark.asyncio
    async def test_wrong_gross_fails(self):
        """Test that wrong gross total fails verification"""
        items = [{"net_amount": "1000.00", "vat_rate": "25"}]

        result = await verify_tax_calculation(
            items=items,
            claimed_total_net="1000.00",
            claimed_total_tax="250.00",
            claimed_total_gross="1249.00"  # Wrong!
        )

        assert result["valid"] is False
        assert any(d["field"] == "total_gross" for d in result["discrepancies"])

    @pytest.mark.asyncio
    async def test_penny_difference_fails(self):
        """Test that even 1 cent difference fails (zero tolerance)"""
        items = [{"net_amount": "1000.00", "vat_rate": "25"}]

        result = await verify_tax_calculation(
            items=items,
            claimed_total_net="1000.00",
            claimed_total_tax="250.01",  # 1 cent off!
            claimed_total_gross="1250.01"
        )

        assert result["valid"] is False


# ============================================================================
# SUBTOTAL TESTS
# ============================================================================

class TestSubtotals:
    """Test the subtotal breakdown by VAT rate"""

    @pytest.mark.asyncio
    async def test_subtotals_structure(self):
        """Test subtotal structure"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"}
        ])

        assert "subtotals" in result
        assert len(result["subtotals"]) == 1

        subtotal = result["subtotals"][0]
        assert "vat_rate" in subtotal
        assert "taxable_amount" in subtotal
        assert "tax_amount" in subtotal

    @pytest.mark.asyncio
    async def test_subtotals_by_rate(self):
        """Test subtotals are correctly grouped by rate"""
        result = await calculate_tax([
            {"net_amount": "100.00", "vat_rate": "25"},
            {"net_amount": "200.00", "vat_rate": "13"},
            {"net_amount": "50.00", "vat_rate": "25"},
        ])

        # Should have 2 subtotals (25% and 13%)
        assert len(result["subtotals"]) == 2

        # Find 25% subtotal
        subtotal_25 = next(s for s in result["subtotals"] if s["vat_rate"] == "25")
        assert subtotal_25["taxable_amount"] == "150.00"  # 100 + 50
        assert subtotal_25["tax_amount"] == "37.50"

        # Find 13% subtotal
        subtotal_13 = next(s for s in result["subtotals"] if s["vat_rate"] == "13")
        assert subtotal_13["taxable_amount"] == "200.00"
        assert subtotal_13["tax_amount"] == "26.00"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling"""

    @pytest.mark.asyncio
    async def test_missing_net_amount(self):
        """Test handling of missing net_amount"""
        result = await calculate_tax([
            {"vat_rate": "25"}  # Missing net_amount
        ])

        # Should handle gracefully (use 0)
        assert result["total_net"] == "0.00"

    @pytest.mark.asyncio
    async def test_invalid_amount_format(self):
        """Test handling of invalid amount format"""
        result = await calculate_tax([
            {"net_amount": "not_a_number", "vat_rate": "25"}
        ])

        # Should return error
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

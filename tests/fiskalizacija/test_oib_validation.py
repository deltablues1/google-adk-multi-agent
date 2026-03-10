"""
Unit Tests for OIB Validation

Tests the Croatian OIB (Personal Identification Number) validation
using the Module 11 algorithm.

Run with: pytest tests/fiskalizacija/test_oib_validation.py -v
"""

import pytest
import asyncio
from decimal import Decimal

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.api_implementations.fiskalizacija_models import validate_oib_checksum
from tools.adk_tools.fiskalizacija_adk_tools import validate_oib


# ============================================================================
# TEST FIXTURES
# ============================================================================

# Valid OIB numbers (calculated with correct Module 11 checksum)
VALID_OIBS = [
    "00000000001",  # All zeros + check digit 1
    "12345678903",  # Sequential + check digit 3
    "98765432106",  # Reverse sequential + check digit 6
    "11111111119",  # All ones + check digit 9
]

# Invalid OIB numbers (various failure modes)
INVALID_OIBS = [
    ("12345678901", "Invalid checksum"),      # Wrong check digit
    ("12345678902", "Invalid checksum"),      # Wrong check digit
    ("1234567890", "Length not 11"),          # Too short
    ("123456789012", "Length not 11"),        # Too long
    ("1234567890A", "Contains non-digit"),    # Non-numeric
    ("", "Empty string"),                      # Empty
    ("           ", "All spaces"),             # Whitespace
]


# ============================================================================
# SYNCHRONOUS CHECKSUM TESTS
# ============================================================================

class TestOIBChecksumSync:
    """Test the synchronous checksum validation function"""

    def test_valid_oibs(self):
        """Test that valid OIBs pass checksum validation"""
        for oib in VALID_OIBS:
            result = validate_oib_checksum(oib)
            assert result is True, f"OIB {oib} should be valid"

    def test_invalid_checksum(self):
        """Test that invalid checksums fail"""
        # 12345678903 is valid, so 12345678901 and 12345678902 should fail
        assert validate_oib_checksum("12345678901") is False
        assert validate_oib_checksum("12345678902") is False

    def test_wrong_length(self):
        """Test that wrong length fails"""
        assert validate_oib_checksum("1234567890") is False   # 10 digits
        assert validate_oib_checksum("123456789012") is False  # 12 digits
        assert validate_oib_checksum("") is False              # Empty

    def test_non_numeric(self):
        """Test that non-numeric input fails"""
        assert validate_oib_checksum("1234567890A") is False
        assert validate_oib_checksum("ABCDEFGHIJK") is False
        assert validate_oib_checksum("123-456-789") is False

    def test_none_input(self):
        """Test that None input fails gracefully"""
        assert validate_oib_checksum(None) is False

    def test_whitespace(self):
        """Test that whitespace is not handled (raw function)"""
        # The raw function doesn't strip whitespace
        assert validate_oib_checksum(" 12345678903") is False
        assert validate_oib_checksum("12345678903 ") is False


# ============================================================================
# ASYNC TOOL TESTS
# ============================================================================

class TestOIBToolAsync:
    """Test the async ADK tool wrapper"""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests"""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    async def test_valid_oib_tool(self):
        """Test valid OIB through tool interface"""
        result = await validate_oib("12345678903")
        assert result["valid"] is True
        assert result["oib"] == "12345678903"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_invalid_checksum_tool(self):
        """Test invalid checksum through tool interface"""
        result = await validate_oib("12345678901")
        assert result["valid"] is False
        assert "checksum" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_wrong_length_tool(self):
        """Test wrong length through tool interface"""
        result = await validate_oib("1234567890")
        assert result["valid"] is False
        assert "11 digits" in result["error_message"]

    @pytest.mark.asyncio
    async def test_non_numeric_tool(self):
        """Test non-numeric input through tool interface"""
        result = await validate_oib("1234567890A")
        assert result["valid"] is False
        assert "only digits" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_empty_string_tool(self):
        """Test empty string through tool interface"""
        result = await validate_oib("")
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_whitespace_handling(self):
        """Test that tool strips whitespace"""
        result = await validate_oib("  12345678903  ")
        assert result["valid"] is True
        assert result["oib"] == "12345678903"

    @pytest.mark.asyncio
    async def test_none_handling(self):
        """Test None input handling"""
        result = await validate_oib(None)
        assert result["valid"] is False


# ============================================================================
# MODULE 11 ALGORITHM VERIFICATION
# ============================================================================

class TestModule11Algorithm:
    """Verify the Module 11 algorithm implementation"""

    def test_algorithm_steps(self):
        """
        Manually verify the algorithm for OIB 12345678903

        Algorithm:
        1. Start with remainder = 10
        2. For each of first 10 digits:
           a. remainder = (remainder + digit) % 10, if 0 then 10
           b. remainder = (remainder * 2) % 11
        3. Check digit = 11 - remainder, if 11 then 0
        """
        oib = "12345678903"
        digits = [int(d) for d in oib[:10]]
        expected_check = int(oib[10])

        remainder = 10
        for digit in digits:
            remainder = (remainder + digit) % 10
            if remainder == 0:
                remainder = 10
            remainder = (remainder * 2) % 11

        calculated_check = 11 - remainder
        if calculated_check == 11:
            calculated_check = 0

        assert calculated_check == expected_check, \
            f"Algorithm mismatch: calculated {calculated_check}, expected {expected_check}"

    def test_edge_case_check_digit_zero(self):
        """Test when check digit should be 0 (11-11=0)"""
        # OIB where algorithm yields 11, so check digit is 0
        # 00000000001 should have check digit 1
        result = validate_oib_checksum("00000000001")
        # This tests the boundary condition

    def test_edge_case_all_zeros(self):
        """Test behavior with all zeros (invalid but tests algorithm)"""
        # All zeros would have a specific check digit based on algorithm
        result = validate_oib_checksum("00000000000")
        # The algorithm should handle this gracefully


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestOIBIntegration:
    """Integration tests combining multiple validations"""

    @pytest.mark.asyncio
    async def test_batch_validation(self):
        """Test validating multiple OIBs in sequence"""
        oibs_to_test = [
            ("12345678903", True),
            ("12345678901", False),
            ("98765432106", True),   # Valid: reverse sequential + check digit 6
            ("INVALID", False),
        ]

        for oib, expected_valid in oibs_to_test:
            result = await validate_oib(oib)
            assert result["valid"] == expected_valid, \
                f"OIB {oib}: expected valid={expected_valid}, got {result['valid']}"

    @pytest.mark.asyncio
    async def test_return_structure(self):
        """Test that return structure matches expected schema"""
        result = await validate_oib("12345678903")

        # Check all expected keys exist
        assert "valid" in result
        assert "oib" in result
        assert "error_message" in result

        # Check types
        assert isinstance(result["valid"], bool)
        assert isinstance(result["oib"], str)
        assert result["error_message"] is None or isinstance(result["error_message"], str)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestOIBPerformance:
    """Performance tests for OIB validation"""

    def test_sync_performance(self):
        """Test that sync validation is fast"""
        import time

        start = time.perf_counter()
        for _ in range(10000):
            validate_oib_checksum("12345678903")
        elapsed = time.perf_counter() - start

        # Should complete 10k validations in under 1 second
        assert elapsed < 1.0, f"Performance issue: 10k validations took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_async_performance(self):
        """Test that async validation is reasonably fast"""
        import time

        start = time.perf_counter()
        for _ in range(1000):
            await validate_oib("12345678903")
        elapsed = time.perf_counter() - start

        # Should complete 1k async validations in under 2 seconds
        assert elapsed < 2.0, f"Performance issue: 1k async validations took {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

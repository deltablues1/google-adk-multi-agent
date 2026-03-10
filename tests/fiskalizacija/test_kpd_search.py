"""
Unit Tests for KPD Code Search

Tests the KPD (Klasifikacija Proizvoda po Djelatnostima) semantic search tool.
KPD is the Croatian product/service classification system based on EU CPA.

Run with: pytest tests/fiskalizacija/test_kpd_search.py -v
"""

import pytest
import asyncio

# Import the module to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.adk_tools.fiskalizacija_adk_tools import search_kpd_code


# ============================================================================
# BASIC SEARCH TESTS
# ============================================================================

class TestBasicKPDSearch:
    """Test basic KPD search functionality"""

    @pytest.mark.asyncio
    async def test_it_consulting_search(self):
        """Test search for IT consulting services"""
        result = await search_kpd_code("IT konzultacije")

        assert "query" in result
        assert "matches" in result
        assert "best_match" in result
        assert "needs_review" in result

        # Should find some matches
        assert len(result["matches"]) > 0

    @pytest.mark.asyncio
    async def test_software_development_search(self):
        """Test search for software development"""
        result = await search_kpd_code("razvoj softvera")

        assert len(result["matches"]) > 0
        # Should find 62.01.xx codes
        codes = [m["code"] for m in result["matches"]]
        assert any(c.startswith("62.01") for c in codes)

    @pytest.mark.asyncio
    async def test_english_search(self):
        """Test search with English terms"""
        result = await search_kpd_code("software development")

        assert len(result["matches"]) > 0

    @pytest.mark.asyncio
    async def test_empty_query(self):
        """Test search with empty query"""
        result = await search_kpd_code("")

        assert result["matches"] == []
        assert result["best_match"] is None
        assert result["needs_review"] is True
        assert "error" in result

    @pytest.mark.asyncio
    async def test_top_k_parameter(self):
        """Test that top_k limits results"""
        result_3 = await search_kpd_code("konzultacije", top_k=3)
        result_5 = await search_kpd_code("konzultacije", top_k=5)

        assert len(result_3["matches"]) <= 3
        assert len(result_5["matches"]) <= 5


# ============================================================================
# MATCH STRUCTURE TESTS
# ============================================================================

class TestKPDMatchStructure:
    """Test the structure of KPD matches"""

    @pytest.mark.asyncio
    async def test_match_has_required_fields(self):
        """Test that matches have all required fields"""
        result = await search_kpd_code("hosting")

        assert len(result["matches"]) > 0
        match = result["matches"][0]

        assert "code" in match
        assert "name_hr" in match
        assert "confidence" in match
        assert "default_vat_rate" in match

    @pytest.mark.asyncio
    async def test_code_format(self):
        """Test that KPD codes are in correct format (XX.XX.XX)"""
        result = await search_kpd_code("usluge")

        for match in result["matches"]:
            code = match["code"]
            # Should be format XX.XX.XX
            parts = code.split(".")
            assert len(parts) == 3, f"Invalid code format: {code}"
            assert all(p.isdigit() for p in parts), f"Non-numeric parts in: {code}"

    @pytest.mark.asyncio
    async def test_confidence_range(self):
        """Test that confidence is between 0 and 1"""
        result = await search_kpd_code("dizajn")

        for match in result["matches"]:
            assert 0.0 <= match["confidence"] <= 1.0


# ============================================================================
# REVIEW FLAG TESTS
# ============================================================================

class TestReviewFlag:
    """Test the needs_review flag logic"""

    @pytest.mark.asyncio
    async def test_high_confidence_no_review(self):
        """Test that high confidence matches don't need review"""
        # This depends on the sample catalog and matching algorithm
        # In production with proper RAG, this would be more predictable
        result = await search_kpd_code("software development services")

        # If best match confidence >= 0.95, needs_review should be False
        if result["best_match"] and result["best_match"]["confidence"] >= 0.95:
            assert result["needs_review"] is False

    @pytest.mark.asyncio
    async def test_low_confidence_needs_review(self):
        """Test that low confidence matches need review"""
        # Vague query should result in lower confidence
        result = await search_kpd_code("neke usluge")

        # With vague query, if confidence < 0.95, needs_review should be True
        if result["best_match"] and result["best_match"]["confidence"] < 0.95:
            assert result["needs_review"] is True

    @pytest.mark.asyncio
    async def test_no_matches_needs_review(self):
        """Test that no matches means needs review"""
        result = await search_kpd_code("xyzabc123nonexistent")

        if len(result["matches"]) == 0:
            assert result["needs_review"] is True


# ============================================================================
# BEST MATCH TESTS
# ============================================================================

class TestBestMatch:
    """Test best match selection"""

    @pytest.mark.asyncio
    async def test_best_match_is_highest_confidence(self):
        """Test that best match has highest confidence"""
        result = await search_kpd_code("računalne usluge")

        if result["matches"] and result["best_match"]:
            best_confidence = result["best_match"]["confidence"]
            all_confidences = [m["confidence"] for m in result["matches"]]
            assert best_confidence == max(all_confidences)

    @pytest.mark.asyncio
    async def test_best_match_is_first_in_list(self):
        """Test that best match equals first match (sorted by confidence)"""
        result = await search_kpd_code("grafički dizajn")

        if result["matches"] and result["best_match"]:
            assert result["best_match"]["code"] == result["matches"][0]["code"]


# ============================================================================
# SPECIFIC CATEGORY TESTS
# ============================================================================

class TestSpecificCategories:
    """Test search for specific service categories"""

    @pytest.mark.asyncio
    async def test_hotel_services(self):
        """Test search for hotel/accommodation services (13% VAT)"""
        result = await search_kpd_code("hotel smještaj")

        # Should find accommodation services (typically 13% VAT)
        if result["best_match"]:
            # 55.xx codes are hospitality
            assert result["best_match"]["code"].startswith("55") or \
                   result["best_match"]["default_vat_rate"] == "13"

    @pytest.mark.asyncio
    async def test_restaurant_services(self):
        """Test search for restaurant services (13% VAT)"""
        result = await search_kpd_code("restoran usluge")

        # Should find restaurant services (typically 13% VAT)
        if result["best_match"]:
            assert result["best_match"]["code"].startswith("56") or \
                   result["best_match"]["default_vat_rate"] == "13"

    @pytest.mark.asyncio
    async def test_book_publishing(self):
        """Test search for book publishing (5% VAT)"""
        result = await search_kpd_code("izdavanje knjiga")

        # Should find publishing services (typically 5% VAT)
        if result["best_match"]:
            assert result["best_match"]["code"].startswith("58") or \
                   result["best_match"]["default_vat_rate"] == "5"

    @pytest.mark.asyncio
    async def test_advertising_services(self):
        """Test search for advertising services (25% VAT)"""
        result = await search_kpd_code("reklamna agencija")

        # Should find advertising services (25% VAT)
        if result["best_match"]:
            assert result["best_match"]["code"].startswith("73")


# ============================================================================
# CROATIAN LANGUAGE TESTS
# ============================================================================

class TestCroatianLanguage:
    """Test Croatian language handling"""

    @pytest.mark.asyncio
    async def test_croatian_diacritics(self):
        """Test search with Croatian diacritics"""
        result = await search_kpd_code("održavanje softvera")

        # Should work with Croatian characters
        assert "error" not in result or result["error"] is None

    @pytest.mark.asyncio
    async def test_mixed_case(self):
        """Test case insensitivity"""
        result_lower = await search_kpd_code("konzultacije")
        result_upper = await search_kpd_code("KONZULTACIJE")
        result_mixed = await search_kpd_code("Konzultacije")

        # All should return similar results
        if result_lower["best_match"] and result_upper["best_match"]:
            assert result_lower["best_match"]["code"] == result_upper["best_match"]["code"]


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Test error handling"""

    @pytest.mark.asyncio
    async def test_none_input(self):
        """Test handling of None input"""
        result = await search_kpd_code(None)

        assert result["matches"] == []
        assert result["needs_review"] is True

    @pytest.mark.asyncio
    async def test_whitespace_only(self):
        """Test handling of whitespace-only input"""
        result = await search_kpd_code("   ")

        assert result["matches"] == []
        assert result["needs_review"] is True

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test handling of special characters"""
        result = await search_kpd_code("IT/software & consulting!")

        # Should handle gracefully, not crash
        assert "query" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

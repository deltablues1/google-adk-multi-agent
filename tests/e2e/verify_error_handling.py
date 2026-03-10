"""
Verification Script for Advanced Error Handling

Tests:
1. Error Classification
2. Localized Messages
3. BaseAgent Fallback Mechanism
"""

import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from tools.error_handling.error_classifier import classify_error, ErrorSeverity, ErrorCategory
from tools.error_handling.error_messages import get_error_message
from agents.base_agent import BaseAgent
import google.api_core.exceptions

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

async def test_classification():
    logger.info("--- Testing Error Classification ---")
    
    # Test 429 Resource Exhausted
    e_429 = google.api_core.exceptions.ResourceExhausted("Quota exceeded")
    c_429 = classify_error(e_429)
    assert c_429.severity == ErrorSeverity.TRANSIENT
    assert c_429.category == ErrorCategory.RESOURCE
    assert c_429.retryable == True
    logger.info("[OK] 429 ResourceExhausted classified correctly (Transient)")

    # Test 404 Not Found
    e_404 = google.api_core.exceptions.NotFound("File not found")
    c_404 = classify_error(e_404)
    assert c_404.severity == ErrorSeverity.PERMANENT
    assert c_404.category == ErrorCategory.RESOURCE
    assert c_404.retryable == False
    logger.info("[OK] 404 NotFound classified correctly (Permanent)")

    # Test 401 Unauthenticated
    e_401 = google.api_core.exceptions.Unauthenticated("Invalid token")
    c_401 = classify_error(e_401)
    assert c_401.severity == ErrorSeverity.PERMANENT
    assert c_401.category == ErrorCategory.AUTHENTICATION
    logger.info("[OK] 401 Unauthenticated classified correctly (Permanent)")

async def test_messages():
    logger.info("\n--- Testing Localized Messages ---")
    
    msg_hr = get_error_message("quota_exceeded", "hr")
    assert "Sustav je trenutno opterećen" in msg_hr
    logger.info("[OK] HR Message retrieved successfully")

    msg_en = get_error_message("quota_exceeded", "en")
    assert "The system is currently experiencing high traffic" in msg_en
    logger.info("[OK] EN Message retrieved successfully")

async def test_agent_fallback():
    logger.info("\n--- Testing Agent Fallback ---")
    
    # Create a mock agent
    agent = BaseAgent(name="test_agent", model="gemini-1.5-flash")
    
    # Mock the run method to raise an exception
    # We need to patch the run method on the instance or class
    
    with patch.object(BaseAgent, 'run', side_effect=google.api_core.exceptions.ServiceUnavailable("Service down")) as mock_run:
        result = await agent.run_with_fallback("Test request")
        
        # Sanitize result for logging (remove non-ascii chars)
        safe_result = result.encode('ascii', 'ignore').decode('ascii')
        logger.info(f"Result (sanitized): {safe_result}")
        
        # Verify result contains friendly message
        # We check for the text part, ignoring the emoji
        assert "Google servisi su privremeno nedostupni" in result
        logger.info("[OK] Fallback mechanism caught error and returned friendly message")

async def main():
    try:
        await test_classification()
        await test_messages()
        await test_agent_fallback()
        print("\n[SUCCESS] ALL TESTS PASSED!")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

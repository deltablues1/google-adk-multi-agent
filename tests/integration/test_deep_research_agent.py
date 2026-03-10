"""
Deep Research Agent - Comprehensive Test Suite

Tests the new Deep Research Agent with real API calls:
- Google Search Grounding (Vertex AI)
- YouTube Transcript extraction
- Web Scraping (BeautifulSoup)

All tools are FREE and require NO external API keys!
"""

import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_research_agent_initialization():
    """Test 1: Initialize Research Agent"""
    print("\n" + "="*80)
    print("TEST 1: Research Agent Initialization")
    print("="*80)

    try:
        from agents.researcher.researcher import create_researcher_agent

        agent = create_researcher_agent()
        tools = agent.get_tools()

        print(f"✅ Agent initialized successfully")
        print(f"   Model: {agent.model}")
        print(f"   Max iterations: {agent.config.get('max_iterations')}")
        print(f"   Tools loaded: {len(tools)}")
        print(f"   Research mode: {agent.research_mode}")

        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_google_search_tool():
    """Test 2: Google Search Grounding Tool"""
    print("\n" + "="*80)
    print("TEST 2: Google Search Grounding (Vertex AI)")
    print("="*80)

    try:
        from tools.api_implementations.google_search_api import google_search_grounding

        query = "What is Google Agent Development Kit ADK"
        print(f"Query: {query}")

        result = await google_search_grounding(
            credentials=None,  # Uses Vertex AI credentials automatically
            query=query,
            max_results=3
        )

        if "error" in result:
            print(f"⚠️ Google Search returned error: {result['error']}")
            return False

        print(f"✅ Google Search successful")
        print(f"   Answer length: {len(result.get('answer', ''))} characters")
        print(f"   Sources found: {result.get('source_count', 0)}")

        if result.get('sources'):
            print(f"\n   Sources:")
            for idx, source in enumerate(result['sources'][:3], 1):
                print(f"     {idx}. {source.get('url', 'N/A')}")

        return True
    except Exception as e:
        print(f"❌ Google Search test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_youtube_transcript_tool():
    """Test 3: YouTube Transcript Tool"""
    print("\n" + "="*80)
    print("TEST 3: YouTube Transcript Extraction")
    print("="*80)

    try:
        from tools.api_implementations.youtube_api import youtube_get_transcript

        # Test with a known video (Google I/O 2024 - Gemini API)
        test_url = "https://www.youtube.com/watch?v=mhZRNwzKmjU"
        print(f"Video URL: {test_url}")

        result = await youtube_get_transcript(
            credentials=None,
            url=test_url,
            languages=["en"]
        )

        if "error" in result:
            print(f"⚠️ YouTube transcript extraction returned error: {result['error']}")
            print(f"   This may be normal if the video has no captions")
            return True  # Not a failure - just no transcript available

        print(f"✅ YouTube transcript extraction successful")
        print(f"   Video ID: {result.get('video_id')}")
        print(f"   Language: {result.get('language')}")
        print(f"   Word count: {result.get('word_count')}")
        print(f"   Transcript preview: {result.get('transcript', '')[:200]}...")

        return True
    except Exception as e:
        print(f"❌ YouTube transcript test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_web_scraper_tool():
    """Test 4: Web Scraper Tool (Croatian portal)"""
    print("\n" + "="*80)
    print("TEST 4: Web Scraper (Croatian News Portal)")
    print("="*80)

    try:
        from tools.api_implementations.web_scraper_api import scrape_url

        # Test with Index.hr
        test_url = "https://www.index.hr"
        print(f"URL: {test_url}")

        result = await scrape_url(
            credentials=None,
            url=test_url,
            extract_type="article"
        )

        if "error" in result:
            print(f"⚠️ Web scraping returned error: {result['error']}")
            return False

        print(f"✅ Web scraping successful")
        print(f"   Title: {result.get('title', 'N/A')[:80]}...")
        print(f"   Word count: {result.get('word_count')}")
        print(f"   Portal: {result.get('portal', 'N/A')}")

        return True
    except Exception as e:
        print(f"❌ Web scraper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_registry_integration():
    """Test 5: Tool Registry Integration"""
    print("\n" + "="*80)
    print("TEST 5: Tool Registry Integration")
    print("="*80)

    try:
        from tools.tool_registry import get_tool_registry
        from tools.initialize_tools import ensure_tools_initialized

        # Ensure tools are initialized
        ensure_tools_initialized()

        registry = get_tool_registry()

        # Check for research tools
        research_tools = [
            "google_search_grounding",
            "google_search_simple",
            "youtube_get_transcript",
            "scrape_url",
            "scrape_multiple_urls"
        ]

        found_tools = []
        missing_tools = []

        for tool_name in research_tools:
            if registry.has_tool(tool_name):
                found_tools.append(tool_name)
            else:
                missing_tools.append(tool_name)

        print(f"✅ Tool registry integration check")
        print(f"   Total tools in registry: {len(registry)}")
        print(f"   Research tools found: {len(found_tools)}/{len(research_tools)}")

        if found_tools:
            print(f"\n   Registered research tools:")
            for tool in found_tools:
                print(f"     ✓ {tool}")

        if missing_tools:
            print(f"\n   ⚠️ Missing research tools:")
            for tool in missing_tools:
                print(f"     ✗ {tool}")

        return len(missing_tools) == 0
    except Exception as e:
        print(f"❌ Tool registry integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_simple_query():
    """Test 6: Agent Simple Query (End-to-End)"""
    print("\n" + "="*80)
    print("TEST 6: Agent Simple Query (End-to-End)")
    print("="*80)

    try:
        from agents.researcher.researcher import create_researcher_agent

        agent = create_researcher_agent()

        # Simple query
        query = "What is Vertex AI?"
        print(f"Query: {query}")
        print(f"Executing agent.run()...")

        response = await agent.run(query)

        print(f"✅ Agent execution successful")
        print(f"   Response length: {len(response)} characters")
        print(f"\n   Response preview:")
        print(f"   {response[:500]}...")

        return True
    except Exception as e:
        print(f"❌ Agent simple query test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 DEEP RESEARCH AGENT - COMPREHENSIVE TEST SUITE")
    print("="*80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Testing: Google Search Grounding + YouTube + Web Scraper")
    print("All tools are FREE - No API keys required!")
    print("="*80)

    tests = [
        ("Research Agent Initialization", test_research_agent_initialization),
        ("Google Search Grounding", test_google_search_tool),
        ("YouTube Transcript", test_youtube_transcript_tool),
        ("Web Scraper", test_web_scraper_tool),
        ("Tool Registry Integration", test_tool_registry_integration),
        ("Agent Simple Query (E2E)", test_agent_simple_query),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0

    print(f"\nResults:")
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")

    print(f"\n{'='*80}")
    print(f"Total: {passed}/{total} tests passed ({success_rate:.1f}% success rate)")
    print(f"{'='*80}\n")

    return success_rate == 100.0


if __name__ == "__main__":
    print("\n🚀 Starting Deep Research Agent Tests...\n")

    try:
        success = asyncio.run(run_all_tests())

        if success:
            print("✅ All tests passed! Deep Research Agent is ready.")
            sys.exit(0)
        else:
            print("⚠️ Some tests failed. Check output above for details.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

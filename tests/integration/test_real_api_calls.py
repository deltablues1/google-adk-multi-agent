"""
DIRECT API TESTING - Bypass agents, test tools directly
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Import tools directly
from tools.api_implementations.google_search_api import google_search_grounding, google_search_simple
from tools.api_implementations.youtube_api import youtube_get_transcript
from tools.api_implementations.web_scraper_api import scrape_url

print("=" * 80)
print("DIRECT API TESTING - Real API Calls")
print("=" * 80)

async def test_google_search():
    """Test Google Search directly"""
    print("\n1. Testing Google Search Grounding...")

    result = await google_search_grounding(
        credentials=None,
        query="What is Google Gemini AI",
        max_results=3
    )

    print(f"\nResult keys: {result.keys()}")
    print(f"Query: {result.get('query')}")
    print(f"Answer length: {len(result.get('answer', ''))}")
    print(f"Sources: {result.get('source_count')}")

    if result.get('answer'):
        print(f"\nAnswer:\n{result['answer'][:500]}...")

    if result.get('sources'):
        print(f"\nSources:")
        for i, src in enumerate(result['sources'][:3], 1):
            print(f"  {i}. {src.get('url', 'N/A')}")
            print(f"     {src.get('title', 'No title')}")

    if 'error' in result:
        print(f"\nERROR: {result['error']}")

    return result

async def test_web_scraper():
    """Test web scraper directly"""
    print("\n\n2. Testing Web Scraper...")

    # Test with a simple URL
    url = "https://en.wikipedia.org/wiki/Artificial_intelligence"

    result = await scrape_url(
        credentials=None,
        url=url,
        extract_type="article"
    )

    print(f"\nURL: {url}")
    print(f"Result keys: {result.keys()}")

    if 'error' in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Word count: {result.get('word_count', 0)}")
        print(f"Text preview: {result.get('text', '')[:200]}...")

    return result

async def test_simple_search():
    """Test simple search"""
    print("\n\n3. Testing Simple Google Search...")

    result = await google_search_simple(
        credentials=None,
        query="Google Gemini documentation",
        num_results=5
    )

    print(f"\nQuery: {result.get('query')}")
    print(f"Sources found: {result.get('source_count', 0)}")

    if result.get('sources'):
        print(f"\nURLs:")
        for i, src in enumerate(result['sources'][:5], 1):
            print(f"  {i}. {src.get('url', 'N/A')}")

    if 'error' in result:
        print(f"\nERROR: {result['error']}")

    return result

async def main():
    try:
        # Test 1: Google Search Grounding
        search_result = await test_google_search()

        # Test 2: Web Scraper
        scrape_result = await test_web_scraper()

        # Test 3: Simple Search
        simple_result = await test_simple_search()

        print("\n\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        print(f"\n1. Google Search Grounding:")
        if search_result.get('answer'):
            print(f"   [OK] Got answer: {len(search_result['answer'])} chars")
        else:
            print(f"   [FAIL] No answer: {search_result.get('error', 'Unknown error')}")

        print(f"\n2. Web Scraper:")
        if scrape_result.get('text'):
            print(f"   [OK] Scraped: {scrape_result.get('word_count', 0)} words")
        else:
            print(f"   [FAIL] No text: {scrape_result.get('error', 'Unknown error')}")

        print(f"\n3. Simple Search:")
        if simple_result.get('sources'):
            print(f"   [OK] Found {len(simple_result['sources'])} sources")
        else:
            print(f"   [FAIL] No sources: {simple_result.get('error', 'Unknown error')}")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

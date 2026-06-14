"""Validate the fixed Vertex AI Search grounding tool end-to-end."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()

from tools.api_implementations.google_search_api import google_search_grounding


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Anthropic Claude Fable 5 model news June 2026"
    r = await google_search_grounding(None, query, max_results=5)
    print("QUERY:", query)
    print("ANSWER:", (r.get("answer") or "(empty)")[:500])
    print("SOURCE_COUNT:", r.get("source_count"))
    for s in (r.get("sources") or [])[:5]:
        print("  -", s.get("url"))


asyncio.run(main())

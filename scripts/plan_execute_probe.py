"""Probe the plan-execute layer end-to-end without the web/CLI stack.

Builds the worker agents from the registry, then runs a request through
``run_plan_execute``. The planner decides whether it is a genuine multi-step chain;
if so you'll see [PLAN] and [STEP n] logs and the final summarized answer.

Usage:
    python scripts/plan_execute_probe.py
    python scripts/plan_execute_probe.py "istraži X i pošalji izvješće kontaktu Y"

Note: single-step requests intentionally hit the fallback (a stub here) — this probe
is for exercising the multi-step path. Requires the same Google/Vertex creds as the
live system.
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("plan_execute_probe")

from config.agent_registry import get_worker_agent_names, create_agent_instance
from agents.adk_agents.plan_execute import run_plan_execute

DEFAULT_PROMPT = (
    "Istraži ukratko što se dogodilo s Claude Fable modelom i pošalji to "
    "izvješće na mail kontaktu Tomislav Golić."
)


async def _fallback(message: str) -> str:
    logger.info("[PROBE] Planner chose single-step/special — would defer to orchestrator.")
    return "[fallback] Nije višekoračni lanac — Smart Orchestrator bi ovo obradio."


async def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    worker_agents = []
    for name in get_worker_agent_names():
        try:
            worker_agents.append(create_agent_instance(name))
        except Exception as e:
            logger.warning("Skipping worker '%s': %s", name, e)

    logger.info("Loaded %d worker agents", len(worker_agents))
    logger.info("PROMPT: %s", prompt)

    result = await run_plan_execute(
        prompt,
        worker_agents,
        fallback=_fallback,
        session_id="probe-plan-execute",
        user_id="probe-user",
    )

    print("\n" + "=" * 70)
    print("FINAL ANSWER:")
    print("=" * 70)
    print(result)


asyncio.run(main())

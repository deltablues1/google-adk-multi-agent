"""
Final System Verification - "Grand Finale"

This script executes a complex, multi-agent workflow to verify the entire system
functionality, including:
1. Orchestrator Routing (Gemini 3.0 Pro)
2. Researcher Agent (Web Search + YouTube)
3. Synthesizer Agent (Report Writing)
4. Mailer Agent (Draft Creation)
5. Caching & Rate Limiting (Performance)
6. Cloud Monitoring (Dashboard)

Scenario:
"Research the top 3 AI Agent Frameworks in 2024, summarize their key features,
and draft an email to 'team@example.com' with the summary."
"""

import asyncio
import logging
import os
import sys

# Force Cloud Logging for Dashboard visibility
os.environ["USE_CLOUD_LOGGING"] = "true"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from main import WorkspaceADKSystem
from monitoring.metrics import get_metrics_collector

async def run_grand_finale():
    logger.info("🚀 STARTING GRAND FINALE SYSTEM VERIFICATION 🚀")
    logger.info("==================================================")
    
    # 1. Initialize System
    logger.info("1️⃣ Initializing ADK System...")
    system = WorkspaceADKSystem()
    system.initialize_agents()
    
    # 2. Define Complex Query
    query = (
        "Research the top 3 AI Agent Frameworks in 2024 (focus on Python). "
        "Summarize their key features and pros/cons. "
        "Then, draft an email to 'team@example.com' with the subject 'AI Frameworks Research' "
        "containing this summary."
    )
    
    logger.info(f"📝 Query: {query}")
    
    # 3. Execute Workflow
    logger.info("2️⃣ Executing Workflow (this may take 1-2 minutes)...")
    try:
        result = await system.orchestrator.execute(query)
        
        logger.info("✅ Workflow Complete!")
        logger.info("==================================================")
        logger.info("RESULT SUMMARY:")
        print(result)
        logger.info("==================================================")
        
        # 4. Verify Metrics
        logger.info("3️⃣ Verifying Metrics...")
        metrics = get_metrics_collector().get_metrics()
        
        logger.info(f"   Total Agent Calls: {len(metrics['counters'])}")
        logger.info(f"   Errors: {len(metrics['errors'])}")
        
        if len(metrics['counters']) > 0:
            logger.info("✅ Metrics captured successfully!")
        else:
            logger.warning("⚠️ No metrics captured. Check Cloud Logging configuration.")
            
        logger.info("🎉 GRAND FINALE COMPLETE! Please check the Dashboard.")
        
    except Exception as e:
        logger.error(f"❌ Workflow Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(run_grand_finale())
    except KeyboardInterrupt:
        pass

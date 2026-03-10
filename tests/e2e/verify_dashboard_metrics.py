"""
Dashboard Metrics Verification Script

Generates synthetic traffic to verify that metrics are correctly
appearing in the Google Cloud Monitoring Dashboard.

Scenarios:
1. Successful Agent Calls (Success Rate)
2. Failed Agent Calls (Error Rate)
3. Tool Executions (Tool Usage)
4. Latency Simulation (Latency Distribution)
"""

import asyncio
import logging
import os
import random
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Force Cloud Logging
os.environ["USE_CLOUD_LOGGING"] = "true"

from monitoring.metrics import (
    get_metrics_collector,
    AgentMetrics,
    track_time,
    track_errors
)

async def simulate_agent_activity():
    """Simulate realistic agent activity"""
    logger.info("🚀 Starting Dashboard Verification Simulation...")
    logger.info("Generating traffic for Google Cloud Monitoring...")
    
    agents = ["orchestrator", "mailer", "librarian", "analyst"]
    tools = ["gmail_send", "drive_search", "sheets_read", "calendar_create"]
    
    # 1. Generate Successful Calls (High Volume)
    logger.info("1️⃣ Generating Successful Agent Calls...")
    for _ in range(20):
        agent = random.choice(agents)
        duration = random.uniform(0.1, 2.0)
        
        # Simulate work
        await asyncio.sleep(0.05) 
        
        # Record metrics
        AgentMetrics.record_agent_call(agent, success=True)
        get_metrics_collector().record_timing("agent_execution", duration, labels={"agent": agent})
        
        if _ % 5 == 0:
            print(f"   Processed {_} successful requests...")

    # 2. Generate Errors (Low Volume)
    logger.info("2️⃣ Generating Agent Errors...")
    for _ in range(5):
        agent = random.choice(agents)
        
        # Record error
        AgentMetrics.record_agent_call(agent, success=False)
        get_metrics_collector().record_error("api_error", labels={"agent": agent, "code": "500"})
        print(f"   Generated error for {agent}")

    # 3. Generate Tool Executions
    logger.info("3️⃣ Generating Tool Executions...")
    for _ in range(15):
        agent = random.choice(agents)
        tool = random.choice(tools)
        
        AgentMetrics.record_tool_call(agent, tool, success=True)
        
    # 4. Simulate Latency Spikes
    logger.info("4️⃣ Simulating Latency Spikes...")
    for _ in range(3):
        agent = "analyst"
        duration = random.uniform(3.0, 5.0) # High latency
        get_metrics_collector().record_timing("agent_execution", duration, labels={"agent": agent})
        print(f"   High latency request: {duration:.2f}s")

    logger.info("✅ Simulation Complete!")
    logger.info("👉 Please check your Google Cloud Dashboard in 1-2 minutes.")

if __name__ == "__main__":
    try:
        asyncio.run(simulate_agent_activity())
    except KeyboardInterrupt:
        pass

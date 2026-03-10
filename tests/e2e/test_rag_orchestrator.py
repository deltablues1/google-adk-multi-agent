import asyncio
import logging
import os
from dotenv import load_dotenv
import google.auth

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
if not project_id:
    _, project_id = google.auth.default()
    os.environ['GOOGLE_CLOUD_PROJECT'] = project_id

async def test_orchestrator_rag():
    logger.info("🚀 Starting Orchestrator -> RAG Delegation Test...")
    
    # Imports inside function to ensure env is set
    from agents.orchestrator.orchestrator import OrchestratorAgent
    from agents.knowledge_agent import create_knowledge_agent
    
    # 1. Initialize Agents
    logger.info("1️⃣ Initializing Agents...")
    knowledge_agent = create_knowledge_agent()
    orchestrator = OrchestratorAgent()
    
    # Pre-flight check for Knowledge Agent
    logger.info(f"   Testing Knowledge Agent Model: {knowledge_agent.model}")
    try:
        await knowledge_agent.run("Hello")
        logger.info("   ✅ Knowledge Agent Model OK")
    except Exception as e:
        logger.error(f"   ❌ Knowledge Agent Model Failed: {e}")
        
    # Pre-flight check for Orchestrator Agent
    logger.info(f"   Testing Orchestrator Agent Model: {orchestrator.model}")
    try:
        await orchestrator.run("Hello")
        logger.info("   ✅ Orchestrator Agent Model OK")
    except Exception as e:
        logger.error(f"   ❌ Orchestrator Agent Model Failed: {e}")
    
    # 2. Add Knowledge Agent to Orchestrator
    orchestrator.add_sub_agent(knowledge_agent)
    logger.info(f"   Sub-agents: {orchestrator.list_sub_agents()}")
    
    # 3. Ask Question
    question = "Tko je direktor firme Luxtech?"
    logger.info(f"2️⃣ Asking Orchestrator: '{question}'")
    
    try:
        # 1. Get Routing Decision
        logger.info("3️⃣ Getting Routing Decision...")
        decision = await orchestrator.route_request(question)
        logger.info(f"🧭 Routing Decision: {decision}")
        
        target_agent_name = decision.get("agent")
        
        if target_agent_name and target_agent_name != "self":
            # 2. Delegate to Sub-agent
            logger.info(f"4️⃣ Delegating to '{target_agent_name}'...")
            target_agent = orchestrator.get_sub_agent(target_agent_name)
            
            if target_agent:
                response = await target_agent.run(question)
                logger.info(f"🤖 Final Response from {target_agent_name}: {response}")
                
                # Write response to file
                with open("orchestrator_response.txt", "w", encoding="utf-8") as f:
                    f.write(f"Question: {question}\n")
                    f.write(f"Routing Decision: {decision}\n")
                    f.write(f"Final Response: {response}\n")
            else:
                logger.error(f"❌ Target agent '{target_agent_name}' not found in sub-agents.")
        else:
            logger.info("   Handled by Orchestrator directly (or failed to route).")
            response = await orchestrator.run(question)
            logger.info(f"🤖 Orchestrator Response: {response}")
            
    except Exception as e:
        logger.error(f"❌ Orchestrator Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_rag())

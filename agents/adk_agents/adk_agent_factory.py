"""
ADK Agent Factory

Factory functions for creating ADK-compliant agents using LlmAgent primitives.
Replaces custom BaseAgent with native Google ADK agents.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
from google.adk.agents import LlmAgent
from google.genai import types

logger = logging.getLogger(__name__)


def load_instruction_file(agent_name: str) -> Optional[str]:
    """
    Load agent instructions from markdown file.

    Args:
        agent_name: Name of the agent (e.g., "mailer", "researcher")

    Returns:
        Instruction text or None if file not found

    Looks for instructions in: agents/{agent_name}/instructions.md
    """
    # Try to find instructions.md in agent's directory
    base_path = Path(__file__).parent.parent  # Go up to agents/
    instruction_path = base_path / agent_name / "instructions.md"

    if instruction_path.exists():
        try:
            with open(instruction_path, 'r', encoding='utf-8') as f:
                instructions = f.read()
            logger.debug(f"Loaded instructions for {agent_name} from {instruction_path}")
            return instructions
        except Exception as e:
            logger.warning(f"Failed to load instructions for {agent_name}: {e}")
            return None
    else:
        logger.debug(f"No instruction file found at {instruction_path}")
        return None


def create_adk_agent(
    name: str,
    model: str,
    instruction: Optional[str] = None,
    description: Optional[str] = None,
    tools: Optional[List] = None,
    sub_agents: Optional[List] = None,
    config: Optional[Dict[str, Any]] = None,
    load_instruction_from_file: bool = True
) -> LlmAgent:
    """
    Factory for creating ADK LlmAgent instances.

    This replaces the custom BaseAgent class with native ADK agents.

    Args:
        name: Unique agent name (e.g., "mailer", "researcher")
        model: Gemini model name (e.g., "gemini-2.5-flash", "gemini-2.5-pro")
        instruction: System instruction text. If None and load_instruction_from_file=True,
                    will try to load from agents/{name}/instructions.md
        description: Short description for AutoFlow routing (used when agent is a sub-agent)
        tools: List of ADK Tool objects (FunctionTool, google_search, etc.)
        sub_agents: List of child agents for hierarchical composition
        config: Additional configuration (temperature, max_tokens, etc.)
                Note: These are passed through Runner.run_async(), not directly to LlmAgent
        load_instruction_from_file: If True, attempts to load instruction from .md file

    Returns:
        LlmAgent instance

    Example:
        >>> from tools.adk_tools.gmail_adk_tools import get_gmail_adk_tools
        >>> mailer = create_adk_agent(
        ...     name="mailer",
        ...     model="gemini-2.5-flash",
        ...     description="Gmail specialist for email operations",
        ...     tools=get_gmail_adk_tools()
        ... )
    """
    # Load instruction from file if not provided
    if instruction is None and load_instruction_from_file:
        instruction = load_instruction_file(name)

    # Default instruction if still None
    if instruction is None:
        instruction = f"You are {name}, a specialized AI agent."
        logger.warning(f"No instruction found for {name}, using default")

    # Default description
    if description is None:
        description = f"{name.capitalize()} agent"

    # Log agent creation
    logger.info(
        f"Creating ADK agent: {name}",
        extra={
            "model": model,
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "has_sub_agents": bool(sub_agents),
            "sub_agent_count": len(sub_agents) if sub_agents else 0,
            "has_instruction_file": load_instruction_from_file and load_instruction_file(name) is not None
        }
    )

    # Create LlmAgent
    agent = LlmAgent(
        name=name,
        model=model,
        instruction=instruction,
        description=description,
        tools=tools or [],
        sub_agents=sub_agents or []
    )

    # Apply generate_content_config from config dict
    if config:
        gen_config_kwargs = {}
        if "temperature" in config:
            gen_config_kwargs["temperature"] = config["temperature"]
        if "max_tokens" in config:
            gen_config_kwargs["max_output_tokens"] = config["max_tokens"]
        if "max_output_tokens" in config:
            gen_config_kwargs["max_output_tokens"] = config["max_output_tokens"]
        if gen_config_kwargs:
            agent.generate_content_config = types.GenerateContentConfig(**gen_config_kwargs)
            logger.info(f"Agent '{name}' config: {gen_config_kwargs}")

    logger.info(f"ADK agent '{name}' created successfully")
    return agent


def create_sequential_workflow(
    name: str,
    sub_agents: List[LlmAgent],
    description: Optional[str] = None
):
    """
    Create a SequentialAgent workflow.

    SequentialAgent executes sub-agents in order, passing context between them.

    Args:
        name: Workflow name
        sub_agents: List of agents to execute sequentially
        description: Workflow description

    Returns:
        SequentialAgent instance

    Example:
        >>> research_and_report = create_sequential_workflow(
        ...     name="research_pipeline",
        ...     sub_agents=[researcher_agent, scribe_agent, mailer_agent],
        ...     description="Research topic, create document, send email"
        ... )
    """
    from google.adk.agents import SequentialAgent

    return SequentialAgent(
        name=name,
        sub_agents=sub_agents,
        description=description or f"Sequential workflow: {name}"
    )


def create_parallel_workflow(
    name: str,
    sub_agents: List[LlmAgent],
    description: Optional[str] = None,
    aggregation_mode: str = "concatenate"
):
    """
    Create a ParallelAgent workflow.

    ParallelAgent executes sub-agents concurrently and aggregates results.

    Args:
        name: Workflow name
        sub_agents: List of agents to execute in parallel
        description: Workflow description
        aggregation_mode: How to combine results ("concatenate" or "summarize")

    Returns:
        ParallelAgent instance

    Example:
        >>> multi_source_research = create_parallel_workflow(
        ...     name="parallel_research",
        ...     sub_agents=[web_researcher, youtube_researcher, news_researcher],
        ...     aggregation_mode="summarize"
        ... )
    """
    from google.adk.agents import ParallelAgent

    return ParallelAgent(
        name=name,
        sub_agents=sub_agents,
        description=description or f"Parallel workflow: {name}",
        aggregation_mode=aggregation_mode
    )


def create_loop_workflow(
    name: str,
    sub_agents: List[LlmAgent],
    max_iterations: int = 5,
    termination_condition=None,
    description: Optional[str] = None
):
    """
    Create a LoopAgent workflow for iterative improvement.

    LoopAgent executes sub-agents repeatedly until termination condition is met.

    Args:
        name: Workflow name
        sub_agents: List of agents to execute in loop (typically 2: generator + critic)
        max_iterations: Maximum number of iterations
        termination_condition: Callable that takes InvocationContext and returns bool
        description: Workflow description

    Returns:
        LoopAgent instance

    Example:
        >>> def is_approved(ctx):
        ...     return "APPROVED" in ctx.state.get("review_status", "")
        >>>
        >>> iterative_writer = create_loop_workflow(
        ...     name="iterative_document",
        ...     sub_agents=[writer_agent, critic_agent],
        ...     max_iterations=5,
        ...     termination_condition=is_approved
        ... )
    """
    from google.adk.agents import LoopAgent

    return LoopAgent(
        name=name,
        sub_agents=sub_agents,
        max_iterations=max_iterations,
        termination_condition=termination_condition,
        description=description or f"Loop workflow: {name}"
    )

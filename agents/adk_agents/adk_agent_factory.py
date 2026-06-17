"""
ADK Agent Factory

Factory functions for creating ADK-compliant agents using LlmAgent primitives.
Replaces custom BaseAgent with native Google ADK agents.
"""

import os
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
import logging
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types

logger = logging.getLogger(__name__)


# ---- Provider routing (Gemini default; Claude via LiteLLM when enabled) ----

def _gemini_pinned_agents() -> set:
    """Agents that must stay on Gemini/Vertex (e.g. Vertex RAG tools)."""
    base = {"socrates", "christian_guide"}
    for a in os.getenv("CLAUDE_GEMINI_ONLY_AGENTS", "").split(","):
        a = a.strip().lower()
        if a:
            base.add(a)
    return base


def _claude_model_for(model: str) -> str:
    """Map a Gemini tier to a Claude tier (configurable via env)."""
    m = (model or "").lower()
    if "pro" in m:
        return os.getenv("CLAUDE_PRO_MODEL", "claude-sonnet-4-6")
    if "lite" in m:
        return os.getenv("CLAUDE_LITE_MODEL", "claude-haiku-4-5")
    return os.getenv("CLAUDE_FLASH_MODEL", "claude-haiku-4-5")


def _use_anthropic(agent_name: Optional[str]) -> bool:
    if os.getenv("LLM_PROVIDER", "gemini").lower() != "anthropic":
        return False
    return (agent_name or "").lower() not in _gemini_pinned_agents()


def _effective_model_name(model, agent_name: Optional[str] = None) -> str:
    """The model string we actually run with — for logging and token labels."""
    if isinstance(model, str) and _use_anthropic(agent_name):
        return "anthropic/" + _claude_model_for(model)
    return model if isinstance(model, str) else getattr(model, "model", str(model))


def _build_model(model: str, agent_name: Optional[str] = None):
    """Build the model object for an agent.

    Provider is chosen by ``LLM_PROVIDER`` (default ``gemini``). When set to
    ``anthropic``, agents not pinned to Gemini are routed to Claude through
    ADK's LiteLLM wrapper; everything else keeps the Gemini path below.

    Wrap a model name in a Gemini model that retries transient LLM failures.

    The Vertex AI Gemini endpoint returns 429 RESOURCE_EXHAUSTED when the
    per-minute quota bucket is momentarily empty (bursts of requests). Those
    calls are made by the ADK runner itself, so our Workspace-tool retry layer
    (tools/resilience/retry_handler) never sees them. Attaching HttpRetryOptions
    retries ONLY the failed generate_content HTTP call with backoff — the agent
    loop is not re-run, so tool side effects are never duplicated.

    Configurable via env (defaults cover a ~60s per-minute quota window):
      LLM_RETRY_ATTEMPTS (default 5; <=1 disables and uses the plain string)
      LLM_RETRY_INITIAL_DELAY (s, default 2)
      LLM_RETRY_MAX_DELAY (s, default 60)
      LLM_RETRY_EXP_BASE (default 2)
    """
    # Provider routing: Claude via LiteLLM when enabled and not pinned to Gemini.
    if _use_anthropic(agent_name):
        try:
            from google.adk.models.lite_llm import LiteLlm

            claude = _claude_model_for(model)
            logger.info(
                "Routing agent '%s' to Claude via LiteLLM: anthropic/%s",
                agent_name, claude,
            )
            return LiteLlm(model=f"anthropic/{claude}")
        except Exception as e:
            logger.warning(
                "LiteLLM/Claude unavailable for '%s' (%s); falling back to Gemini.",
                agent_name, e,
            )

    try:
        attempts = int(os.getenv("LLM_RETRY_ATTEMPTS", "5"))
    except ValueError:
        attempts = 5

    if attempts <= 1:
        return model

    try:
        retry_options = types.HttpRetryOptions(
            attempts=attempts,
            initial_delay=float(os.getenv("LLM_RETRY_INITIAL_DELAY", "2")),
            max_delay=float(os.getenv("LLM_RETRY_MAX_DELAY", "60")),
            exp_base=float(os.getenv("LLM_RETRY_EXP_BASE", "2")),
            http_status_codes=[429, 503],
        )
        return Gemini(model=model, retry_options=retry_options)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(
            f"Could not build Gemini model with retry_options ({e}); "
            "using plain model string (no LLM retry)"
        )
        return model


def _make_usage_callback(agent_name: str, model_str: str):
    """Build an ADK after_model_callback that records per-agent token usage.

    Framework-level, provider-agnostic — fires for Gemini today and for any
    LiteLLM-routed model (Claude/GPT) later, so the numbers compare directly.
    Fully defensive: any extraction failure is swallowed so it can never break
    a model turn.
    """

    def _after_model(callback_context, llm_response):
        try:
            from tools.observability.token_stats import get_token_stats

            um = getattr(llm_response, "usage_metadata", None)
            if um is None:
                return None
            prompt = getattr(um, "prompt_token_count", 0) or 0
            output = getattr(um, "candidates_token_count", 0) or 0
            cached = getattr(um, "cached_content_token_count", 0) or 0
            total = getattr(um, "total_token_count", 0) or 0
            name = getattr(callback_context, "agent_name", None) or agent_name
            get_token_stats().record(name, model_str, prompt, output, cached, total)
        except Exception:  # never let accounting break inference
            pass
        return None  # do not modify the response

    return _after_model


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
    load_instruction_from_file: bool = True,
    after_tool_callback: Optional[Any] = None,
    before_tool_callback: Optional[Any] = None
) -> LlmAgent:
    """
    Factory for creating ADK LlmAgent instances.

    This replaces the custom BaseAgent class with native ADK agents.

    Args:
        name: Unique agent name (e.g., "mailer", "researcher")
        model: Gemini model name (e.g., "gemini-3.5-flash", "gemini-2.5-pro")
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
        ...     model="gemini-3.5-flash",
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

    # Create LlmAgent (wrap the model so transient LLM 429/503s are retried;
    # routes to Claude via LiteLLM when LLM_PROVIDER=anthropic and not pinned).
    agent_kwargs = dict(
        name=name,
        model=_build_model(model, name),
        instruction=instruction,
        description=description,
        tools=tools or [],
        sub_agents=sub_agents or []
    )
    # Optional ADK guardrail callbacks (validate/transform tool results).
    if after_tool_callback is not None:
        agent_kwargs["after_tool_callback"] = after_tool_callback
    if before_tool_callback is not None:
        agent_kwargs["before_tool_callback"] = before_tool_callback

    # Per-agent token accounting (provider-agnostic; disable with TOKEN_STATS_ENABLED=false).
    if os.getenv("TOKEN_STATS_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
        agent_kwargs["after_model_callback"] = _make_usage_callback(
            name, _effective_model_name(model, name)
        )

    agent = LlmAgent(**agent_kwargs)

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

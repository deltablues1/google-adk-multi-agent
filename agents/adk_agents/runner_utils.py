"""
ADK Runner Utilities

Helper functions for working with Google ADK Runner.
Simplifies common patterns and handles API complexity.
"""

from typing import Optional, AsyncGenerator, Any
import logging
from google.adk.runners import Runner
from google.adk.agents.run_config import RunConfig
from google.adk.sessions import InMemorySessionService, BaseSessionService
from google.genai import types

from config.runtime_patches import apply_runtime_patches

logger = logging.getLogger(__name__)

apply_runtime_patches()


async def run_agent_simple(
    agent,
    user_message: str,
    session_id: str = "default-session",
    user_id: str = "default-user",
    session_service: Optional[BaseSessionService] = None,
    app_name: Optional[str] = None
) -> str:
    """
    Simplified agent execution - returns final text response.

    This is a convenience wrapper that:
    - Creates Runner if needed
    - Converts string to types.Content
    - Handles event iteration
    - Properly processes all event parts (text, function_call, function_response)
    - Extracts final text response

    **Note on Function Calls:**
    When an agent uses tools, this function logs function calls at DEBUG level
    and returns only the final text response. Function calls and responses are
    processed correctly but not included in the returned string.

    Args:
        agent: ADK LlmAgent instance
        user_message: User's message as plain string
        session_id: Session identifier
        user_id: User identifier
        session_service: Optional session service (creates InMemory if None)
        app_name: Application name

    Returns:
        Final response text as string (function calls processed but not included)

    Example:
        >>> from agents.adk_agents.mailer_adk import create_mailer_agent
        >>> mailer = create_mailer_agent()
        >>> response = await run_agent_simple(mailer, "List my Gmail labels")
        >>> print(response)
    """
    # Create session service if not provided
    if session_service is None:
        session_service = InMemorySessionService()

    # Use agent's name if app_name not provided
    if app_name is None:
        # ADK expects app_name to match directory structure
        # Since our agents are in agents/adk_agents/, use "agents"
        app_name = "agents"

    # Create runner
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service
    )

    # Create session - InMemorySessionService requires explicit creation
    # Use get_or_create pattern
    try:
        session = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
    except Exception as e:
        # Session might already exist, that's OK
        logger.debug(f"Session creation note: {e}")

    # Convert string to Content
    content = types.Content(
        role="user",
        parts=[types.Part(text=user_message)]
    )

    # Run agent and collect response
    response_text = ""
    function_calls_made = []
    last_function_responses = []

    try:
        # Call run_async with RunConfig to allow multi-step workflows
        run_config = RunConfig(max_llm_calls=30)
        events = runner.run_async(
            new_message=content,
            session_id=session_id,
            user_id=user_id,
            run_config=run_config
        )

        # Iterate through events
        async for event in events:
            # Log event metadata for debugging
            author = getattr(event, 'author', 'unknown')
            logger.info(f"[EVENT] author='{author}', type={type(event).__name__}")

            # Process event content
            if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
                for part in event.content.parts:
                    # Handle text parts
                    if hasattr(part, 'text') and part.text is not None and part.text.strip():
                        logger.info(f"[TEXT] from '{author}': {part.text[:150]}...")
                        response_text += part.text

                    # Handle function_call parts (log but don't include in text)
                    if hasattr(part, 'function_call') and part.function_call:
                        func_call = part.function_call
                        func_name = getattr(func_call, 'name', 'unknown')
                        function_calls_made.append(func_name)
                        logger.info(f"[TOOL_CALL] {func_name}")

                    # Handle function_response parts - capture FULL response
                    if hasattr(part, 'function_response') and part.function_response:
                        func_resp = part.function_response
                        func_name = getattr(func_resp, 'name', 'unknown')
                        resp_data = getattr(func_resp, 'response', None)
                        if resp_data:
                            # Extract 'result' key if it's a dict, otherwise use full response
                            if isinstance(resp_data, dict) and 'result' in resp_data:
                                result_text = str(resp_data['result'])
                            else:
                                result_text = str(resp_data)
                            last_function_responses.append((func_name, result_text))
                            logger.info(f"[TOOL_RESP] {func_name}: {result_text[:150]}...")
                        else:
                            logger.info(f"[TOOL_RESP] {func_name}: (empty)")

            # Fallback: try direct text access (streaming events)
            elif hasattr(event, 'text') and event.text:
                response_text += event.text

        # Log function calls if any were made
        if function_calls_made:
            logger.info(f"Agent executed {len(function_calls_made)} tool(s): {', '.join(set(function_calls_made))}")

        # Return text if available
        if response_text.strip():
            return response_text

        # Fallback: if tools ran but no text, return the full tool result directly
        if function_calls_made and last_function_responses:
            logger.warning("Orchestrator did not generate summary text - returning tool result directly")
            # Return the last (most complete) function response as the answer
            last_name, last_resp = last_function_responses[-1]
            return last_resp

        return "No response generated"

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise


async def run_agent_stream(
    agent,
    user_message: str,
    session_id: str = "default-session",
    user_id: str = "default-user",
    session_service: Optional[BaseSessionService] = None,
    app_name: Optional[str] = None
) -> AsyncGenerator[Any, None]:
    """
    Stream agent execution - yields events as they occur.

    Use this for streaming responses or when you need fine-grained
    control over event processing.

    Args:
        agent: ADK LlmAgent instance
        user_message: User's message as plain string
        session_id: Session identifier
        user_id: User identifier
        session_service: Optional session service
        app_name: Application name

    Yields:
        Events from agent execution

    Example:
        >>> async for event in run_agent_stream(mailer, "Search emails"):
        ...     print(f"Event: {type(event).__name__}")
        ...     if hasattr(event, 'text'):
        ...         print(f"Text chunk: {event.text}")
    """
    # Create session service if not provided
    if session_service is None:
        session_service = InMemorySessionService()

    # Use agent's name if app_name not provided
    if app_name is None:
        # ADK expects app_name to match directory structure
        # Since our agents are in agents/adk_agents/, use "agents"
        app_name = "agents"

    # Create runner
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service
    )

    # Create session - InMemorySessionService requires explicit creation
    try:
        session = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
    except Exception as e:
        # Session might already exist, that's OK
        logger.debug(f"Session creation note: {e}")

    # Convert string to Content
    content = types.Content(
        role="user",
        parts=[types.Part(text=user_message)]
    )

    # Run agent and yield events
    events = runner.run_async(
        new_message=content,
        session_id=session_id,
        user_id=user_id
    )

    async for event in events:
        yield event


class RunnerHelper:
    """
    Helper class for managing Runner with persistent session.

    Use this when you need multiple interactions with same agent/session.

    Example:
        >>> helper = RunnerHelper(mailer_agent)
        >>> response1 = await helper.run("Search recent emails")
        >>> response2 = await helper.run("Reply to first one")
        >>> # Both use same session, so context is maintained
    """

    def __init__(
        self,
        agent,
        session_id: str = "persistent-session",
        user_id: str = "default-user",
        session_service: Optional[BaseSessionService] = None,
        app_name: Optional[str] = None
    ):
        """
        Initialize helper with agent and session.

        Args:
            agent: ADK LlmAgent instance
            session_id: Session identifier (persistent across calls)
            user_id: User identifier
            session_service: Optional session service
            app_name: Application name
        """
        self.agent = agent
        self.session_id = session_id
        self.user_id = user_id

        # Use agent's name if app_name not provided
        if app_name is None:
            # ADK expects app_name to match directory structure
            # Since our agents are in agents/adk_agents/, use "agents"
            app_name = "agents"
        self.app_name = app_name

        # Create session service
        if session_service is not None:
            self.session_service = session_service
        else:
            import os
            use_persistent = os.environ.get("USE_PERSISTENT_ADK_SESSIONS", "false").lower() == "true"
            if use_persistent:
                from services.adk_session_service import FirestoreADKSessionService
                self.session_service = FirestoreADKSessionService()
                logger.info(f"RunnerHelper using FirestoreADKSessionService for session '{session_id}'")
            else:
                self.session_service = InMemorySessionService()

        # Create runner
        self.runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=self.session_service
        )

        logger.info(f"RunnerHelper initialized for agent '{agent.name}' with session '{session_id}'")

    async def run(self, user_message: str) -> str:
        """
        Run agent with message, maintaining session context.

        Args:
            user_message: User's message

        Returns:
            Response text
        """
        return await run_agent_simple(
            agent=self.agent,
            user_message=user_message,
            session_id=self.session_id,
            user_id=self.user_id,
            session_service=self.session_service,
            app_name=self.app_name
        )

    async def stream(self, user_message: str) -> AsyncGenerator[Any, None]:
        """
        Stream agent execution with message.

        Args:
            user_message: User's message

        Yields:
            Events from execution
        """
        async for event in run_agent_stream(
            agent=self.agent,
            user_message=user_message,
            session_id=self.session_id,
            user_id=self.user_id,
            session_service=self.session_service,
            app_name=self.app_name
        ):
            yield event

    async def stream_content(self, content: types.Content) -> AsyncGenerator[Any, None]:
        """
        Stream agent execution with pre-built Content (supports multimodal).

        Use this when sending images + text together.

        Args:
            content: types.Content with text and/or image parts

        Yields:
            Events from execution
        """
        # Ensure session exists
        try:
            await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=self.session_id
            )
        except Exception:
            pass  # Session might already exist

        events = self.runner.run_async(
            new_message=content,
            session_id=self.session_id,
            user_id=self.user_id
        )

        async for event in events:
            yield event

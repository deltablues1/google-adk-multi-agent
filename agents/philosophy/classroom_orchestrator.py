"""
Philosophy Classroom Orchestrator
"""

from google.adk.agents import SequentialAgent
from agents.philosophy.philosophy_agents import socrates_agent, termination_checker

# Classroom Orchestrator
# Executes the Socratic flow for a single turn:
# 1. Socrates processes the input and generates a response (question).
# 2. TerminationChecker analyzes the interaction to see if we should exit the classroom mode.

classroom_orchestrator = SequentialAgent(
    name="ClassroomOrchestrator",
    description="Orchestrates the Socratic dialogue flow.",
    sub_agents=[socrates_agent, termination_checker],
    # We want to return Socrates' response to the user, but TerminationChecker's output is for state control.
    # In ADK, SequentialAgent usually returns the last agent's output.
    # We might need a custom implementation if we want to return Socrates' text but use Checker's output for state.
    # For now, let's assume the MasterRouter will inspect the session state or the last message.
)

# To make this work smoothly, we might need to ensure TerminationChecker writes to session state
# instead of just returning text.

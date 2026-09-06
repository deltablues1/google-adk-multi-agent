"""A worker that must not be invoked has to be unreachable on BOTH paths.

voice_qa was removed from the orchestrator's AgentTool list, which closed one
execution path and left the other open: main.py hands run_plan_execute the same
unfiltered self.worker_agents, the planner advertised voice_qa in
{AVAILABLE_AGENTS}, and _validate_plan accepted it as a step. With
USE_PLAN_EXECUTE=true the sentinel could still reach a user as literal text.

The list now lives in one place and both paths filter through it.

Run with:
    pytest tests/unit/test_non_callable_workers.py -v
"""

import pytest
from google.adk.agents import LlmAgent

from agents.adk_agents.plan_execute import (
    _build_available_agents,
    _validate_plan,
    create_workflow_planner,
)
from agents.adk_agents.smart_orchestrator import create_smart_orchestrator
from config.deployment_config import (
    NON_CALLABLE_WORKER_AGENTS,
    callable_worker_agents,
)


def _worker(name: str) -> LlmAgent:
    return LlmAgent(
        name=name, model="gemini-3.5-flash", description=f"{name} desc", instruction="x"
    )


WORKERS = [_worker("voice_qa"), _worker("mailer"), _worker("scribe")]


class TestTheListItself:
    def test_voice_qa_is_on_it(self):
        assert "voice_qa" in NON_CALLABLE_WORKER_AGENTS

    def test_the_filter_drops_it_and_keeps_the_rest(self):
        names = [a.name for a in callable_worker_agents(WORKERS)]
        assert names == ["mailer", "scribe"]

    def test_the_filter_tolerates_objects_without_a_name(self):
        assert callable_worker_agents([object()])


class TestOrchestratorPath:
    def test_it_is_not_a_tool(self):
        orc = create_smart_orchestrator(model="gemini-3.5-flash", worker_agents=WORKERS)
        assert "voice_qa" not in {getattr(t, "name", "") for t in orc.tools}


class TestPlanExecutePath:
    def test_the_planner_does_not_advertise_it(self):
        rendered = _build_available_agents(WORKERS)
        assert "**mailer**" in rendered
        assert "voice_qa" not in rendered

    def test_the_built_planner_prompt_does_not_either(self):
        planner = create_workflow_planner(WORKERS)
        instruction = planner.instruction
        text = instruction(None) if callable(instruction) else instruction
        assert "voice_qa" not in text

    @pytest.mark.parametrize("agent", sorted(NON_CALLABLE_WORKER_AGENTS))
    def test_a_plan_step_naming_it_is_rejected(self, agent):
        valid = {a.name for a in callable_worker_agents(WORKERS)}
        plan = {
            "multi_step": True,
            "language": "hr",
            "steps": [
                {"id": "s1", "agent": agent, "request": "odgovori na pitanje"},
            ],
        }
        assert not _validate_plan(plan, valid)

"""
Unit tests for the warehouse voice lane: skladistar keyword routing in
_classify_voice_route plus the sticky confirmation pin that keeps short
follow-ups ("da", "onaj prvi") in the warehouse lane.

Pure routing logic — no Firestore, no LLM.

Run with:
    pytest tests/unit/test_voice_warehouse_routing.py -v
"""

import time

import pytest

from interfaces.base_interface import (
    BaseInterface,
    ORCHESTRATOR_VOICE_ROUTE,
    VOICE_LANE_PIN_TTL_SECONDS,
)


class _StubSystem:
    philosophy_keywords = {"filozofij", "sokrat"}


class _VoiceInterface(BaseInterface):
    """Minimal concrete BaseInterface for routing tests."""

    def __init__(self):
        super().__init__(session_prefix="test")
        self.system = _StubSystem()

    async def start(self) -> None:  # pragma: no cover - unused
        pass

    async def stop(self) -> None:  # pragma: no cover - unused
        pass

    def format_response(self, response: str) -> str:  # pragma: no cover - unused
        return response


@pytest.fixture
def iface():
    return _VoiceInterface()


class TestWarehouseClassification:

    def test_stock_query_routes_to_skladistar(self, iface):
        assert iface._classify_voice_route(
            "koliko imam vijaka na skladištu"
        ) == ("agent", "skladistar")

    def test_add_stock_routes_to_skladistar(self, iface):
        assert iface._classify_voice_route(
            "dodaj 5 komada kabela na stanje"
        ) == ("agent", "skladistar")

    def test_inventory_keyword_routes_to_skladistar(self, iface):
        assert iface._classify_voice_route(
            "napravi mi inventuru"
        ) == ("agent", "skladistar")

    def test_business_keywords_still_win_over_warehouse(self, iface):
        # "racun" is a business keyword; mixed requests must reach the
        # orchestrator even when warehouse words are present.
        route_type, _ = iface._classify_voice_route(
            "dodaj 5 komada na skladište i izdaj račun"
        )
        assert route_type == ORCHESTRATOR_VOICE_ROUTE

    def test_fiscalization_still_routes_to_orchestrator(self, iface):
        route_type, _ = iface._classify_voice_route("fiskaliziraj fakturu za kupca")
        assert route_type == ORCHESTRATOR_VOICE_ROUTE

    def test_smart_home_lane_unaffected(self, iface):
        assert iface._classify_voice_route(
            "upali svjetlo u kuhinji"
        ) == ("agent", "smart_home")

    def test_general_question_still_falls_to_voice_qa(self, iface):
        assert iface._classify_voice_route(
            "što misliš o vremenu sutra"
        ) == ("agent", "voice_qa")


class TestVoiceLanePin:

    SESSION = "sess-1"

    def _pin_skladistar(self, iface):
        """Simulate a turn that routed to skladistar (sets the pin)."""
        rt, tgt = iface._apply_voice_lane_pin(
            self.SESSION, "dodaj 5 komada vijaka na skladište", "agent", "skladistar"
        )
        assert (rt, tgt) == ("agent", "skladistar")

    def test_confirmation_da_follows_pin(self, iface):
        self._pin_skladistar(iface)
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "skladistar")

    def test_disambiguation_answer_follows_pin(self, iface):
        self._pin_skladistar(iface)
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "onaj prvi", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "skladistar")

    def test_da_without_pin_stays_voice_qa(self, iface):
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_long_unrelated_message_ignores_and_clears_pin(self, iface):
        self._pin_skladistar(iface)
        long_msg = "možeš li mi objasniti kako funkcionira fotosinteza kod biljaka u dubokoj sjeni"
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, long_msg, "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")
        # Pin is void after the topic change: a later "da" must not hijack.
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_other_agent_turn_clears_pin(self, iface):
        self._pin_skladistar(iface)
        # christian_guide is not a pinned lane -> the turn voids the pin
        rt, tgt = iface._apply_voice_lane_pin(
            self.SESSION, "tko je papa", "agent", "christian_guide"
        )
        assert (rt, tgt) == ("agent", "christian_guide")
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_smart_home_turn_clears_pin_like_other_agents(self, iface):
        # smart_home is deliberately NOT pinned per-turn (that was too broad —
        # an unrelated short question after "upali svjetlo" landed in the
        # wrong agent). Its confirmations route via the pending-approval
        # one-shot pin in _process_turn_approvals instead.
        self._pin_skladistar(iface)
        rt, tgt = iface._apply_voice_lane_pin(
            self.SESSION, "ugasi bojler", "agent", "smart_home"
        )
        assert (rt, tgt) == ("agent", "smart_home")
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_expired_pin_is_ignored(self, iface):
        self._pin_skladistar(iface)
        # Force expiry
        agent_name, _expires = iface._voice_pinned_lane[self.SESSION]
        iface._voice_pinned_lane[self.SESSION] = (agent_name, time.time() - 1)
        rt, tgt = iface._apply_voice_lane_pin(self.SESSION, "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_pin_is_per_session(self, iface):
        self._pin_skladistar(iface)
        rt, tgt = iface._apply_voice_lane_pin("other-session", "da", "agent", "voice_qa")
        assert (rt, tgt) == ("agent", "voice_qa")

    def test_pin_ttl_is_sane(self):
        assert 30 <= VOICE_LANE_PIN_TTL_SECONDS <= 600


class TestEndToEndClassifyWithPin:
    """classify + pin composed the same way process_message does."""

    SESSION = "sess-e2e"

    def _route(self, iface, message: str):
        rt, tgt = iface._classify_voice_route(message)
        return iface._apply_voice_lane_pin(self.SESSION, message, rt, tgt)

    def test_full_confirmation_flow(self, iface):
        assert self._route(iface, "dodaj pet komada vijaka na skladište") == ("agent", "skladistar")
        assert self._route(iface, "da") == ("agent", "skladistar")

    def test_abort_flow(self, iface):
        assert self._route(iface, "skini tri metra kabela sa stanja") == ("agent", "skladistar")
        assert self._route(iface, "ne, odustani") == ("agent", "skladistar")

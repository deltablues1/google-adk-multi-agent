"""
A confirmed write must happen once, not once per retry.

erp_record_payment took an idempotency_key and minted a fresh uuid4 whenever the
model left it empty — which defeats the mechanism exactly: the repository dedups
on that key, so a new one per call guarantees a retry is never recognised as a
duplicate. erp_adjust_stock had no key at all and computes an absolute quantity
from a read, so a replay applies the delta a second time. erp_create_product's
auto SKU carries a random suffix, so a retry makes a second product instead of
colliding with the first.

Run with:
    pytest tests/unit/test_erp_write_once.py -v
"""

import pytest

from tools.adk_tools import erp_adk_tools as erp


@pytest.fixture(autouse=True)
def clean():
    erp._RECENT_WRITES.clear()
    yield
    erp._RECENT_WRITES.clear()


class TestDerivedKeysAreStable:
    def test_the_same_payment_yields_the_same_key(self):
        parts = dict(invoice_id="I1", amount=500.0, payment_date="2026-09-03",
                     payment_method="transfer", reference="123")
        assert erp._derive_idempotency_key("payment", **parts) == \
               erp._derive_idempotency_key("payment", **parts)

    def test_a_different_amount_is_a_different_payment(self):
        base = dict(invoice_id="I1", payment_date="2026-09-03", payment_method="transfer")
        assert erp._derive_idempotency_key("payment", amount=500.0, **base) != \
               erp._derive_idempotency_key("payment", amount=50.0, **base)

    def test_the_key_is_not_random(self):
        """The bug was a fresh uuid4 per call — two calls, two keys, no dedup."""
        keys = {erp._derive_idempotency_key("payment", invoice_id="I1", amount=1) for _ in range(5)}
        assert len(keys) == 1


class TestReplayWindow:
    def test_an_identical_write_is_recognised(self):
        key, earlier = erp._replay_of("stock", product_id="P1", delta=-5)
        assert earlier is None
        erp._remember_write(key, {"success": True, "new_quantity": 15})

        _, again = erp._replay_of("stock", product_id="P1", delta=-5)
        assert again == {"success": True, "new_quantity": 15}

    def test_a_different_delta_is_a_different_write(self):
        key, _ = erp._replay_of("stock", product_id="P1", delta=-5)
        erp._remember_write(key, {"success": True})
        _, other = erp._replay_of("stock", product_id="P1", delta=-50)
        assert other is None

    def test_a_different_product_is_a_different_write(self):
        key, _ = erp._replay_of("stock", product_id="P1", delta=-5)
        erp._remember_write(key, {"success": True})
        _, other = erp._replay_of("stock", product_id="P2", delta=-5)
        assert other is None

    def test_the_window_expires(self, monkeypatch):
        import time

        key, _ = erp._replay_of("stock", product_id="P1", delta=-5)
        erp._remember_write(key, {"success": True})
        stale = time.monotonic() - erp._REPLAY_WINDOW_SECONDS - 1
        erp._RECENT_WRITES[key] = (stale, {"success": True})

        _, again = erp._replay_of("stock", product_id="P1", delta=-5)
        assert again is None, "a legitimate correction later must not be suppressed"


class TestWarehousePromptSpeaksTheToolsLanguage:
    """erp_create_product accepts kom|m|kg|l|h; speech does not."""

    def _prompt(self):
        from pathlib import Path

        return (
            Path(__file__).resolve().parents[2] / "agents" / "skladistar" / "instructions.md"
        ).read_text(encoding="utf-8")

    @pytest.mark.parametrize("spoken", ["metara", "kilograma", "litara", "sati", "komada"])
    def test_spoken_units_are_mapped(self, spoken):
        assert spoken in self._prompt()

    def test_unknown_units_are_asked_about_not_invented(self):
        assert "ne izmišljaj novu" in self._prompt()

    def test_candidates_are_numbered_so_onaj_prvi_resolves(self):
        prompt = self._prompt()
        assert "REDNIM BROJEVIMA" in prompt
        assert "onaj prvi" in prompt

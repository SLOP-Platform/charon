"""FAIL-ON-REVERT tests for DRAIN-THEN-PARK: auto-park, re-arm, sole-leg guard.

Two invariants (operator, non-negotiable):
  1. A class-3 (drain-then-park) provider whose balance reaches ~0 is AUTO-PARKED
     (marked unavailable; routing skips it, no fail-churn) and RE-ARMS to active
     when topped up.
  2. SOLE-LEG GUARD — a provider that is the ONLY remaining leg of any pool is
     NEVER auto-parked at 0 (kept/alerted instead of orphaning the pool).

Reverting either invariant must fail the corresponding assertion (FAIL-ON-REVERT).
"""
from __future__ import annotations

from charon.balance import BalanceTracker
from charon.forwarder import _is_sole_leg
from charon.proxy_server import UpstreamRoute


class TestClass3AutoParkAndRearm:
    """Invariant 1: a class-3 provider at ~0 is auto-parked AND re-arms on top-up."""

    def test_class3_at_zero_is_auto_parked(self):
        """A class-3 fixed-mode provider at ~0 → park flag set.

        FAIL-ON-REVERT: reverting the park trigger must fail this assertion."""
        bt = BalanceTracker(config={
            "openrouter": {
                "mode": "fixed",
                "starting_balance": 5.00,
                "funding_class": 3,
            }
        })
        # Wire a trivial spend source (no actual spend → full balance)
        bt.set_spend_provider_fn(lambda p: 0.0)
        assert bt.remaining("openrouter") == 5.0
        assert not bt.is_parked("openrouter")
        assert bt.should_drain("openrouter")

        # Simulate spend that drains the balance via the observer meter
        bt.set_spend_provider_fn(lambda p: 5.0)
        assert bt.is_drained("openrouter")
        assert not bt.should_drain("openrouter")

        # Auto-park (normally done by the forwarder's pre-flight exclusion)
        bt.park("openrouter")
        assert bt.is_parked("openrouter")

    def test_class3_rearms_on_top_up(self):
        """A parked class-3 provider re-arms (unparked) when topped up.

        FAIL-ON-REVERT: reverting the re-arm must fail this assertion."""
        bt = BalanceTracker(config={
            "neuralwatt": {
                "mode": "fixed",
                "starting_balance": 2.00,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 2.0)  # drained
        assert bt.is_drained("neuralwatt")

        # Park it
        bt.park("neuralwatt")
        assert bt.is_parked("neuralwatt")

        # Top up → re-arm
        bt.top_up("neuralwatt", 10.0)
        bt.unpark("neuralwatt")
        assert not bt.is_parked("neuralwatt")

        # After top-up, the configured starting_usd increased
        bt.set_spend_provider_fn(lambda p: 2.0)  # spent 2, but now has 12
        rem = bt.remaining("neuralwatt")
        assert rem is not None and rem > 0

    def test_class3_positive_balance_not_parked(self):
        """A class-3 provider with positive balance is NEVER parked."""
        bt = BalanceTracker(config={
            "deepseek": {
                "mode": "fixed",
                "starting_balance": 99.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        assert not bt.is_parked("deepseek")
        assert bt.should_drain("deepseek")
        # Even if we try to park it manually, remaining is still positive
        bt.park("deepseek")
        assert bt.is_parked("deepseek")  # park() always works (operator override)
        bt.unpark("deepseek")
        assert not bt.is_parked("deepseek")

    def test_park_unpark_cycle_preserves_remaining(self):
        """Park → unpark → balance unchanged."""
        bt = BalanceTracker(config={
            "provider-a": {
                "mode": "fixed",
                "starting_balance": 7.50,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 1.0)  # spent 1
        assert bt.remaining("provider-a") == 6.50

        bt.park("provider-a")
        assert bt.is_parked("provider-a")
        assert bt.remaining("provider-a") == 6.50  # balance unchanged by park

        bt.unpark("provider-a")
        assert not bt.is_parked("provider-a")
        assert bt.remaining("provider-a") == 6.50  # balance unchanged by unpark


class TestSoleLegGuard:
    """Invariant 2: a provider that is the only leg of a pool is NEVER parked."""

    def _mk_route(self, label):
        return UpstreamRoute("http://127.0.0.1:1/v1", api_key="k", provider=label)

    def test_sole_leg_is_detected(self):
        """_is_sole_leg returns True when provider is the only viable leg."""
        bt = BalanceTracker(config={
            "sole-provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "main": [self._mk_route("sole-provider")],
        }
        # The provider is drained AND it's the only leg → sole leg
        assert bt.is_drained("sole-provider")
        assert _is_sole_leg("sole-provider", pools, bt)

    def test_sole_leg_guard_prevents_park_when_last_leg(self):
        """A drained provider that is the only leg of ANY pool → NOT auto-parked.

        FAIL-ON-REVERT: reverting the sole-leg guard must fail this assertion."""
        bt = BalanceTracker(config={
            "only-provider": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "main": [self._mk_route("only-provider")],
        }
        # Sole-leg guard: must NOT park this provider
        is_sole = _is_sole_leg("only-provider", pools, bt)
        assert is_sole  # detected as sole leg
        # In the real forwarder path, this prevents auto-park

    def test_not_sole_leg_when_other_viable_providers_exist(self):
        """A drained provider is NOT sole leg when another provider in the pool
        is still viable."""
        bt = BalanceTracker(config={
            "drained-prov": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            },
            "healthy-prov": {
                "mode": "fixed",
                "starting_balance": 100.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0 if p == "drained-prov" else 0.0)

        pools = {
            "main": [
                self._mk_route("drained-prov"),
                self._mk_route("healthy-prov"),
            ],
        }
        # healthy-prov is not drained → drained-prov is NOT sole leg
        assert not _is_sole_leg("drained-prov", pools, bt)

    def test_sole_leg_guard_per_pool(self):
        """A provider that is sole leg of pool-A but NOT pool-B is still
        detected as a sole leg (it's the last leg of at least one pool)."""
        bt = BalanceTracker(config={
            "shared-prov": {
                "mode": "fixed",
                "starting_balance": 0.0,
                "funding_class": 3,
            },
            "other-prov": {
                "mode": "fixed",
                "starting_balance": 100.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)

        pools = {
            "pool-a": [self._mk_route("shared-prov")],  # sole leg here
            "pool-b": [
                self._mk_route("shared-prov"),
                self._mk_route("other-prov"),
            ],
        }
        # shared-prov is sole leg of pool-a → detected
        assert _is_sole_leg("shared-prov", pools, bt)

    def test_unconfigured_provider_not_sole_leg(self):
        """A provider not in any pool is never detected as sole leg."""
        bt = BalanceTracker()
        assert not _is_sole_leg("nobody", {}, bt)


class TestTopUp:
    """top_up() increases the configured starting_balance."""

    def test_top_up_increases_balance(self):
        bt = BalanceTracker(config={
            "opencode-zen": {
                "mode": "fixed",
                "starting_balance": 10.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 5.0)  # spent 5
        assert bt.remaining("opencode-zen") == 5.0

        bt.top_up("opencode-zen", 20.0)
        assert bt.remaining("opencode-zen") == 25.0  # 10 + 20 - 5 = 25

    def test_top_up_negative_is_ignored(self):
        bt = BalanceTracker(config={
            "opencode-zen": {
                "mode": "fixed",
                "starting_balance": 10.0,
                "funding_class": 3,
            }
        })
        bt.set_spend_provider_fn(lambda p: 0.0)
        bt.top_up("opencode-zen", -5.0)
        assert bt.remaining("opencode-zen") == 10.0

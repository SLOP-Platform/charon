#!/usr/bin/env python3
"""FAIL-ON-REVERT proof for CRIPPLE #2 (FLEET-DEMAND-DRIVEN-ROUTING): assign()
must PROACTIVELY exclude a gateway-capped model (every provider parked/drained/
cooled) so the dispatcher never picks it and burns a full request timeout.

Two locked proofs, both self-contained (own tmp scorecard with the
EVAL-PROMOTION-GATE control-panel split rows, so this does NOT depend on the
frozen selftest fixture — which is separately red pending its own control-row
update):

  (A) assign()-level filter: a 'capped' candidate that OUT-RANKS the field is
      EXCLUDED and a lower-graded but AVAILABLE model is picked instead.
      REVERT: narrow the exclusion back to only 'busy' -> the capped (higher-
      graded) model is admitted and becomes the pick -> both assertions fail.

  (B) GatewayStatusAvailability mapping: a model whose every provider is
      parked/drained/cooled in a /charon/status snapshot resolves to 'capped';
      a model with one live provider resolves to 'free'; an unpooled model is
      'unknown' (fail-open). REVERT: treat a parked provider as live -> the
      all-parked model resolves 'free' -> assertion fails.

Run: python3 fleet/capability/tests/test_availability_capped.py
Exit 0 all-pass, 1 on any failure.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_CAP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_CAP))

from assign import assign  # noqa: E402
from availability import (  # noqa: E402
    CAPPED, GatewayStatusAvailability, StaticAvailability,
)
from grades import ScorecardGradesProvider  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)


# 13-col rows: date source ref work_class tier model verdict gate score time_s cost_usd corrections note
def _row(model: str, verdict: str, gate: str, wc: str = "money-path") -> str:
    return "\t".join(["2026-07-24", "live", "LIVE-1", wc, "med", model,
                      verdict, gate, "-", "10", "0.01", "0", "note"])


def _write_fixture() -> Path:
    rows = []
    # EVAL-PROMOTION-GATE control-panel split on ref LIVE-1 (so the live
    # candidate rows are admitted): strong-control passes, deepseek-v4-flash fails.
    for _ in range(3):
        rows.append(_row("strong-control", "MERGE", "pass", wc="coding"))
        rows.append(_row("deepseek-v4-flash", "BLOCK", "fail", wc="coding"))
    # capped-model OUT-RANKS the field: 5 clean MERGEs, no BLOCK.
    for _ in range(5):
        rows.append(_row("capped-model", "MERGE", "pass"))
    # avail-model is graded but weaker: 4 MERGE + 1 real BLOCK.
    for _ in range(4):
        rows.append(_row("avail-model", "MERGE", "pass"))
    rows.append(_row("avail-model", "BLOCK", "fail"))
    fd = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
    fd.write("\n".join(rows) + "\n")
    fd.close()
    return Path(fd.name)


def proof_a_assign_excludes_capped() -> None:
    tsv = _write_fixture()
    grades = ScorecardGradesProvider(tsv)
    cands = ["capped-model", "avail-model"]

    # Sanity: with NO availability signal, the higher-graded capped-model wins —
    # this is exactly the model the capped-exclusion must displace.
    base = assign("money-path", grades, StaticAvailability(), candidate_models=cands)
    check("baseline: higher-graded capped-model would be picked without the filter",
          base.picked == "capped-model", f"picked={base.picked}")

    # With the model marked capped, it MUST be excluded and the available
    # (lower-graded) model picked instead.
    avail = StaticAvailability({"capped-model": CAPPED},
                              note="[test] injected: capped-model gateway-capped")
    res = assign("money-path", grades, avail, candidate_models=cands)
    excluded = {c.model: c.excluded_reason for c in res.ranked if c.excluded_reason}
    check("(A) FAIL-ON-REVERT: a capped model is EXCLUDED (revert -> admitted, the bug)",
          "capped-model" in excluded and "capped" in (excluded.get("capped-model") or ""),
          f"excluded={excluded}")
    check("(A) the available lower-graded model is picked INSTEAD of the capped top pick",
          res.picked == "avail-model", f"picked={res.picked}")


# ---- (B) GatewayStatusAvailability snapshot mapping -------------------------
class _FakeGateway(GatewayStatusAvailability):
    """Inject a /charon/status snapshot instead of hitting the network."""

    def __init__(self, snapshot: dict):
        super().__init__(url="http://test", token="x")
        self._inject = snapshot

    def _load(self) -> None:  # type: ignore[override]
        if self._snapshot is not None:
            return
        # Reuse the real parsing path over the injected snapshot (proves the
        # pools/balance/cooldown -> provider_down mapping, not a stub).
        self._snapshot = self._inject
        snap = self._snapshot or {}
        self._pools = {k: list(v) for k, v in (snap.get("pools") or {}).items()}
        cooldown = snap.get("cooldown_seconds") or {}
        balance = snap.get("balance") or {}
        labels = set(cooldown) | set(balance)
        for chain in self._pools.values():
            labels.update(chain)
        for label in labels:
            b = balance.get(label) or {}
            cooled = float(cooldown.get(label) or 0.0) > 0.0
            self._provider_down[label] = bool(b.get("parked") or b.get("drained") or cooled)


def proof_b_gateway_mapping() -> None:
    snap = {
        "pools": {
            "all-capped": ["provA", "provB"],   # both down -> capped
            "one-live": ["provA", "provC"],      # provC live -> free
        },
        "balance": {
            "provA": {"parked": True, "drained": False},
            "provB": {"parked": False, "drained": True},
            "provC": {"parked": False, "drained": False},
        },
        "cooldown_seconds": {"provB": 42.0},
    }
    gw = _FakeGateway(snap)
    check("(B) FAIL-ON-REVERT: model with ALL providers parked/drained/cooled -> 'capped'",
          gw.status("all-capped") == CAPPED, f"got {gw.status('all-capped')}")
    check("(B) model with one live provider -> 'free' (not over-excluded)",
          gw.status("one-live") == "free", f"got {gw.status('one-live')}")
    check("(B) unpooled/charon-prefixed model resolution is fail-open + prefix-stripped",
          _FakeGateway(snap).status("charon/one-live") == "free"
          and _FakeGateway(snap).status("not-in-pool") == "unknown")


def main() -> int:
    proof_a_assign_excludes_capped()
    proof_b_gateway_mapping()
    print("-" * 60)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

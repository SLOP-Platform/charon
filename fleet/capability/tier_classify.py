#!/usr/bin/env python3
"""tier_classify.py — the WORK->TIER rule (the ticket-capability classifier).

WHY THIS EXISTS (drift root cause): the ticket `tier:` field was free text,
hand-set at creation, validated for NOTHING. TIER-CANON.md defines `tier` only as
a MODEL cost-band, never as a ticket property, so authors borrowed the model
vocabulary (economy/strong/frontier) with no mapping function behind it. Result:
an 86%-default-to-`strong` catch-all and wrong-capability routing (assign.py:12
filters eligible models by the ticket's declared tier). This module is the missing
mapping function — a PURE, deterministic rule from signals ALREADY captured on
every live ticket (work_class, difficulty, owns) to a tier, plus the LiteLLM
tier-TAG (the routing half) that maps that tier to a litellm.Router model-group.

TWO CONSUMERS, ONE TABLE (mirrors TIER-CANON's TIER_COST_THRESHOLDS discipline):
  1. validate_board.sh drift check  — declared `tier` vs rule-derived tier; a
     hand-set wrong tier can no longer silently drift (WARN, RED for a
     configurable set in fleet/state/tier-drift-red.txt).
  2. the gateway routing path        — classify_tier() emits the tier tag; the
     tag resolves to a litellm model-group via fleet/tier-models.tsv (see
     build_router_model_list / --router-validate). ZERO new deps: reuses the
     litellm.Router already vendored for the gateway.

The rule itself is documented + rationalised in the derived rubric
(scratchpad tier-classification-rubric.md §b). Thresholds/patterns live in the
RULES block below — the ONE table both consumers read.
"""
from __future__ import annotations
import argparse
import glob
import os
import re
import sys

# ── THE ONE TABLE: signal patterns (rubric §b "Signals") ─────────────────────
# security-critical surfaces: mis-run key/egress/auth work leaks credentials.
SEC_RE     = re.compile(r'egress|exfil|secret|(^|[_/])key|token|auth|providers\.py|key-canary')
# LIVE request/spend-forwarding runtime: a bug here drops or misroutes real traffic+spend.
LIVEFWD_RE = re.compile(r'forwarder|proxy_server|gateway\.py|litellm_plane|park_cooldown|cutover')
# money-adjacent modules (pricing tables, inventory, ledgers, quotas).
MONEY_RE   = re.compile(r'balance|metering|cost_rank|routing_policy|pricing|price|tier-models|quota|ledger')
# product runtime (hot path) not otherwise caught.
HOT_RE     = re.compile(r'src/charon/')
MONEY_WORK_CLASSES = ("money-path", "routing")
ECON_WORK_CLASSES  = ("docs", "tests", "rig-meta", "ci-infra", "refactor", "bugfix")
TIERS = ("economy", "strong", "frontier")


def _signals(owns: str):
    paths = [p.strip() for p in owns.split(",") if p.strip()]
    code  = [p for p in paths if not p.lstrip().startswith("(")]  # drop prose entries
    nsurf = len([p for p in code if not p.endswith(".md")]) or len(code)
    sec     = any(SEC_RE.search(p)     for p in code)
    livefwd = any(LIVEFWD_RE.search(p) for p in code)
    money_p = any(MONEY_RE.search(p)   for p in code)
    hot     = any(HOT_RE.search(p)     for p in code)
    return code, nsurf, sec, livefwd, money_p, hot


def classify_tier(work_class: str, difficulty: int, owns: str) -> tuple[str, str]:
    """Pure fn (work_class, difficulty, owns) -> (tier, reason). FIRST match wins.

    Ordered exactly per rubric §b "Tier decision". Returns the reason so the
    drift check and routing path are auditable, never a black box.
    """
    wc = (work_class or "").strip()
    try:
        d = int(str(difficulty).split()[0])
    except (ValueError, IndexError, AttributeError):
        d = 0
    _code, nsurf, sec, livefwd, money_p, hot = _signals(owns or "")
    money = wc in MONEY_WORK_CLASSES or livefwd or money_p

    if sec:
        return "frontier", "security-critical path (ratchet: never trade capability)"
    if money and (d >= 4 or (livefwd and d >= 3) or nsurf >= 3):
        return "frontier", f"money+ (livefwd={int(livefwd)} d{d} nsurf{nsurf})"
    if money:
        return "strong", f"money floor (d{d} nsurf{nsurf})"
    if d >= 5:
        return "frontier", "max difficulty 5"
    if hot and d >= 4:
        return "frontier", f"product hot-path d{d}"
    if wc == "docs":
        return ("strong", f"docs d{d}") if d >= 4 else ("economy", f"docs d{d}")
    if wc == "design-review":
        return ("frontier", f"design-review d{d}") if d >= 4 else ("strong", f"design-review d{d}")
    if not (hot or money or sec) and (
        d == 1 or (d <= 2 and nsurf <= 1 and wc in ECON_WORK_CLASSES)
    ):
        return "economy", f"trivial single-surface {wc} d{d}"
    return "strong", f"middle band d{d} {wc}"


# ── board scan / drift ───────────────────────────────────────────────────────
def _field(txt: str, name: str) -> str:
    m = re.search(r'(?m)^%s: *(.*)$' % re.escape(name), txt)
    return m.group(1).strip() if m else ""


def _red_set(fleet_dir: str) -> set[str]:
    """Configurable RED set — tickets whose tier drift is a hard fail, not WARN.
    One ticket id per line in fleet/state/tier-drift-red.txt (# comments ok).
    Absent/empty -> every mismatch is WARN (advisory-first, per rubric §b)."""
    path = os.path.join(fleet_dir, "state", "tier-drift-red.txt")
    out: set[str] = set()
    if os.path.exists(path):
        for line in open(path):
            s = line.split("#", 1)[0].strip()
            if s:
                out.add(s)
    return out


def board_drift(board_dir: str):
    """-> list of (ticket, declared, derived, reason) where declared != derived."""
    rows = []
    for f in sorted(glob.glob(os.path.join(board_dir, "*.md"))):
        txt = open(f).read()
        tid = os.path.basename(f)[:-3]
        declared = _field(txt, "tier")
        if not declared:
            continue  # tier-missing is validate_board's own concern, not ours
        derived, reason = classify_tier(
            _field(txt, "work_class"), _field(txt, "difficulty"), _field(txt, "owns")
        )
        if derived != declared:
            rows.append((tid, declared, derived, reason))
    return rows


# ── LiteLLM tier-TAG -> model-group (the routing half) ───────────────────────
GATEWAY_API_BASE = os.environ.get("CHARON_GATEWAY", "http://10.0.1.60:8080")


def load_tier_chains(tsv_path: str) -> dict[str, list[str]]:
    """Parse fleet/tier-models.tsv -> {tier: [model-id failover chain]}."""
    chains: dict[str, list[str]] = {}
    for line in open(tsv_path):
        line = line.rstrip("\n")
        if not line or line.lstrip().startswith("#") or "\t" not in line:
            continue
        tier, chain = line.split("\t", 1)
        chains[tier.strip()] = [m.strip() for m in chain.split(",") if m.strip()]
    return chains


def build_router_model_list(tsv_path: str) -> list[dict]:
    """Turn each tier into a litellm.Router model-GROUP: model_name=<tier tag>,
    one deployment per failover-chain id, each pointing at the Charon gateway.
    The derived tier tag IS the litellm model_group name — that is the routing map."""
    ml = []
    for tier, chain in load_tier_chains(tsv_path).items():
        for mid in chain:
            ml.append({
                "model_name": tier,  # <- the tier tag == litellm model_group
                "litellm_params": {
                    "model": f"openai/{mid}",       # Charon gateway = OpenAI-compatible
                    "api_base": GATEWAY_API_BASE,
                    "api_key": os.environ.get("CHARON_KEY", "sk-charon-local"),
                },
            })
    return ml


def validate_router(tsv_path: str) -> list[str]:
    """PROVE the tag/model-group resolves: build a real litellm.Router from the
    tier chains and confirm every derived tier tag is a resolvable model_group.
    Returns human-readable proof lines. Raises if a tag fails to resolve."""
    from litellm import Router  # vendored for the gateway — zero new dep
    ml = build_router_model_list(tsv_path)
    router = Router(model_list=ml)
    groups = set(router.get_model_names())
    out = [f"router model-groups (tier tags): {sorted(groups)}"]
    for tier in TIERS:
        if tier not in groups:
            raise SystemExit(f"ROUTER-PROOF FAIL: tier tag '{tier}' is not a resolvable model_group")
        deps = [d["litellm_params"]["model"] for d in router.get_model_list(model_name=tier)]
        picked = router.get_available_deployment(model=tier)["litellm_params"]["model"]
        out.append(f"  tag '{tier}' -> group of {len(deps)} deployments {deps}; resolves to {picked}")
    return out


# ── CLI ──────────────────────────────────────────────────────────────────────
def _fleet_root() -> str:
    return os.path.dirname(os.path.abspath(__file__)).rsplit("/capability", 1)[0]


def main(argv=None):
    fleet = _fleet_root()
    ap = argparse.ArgumentParser(description="work->tier classifier + litellm tag proof")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("classify", help="classify one ticket or explicit fields")
    p_c.add_argument("ticket", nargs="?")
    p_c.add_argument("--work-class")
    p_c.add_argument("--difficulty")
    p_c.add_argument("--owns")

    p_d = sub.add_parser("drift", help="board declared-vs-derived tier drift (gate mode)")
    p_d.add_argument("--board", default=os.path.join(fleet, "board"))

    sub.add_parser("router-validate", help="prove tier tags resolve as litellm model-groups")

    args = ap.parse_args(argv)

    if args.cmd == "classify":
        if args.ticket:
            txt = open(os.path.join(fleet, "board", args.ticket + ".md")).read()
            wc, diff, owns = _field(txt, "work_class"), _field(txt, "difficulty"), _field(txt, "owns")
        else:
            wc, diff, owns = args.work_class or "", args.difficulty or "0", args.owns or ""
        tier, why = classify_tier(wc, diff, owns)
        print(f"{tier}\t{why}")
        return 0

    if args.cmd == "drift":
        red = _red_set(fleet)
        rows = board_drift(args.board)
        any_red = False
        for tid, decl, der, why in rows:
            level = "RED" if tid in red else "WARN"
            any_red = any_red or (level == "RED")
            print(f"{level} tier-drift: {tid} declared={decl} derived={der} :: {why}")
        # exit 2 iff a RED-set ticket drifted (validate_board maps this to a hard fail)
        return 2 if any_red else 0

    if args.cmd == "router-validate":
        for line in validate_router(os.path.join(fleet, "tier-models.tsv")):
            print(line)
        return 0


if __name__ == "__main__":
    sys.exit(main())

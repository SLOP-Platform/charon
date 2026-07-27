#!/usr/bin/env python3
"""tier_classify.py — the WORK->TIER rule (the ticket-capability classifier).

WHY THIS EXISTS (drift root cause): the ticket `tier:` field was free text,
hand-set at creation, validated for NOTHING. TIER-CANON.md defines `tier` only as
a MODEL cost-band, never as a ticket property, so authors borrowed the model
vocabulary (economy/strong/frontier) with no mapping function behind it. Result:
an 86%-default-to-`strong` catch-all and wrong-capability routing (assign.py:14-16
filters eligible models by the ticket's declared tier). This module is the missing
mapping function — a PURE, deterministic rule from signals ALREADY captured on
every live ticket (work_class, difficulty, owns) to a tier, plus the LiteLLM
tier-TAG (the routing half) that maps that tier to a litellm.Router model-group.

ONE LIVE CONSUMER (mirrors TIER-CANON's TIER_COST_THRESHOLDS discipline):
  1. validate_board.sh drift check — LIVE. Declared `tier` vs rule-derived tier;
     a hand-set wrong tier can no longer silently drift (WARN by default, RED —
     rc DRIFT_RED_RC — for the ids in fleet/state/tier-drift-red.txt).

DESIGNED, NOT YET WIRED (no production caller — do not assume it is running):
  2. the gateway routing path. classify_tier() is intended to emit a tier TAG
     that resolves to a litellm model-group via fleet/tier-models.tsv (see
     build_router_model_list / the `router-validate` subcommand). As of this
     commit the real routing path (fleet/fleet-droid.sh tier_chain,
     fleet/charon-run.sh) parses fleet/tier-models.tsv with awk and never calls
     into this module; validate_router() is a self-contained proof exercised
     only by fleet/capability/tests/test_tier_classify.py. Wiring it is a
     separate ticket — this docstring previously claimed it as a live consumer,
     which it is not.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effort  # noqa: E402  — the ported EFFORT scorer (see effort.py for the port rationale)

# ── THE ONE TABLE: signal patterns (rubric §b "Signals") ─────────────────────
# security-critical surfaces: mis-run key/egress/auth work leaks credentials.
#
# ANCHORED on path-component boundaries. The original pattern was an UNANCHORED
# substring match, and because this is the FIRST rule with no difficulty guard it
# routed ordinary d1 documentation to the most expensive frontier chain:
#   docs/token-budget.md ("token")   docs/authoring-guide.md ("auth")
#   docs/keyboard-shortcuts.md ("/key")  docs/oauth-notes.md ("auth")
#
# Two bands, because the words differ in how ambiguous they are as English:
#   STRONG words are rare and effectively unambiguous in a path, so they match on
#   any component boundary (/ _ - . or string edge). This keeps genuinely
#   security-critical compound names firing, e.g. fleet/checks/egress-key-canary.sh
#   ("egress"), src/charon/secrets.py, src/charon/keyprobe.py, providers.py.
#   AMBIGUOUS words (key/token/auth) are common English fragments, so they match
#   ONLY as a WHOLE path segment or a whole filename stem — src/charon/auth.py and
#   fleet/auth/wire.sh are security; docs/authoring-guide.md is not.
#
# CASE: deliberately case-INSENSITIVE. The old rule was case-SENSITIVE only by
# accident, which made docs/authoring-guide.md frontier while fleet/state/AUTHORS.md
# was economy. Capitalisation of a path must never decide which model chain runs
# the work; anchoring (not case) is what does the discrimination here.
_SEC_STRONG = r'egress|exfil|secrets?|credentials?|keyprobe|key-canary|api[_-]?keys?|providers\.py'
_SEC_AMBIG  = r'keys?|tokens?|auth'
SEC_RE = re.compile(
    r'(?:^|[/_.\-])(?:' + _SEC_STRONG + r')(?:[/_.\-]|$)'      # boundary-anchored
    r'|(?:^|/)(?:' + _SEC_AMBIG + r')(?:\.[^/]*)?(?:/|$)',     # whole segment / stem
    re.IGNORECASE)
# LIVE request/spend-forwarding runtime: a bug here drops or misroutes real traffic+spend.
LIVEFWD_RE = re.compile(r'forwarder|proxy_server|gateway\.py|litellm_plane|park_cooldown|cutover')
# money-adjacent modules (pricing tables, inventory, ledgers, quotas).
MONEY_RE   = re.compile(r'balance|metering|cost_rank|routing_policy|pricing|price|tier-models|quota|ledger')
# product runtime (hot path) not otherwise caught.
HOT_RE     = re.compile(r'src/charon/')
# REVIEW-CLASS work (F11, OPERATOR-DECIDED 2026-07-24, TIER-BALANCE `decisions:`):
# "Review-class work KEEPS its capability tier; tier_classify.py must not demote it."
# Rationale recorded on the ticket: adversarial review is currently THE load-bearing quality
# mechanism in this rig (on 2026-07-24 alone it caught three fake-greens, a repo-wide
# unbounded-recursion hazard and a design fork that NO gate caught). Cost is the wrong axis to
# optimize on the review path, so this is a RATCHET like SEC_RE — never traded down.
#
# SCOPED TO THE work_class, deliberately. A path-pattern over `owns` (review|preflight|audit|
# e2e) was built and MEASURED first: it promoted 16 unrelated rig tickets — MARKER-PROOF-
# MECHANIZE, REPO-MAP-CONVERGE, SYNC-SCHEDULE, REACHABILITY-GATE … — because "review" and
# "preflight" appear in half this rig's filenames. That is the same false-promotion class F5
# exists to remove, with a new proxy. The operator's own wording ("add review-class
# work_classes to the design-review branch of the rule") is the work_class axis; this is it.
REVIEW_WORK_CLASSES = ("design-review",)
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


def classify_tier(work_class: str, difficulty: int, owns: str, accept: str = "") -> tuple[str, str]:
    """Pure fn (work_class, difficulty, owns, accept) -> (tier, reason). FIRST match wins.

    Ordered exactly per rubric §b "Tier decision". Returns the reason so the
    drift check and routing path are auditable, never a black box.

    ``accept`` is OPTIONAL and additive (callers that pre-date the EFFORT axis
    keep working, they simply score 0 behaviours). It carries the ticket's
    accept block, from which ``effort.count_behaviours`` derives the
    BEHAVIOUR-count signal — the second-strongest term in the ported scorer.
    """
    wc = (work_class or "").strip()
    try:
        d = int(str(difficulty).split()[0])
    except (ValueError, IndexError, AttributeError):
        d = 0
    code, nsurf, sec, livefwd, money_p, hot = _signals(owns or "")
    money = wc in MONEY_WORK_CLASSES or livefwd or money_p
    review = wc in REVIEW_WORK_CLASSES

    # EFFORT (replaces the `nsurf >= 3` BREADTH proxy — see effort.py for the
    # measurement that killed breadth: rho +0.075 vs difficulty's +0.413).
    # size = the ticket's own declared owned-path count; behaviours = its accept
    # items. The F5 difficulty floor lives inside is_high_effort, so no branch
    # here can promote on breadth alone.
    high_effort, eff = effort.is_high_effort(d, len(code), effort.count_behaviours(accept))

    if sec:
        return "frontier", "security-critical path (ratchet: never trade capability)"
    # F11 RATCHET — placed immediately after the security ratchet and BEFORE every branch
    # that can return a cheaper tier (money/docs/economy), so review-class work can never be
    # demoted by a later clause. That ordering IS the "keeps its capability tier" guarantee:
    # the floor was d>=4, which demoted every d3 adversarial review to `strong`.
    if review and d >= 3:
        return "frontier", f"review-class ratchet d{d} (F11: capability never traded down)"
    if money and (d >= 4 or (livefwd and d >= 3) or high_effort):
        return "frontier", f"money+ (livefwd={int(livefwd)} d{d} effort{eff:g})"
    if money:
        return "strong", f"money floor (d{d} effort{eff:g})"
    if d >= 5:
        return "frontier", "max difficulty 5"
    if hot and d >= 4:
        return "frontier", f"product hot-path d{d}"
    if wc == "docs":
        return ("strong", f"docs d{d}") if d >= 4 else ("economy", f"docs d{d}")
    if review:
        return "strong", f"review-class d{d} (floor: never economy)"
    if not (hot or money or sec) and (
        d == 1 or (d <= 2 and nsurf <= 1 and wc in ECON_WORK_CLASSES)
    ):
        return "economy", f"trivial single-surface {wc} d{d}"
    return "strong", f"middle band d{d} {wc}"


# ── board scan / drift ───────────────────────────────────────────────────────
def _field(txt: str, name: str) -> str:
    m = re.search(r'(?m)^%s: *(.*)$' % re.escape(name), txt)
    return m.group(1).strip() if m else ""


def _block_field(txt: str, name: str) -> str:
    """Read a ticket field that may be a YAML-ish BLOCK scalar (``accept: |``).

    ``_field`` returns the literal "|" for those, which would score every
    block-form ticket as ONE behaviour and silently flatten the EFFORT axis on
    the majority of this board (all 104 live tickets write ``accept:`` as a
    block). Mirrors fleet/decompose.sh's parse_ticket: a ``|`` header consumes
    the following indented/blank lines, dedented by two spaces.
    """
    lines = txt.splitlines()
    head = name + ":"
    for i, line in enumerate(lines):
        if not line.startswith(head):
            continue
        rest = line[len(head):]
        if rest.strip() != "|":
            return rest.strip()
        block = []
        j = i + 1
        while j < len(lines) and (lines[j][:1].isspace() or lines[j].strip() == ""):
            block.append(lines[j])
            j += 1
        return "\n".join(b[2:] if b.startswith("  ") else b for b in block).strip()
    return ""


# DISTINCT sentinel for "the gate found a RED condition". It is deliberately NOT 2:
# `python3 <missing-file>` exits 2, and argparse exits 2 on an unknown subcommand, so
# rc 2 from this script means "the check itself is broken" and MUST be treated by the
# caller as a hard failure, never as a successful RED/GREEN verdict. Reserving 3 for
# the verdict is what lets validate_board.sh fail CLOSED when its own machinery is
# missing (previously `mv tier_classify.py .bak` made the whole check vanish, GREEN).
DRIFT_RED_RC = 3


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


def board_scan(board_dir: str):
    """-> (rows, examined).

    rows     = [(ticket, declared, derived, reason)] where declared != derived
    examined = how many tickets actually carried a `tier:` and were compared.

    `examined` exists so the caller can tell "zero drift" apart from "zero
    tickets": a bad --board, an empty checkout or a board where nobody declares
    `tier:` used to produce a confident silent pass (NON-VACUOUS requirement).
    """
    rows = []
    examined = 0
    for f in sorted(glob.glob(os.path.join(board_dir, "*.md"))):
        txt = open(f).read()
        tid = os.path.basename(f)[:-3]
        declared = _field(txt, "tier")
        if not declared:
            continue  # tier-missing is validate_board's own concern, not ours
        examined += 1
        derived, reason = classify_tier(
            _field(txt, "work_class"), _field(txt, "difficulty"), _field(txt, "owns"),
            _block_field(txt, "accept"),
        )
        if derived != declared:
            rows.append((tid, declared, derived, reason))
    return rows, examined


def board_drift(board_dir: str):
    """-> list of (ticket, declared, derived, reason) where declared != derived."""
    return board_scan(board_dir)[0]


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
    p_c.add_argument("--accept", default="", help="accept block (EFFORT behaviour count)")

    p_d = sub.add_parser("drift", help="board declared-vs-derived tier drift (gate mode)")
    p_d.add_argument("--board", default=os.path.join(fleet, "board"))

    # The REVIEWABLE OUTPUT of any rule change: every ticket whose DERIVED tier moves.
    # Deliberately read-only — this tool never rewrites fleet/board/*.md, so a rule change
    # can never silently re-tier the board; a human (or the board-owning ticket) applies it.
    p_dl = sub.add_parser("deltas", help="declared-vs-derived table for the WHOLE board (read-only)")
    p_dl.add_argument("--board", default=os.path.join(fleet, "board"))

    sub.add_parser("router-validate", help="prove tier tags resolve as litellm model-groups")

    args = ap.parse_args(argv)

    if args.cmd == "classify":
        if args.ticket:
            txt = open(os.path.join(fleet, "board", args.ticket + ".md")).read()
            wc, diff, owns = _field(txt, "work_class"), _field(txt, "difficulty"), _field(txt, "owns")
            acc = _block_field(txt, "accept")
        else:
            wc, diff, owns = args.work_class or "", args.difficulty or "0", args.owns or ""
            acc = args.accept or ""
        tier, why = classify_tier(wc, diff, owns, acc)
        print(f"{tier}\t{why}")
        return 0

    if args.cmd == "deltas":
        rows, examined = board_scan(args.board)
        for tid, decl, der, why in rows:
            print(f"{tid}\t{decl}\t->\t{der}\t{why}")
        print(f"# {len(rows)} derived-tier delta(s) over {examined} declared tier(s)")
        if examined == 0:
            print("# RED: vacuous scan — 0 declared tiers compared", file=sys.stderr)
            return DRIFT_RED_RC
        return 0

    if args.cmd == "drift":
        red = _red_set(fleet)
        rows, examined = board_scan(args.board)
        any_red = False
        for tid, decl, der, why in rows:
            level = "RED" if tid in red else "WARN"
            any_red = any_red or (level == "RED")
            print(f"{level} tier-drift: {tid} declared={decl} derived={der} :: {why}")
        # NON-VACUOUS: a scan that compared ZERO tickets proves nothing. Zero
        # discovery (bad --board, empty board dir, no `tier:` anywhere) is a RED,
        # not a silent pass.
        if examined == 0:
            print(f"RED tier-drift-vacuous: compared 0 declared tiers under {args.board} "
                  f"— a zero-item scan cannot prove the board is drift-free")
            any_red = True
        # exit DRIFT_RED_RC iff a RED-set ticket drifted or the scan was vacuous.
        # (validate_board maps this rc — and ONLY this rc — to a hard fail.)
        return DRIFT_RED_RC if any_red else 0

    if args.cmd == "router-validate":
        for line in validate_router(os.path.join(fleet, "tier-models.tsv")):
            print(line)
        return 0


if __name__ == "__main__":
    sys.exit(main())

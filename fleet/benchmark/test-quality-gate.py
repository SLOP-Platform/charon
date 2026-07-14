#!/usr/bin/env python3
"""test-quality-gate.py — RED-proof + discrimination-score gate for dogfood tickets.

Implements fleet/state/TEST-QUALITY-GATE-SPEC.md. Closes the confirmed gap: nothing
today evaluates whether a REAL dogfood ticket's own accept: check is too-easy, buggy,
or non-discriminating before the ticket is trusted as a ranking signal (confirmed live
this session: TOOL-REPAIR-MUTATING's D1 bugfix passed ALL 5 candidates -> zero signal;
its own `tests/test_tool_repair.py` already passes on unmodified origin/master).

Read-only / dry-run-safe. Rig-side only:
  - NEVER edits tools/gates.json or src/charon/gate_runner.py (owned elsewhere — see
    spec's "follow-on wiring step").
  - NEVER edits dogfood-eval.sh or promote.py — composes them.
  - NEVER auto-applies its Step 3 proposal; only prints it for a human to act on.
  - The only mutation this script ever performs is creating/removing its OWN throwaway
    git worktrees (same convention as dogfood-eval.sh: fresh worktree off origin/master,
    a dedicated branch, never touches the primary checkout, never commits/pushes/merges).

Reuses (does not reimplement):
  - promote.py's `evaluate_gate()` for the spread/distinct-count math — imported
    directly, not forked. (fleet/benchmark/promote.py)
  - dogfood-eval.sh's isolated-worktree convention (same env var names + git worktree
    add/remove sequence) for RED-proof isolation.
  - dogfood-eval.sh's own verdict vocabulary (REVIEW-READY / FIXES-NEEDED /
    DETAIN(quality|latency) / RETRY(...)) when reading
    fleet/state/dogfood-eval/results/*-SUMMARY.md.

Step 1 — RED-proof (mandatory, run first):
  Run the ticket's own accept: check, UNMODIFIED, in a fresh worktree off origin/master
  (zero candidate changes applied). A PASS here is a RED FLAG (TOO-EASY /
  NON-DISCRIMINATING — the ticket is already-done or the check never exercised the bug).
  If --ref-diff is given, a second worktree applies it and re-runs the same check: still
  failing there means BUGGY-TEST (the check itself is broken). No --ref-diff -> UNVERIFIED.

Step 2 — discrimination score (read-only post-processor over real candidate outcomes):
  Reads fleet/state/dogfood-eval/results/<ticket>-*-SUMMARY.md (>=1 already-run
  dogfood-eval.sh batches), maps each candidate's `overall` verdict to a numeric score
  (REVIEW-READY=100, FIXES-NEEDED=50, DETAIN=0, RETRY excluded entirely — never
  disqualifying, never scored), and calls promote.py's own evaluate_gate() over the
  per-model mean scores. A ticket whose real candidates all land on the same score is
  flagged NON-DISCRIMINATING.

Step 3 — proposal (printed only, never auto-applied) — see render_proposal().

Usage:
  test-quality-gate.py --ticket fleet/board/<TICKET>.md [--ref-diff PATH]
                        [--skip-red-proof] [--skip-discrimination] [--keep-worktree]
                        [--product-repo PATH] [--worktree-parent DIR] [--base-ref REF]
                        [--results-dir DIR] [--spread-min N] [--k N]

Follow-on (explicitly NOT done here, owned elsewhere): wiring Step 1 into
tools/gates.json / gate_runner.py so a ticket can't join a live battery matrix without
first passing RED-proof.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLEET_DIR = HERE.parent
sys.path.insert(0, str(HERE))
import promote  # noqa: E402  reuse evaluate_gate() — do not reimplement the spread/distinct math

DEFAULT_PRODUCT_REPO = Path("/home/stack/code/charon")
DEFAULT_WORKTREE_PARENT = Path("/home/stack/code")
DEFAULT_BASE_REF = "origin/master"
DEFAULT_RESULTS_DIR = FLEET_DIR / "state" / "dogfood-eval" / "results"
CONFIRM_MIN = 3  # >= this many distinct graded candidates before NON-DISCRIMINATING is
                 # called "real-world confirmed" rather than an early (2-candidate) signal

# dogfood-eval.sh's own verdict vocabulary -> promote.py's verdict-score convention
# (promote.py:50 _VERDICT_SCORE, adapted per TEST-QUALITY-GATE-SPEC.md Step 2).
_DOGFOOD_VERDICT_SCORE = [
    ("REVIEW-READY", 100.0),
    ("FIXES-NEEDED", 50.0),
    ("DETAIN", 0.0),          # DETAIN(quality) / DETAIN(latency)
]
# RETRY(...) is intentionally absent -> excluded entirely (never scored, never disqualifying).


def score_for_verdict(verdict: str) -> float | None:
    """dogfood-eval.sh verdict string -> promote.py-style numeric score, or None if the
    row should be EXCLUDED from the score set (RETRY(...) rows, or an unrecognized
    verdict shape — never silently guessed)."""
    v = verdict.strip()
    if v.startswith("RETRY"):
        return None
    for prefix, score in _DOGFOOD_VERDICT_SCORE:
        if v.startswith(prefix):
            return score
    return None


# ---------------------------------------------------------------------------
# ticket parsing — fleet/board/<TICKET>.md flat `key: value` fields, handling both
# single-line values and YAML-block-scalar `key: |` + indented body.
# ---------------------------------------------------------------------------
_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):(.*)$")


def parse_ticket(path: Path) -> dict[str, str]:
    """Return {field_name: value} for a board ticket file. A column-0 `key:` starts a
    new field; every following line (indented or not) is appended to it until the next
    column-0 `key:` line. Block-scalar fields (`key: |`) are dedented and newline-joined;
    plain fields are space-joined after stripping."""
    lines = path.read_text().splitlines()
    raw: dict[str, list[str]] = {}
    is_block: dict[str, bool] = {}
    current: str | None = None
    for line in lines:
        m = _KEY_RE.match(line) if not line.startswith(" ") else None
        if m:
            current = m.group(1)
            rest = m.group(2).strip()
            raw[current] = []
            is_block[current] = rest == "|"
            if rest and rest != "|":
                raw[current].append(rest)
            continue
        if current is not None:
            raw[current].append(line)

    fields: dict[str, str] = {}
    for key, parts in raw.items():
        if is_block[key]:
            body = [p for p in parts]
            indents = [len(p) - len(p.lstrip(" ")) for p in body if p.strip()]
            dedent = min(indents) if indents else 0
            fields[key] = "\n".join(p[dedent:] if len(p) >= dedent else p.strip() for p in body).strip()
        else:
            fields[key] = " ".join(p.strip() for p in parts if p.strip()).strip()
    return fields


def ticket_label(path: Path) -> str:
    return path.stem


# ---------------------------------------------------------------------------
# Step 1 — RED-proof
# ---------------------------------------------------------------------------
def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", s)


def make_worktree(product_repo: Path, worktree_parent: Path, base_ref: str, label: str, suffix: str) -> tuple[Path, str]:
    """Fresh throwaway worktree off base_ref — same convention as dogfood-eval.sh's
    run_one(): sibling dir under worktree_parent, dedicated local branch, prune+force
    -remove any stale same-named worktree/branch first. Never touches product_repo
    itself; never commits/pushes/merges."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    branch = f"test-quality-gate/{_safe(label)}/{suffix}-{ts}"
    wt = worktree_parent / f"charon-fleet-tqg-{_safe(label)}-{suffix}-{ts}"
    subprocess.run(["git", "-C", str(product_repo), "worktree", "prune"], capture_output=True)
    if wt.exists():
        subprocess.run(["git", "-C", str(product_repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(product_repo), "branch", "-D", branch], capture_output=True)
    r = subprocess.run(["git", "-C", str(product_repo), "worktree", "add", str(wt), "-b", branch, base_ref],
                        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git worktree add failed for {label}/{suffix}: {r.stderr.strip()}")
    return wt, branch


def remove_worktree(product_repo: Path, wt: Path, branch: str, keep: bool) -> None:
    if keep:
        return
    subprocess.run(["git", "-C", str(product_repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(product_repo), "branch", "-D", branch], capture_output=True)


def run_test_cmd(test_cmd: str, cwd: Path, timeout_s: int = 600) -> tuple[int, str]:
    try:
        r = subprocess.run(["bash", "-lc", test_cmd], cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)
        return r.returncode, (r.stdout + r.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        return 124, "(timed out)"


def classify_red_proof(unmodified_pass: bool, ref_result: str | None) -> str:
    """PURE decision function (unit-testable without git/subprocess) — spec's Step 1
    rules #3-#5. `ref_result` is None (no --ref-diff given), 'pass', 'fail', or
    'did-not-apply'."""
    if unmodified_pass:
        return "TOO-EASY"
    if ref_result is None:
        return "UNVERIFIED"
    if ref_result == "pass":
        return "OK"
    return "BUGGY-TEST"  # ref_result in {'fail', 'did-not-apply'}


def red_proof(ticket: str, test_cmd: str, *, product_repo: Path, worktree_parent: Path,
              base_ref: str, ref_diff: Path | None, keep_worktree: bool, timeout_s: int = 600) -> dict:
    subprocess.run(["git", "-C", str(product_repo), "fetch", "origin", "--quiet"], capture_output=True)

    wt, branch = make_worktree(product_repo, worktree_parent, base_ref, ticket, "unmodified")
    rc, log = run_test_cmd(test_cmd, wt, timeout_s)
    remove_worktree(product_repo, wt, branch, keep_worktree)
    unmodified_pass = rc == 0

    ref_result: str | None = None
    ref_log = ""
    if ref_diff is not None:
        wt2, branch2 = make_worktree(product_repo, worktree_parent, base_ref, ticket, "reffix")
        applied = subprocess.run(["git", "apply", str(ref_diff)], cwd=str(wt2), capture_output=True, text=True)
        if applied.returncode != 0:
            ref_result = "did-not-apply"
            ref_log = applied.stderr
        else:
            rc2, ref_log = run_test_cmd(test_cmd, wt2, timeout_s)
            ref_result = "pass" if rc2 == 0 else "fail"
        remove_worktree(product_repo, wt2, branch2, keep_worktree)

    verdict = classify_red_proof(unmodified_pass, ref_result)
    return {
        "ticket": ticket, "test_cmd": test_cmd, "base_ref": base_ref,
        "unmodified_rc": rc, "unmodified_pass": unmodified_pass, "unmodified_log_tail": log,
        "ref_diff": str(ref_diff) if ref_diff else None, "ref_result": ref_result, "ref_log_tail": ref_log,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Step 2 — discrimination score (read-only over fleet/state/dogfood-eval/results/)
# ---------------------------------------------------------------------------
def load_ticket_scores(ticket: str, results_dir: Path) -> tuple[dict[str, float], list[Path], list[tuple[str, str, str]]]:
    """Parse every `<ticket>-*-SUMMARY.md` markdown table under results_dir. Returns
    (per-model MEAN score dict — a model with zero eligible rows is simply absent,
    matching promote.py's own unit_scores() behavior; list of summary files read;
    list of (file, model, verdict) rows that were EXCLUDED (RETRY or unrecognized))."""
    files = sorted(results_dir.glob(f"{ticket}-*-SUMMARY.md"))
    acc: dict[str, list[float]] = {}
    excluded: list[tuple[str, str, str]] = []
    for f in files:
        for line in f.read_text().splitlines():
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) < 2:
                continue
            model, verdict = cols[0], cols[1]
            if model in ("model", "") or set(model) <= {"-"}:
                continue  # header / separator row
            score = score_for_verdict(verdict)
            if score is None:
                excluded.append((f.name, model, verdict))
                continue
            acc.setdefault(model, []).append(score)
    scores_by_model = {m: sum(v) / len(v) for m, v in acc.items()}
    return scores_by_model, files, excluded


def discrimination_verdict(scores_by_model: dict[str, float], spread_min: float = promote.SPREAD_MIN,
                            k: int = promote.DISTINCT_MODELS_MIN, confirm_min: int = CONFIRM_MIN) -> tuple[str, str]:
    """Reuses promote.evaluate_gate() for the actual spread/distinct-count math — only
    adds the spec's >= confirm_min distinction between an early (2-candidate) signal and
    a 'real-world confirmed' one. Returns (label, reason)."""
    should, reason = promote.evaluate_gate(scores_by_model, spread_min, k)
    n = len(scores_by_model)
    if n < k:
        return "INSUFFICIENT-DATA", reason
    if should:
        return "DISCRIMINATES", reason
    if n >= confirm_min:
        return "NON-DISCRIMINATING (real-world confirmed)", reason
    return "NON-DISCRIMINATING (early signal, only 2 candidates — treat cautiously)", reason


# ---------------------------------------------------------------------------
# Step 3 — proposal (printed only; never auto-applied)
# ---------------------------------------------------------------------------
def render_proposal(ticket: str, red: dict | None, disc: tuple[str, str] | None) -> list[str]:
    lines: list[str] = []
    if red is not None:
        if red["verdict"] == "TOO-EASY":
            lines.append(
                f"PROPOSAL (TOO-EASY): {ticket}'s accept: check ('{red['test_cmd']}') already "
                f"PASSES on unmodified {red['base_ref']} (rc=0) — it re-runs the pre-existing "
                f"suite rather than proving a NEW behavior. Tighten per the SECRET-HOTROTATE "
                f"pattern (grep-confirm a NEW fail-on-revert test function exists BY NAME in the "
                f"diff, not just re-run the existing suite) or escalate scope/difficulty so the "
                f"fix is a genuine multi-file diff (the TOOL-REPAIR-MUTATING precedent: keep as "
                f"smoke-test-only). Do not trust this ticket's ranking signal until fixed.")
        elif red["verdict"] == "BUGGY-TEST":
            lines.append(
                f"PROPOSAL (BUGGY-TEST): {ticket}'s accept: check fails BOTH unmodified AND with "
                f"the reference fix ({red['ref_diff']}) applied — the check itself is broken. A "
                f"human must repair it before any candidate is judged against it; do not "
                f"misattribute a failing run here to the candidate.")
        elif red["verdict"] == "UNVERIFIED":
            lines.append(
                f"NOTE (UNVERIFIED): {ticket} fails unmodified (good) but no --ref-diff was given "
                f"— this only proves the check currently fails, not that a real fix makes it "
                f"pass. Curate a reference fix diff (fleet/state/DOGFOOD-BATTERY-DESIGN.md's "
                f"PROPOSED-NEW convention) before fully trusting this ticket.")
    if disc is not None and disc[0].startswith("NON-DISCRIMINATING"):
        lines.append(
            f"PROPOSAL (RETIRE-FROM-RANKING): {ticket}'s real candidate outcomes show "
            f"{disc[1]} — demote to smoke-test-only (same treatment as TOOL-REPAIR-MUTATING) "
            f"rather than deleting the historical data; it may still catch a genuine early-ditch "
            f"no-diff case even with a low discrimination score.")
    if not lines:
        lines.append(f"No flags raised for {ticket} by either step.")
    return lines


# ---------------------------------------------------------------------------
# orchestration / CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticket", required=True, help="path to fleet/board/<TICKET>.md")
    ap.add_argument("--ref-diff", help="reference-fix diff to apply for the BUGGY-TEST sanity check (optional)")
    ap.add_argument("--test-cmd", help="override the ticket's own accept: field")
    ap.add_argument("--skip-red-proof", action="store_true")
    ap.add_argument("--skip-discrimination", action="store_true")
    ap.add_argument("--keep-worktree", action="store_true", help="leave RED-proof worktrees in place for audit")
    ap.add_argument("--product-repo", default=str(DEFAULT_PRODUCT_REPO))
    ap.add_argument("--worktree-parent", default=str(DEFAULT_WORKTREE_PARENT))
    ap.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    ap.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    ap.add_argument("--spread-min", type=float, default=promote.SPREAD_MIN)
    ap.add_argument("--k", type=int, default=promote.DISTINCT_MODELS_MIN)
    ap.add_argument("--timeout-s", type=int, default=600)
    args = ap.parse_args(argv)

    ticket_path = Path(args.ticket)
    label = ticket_label(ticket_path)
    fields = parse_ticket(ticket_path)
    test_cmd = args.test_cmd or fields.get("accept")
    print(f"=== test-quality-gate: {label} ===")
    print(f"ticket file: {ticket_path}")
    print(f"accept: check: {test_cmd!r}")

    red = None
    if not args.skip_red_proof:
        if not test_cmd:
            print("RED-proof: SKIPPED (no accept: field found and no --test-cmd given)")
        else:
            red = red_proof(
                label, test_cmd,
                product_repo=Path(args.product_repo), worktree_parent=Path(args.worktree_parent),
                base_ref=args.base_ref, ref_diff=Path(args.ref_diff) if args.ref_diff else None,
                keep_worktree=args.keep_worktree, timeout_s=args.timeout_s,
            )
            print(f"\n-- Step 1: RED-proof --")
            print(f"unmodified {args.base_ref}: rc={red['unmodified_rc']} pass={red['unmodified_pass']}")
            if red["ref_diff"]:
                print(f"reference-fix ({red['ref_diff']}): {red['ref_result']}")
            print(f"verdict: {red['verdict']}")

    disc = None
    if not args.skip_discrimination:
        scores, files, excluded = load_ticket_scores(label, Path(args.results_dir))
        print(f"\n-- Step 2: discrimination score --")
        print(f"result summaries read: {len(files)}")
        if not files:
            print("(no dogfood-eval.sh SUMMARY files found for this ticket yet)")
        else:
            label_verdict, reason = discrimination_verdict(scores, args.spread_min, args.k)
            disc = (label_verdict, reason)
            print(f"per-model mean scores: {scores}")
            print(f"excluded rows (RETRY/unrecognized): {len(excluded)}")
            print(f"verdict: {label_verdict} — {reason}")

    print(f"\n-- Step 3: proposal --")
    for line in render_proposal(label, red, disc):
        print(f"- {line}")

    flagged = (red is not None and red["verdict"] != "OK") or (disc is not None and disc[0].startswith("NON-DISCRIMINATING"))
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())

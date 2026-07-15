#!/usr/bin/env bash
# launch-plan.sh — mechanizes the manager pre-launch discipline (MANAGER-OPERATING-RULES.md
# §3: decompose -> right-model -> monitor) that today is a RULE, not a gate. Turns "ready
# tickets" into a model-named, collision-free, context-fit WAVE PLAN the operator can open
# tabs from. COMPOSES existing tools; never reimplements their decisions:
#
#   1. fleet/checks/parallelizability-gate.sh check <id>   — HARD refuse a splittable-but-
#      undecomposed ticket (difficulty>=M AND >1 owned surface, not decomposed, not
#      serial_justified). This is a hard gate: the ticket is dropped from every wave and the
#      operator is pointed at fleet/decompose.sh.
#   2. fleet/capability/assign.py <id>                     — pick the best model for the
#      ticket's work_class+tier. A REFUSED (D&S-blocked / no-eligible-candidate) ticket is
#      dropped, with assign.py's own blocker text shown verbatim.
#   3. CONTEXT-FIT FILTER (v1, mechanical) — drop a ticket whose assign.py-picked model
#      declares a max_context smaller than the ticket's `est_tokens:` field. See the `# v2:`
#      hook below for what this deliberately does NOT do yet.
#   4. WAVE GROUPING — partition the surviving (launchable) tickets into collision-free waves
#      by depends_on + owns: no two tickets in the same wave write the same owned path, and a
#      ticket only lands in a wave once every in-batch dependency it has is already placed in
#      an earlier wave.
#
# Output is a plain-text wave plan (matches fleet/report.sh's plain-text style): per wave, per
# ticket -> tier, the NAMED model, and the exact operator tab command.
#
# Usage:
#   launch-plan.sh [ticket ...]     plan the named tickets (bypasses the default READY filter
#                                   — an explicitly-named ticket is still subject to gates 1-3)
#   launch-plan.sh                  default: plan every READY board ticket (not done/claimed/
#                                   submitted/needs-push/parked, and every depends_on satisfied)
#
# Exit code: 0 whenever a plan is produced, even if some candidates were refused — refusal is
# the STEADY STATE of a healthy board (blocked/splittable tickets exist at any given time), not
# a tool failure. Non-zero only on a hard usage/setup error.
#
# Env overrides (isolated self-test seams; defaults are the real fleet — see
# fleet/tests/launch-plan.test.sh for the hermetic stub-assign.py harness):
#   LAUNCH_PLAN_BOARD        board dir (default <fleet>/board)
#   LAUNCH_PLAN_STATE        state dir (default <fleet>/state)
#   LAUNCH_PLAN_ASSIGN_PY    path to assign.py (or a CLI-compatible stub)
#   LAUNCH_PLAN_PARGATE      path to parallelizability-gate.sh
#   LAUNCH_PLAN_CONTEXT_TSV  model<TAB>max_context roster (default <state>/model-context.tsv;
#                            optional — a missing file/row means "no cap data", which the v1
#                            filter treats as PASS-THROUGH + a note, never a false drop)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # fleet/

case "${1:-}" in
  -h|--help)
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
esac

BOARD="${LAUNCH_PLAN_BOARD:-$HERE/board}"
STATE="${LAUNCH_PLAN_STATE:-$HERE/state}"
ASSIGN_PY="${LAUNCH_PLAN_ASSIGN_PY:-$HERE/capability/assign.py}"
PARGATE="${LAUNCH_PLAN_PARGATE:-$HERE/checks/parallelizability-gate.sh}"
CONTEXT_TSV="${LAUNCH_PLAN_CONTEXT_TSV:-$STATE/model-context.tsv}"

exec python3 - "$BOARD" "$STATE" "$ASSIGN_PY" "$PARGATE" "$CONTEXT_TSV" "$@" <<'PY'
import glob
import os
import re
import subprocess
import sys

board, state, assign_py, pargate, context_tsv, *ticket_args = sys.argv[1:]

_FIELD_RE_CACHE = {}


def field(path, key):
    pat = _FIELD_RE_CACHE.get(key)
    if pat is None:
        pat = re.compile(r"^\s*" + re.escape(key) + r":\s?(.*)$")
        _FIELD_RE_CACHE[key] = pat
    try:
        for line in open(path):
            m = pat.match(line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return ""


def owns_of(tf):
    # Same skip rule as parallelizability-gate.sh's surfaces_of: an entry containing
    # whitespace or starting with '(' is prose/descriptive, not a real path.
    out = []
    for p in field(tf, "owns").split(","):
        t = p.strip()
        if not t or " " in t or "\t" in t or t.startswith("("):
            continue
        out.append(t)
    return out


def is_parked(tf):
    p = field(tf, "parked").strip().lower()
    if p in ("true", "yes", "1"):
        return True
    return "PARKED" in field(tf, "note").upper()


def canon(tid):
    tidl = tid.lower()
    for f in glob.glob(os.path.join(board, "*.md")):
        b = os.path.basename(f)[:-3]
        if b.lower() == tidl:
            return b
    return None


def deps_done(dep_field):
    if not dep_field.strip():
        return True
    for raw in dep_field.split(","):
        d = raw.strip()
        if not d:
            continue
        c = canon(d) or d
        if not os.path.exists(os.path.join(state, "done", c)):
            return False
    return True


def is_ready(tid, tf):
    for sub in ("done", "submitted", "needs-push", "claims"):
        if os.path.exists(os.path.join(state, sub, tid)):
            return False
    if is_parked(tf):
        return False
    return deps_done(field(tf, "depends_on"))


# ---------------------------------------------------------------------------
# 0. candidate set: explicit args (gates 1-3 still apply) or all READY tickets.
# ---------------------------------------------------------------------------
candidates = []
if ticket_args:
    for t in ticket_args:
        c = canon(t)
        if c is None:
            print(f"launch-plan: WARN — no such board ticket '{t}', skipping", file=sys.stderr)
            continue
        candidates.append(c)
else:
    for f in sorted(glob.glob(os.path.join(board, "*.md"))):
        tid = os.path.basename(f)[:-3]
        if is_ready(tid, f):
            candidates.append(tid)

refused = []       # list of (id, human reason)
launchable = []    # list of dicts: id/tier/work_class/model/owns/deps/context_note

for tid in candidates:
    tf = os.path.join(board, tid + ".md")
    if not os.path.exists(tf):
        refused.append((tid, "no such board ticket"))
        continue

    # --- 1. parallelizability gate (HARD, not advisory) ---------------------------------
    pg_env = dict(os.environ)
    pg_env["PARALLEL_GATE_BOARD"] = board
    pg_env["PARALLEL_GATE_DONE_DIR"] = os.path.join(state, "done")
    pg = subprocess.run(["bash", pargate, "check", tid],
                         capture_output=True, text=True, env=pg_env, check=False)
    if pg.returncode == 2:
        refused.append((tid, "parallelizability-gate error: " + (pg.stderr.strip() or "usage/unknown-ticket")))
        continue
    if pg.returncode != 0:
        detail = "\n      ".join((pg.stderr.strip() or pg.stdout.strip()).splitlines())
        refused.append((tid, "SPLITTABLE-UNDECOMPOSED (parallelizability-gate):\n      " + detail))
        continue

    # --- 2. assign.py: pick the model; drop D&S-blocked / REFUSED tickets -----------------
    ap = subprocess.run(["python3", assign_py, tid], capture_output=True, text=True, check=False)
    picked = None
    for line in ap.stdout.splitlines():
        m = re.match(r"PICK:\s*(\S+)", line)
        if m:
            picked = m.group(1)
            break
    if picked is None or ap.returncode != 0:
        detail = "\n      ".join(line for line in ap.stdout.strip().splitlines() if line.strip())
        if not detail:
            detail = (ap.stderr.strip() or "assign.py produced no pick")
        refused.append((tid, "D&S/REFUSED (assign.py):\n      " + detail))
        continue

    tier = field(tf, "tier") or "(no tier)"
    work_class = field(tf, "work_class") or "(no work_class)"
    owns = owns_of(tf)
    deps = [d.strip() for d in field(tf, "depends_on").split(",") if d.strip()]

    # --- 3. CONTEXT-FIT FILTER (v1, mechanical) --------------------------------------------
    # v2: empirical work_class fitness from dogfood (see task work-context-fitness)
    est_raw = field(tf, "est_tokens")
    context_note = "context-fit: no est_tokens declared — pass-through"
    if est_raw:
        m = re.match(r"\d+", est_raw)
        if m is None:
            context_note = f"context-fit: unparseable est_tokens '{est_raw}' — pass-through"
        else:
            est = int(m.group())
            cap = None
            if os.path.exists(context_tsv):
                for line in open(context_tsv):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2 and parts[0] == picked:
                        try:
                            cap = int(parts[1].strip())
                        except ValueError:
                            cap = None
                        break
            if cap is None:
                context_note = (f"context-fit: no max_context data for '{picked}' in "
                                 f"{context_tsv} — pass-through (no cap to check)")
            elif cap < est:
                refused.append((tid, f"CONTEXT-FIT — picked model '{picked}' max_context={cap} "
                                      f"< est_tokens={est}; drop and re-plan (v2 hook: empirical "
                                      f"work_class fitness would re-rank instead of dropping)"))
                continue
            else:
                context_note = f"context-fit: OK ({picked} max_context={cap} >= est_tokens={est})"

    launchable.append({
        "id": tid, "tier": tier, "work_class": work_class, "model": picked,
        "owns": owns, "deps": deps, "context_note": context_note,
    })

# ---------------------------------------------------------------------------
# 4. GROUP into collision-free waves by depends_on + owns.
# ---------------------------------------------------------------------------
launch_ids = {t["id"] for t in launchable}
placed = {}          # id -> wave number (1-based)
waves = []
remaining = list(launchable)
while remaining:
    wave_no = len(waves) + 1
    this_wave = []
    used_paths = set()
    still_remaining = []
    for t in remaining:
        deps_in_set = [d for d in t["deps"] if (canon(d) or d) in launch_ids]
        deps_satisfied = all(placed.get(canon(d) or d, 0) < wave_no for d in deps_in_set)
        collides = any(p in used_paths for p in t["owns"])
        if deps_satisfied and not collides:
            this_wave.append(t)
            used_paths.update(t["owns"])
            placed[t["id"]] = wave_no
        else:
            still_remaining.append(t)
    if not this_wave:
        # Safety valve: a dependency cycle (or a persistent collision) among the surviving
        # candidates would otherwise spin forever. Surface it as a refusal instead.
        for t in still_remaining:
            refused.append((t["id"], "WAVE-GROUPING — could not place (dependency cycle or "
                                      "unresolved owns collision among candidates); plan/launch it manually"))
        break
    waves.append(this_wave)
    remaining = still_remaining

# ---------------------------------------------------------------------------
# 5. OUTPUT — plain text, report.sh-style.
# ---------------------------------------------------------------------------
print("LAUNCH PLAN")
print("===========")
if not waves and not refused:
    print("\n  (no READY tickets)")

for wi, w in enumerate(waves, 1):
    print(f"\nWave {wi}")
    for t in w:
        print(f"  {t['id']:<22} tier={t['tier']:<9} model={t['model']}")
        print(f"      {t['context_note']}")
        print(f"      tab: fleet-droid.sh {t['tier']} --wait 3 --retries 10   (claims {t['id']})")

if refused:
    print("\nREFUSED / not planned")
    for tid, reason in refused:
        print(f"  {tid}: {reason}")

n_launch = sum(len(w) for w in waves)
print(f"\nSUMMARY  waves={len(waves)}  launchable={n_launch}  refused={len(refused)}")
sys.exit(0)
PY

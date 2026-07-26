#!/usr/bin/env bash
# wci-contention.sh — WCI high-contention-file DETECTOR + AUTO-TICKET GENERATOR (build-rig only).
# Turns the collision metric into a REFACTOR TRIGGER: scans every board ticket's
# `owns:` field, counts how many tickets own each file, and flags any file owned by
# >= N tickets as a DECOMPOSE CANDIDATE (a god-file = refactoring debt — split it so
# tickets re-slice onto disjoint modules and parallelize by construction).
# See fleet/WCI-METHOD.md (Step 2/3).
#
# WHY THIS FILE GREW TEETH (2026-07-24, operator directive): the detector was ALREADY
# wired into fleet/preflight.sh and had been printing
#   "DETECTED (unregistered): wci-contention — N DECOMPOSE CANDIDATE file(s)"
# every session for weeks. Nobody acted on it: an advisory that mutates nothing and
# always exits 0 is indistinguishable from noise. The fix is NOT a louder print — it is
# to convert the recommendation into TRACKED WORK: a board ticket at `priority: 1`, one
# per contended FILE, idempotent, board-valid, and self-closing.
#
# Modes:
#   (default)   ADVISORY god-file detector. N defaults to 4. Scans live AND parked
#               tickets. Prints hits, mutates nothing.
#   --strict    HARD PRE-CHECK (DEC-VALIDATE-STRICT). N defaults to 2. Scans only
#               LIVE tickets (parked are not schedulable, so they cannot collide).
#               Any file owned by >= N live tickets is a concurrency COLLISION: print
#               the collisions + exit NON-ZERO. Complements the engine's
#               intake.assert_disjoint_waves as a rig-side pre-flight.
#   --generate  AUTO-TICKET the advisory (the teeth). For every DECOMPOSE CANDIDATE,
#               ensure exactly ONE board ticket exists (keyed by the contended PATH),
#               at `priority: 1`, board-valid, with a matching state/ROADMAP.tsv row.
#               Also RECONCILES: an auto-ticket whose contention has dropped below N,
#               or whose file is now justified-serial, is PARKED as stale (non-accreting).
#   --ratchet [DAYS]
#               ESCALATION. An auto-ticket that has sat open+unclaimed for more than
#               DAYS is no longer "tracked work", it is an ignored advisory again ->
#               exit NON-ZERO so the caller can register a REAL blocking red.
#               DEFAULT OFF (see fleet/preflight.sh: WCI_RATCHET_DAYS).
#
# Usage: wci-contention.sh [--strict|--generate] [--dry-run] [--ratchet [DAYS]] [N]
#
# Exit codes (FAIL-CLOSED — uncertainty is never green):
#   0  OK / advisory printed / generation succeeded
#   1  --strict collision, or --ratchet escalation (an ignored auto-ticket)
#   2  RED: bad args, missing board dir, ZERO tickets scanned, or a generator refusal.
#      Zero discovery is NEVER proof of no contention — an empty scan means the input
#      was wrong, and that must be loud, not a silent pass.
#
# Env (test seams; every one defaults to the LIVE rig path):
#   WCI_BOARD_DIR   board dir            (default <fleet>/board)
#   WCI_ROADMAP     roadmap tsv          (default <fleet>/state/ROADMAP.tsv)
#   WCI_STATE_DIR   state dir            (default <fleet>/state)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="${WCI_BOARD_DIR:-$HERE/board}"
ROADMAP="${WCI_ROADMAP:-$HERE/state/ROADMAP.tsv}"
STATE="${WCI_STATE_DIR:-$HERE/state}"

# --- arg parse ---------------------------------------------------------------
# FAIL-CLOSED: an UNKNOWN flag used to fall through to the positional-N slot, where
# "--oops" failed the integer test and exited 0 — a typo'd invocation reported success.
STRICT=0
GENERATE=0
DRY_RUN=0
RATCHET_DAYS=0
POS=()
want_ratchet_days=0
for a in "$@"; do
  if [ "$want_ratchet_days" -eq 1 ]; then
    want_ratchet_days=0
    case "$a" in ''|*[!0-9]*) ;; *) RATCHET_DAYS="$a"; continue;; esac
  fi
  case "$a" in
    --strict)   STRICT=1 ;;
    --generate) GENERATE=1 ;;
    --dry-run)  DRY_RUN=1 ;;
    --ratchet)  RATCHET_DAYS=7; want_ratchet_days=1 ;;
    --ratchet=*) RATCHET_DAYS="${a#*=}" ;;
    --*) echo "wci-contention: unknown flag '$a' (usage: [--strict|--generate] [--dry-run] [--ratchet [DAYS]] [N])" >&2; exit 2 ;;
    *) POS+=("$a") ;;
  esac
done
if [ "$STRICT" -eq 1 ]; then
  N="${POS[0]:-2}"
else
  N="${POS[0]:-4}"
fi

if [ "$STRICT" -eq 1 ] && [ "$GENERATE" -eq 1 ]; then
  echo "wci-contention: --strict and --generate are different jobs; run them separately" >&2; exit 2
fi

# FAIL-CLOSED (was: exit 0 on all three — a bad arg or a missing board printed a
# complaint and then reported SUCCESS, so every caller read it as "no contention").
case "$N" in ''|*[!0-9]*) echo "wci-contention: RED — N must be a positive integer (got '$N')" >&2; exit 2;; esac
[ "$N" -ge 1 ] || { echo "wci-contention: RED — N must be >= 1 (got '$N')" >&2; exit 2; }
[ -d "$BOARD" ] || { echo "wci-contention: RED — no board dir at $BOARD (cannot scan; refusing to report clean)" >&2; exit 2; }
case "$RATCHET_DAYS" in ''|*[!0-9]*) echo "wci-contention: RED — --ratchet DAYS must be a non-negative integer (got '$RATCHET_DAYS')" >&2; exit 2;; esac

# owners.tsv: one "<file>\t<ticket>" row per (file, owning-ticket) pair.
# In --strict mode only LIVE tickets (*.md) are considered — parked tickets
# (*.md.parked) are not schedulable, so they cannot create a real collision.
#
# AUTO-TICKETS ARE EXCLUDED FROM THE COUNT. A ticket carrying `auto_generated:
# wci-contention` is this detector's own REMEDIATION for that file; counting it would
# (a) inflate the contention it is meant to retire and (b) keep itself alive forever —
# the accretion failure mode. The remedy is never the disease.
scanned=0
owners="$(
  shopt -s nullglob
  globs=("$BOARD"/*.md)
  [ "$STRICT" -eq 1 ] || globs+=("$BOARD"/*.md.parked)
  for tk in "${globs[@]}"; do
    [ -f "$tk" ] || continue
    grep -qE '^[[:space:]]*auto_generated:[[:space:]]*wci-contention' "$tk" 2>/dev/null && continue
    base="$(basename "$tk")"
    ticket="${base%.md}"; ticket="${ticket%.md.parked}"
    # Grab the value on the FIRST `owns:` line; robust to missing/empty/extra spaces.
    line="$(grep -m1 -E '^[[:space:]]*owns:' "$tk" 2>/dev/null || true)"
    val="${line#*:}"
    # split on commas
    IFS=',' read -ra parts <<< "$val"
    for p in "${parts[@]:-}"; do
      # trim leading/trailing whitespace
      f="$(printf '%s' "$p" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
      [ -n "$f" ] || continue
      printf '%s\t%s\n' "$f" "$ticket"
    done
  done
)"

# NON-VACUOUS: how many ticket FILES did we actually look at? "no owned files found"
# has two very different causes — a board of tickets that legitimately own nothing
# (impossible in practice), and a board we failed to read (wrong dir, bad glob,
# permissions). Both used to print one reassuring line and exit 0.
shopt -s nullglob
_scan_files=("$BOARD"/*.md)
[ "$STRICT" -eq 1 ] || _scan_files+=("$BOARD"/*.md.parked)
shopt -u nullglob
scanned="${#_scan_files[@]}"

if [ "$scanned" -eq 0 ]; then
  echo "wci-contention: RED — scanned ZERO ticket files in $BOARD. An empty scan is not" >&2
  echo "  evidence of no contention, it is evidence the input is wrong. Refusing to report clean." >&2
  exit 2
fi

if [ -z "$owners" ]; then
  echo "wci-contention: RED — $scanned ticket file(s) scanned but NOT ONE declares an 'owns:' path." >&2
  echo "  Contention is computed from owns; with no owns the metric is undefined, not zero." >&2
  exit 2
fi

# Aggregate: for each file, count distinct owning tickets + collect the list.
hits="$(
  printf '%s\n' "$owners" | sort -u | awk -F'\t' -v N="$N" '
    { cnt[$1]++; if (list[$1]=="") list[$1]=$2; else list[$1]=list[$1] ", " $2 }
    END {
      for (f in cnt) if (cnt[f] >= N) printf "%d\t%s\t%s\n", cnt[f], f, list[f]
    }
  ' | sort -rn -k1,1
)"

# ---------------------------------------------------------------------------
# GENERATE / RECONCILE / RATCHET — the teeth.
# ---------------------------------------------------------------------------
# Delegated to an embedded python3 block (same pattern as validate_board.sh and
# decompose.sh): ticket emission needs real parsing + all-or-nothing validation, and
# ANTI-ACCRETION forbids a new standalone script for it. Everything it writes is
# validated BEFORE it lands; a ticket that would red the board is never written.
if [ "$GENERATE" -eq 1 ] || [ "$RATCHET_DAYS" -gt 0 ]; then
  WCI_N="$N" WCI_HITS="$hits" WCI_DRY="$DRY_RUN" WCI_DO_GEN="$GENERATE" \
  WCI_RATCHET="$RATCHET_DAYS" WCI_BOARD="$BOARD" WCI_ROADMAP_F="$ROADMAP" \
  WCI_STATE_D="$STATE" python3 - <<'PY'
import os, re, sys, datetime, glob

BOARD    = os.environ["WCI_BOARD"]
ROADMAP  = os.environ["WCI_ROADMAP_F"]
STATE    = os.environ["WCI_STATE_D"]
N        = int(os.environ["WCI_N"])
DRY      = os.environ["WCI_DRY"] == "1"
DO_GEN   = os.environ["WCI_DO_GEN"] == "1"
RATCHET  = int(os.environ["WCI_RATCHET"])
HITS     = os.environ["WCI_HITS"]
TODAY    = datetime.date.today()

AUTO_MARK = "wci-contention"
rc = 0
red = []

def say(msg):
    print(f"wci-autoticket: {msg}")

# --- ticket parsing. field() MIRRORS fleet/validate_board.sh EXACTLY (first line
# starting "<key>:", value = remainder). Any divergence here and this generator would
# compute a different live-set than the validator, i.e. emit tickets the validator reds.
def field(path, key):
    try:
        for line in open(path, errors="replace"):
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return ""
    return ""

def has_key(path, key):
    try:
        for line in open(path, errors="replace"):
            if line.startswith(key + ":"):
                return True
    except OSError:
        return False
    return False

def owns_of(path):
    return [o.strip() for o in field(path, "owns").split(",") if o.strip()]

def is_parked(path):
    # validate_board.sh's rule, verbatim: explicit truthy `parked:` OR "PARKED" in the
    # single-line `note:` value.
    if field(path, "parked").lower() in ("true", "yes", "1"):
        return True
    return "PARKED" in field(path, "note").upper()

def is_done(tid):
    return os.path.exists(os.path.join(STATE, "done", tid))

def is_claimed(tid):
    return os.path.exists(os.path.join(STATE, "claims", tid))

live_files  = sorted(glob.glob(os.path.join(BOARD, "*.md")))
all_files   = live_files + sorted(glob.glob(os.path.join(BOARD, "*.md.parked")))
def tid_of(p):
    b = os.path.basename(p)
    return b[:-len(".md.parked")] if b.endswith(".md.parked") else b[:-3]

# ARCHIVE + PARKED-FILE awareness: an auto-ticket that was retired (board/archive/) or
# renamed to *.md.parked must NOT be re-created. Idempotency is keyed on the contended
# PATH, and the key is looked up across EVERY place a ticket can legitimately live.
archive_files = sorted(glob.glob(os.path.join(BOARD, "archive", "*.md")))

# map: contended path -> auto-ticket file, over live + parked + archived
auto_by_target = {}
for p in all_files + archive_files:
    if field(p, "auto_generated") != AUTO_MARK:
        continue
    tgt = field(p, "wci_contention_target")
    if tgt:
        auto_by_target.setdefault(tgt, p)

# non-auto owners (live + parked), matching the bash scan above
owners_by_file = {}
for p in all_files:
    if field(p, "auto_generated") == AUTO_MARK:
        continue
    for o in owns_of(p):
        owners_by_file.setdefault(o, []).append(p)

def live_owner_ids(path):
    out = []
    for p in owners_by_file.get(path, []):
        if not p.endswith(".md"):
            continue
        t = tid_of(p)
        if is_done(t) or is_parked(p):
            continue
        out.append(t)
    return sorted(set(out))

def slug(path):
    s = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").upper()
    return s

def ticket_id(path):
    return "WCI-DEC-" + slug(path)

# ---- board-validity self-check. A generator that REDs the board is worse than no
# generator, so every emitted ticket is checked against the marker-independent rules
# (fleet/checks/rig-ci-scope.sh::_check_ticket + validate_board.sh's field rules)
# BEFORE it is allowed to stay on disk.
VALID_WORK_CLASSES = {"bugfix","ci-infra","design-review","docs","frontend","generalist",
                      "greenfield-feature","money-path","refactor","rig-meta","routing","tests"}
VALID_REPOS = {"charon","product","keystone","ksf","charon-private","rig","fleet"}

def validate_emitted(path, tid, known_branches):
    p = []
    br = field(path, "branch")
    if not br: p.append("missing branch:")
    elif br in known_branches: p.append(f"duplicate branch: {br}")
    ow = owns_of(path)
    if not ow: p.append("missing owns:")
    for o in ow:
        if o.startswith("/"): p.append(f"absolute owns path {o!r}")
        if re.search(r"\s", o): p.append(f"whitespace in owns path {o!r}")
    wc = field(path, "work_class")
    if wc not in VALID_WORK_CLASSES: p.append(f"work_class {wc!r} invalid")
    rp = field(path, "repo").lower()
    if rp and rp not in VALID_REPOS: p.append(f"repo {rp!r} invalid")
    d = field(path, "difficulty")
    if not re.match(r"^[1-5]$", d.split()[0] if d.split() else ""): p.append(f"difficulty {d!r} not 1-5")
    pr = field(path, "priority")
    if not re.match(r"^[0-5]$", pr): p.append(f"priority {pr!r} not an int 0..5 (fleet/state/PRIORITY-LADDER.md)")
    if not has_key(path, "substrate"): p.append("no substrate: answer")
    txt = open(path, errors="replace").read()
    if not re.search(r"##\s*dependencies\s*&\s*sequence", txt, re.I):
        p.append("no Dependencies & Sequence section")
    if "fail-on-revert" not in txt.lower(): p.append("acceptance is not fail-on-revert")
    return p

known_branches = set()
for p in all_files:
    b = field(p, "branch")
    if b:
        known_branches.add(b)

# ---- roadmap ----------------------------------------------------------------
def roadmap_ids():
    try:
        rows = open(ROADMAP, errors="replace").read().splitlines()
    except OSError:
        return None
    ids = set()
    for r in rows:
        if r.startswith("#") or not r.strip():
            continue
        parts = r.split("\t")
        if len(parts) >= 2:
            ids.add(parts[1])
    return ids

def roadmap_append(tid, target):
    row = "\t".join(["Fleet", tid, "queued", "-", f"wci-decompose {target}",
                     f"split {target} so its owners re-slice onto disjoint modules",
                     "WCI — decompose contended files"])
    with open(ROADMAP, "a") as fh:
        fh.write(row + "\n")

def roadmap_set_status(tid, status):
    try:
        rows = open(ROADMAP, errors="replace").read().splitlines()
    except OSError:
        return
    out, hit = [], False
    for r in rows:
        parts = r.split("\t")
        if not r.startswith("#") and len(parts) >= 3 and parts[1] == tid:
            parts[2] = status; r = "\t".join(parts); hit = True
        out.append(r)
    if hit:
        with open(ROADMAP, "w") as fh:
            fh.write("\n".join(out) + "\n")

# ---- ticket rendering -------------------------------------------------------
def render(tid, target, count, owners_live, repo):
    deps = ", ".join(owners_live)
    lines = [
        f"repo: {repo}",
        "tier: strong",
        "priority: 1",
        "difficulty: 3",
        "work_class: refactor",
        f"branch: feat/{tid.lower()}",
        f"owns: {target}",
        f"depends_on: {deps}",
    ]
    if owners_live:
        # dep-kind: build — the owns OVERLAP (this ticket rewrites the very file they are
        # editing), so decomposing before they land would rebase-bomb every one of them.
        # It also makes every (auto, owner) pair dep-ORDERED, which is what keeps
        # validate_board.sh check-4 (owns-collision LIVE) green.
        lines.append("dep-kind: build")
    lines += [
        f"auto_generated: {AUTO_MARK}",
        f"wci_contention_target: {target}",
        f"wci_contention_count: {count}",
        f"created: {TODAY.isoformat()}",
        "substrate: N/A",
        "substrate-novel: |",
        "  Decomposing THIS repository's own god-file along its internal seams is not a task any",
        "  external tool performs: the seams are semantic (which gate belongs in which module) and",
        "  the acceptance is our own board invariant (owners re-slice onto disjoint paths). Standard",
        "  refactoring substrate (rope, sourcery, ast-grep, shellcheck) can move or lint code but",
        "  none of them decides the ownership partition this ticket exists to produce.",
        "source: |",
        f"  AUTO-GENERATED by fleet/wci-contention.sh --generate: {target} is owned by {count} board",
        f"  ticket(s) (threshold N={N}). WCI-METHOD.md Step 3 — a file owned by >= N tickets is",
        "  refactoring debt that serializes every one of its owners.",
        "note: |",
        f"  Owners at generation time: {deps if deps else '(none live)'}.",
        "  This ticket is machine-owned: fleet/wci-contention.sh --generate re-runs it every",
        "  preflight, never creates a second ticket for this path, and PARKS this one as stale the",
        "  moment contention drops below the threshold or the file is justified-serial.",
        "accept: |",
        f"  - {target} is split along its seams; each resulting module is owned by AT MOST one",
        "    live board ticket (re-run: bash fleet/wci-contention.sh — this path must NO LONGER be",
        "    listed as a DECOMPOSE CANDIDATE).",
        "  - every behaviour of the original file is preserved: prove it by EXECUTION per seam, not",
        "    by reading (fail-on-revert — reverting any single extracted piece must go RED).",
        "  - a non-vacuous test exercises the split: zero units discovered is RED, never a pass.",
        "scope: |",
        f"  ONLY the decomposition of {target} and the mechanical re-pointing of its callers.",
        "  Does NOT change behaviour, and does NOT re-slice the owning tickets' own work.",
        "ds: |",
        "  ## Dependencies & sequence",
        f"  depends_on: {deps if deps else '(none — no live owner)'}",
        "  Sequenced STRICTLY AFTER every live owner above: this ticket rewrites the file they are",
        "  editing, so it must not run concurrently with them (that is the collision it exists to",
        "  end, not to cause). Concurrency-safe once they land — it owns a single path.",
    ]
    return "\n".join(lines) + "\n"

# ---- 1. CREATE / KEEP -------------------------------------------------------
hits = []
for line in HITS.splitlines():
    if not line.strip():
        continue
    parts = line.split("\t")
    if len(parts) >= 2:
        hits.append((int(parts[0]), parts[1]))

created = kept = covered = skipped = 0
if DO_GEN:
    rid = roadmap_ids()
    if rid is None:
        red.append(f"ROADMAP.tsv not readable at {ROADMAP} — every auto-ticket needs a matching "
                   f"roadmap row, so refusing to emit a half-registered ticket")
    for count, target in hits:
        tid = ticket_id(target)
        existing = auto_by_target.get(target)
        if existing:
            kept += 1
            say(f"EXISTS {tid} -> {target} (idempotent: one ticket per path, no second created)")
            continue
        # --- respect EXISTING COVERAGE: never duplicate live work -------------
        cover = None
        for p in live_files:
            if is_done(tid_of(p)) or is_parked(p):
                continue
            ow = set(owns_of(p))
            if target not in ow:
                continue
            t = tid_of(p)
            if re.search(r"DECOMPOS|SPLIT|EXTRACT", t, re.I):
                cover = (t, "id names a decompose/split/extract of this file")
                break
            if ow == {target}:
                # identical owns set => validate_board.sh WCI-2 would call our ticket a
                # REDUNDANCY. Annotate the covering ticket instead of emitting.
                cover = (t, "already owns EXACTLY this path (identical owns set)")
                break
        if cover:
            covered += 1
            say(f"COVERED {target} — live ticket {cover[0]} {cover[1]}; NO ticket created (linked, not duplicated)")
            continue
        if red:
            skipped += 1
            continue
        owners_live = live_owner_ids(target)
        repo = "charon-private"
        for p in owners_by_file.get(target, []):
            r = field(p, "repo")
            if r:
                repo = r
                break
        body = render(tid, target, count, owners_live, repo)
        dest = os.path.join(BOARD, tid + ".md")
        if DRY:
            say(f"DRY-RUN would CREATE {tid} -> {target} (owned by {count}, priority 1, "
                f"depends_on: {', '.join(owners_live) or '(none)'})")
            created += 1
            continue
        tmp = dest + ".wci-tmp"
        with open(tmp, "w") as fh:
            fh.write(body)
        problems = validate_emitted(tmp, tid, known_branches)
        if problems:
            os.unlink(tmp)
            red.append(f"refused to emit {tid}: " + "; ".join(problems))
            continue
        os.rename(tmp, dest)
        known_branches.add(field(dest, "branch"))
        if rid is not None and tid not in rid:
            roadmap_append(tid, target)
        created += 1
        say(f"CREATE {tid} -> {target} (owned by {count} ticket(s), priority 1, "
            f"depends_on: {', '.join(owners_live) or '(none)'}) + ROADMAP.tsv row")

# ---- 2. RECONCILE: stale auto-tickets get PARKED (non-accreting) -------------
stale = blocked = 0
if DO_GEN:
    contended = {t for _, t in hits}
    for target, p in sorted(auto_by_target.items()):
        if not p.endswith(".md") or os.path.dirname(p) != BOARD:
            continue  # already parked/archived — nothing to reconcile
        t = tid_of(p)
        if is_done(t) or is_parked(p):
            continue
        reason = None
        if target not in contended:
            live_n = len(owners_by_file.get(target, []))
            reason = f"contention dropped to {live_n} (< N={N})"
        else:
            for op in owners_by_file.get(target, []):
                if field(op, "serial_justified") or has_key(op, "serial_justified"):
                    reason = f"owner {tid_of(op)} carries a justified 'serial_justified:' — the file is serial BY DESIGN"
                    break
        if not reason:
            continue
        if is_claimed(t):
            blocked += 1
            say(f"BLOCKED-STALE {t} is stale ({reason}) but has an ACTIVE claim — NOT parking "
                f"(parking a claimed ticket is the parked-but-claimed red). Release it first.")
            continue
        if DRY:
            stale += 1
            say(f"DRY-RUN would PARK {t} as STALE ({reason})")
            continue
        txt = open(p, errors="replace").read()
        if not re.search(r"^parked:", txt, re.M):
            txt = txt.replace("auto_generated:", "parked: true\nauto_generated:", 1)
        # Drop the sequencing on the way out. A retired ticket's depends_on is dead weight,
        # and once its owners are retired/archived it becomes a DANGLING dep — a hard RED in
        # validate_board.sh check 2 that would outlive the ticket it belongs to.
        txt = re.sub(r"^depends_on:.*$", "depends_on:", txt, count=1, flags=re.M)
        txt += (f"stale: |\n  PARKED {TODAY.isoformat()} by fleet/wci-contention.sh --generate: {reason}.\n"
                f"  The contention this ticket tracked is gone; it is retired rather than left to accrete.\n")
        open(p, "w").write(txt)
        roadmap_set_status(t, "parked")
        stale += 1
        say(f"STALE {t} -> parked ({reason})")

# ---- 3. RATCHET (default OFF) ----------------------------------------------
if RATCHET > 0:
    over = []
    for target, p in sorted(auto_by_target.items()):
        if not p.endswith(".md") or os.path.dirname(p) != BOARD:
            continue
        t = tid_of(p)
        if is_done(t) or is_parked(p) or is_claimed(t):
            continue
        c = field(p, "created")
        try:
            age = (TODAY - datetime.date.fromisoformat(c)).days
        except ValueError:
            age = 10 ** 6  # unparseable created: date -> treat as maximally stale (fail-closed)
        if age > RATCHET:
            over.append((t, target, age))
    if over:
        rc = 1
        for t, target, age in over:
            say(f"RATCHET ESCALATION: {t} ({target}) has been open and UNCLAIMED for {age}d "
                f"(> {RATCHET}d) — an auto-ticket nobody actions is an advisory again.")
    else:
        say(f"ratchet: OK — no auto-ticket open+unclaimed beyond {RATCHET}d")

if DO_GEN:
    say(f"summary: {created} created, {kept} already tracked, {covered} covered by existing work, "
        f"{stale} parked stale, {blocked} blocked, {skipped} skipped"
        + (" [DRY-RUN — nothing written]" if DRY else ""))

for r in red:
    print(f"wci-autoticket: RED {r}", file=sys.stderr)
if red:
    sys.exit(2)
sys.exit(rc)
PY
  gen_rc=$?
  [ "$gen_rc" -ne 0 ] && exit "$gen_rc"
fi

if [ -z "$hits" ]; then
  if [ "$STRICT" -eq 1 ]; then
    echo "wci-contention --strict: OK — no file owned by >= $N live ticket(s) ($scanned ticket file(s) scanned)."
  else
    echo "wci-contention: no DECOMPOSE CANDIDATE — no file owned by >= $N ticket(s) ($scanned ticket file(s) scanned)."
  fi
  exit 0
fi

if [ "$STRICT" -eq 1 ]; then
  echo "wci-contention --strict: COLLISION — files owned by >= $N LIVE ticket(s):"
  while IFS=$'\t' read -r count file list; do
    [ -n "$file" ] || continue
    echo "  COLLISION: $file — owned by $count live tickets"
    echo "      owners: $list"
  done <<< "$hits"
  echo "  -> two live tickets sharing a file will collide when run concurrently; make owns"
  echo "     DISJOINT (or add a real build-dep to sequence them) before launching the wave."
  exit 1
fi

echo "WCI CONTENTION — files owned by >= $N ticket(s) (DECOMPOSE CANDIDATES):"
while IFS=$'\t' read -r count file list; do
  [ -n "$file" ] || continue
  echo "  DECOMPOSE CANDIDATE: $file — owned by $count tickets"
  echo "      owners: $list"
done <<< "$hits"
echo "  -> a file owned by >= $N tickets is refactoring debt; split along seams so tickets re-slice"
echo "     onto DISJOINT modules and parallelize (fleet/WCI-METHOD.md Step 3)."
[ "$GENERATE" -eq 1 ] || echo "  -> these are now AUTO-TICKETED: bash fleet/wci-contention.sh --generate"
exit 0

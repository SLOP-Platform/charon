#!/usr/bin/env bash
# research.sh — Mechanized research/review/comparison protocol (FN4-RESEARCH-GATE).
#
# What this is: a launcher front-end for research sub-sessions. It enforces the
# discipline today's sessions kept missing:
#
#   1. PRE-LAUNCH GATE (dedup/staleness): every call consults the local registry
#      FIRST. FRESH = return the cached record (no re-research). STALE = launch
#      in UPDATE mode (refresh the record, do NOT redo from scratch).
#      MISSING = full research (default).
#
#   2. METHODOLOGY INJECTION (enforced, not left to the prompt/recall): every
#      sub-session prompt we emit carries the three directives as a
#      machine-checkable pre-amble block, so a sub-agent cannot silently skip
#      the reuse-check or write prose-only cards.
#        (1) REUSE-CHECK FIRST — search our repos / tools / memories /
#            prior-research BEFORE external (catches the Graphify-in-house case).
#        (2) EVIDENCE-OVER-PROSE — every feature/ability confirmed against REAL
#            docs/code with a cited URL or path:line; unverified marked
#            "unverified"; NO taglines/assumptions.
#        (3) Per-item verified cards.
#
#   3. POST-OUTPUT COMPLETENESS GATE (KS23 verification-delta shape): a research
#      record lacking a reuse-check section, or containing uncited prose
#      feature claims, or missing verified cards, is REJECTED. Only a passing
#      record is admitted to the registry.
#
#   4. REGISTRY (KS29-style): each review recorded
#        {topic, date, sources, verdict, freshness}
#      and staleness computed via FN2's bi-temporal decay half-life (default
#      30 days, env RESEARCH_FRESHNESS_DAYS overrides).
#
# Usage:
#   research.sh <topic>                       # pre-launch gate → output prompt or cached record
#   research.sh --update <topic>              # force UPDATE mode (treat STALE as MISSING)
#   research.sh --force <topic>               # bypass cache, full research (operator override)
#   research.sh --verify <record.md>          # run completeness gate; exit 0=PASS, 1=REJECT
#   research.sh --record <record.md>          # re-run gate and admit to registry if PASS
#   research.sh --list                        # show every registry record + freshness
#   research.sh --help
#
# Environment:
#   RESEARCH_REGISTRY_DIR    — registry location (default $FLEET/state/research-registry)
#   RESEARCH_FRESHNESS_DAYS  — staleness half-life days (default 30; uses FN2 decay primitive)
#   RESEARCH_MIN_SOURCES     — minimum distinct source count (default 1; 0 disables)
#   RESEARCH_REQUIRE_2ND_PASS— if set to 1, blocks admit until --record is run twice
#                              by different operators (adversarial-second-pass mode)
#   RESEARCH_VERIFY_DISABLE  — debug toggle (1 disables the verifier; FAIL-ON-REVERT contract)
#   RESEARCH_PROMPT_OUT      — override the auto-generated sub-session prompt path
#   FLEET                    — rig root (default $(cd "$(dirname "$0")/.." && pwd))

set -euo pipefail

FLEET="${FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# (no-op) SCRIPT literal — kept for downstream log filtering

REGISTRY_DIR="${RESEARCH_REGISTRY_DIR:-$FLEET/state/research-registry}"
FRESHNESS_DAYS="${RESEARCH_FRESHNESS_DAYS:-30}"
MIN_SOURCES="${RESEARCH_MIN_SOURCES:-1}"
SECOND_PASS="${RESEARCH_REQUIRE_2ND_PASS:-0}"
VERIFY_DISABLE="${RESEARCH_VERIFY_DISABLE:-0}"
PROMPT_OUT="${RESEARCH_PROMPT_OUT:-}"

# ANSI helpers (only when stderr is a TTY; degrade gracefully).
if [ -t 2 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_DIM=""; C_RST=""
fi
log(){ printf '%s[research]%s %s\n' "$C_DIM" "$C_RST" "$*" >&2; }
warn(){ printf '%s[research]%s %s%s!\n' "$C_YEL" "$C_RST" "$*" "$C_RST" >&2; }
err(){ printf '%s[research]%s %s\n' "$C_RED" "$C_RST" "$*" >&2; }
ok(){ printf '%s[research]%s %s\n' "$C_GRN" "$C_RST" "$*" >&2; }

usage(){
  cat <<'USAGE'
research.sh — FN4 mechanized research protocol

USAGE:
  research.sh <topic>                       pre-launch gate (FRESH|STALE|MISSING)
  research.sh --update <topic>              force UPDATE (refresh stale record)
  research.sh --force <topic>               bypass cache; full research
  research.sh --verify <record.md>          gate a record (0=PASS, 1=REJECT)
  research.sh --record <record.md>          gate + admit to registry
  research.sh --list                        list registry records + freshness
  research.sh --help

ENVIRONMENT:
  RESEARCH_REGISTRY_DIR     registry location (default fleet/state/research-registry)
  RESEARCH_FRESHNESS_DAYS   staleness half-life days (default 30; FN2 decay)
  RESEARCH_MIN_SOURCES      minimum distinct sources per record (default 1; 0 disables)
  RESEARCH_REQUIRE_2ND_PASS if 1, blocks admit until a 2nd operator pass wrote the record
  RESEARCH_VERIFY_DISABLE   debug toggle (1 = disable gate; FAIL-ON-REVERT contract)
USAGE
}

# --- argument parsing ----------------------------------------------------------

mode="auto"
topic=""
verify_path=""
record_path=""
topic_arg=""
case "${1:-}" in
  "") usage; exit 0 ;;
  --help|-h) usage; exit 0 ;;
  --list|-l) mode="list" ;;
  --verify)
    mode="verify"; verify_path="${2:?research.sh --verify <record.md>}"
    shift 2
    ;;
  --record)
    mode="record"; record_path="${2:?research.sh --record <record.md>}"
    shift 2
    ;;
  --update)
    mode="update"; topic_arg="${2:?research.sh --update <topic>}"
    shift 2
    ;;
  --force)
    mode="force"; topic_arg="${2:?research.sh --force <topic>}"
    shift 2
    ;;
  --*)
    err "unknown flag: $1"; usage; exit 2
    ;;
  *)
    mode="auto"; topic_arg="${1:?research.sh <topic>}"
    shift
    ;;
esac

# --- helpers -------------------------------------------------------------------

slug(){
  # topic -> registry slug (lowercase, non-alnum -> '-', max 80 chars).
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g' \
    | cut -c1-80
}

now_utc(){ date -u +%FT%TZ; }
date_to_epoch(){ date -u -d "$1" +%s 2>/dev/null || echo 0; }
epoch_to_iso(){ date -u -d "@$1" +%FT%TZ 2>/dev/null || printf '%s' "$1"; }

# FN2-style bi-temporal decay weight: exp2(-age_days / half_life_days).
# Returns a number in (0,1] for fresh records, ~0 for ancient ones, 0 for invalid.
freshness_weight(){
  local recorded_at="$1" half_life="$2" now
  now="$(date -u +%s)"
  local then
  
  then="$(date_to_epoch "$recorded_at")"
  [ "$then" -le 0 ] && { echo 0; return; }
  local age_days=$(( (now - then) / 86400 ))
  # exp2(-age/h) via python (the FN2 primitive lives fleet-side; we are bash + minimal)
  python3 - "$age_days" "$half_life" <<'PY'
import sys, math
age = float(sys.argv[1]); h = float(sys.argv[2])
if h <= 0:
    print(0); sys.exit(0)
print(math.exp2(-(age / h)))
PY
}

frontmatter_field(){
  # frontmatter_field <key> <file>
  awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null
}

find_existing_record(){
  local topic_slug="$1"
  # Match either exact slug or topic-name match in frontmatter (case-insensitive).
  for f in "$REGISTRY_DIR"/*.md; do
    [ -e "$f" ] || continue
    local n; n="$(basename "$f" .md)"
    if [ "$n" = "$topic_slug" ]; then echo "$f"; return 0; fi
    local t; t="$(frontmatter_field topic "$f")"
    # Topic frontmatter may be space-separated words — compare slug-equivalence.
    if [ -n "$t" ]; then
      local t_slug; t_slug="$(slug "$t")"
      [ "$t_slug" = "$topic_slug" ] && { echo "$f"; return 0; }
    fi
  done
  return 1
}

list_records(){
  mkdir -p "$REGISTRY_DIR" 2>/dev/null || true
  if compgen -G "$REGISTRY_DIR/*.md" >/dev/null; then
    printf '%-22s %-22s %-8s %s\n' "SLUG" "RECORDED" "WEIGHT" "VERDICT"
    for f in "$REGISTRY_DIR"/*.md; do
      [ -e "$f" ] || continue
      local n recorded at verdict w
      n="$(basename "$f" .md)"
      recorded="$(frontmatter_field recorded_at "$f")"
      at="${recorded:-unknown}"
      verdict="$(frontmatter_field verdict "$f")"
      w="$(freshness_weight "${recorded:-1970-01-01T00:00:00Z}" "$FRESHNESS_DAYS")"
      local w_fmt
      w_fmt="$(python3 -c "import sys; sys.stdout.write(f'{float(sys.argv[1]):.3f}')" "$w")"
      printf '%-22s %-22s %-8s %s\n' "$n" "$at" "$w_fmt" "${verdict:-?}"
    done
  else
    echo "(no records)"
  fi
}

# --- verifier ------------------------------------------------------------------

# verify_record <record.md>
#   Returns 0 on PASS, 1 on REJECT. Prints a single-line verdict to stdout and
#   a numbered check-list to stderr.
#
# Checks (numbered, deterministic order — FAIL-ON-REVERT contract depends on each one):
#   1. ## Reuse-Check   section present
#   2. No prose feature claims without evidence citation
#   3. At least one ## Verified card per item
#   4. Min-source-count (if RESEARCH_MIN_SOURCES > 0)
#   5. Verdict frontmatter field present (admits only explicitly verdicted records)
verify_record(){
  local rec="$1"
  [ -e "$rec" ] || { err "no such record: $rec"; return 1; }

  if [ "${VERIFY_DISABLE:-0}" = "1" ]; then
    log "verifier DISABLED (RESEARCH_VERIFY_DISABLE=1) → admitting WITHOUT checks"
    echo "VERIFY: PASS (disabled)"
    return 0
  fi

  local out
  # `set -e` + a python heredoc that exits 1 (REJECT) would kill this function
  # at the assignment; use `|| true` so the capture is unconditional.
  out="$(RESEARCH_MIN_SOURCES="$MIN_SOURCES" \
         python3 - "$rec" <<'PY' 2>&1 || true
import os, re, sys
from pathlib import Path

rec_path = Path(sys.argv[1])
min_sources = int(os.environ.get("RESEARCH_MIN_SOURCES", "1"))
text = rec_path.read_text()

def line(label, ok, detail=""):
    state = "PASS" if ok else "FAIL"
    sys.stderr.write(f"  [{state}] {label}{(': ' + detail) if detail else ''}\n")
    return 0 if ok else 1

# 1. Reuse-Check section present.
has_reuse = bool(re.search(r"(?m)^#{1,3}\s+Reuse[-\s]?Check\b", text))
rc1 = line("1. Reuse-Check section present", has_reuse)

# 2. Cards: every "feature / capability / ability" claim line must carry a citation OR be
#    explicitly marked unverified. We treat a "card" as any list item under a ##Verified card
#    heading (or a card-shaped paragraph). For each, look for evidence patterns: URL, a
#    path:line, a code block referencing a real source, or the literal "[unverified]" tag.
#
# A "prose feature claim" we define as any line that names a *specific feature* ("can", "supports",
# "provides", "offers") AND is NOT followed on the same line by a citation OR the [unverified] tag.
CITATION_RE = re.compile(r"https?://|[\w/.\-]+:\d+|\[unverified\]", re.IGNORECASE)
FEATURE_TRIGGER_RE = re.compile(r"\b(can|supports?|provides?|offers?|ships|includes?|features?)\b", re.IGNORECASE)

prose_failures = []
in_card_section = False
for raw_line in text.splitlines():
    body = raw_line.rstrip()
    stripped = body.strip()
    # Empty lines are paragraph separators, not section-end markers — section state
    # is owned by headings, not by blank lines.
    if not stripped:
        continue
    if re.match(r"^#{1,4}\s+", stripped):
        # Heading toggles card-section for ## Verified/Claims/Findings sections.
        in_card_section = bool(re.match(r"^#{2,4}\s+(Verified\s+card|Verified|Claims?|Findings?)\b", stripped, re.IGNORECASE))
        continue
    if not in_card_section:
        continue
    # Inside a card — only consider lines that read like a feature claim.
    if not FEATURE_TRIGGER_RE.search(stripped):
        continue
    if CITATION_RE.search(stripped):
        continue
    # any "tagline-style" line that is PURELY prose (no colon-prefix citation, no code block on this line)
    prose_failures.append(stripped[:120])

if prose_failures:
    detail = f"{len(prose_failures)} uncited feature claim(s); first: {prose_failures[0][:80]!r}"
else:
    detail = "0"
rc2 = line("2. Every feature claim cited or marked [unverified]", not prose_failures, detail)

# 3. At least one verified card.
card_count = len(re.findall(r"(?m)^#{2,4}\s+(Verified\s+card|Card)\b", text))
if card_count == 0:
    # fallback: any heading named "Verified" counts as one card section
    card_count = len(re.findall(r"(?m)^#{2,4}\s+Verified\b", text))
rc3 = line("3. At least one verified card present", card_count >= 1, f"{card_count} card(s)")

# 4. Min source count (extract URLs).
urls = set(re.findall(r"https?://\S+", text))
local_paths = set(re.findall(r"\b[\w/.\-]+\.[a-zA-Z]{1,5}:\d+\b", text))
src_count = len(urls) + len(local_paths)
if min_sources > 0:
    rc4 = line(f"4. Sources >= {min_sources}", src_count >= min_sources, f"distinct={src_count}")
else:
    rc4 = 0
    sys.stderr.write(f"  [PASS] 4. Min-source-count disabled (RESEARCH_MIN_SOURCES=0)\n")

# 5. verdict frontmatter.
verdict = ""
for ln in text.splitlines()[:20]:
    if ln.startswith("verdict:"):
        verdict = ln.split(":", 1)[1].strip()
        break
rc5 = line("5. `verdict:` frontmatter present", bool(verdict), f"verdict={verdict!r}")

if rc1 or rc2 or rc3 or rc4 or rc5:
    sys.stdout.write("VERIFY: REJECT\n")
    sys.exit(1)
sys.stdout.write("VERIFY: PASS\n")
sys.exit(0)
PY
)"
  echo "$out"
  echo "$out" | grep -q '^VERIFY: PASS$' && return 0
  return 1
}

# --- prompt construction -------------------------------------------------------

write_subagent_prompt(){
  local topic="$1" prompt_path="$2"
  mkdir -p "$(dirname "$prompt_path")"
  cat > "$prompt_path" <<EOF
# Research sub-session prompt — $topic

> Generated by \`fleet/research.sh\` (FN4-RESEARCH-GATE) on $(now_utc).
> The methodology directives below are ENFORCED inputs; a record that ignores them is
> REJECTED by the verifier. Treat every directive as non-negotiable.

## Topic
$topic

## Three non-negotiable directives (METHODOLOGY — must appear in your final record)

### (1) REUSE-CHECK FIRST
Search OUR internal sources BEFORE any external one:
- \`fleet/research-registry/*.md\` — prior research on the same or related topics
  (registry lives at \`\${RESEARCH_REGISTRY_DIR:-$FLEET/state/research-registry}\`)
- \`fleet/scratch/*.md\` — past ad-hoc research notes
- \`docs/review-log/*.md\` — past per-ticket review fragments

If any of those surface relevant prior work, CITE IT before going to external. Cite
as \`path:line\` or full file URL. If they don't, SAY SO explicitly (\"no prior
internal research on this topic\") before moving on. The Graphify-in-house miss is
the canonical example this directive exists to prevent.

### (2) EVIDENCE-OVER-PROSE
Every feature / ability / claim you write MUST carry one of:
- a cited URL (\`https://...\`, including the page anchor if relevant), OR
- a \`path:line\` citation against our own tree, OR
- the literal \`[unverified]\` tag (use sparingly; the operator may downgrade an
  unverifiable claim later, but a fabricated one is a hard REJECT).

NO taglines, NO marketing prose, NO \"based on the docs they ship\". If a citation
isn't possible, mark it [unverified] and move on.

### (3) Per-item verified cards
Structure each finding as a card with these fields:

\`\`\`
### [VERIFIED] <one-line claim>
- source: <URL or path:line>
- evidence: <direct quote / function signature / API excerpt>
- notes: <optional caveats>
\`\`\`

For claims that genuinely could not be verified, use \`[UNVERIFIED]\` instead and
list what you TRIED (so a second-pass reviewer can pick it up).

## Verdict (frontmatter field)
Your final record's YAML frontmatter MUST end with:

\`\`\`
verdict: <one of: ADOPT | WRAP | REJECT | NEEDS-MORE-WORK>
\`\`\`

with a 1-2 sentence rationale in the body.

## Writing the record
Save your final record as \`$prompt_path.out.md\` (or any path the launcher hands
you). It will then be admitted to the registry via:

    research.sh --record <path-to-your-record.md>

If the record is REJECTED, fix and re-emit; do NOT paper over with prose.

## How the verifier checks your work
The verifier reads your record and rejects on ANY of:
1. missing \`## Reuse-Check\` section
2. uncited feature claims (lines using \"can/supports/provides/ships/offers\"
   without an URL, a path:line, or [unverified])
3. zero verified cards
4. fewer sources than \`RESEARCH_MIN_SOURCES\` (default: 1)
5. missing \`verdict:\` frontmatter

Treat each as a gate you have to pass — not a suggestion.

---
END OF PROMPT — produced by FN4-RESEARCH-GATE
EOF
  echo "$prompt_path"
}

# --- pre-launch ---------------------------------------------------------------

pre_launch(){
  local topic="$1" forced="${2:-0}"
  local topic_slug; topic_slug="$(slug "$topic")"
  local rec; if rec="$(find_existing_record "$topic_slug")"; then
    local recorded; recorded="$(frontmatter_field recorded_at "$rec")"
    local w fresh_rc
    w="$(freshness_weight "${recorded:-1970-01-01T00:00:00Z}" "$FRESHNESS_DAYS")"
    # w > 0.5 = fresh; 0 < w <= 0.5 = stale; 0 = ancient (treat as stale).
    # set -e + a "stale" answer (python exits 1) would crash the script — capture the
    # exit code into a variable so we can branch on it without tripping set -e.
    fresh_rc=0
    python3 -c "import sys; sys.exit(0 if float('$w') > 0.5 else 1)" || fresh_rc=$?
    if [ "$fresh_rc" -eq 0 ] && [ "$forced" != "force" ]; then
      ok "FRESH: returning cached record for '$topic' (weight=$w)"
      printf '%s\n' "$rec"
      exit 0
    fi
    # STALE — UPDATE mode unless forced
    if [ "$forced" = "force" ]; then
      log "STALE but --force given: full research for '$topic' (weight=$w)"
    else
      log "STALE: launching UPDATE sub-session for '$topic' (weight=$w, prior=$rec)"
    fi
    local prompt="$PROMPT_OUT"
    if [ -z "$prompt" ]; then prompt="$(mktemp -t research-prompt-XXXXXX.md)"; fi
    write_subagent_prompt "UPDATE $topic (refresh of $rec)" "$prompt"
    printf '%s\n' "$prompt"
    exit 10
  fi
  if [ "$forced" = "update" ]; then
    warn "--update on a topic with no record → falling back to MISSING/full research"
  fi
  # MISSING — full research
  log "MISSING: launching full research sub-session for '$topic'"
  local prompt="$PROMPT_OUT"
  if [ -z "$prompt" ]; then prompt="$(mktemp -t research-prompt-XXXXXX.md)"; fi
  write_subagent_prompt "$topic" "$prompt"
  printf '%s\n' "$prompt"
  exit 10
}

# --- record admit -------------------------------------------------------------

record_admit(){
  local rec="$1"
  if [ ! -e "$rec" ]; then err "no record: $rec"; exit 1; fi
  if ! verify_record "$rec"; then
    err "record REJECTED by completeness gate; fix and re-try"
    exit 1
  fi
  # Optional adversarial second pass.
  if [ "$SECOND_PASS" = "1" ]; then
    local first_admit
    first_admit="$REGISTRY_DIR/.admit-by-$(whoami).$(date -u +%FT%TZ).$(slug "$(basename "$rec" .md)")"
    if [ ! -e "$first_admit" ]; then
      err "adversarial second-pass REQUIRED (RESEARCH_REQUIRE_2ND_PASS=1):"
      err "  no prior operator admit for this slug at $(date -u +%FT%TZ)."
      err "  re-run after at least one independent operator has seen this record:"
      err "    touch $first_admit"
      exit 1
    fi
  fi
  local topic_slug; topic_slug="$(basename "$rec" .md)"
  local slot="$REGISTRY_DIR/$topic_slug.md"
  mkdir -p "$REGISTRY_DIR"
  # Stamp canonical recorded_at if the record doesn't carry one.
  if ! grep -q '^recorded_at:' "$rec"; then
    local stamped="${rec}.staged"
    { head -n 2 "$rec" || true; printf 'recorded_at: %s\n' "$(now_utc)"
      tail -n +3 "$rec"; } > "$stamped"
    mv "$stamped" "$slot"
  else
    cp "$rec" "$slot"
  fi
  ok "admitted to registry: $slot"
  printf '%s\n' "$slot"
}

# --- main dispatch -------------------------------------------------------------

case "$mode" in
  list) list_records ;;
  verify) verify_record "$verify_path" ;;
  record) record_admit "$record_path" ;;
  auto)
    [ -n "$topic_arg" ] || { err "topic required"; usage; exit 2; }
    pre_launch "$topic_arg" "auto"
    ;;
  update)
    [ -n "$topic_arg" ] || { err "topic required"; usage; exit 2; }
    pre_launch "$topic_arg" "update"
    ;;
  force)
    [ -n "$topic_arg" ] || { err "topic required"; usage; exit 2; }
    pre_launch "$topic_arg" "force"
    ;;
  *)
    err "internal dispatch: unknown mode $mode"; exit 2
    ;;
esac

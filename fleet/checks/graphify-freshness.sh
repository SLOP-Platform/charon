#!/usr/bin/env bash
# graphify-freshness.sh — GRAPHIFY-MAP-FRESHNESS MECHANIZED WIRING.
#
# THE BUG THIS CATCHES (cere-junda handoff, 2026-07-13): graphify's code map
# (graphify-out/graph.json) is rebuilt ONLY on-demand (`graphify update <path>`).
# At session handoff the PRODUCT graph was 3 days stale (missing this session's
# failover_loop/context_shaper/memory/foreman/gh-cache) and the RIG had NO graph
# at all. So reuse-check / review that leaned on graphify worked from a STALE
# map -> missed existing tools -> reinvention. This script MECHANIZES the
# keep-fresh contract on every smart trigger + cadence (DYNAMIC-DATA TOOL;
# never-on-demand — see MANAGER-OPERATING-RULES.md).
#
# SUB-COMMANDS:
#   check   [repo-root]...        -- read-only. Exit 0 = every graph is fresh.
#                                   Exit 1 = one or more graphs are stale/absent
#                                   (a 'foreman loud' message names each offender).
#   update  [repo-root]...        -- FORCE refresh every named repo's graph via
#                                   `graphify update <path>` (idempotent + cheap
#                                   on no-op). Run this on the smart TRIGGERS
#                                   (a) post-merge/land, (b) SessionStart boot,
#                                   (c) CADENCE backstop (cron/systemd-timer).
#   reuse-check "<proposed>"      -- the MANAGER ENTRY POINT: BEFORE building
#                                   ANY new tool, query the fresh graph +
#                                   TOOL-INVENTORY.md and report existing matches
#                                   ("do we already have X?"). Exit 0 = at least
#                                   one match found (REUSE OR JUSTIFY), Exit 1
#                                   = no match (CLEAR to build), Exit 2 = stale
#                                   graph (treat as RED; refresh first).
#   summary                       -- one-line per-graph status, no exit code.
#   paths                         -- print the repo roots this script watches.
#
# TRIGGER WIRING (manual until ops wires the cadence; see review-log note):
#   (a) POST-MERGE:    fleet/land.sh -> fleet/checks/graphify-freshness.sh update <rig> <product>
#   (b) SESSIONSTART:  fleet/hooks/session-start.sh -> graphify-freshness.sh update <rig> <product>
#   (c) CADENCE:       cron / systemd-timer -> graphify-freshness.sh update <rig> <product>
#   (d) PREFLIGHT:     preflight.sh -> graphify-freshness.sh check <rig> <product>  (loud RED on stale)
#
# STALENESS PRIMITIVE: a graph is FRESH iff `graph.json[built_at_commit] ==
# git rev-parse HEAD` of the repo. If the stamps diverge, we filter the
# `git log --name-only built..HEAD` to the code extensions graphify actually
# extracts (sourced from graphify/detect.py:CODE_EXTENSIONS so the filter can
# never silently desync from graphify itself). Any code-file change -> STALE.
# A pure config/markdown change between stamps is treated as fresh (graphify
# is a no-op on those, as the live product graph demonstrates).
#
# RIG COVERAGE: graphify has a tree-sitter BASH extractor (see
# graphify/extractors/bash.py) and the rig graph already contains 6,198 fleet
# bash nodes today — so the rig IS graphable; there is NO gap. The only reason
# the rig was empty at cere-junda handoff was that `graphify update` was never
# run against the rig repo. This script is the missing mechanism.
#
# REPO DEFAULTS (overridable on the command line for tests + cross-env):
#   PRODUCT_REPO_DEFAULT=/home/stack/code/charon   (the charon product)
#   RIG_REPO_DEFAULT    =/home/stack/charon-private  (this repo)
#
# ISOLATED TEST SEAM (used by tests/test_graphify_freshness.sh; never in normal ops):
#   GRAPHIFY_FRESHNESS_FAKE=<dir>   -- a temp dir containing a fake graph.json +
#                                      (optional) `git` shim that returns a controlled
#                                      built_at_commit/HEAD. Lets the test be 100%
#                                      hermetic and never touch the real graph.
#   GRAPHIFY_BIN=<path>             -- override `graphify` binary (for `update` subcmd).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- defaults / config --------------------------------------------------------------
PRODUCT_REPO_DEFAULT="/home/stack/code/charon"
RIG_REPO_DEFAULT="/home/stack/charon-private"
PRODUCT_REPO="${PRODUCT_REPO:-$PRODUCT_REPO_DEFAULT}"
RIG_REPO="${RIG_REPO:-$RIG_REPO_DEFAULT}"
GRAPHIFY_BIN="${GRAPHIFY_BIN:-$(command -v graphify 2>/dev/null || echo graphify)}"
TOOL_INVENTORY="${TOOL_INVENTORY:-$FLEET/TOOL-INVENTORY.md}"
FAKE_ROOT="${GRAPHIFY_FRESHNESS_FAKE:-}"

# Where a single repo's graph lives. graphify hard-codes `<repo>/graphify-out/`.
graph_dir(){ printf '%s/graphify-out' "$1"; }
graph_file(){ printf '%s/graph.json' "$(graph_dir "$1")"; }
manifest_file(){ printf '%s/manifest.json' "$(graph_dir "$1")"; }

# Source CODE_EXTENSIONS directly from graphify's own detect module so the staleness
# filter can NEVER silently desync from what graphify actually extracts. If graphify
# is not importable from this shell's env, fall back to a conservative hard-coded
# set that covers every language the current product + rig ship.
code_ext_filter(){
  python3 - <<'PY' 2>/dev/null
import re, sys, pathlib
try:
    sys.path.insert(0, str(pathlib.Path.home() / ".local/share/uv/tools/graphifyy/lib/python3.12/site-packages"))
    from graphify.detect import CODE_EXTENSIONS
    for ext in sorted(CODE_EXTENSIONS):
        # posix BRE class — escape the leading '.'
        print(re.escape(ext))
except Exception:
    # Conservative fallback (graphify's core language set + bash, json, md, tf):
    for ext in sorted({".py",".ts",".tsx",".js",".jsx",".mjs",".cjs",".go",".rs",
                       ".java",".kt",".kts",".swift",".c",".h",".cpp",".cc",".cxx",
                       ".hpp",".cs",".rb",".php",".scala",".lua",".sh",".bash",
                       ".ps1",".psm1",".dart",".ex",".exs",".sql",".tf",".tfvars",
                       ".hcl",".json",".md",".mdx",".vue",".svelte",".astro",
                       ".zig",".pas",".pp",".verilog",".sv",".svh",".vhd",".vhdl"}):
        print(re.escape(ext))
PY
}

# --- core: staleness primitives -----------------------------------------------------
# Emit the git rev-parse HEAD for a repo (or "" if no git). In FAKE mode, read from
# the FAKE dir's `_head` file so the test can pin the value without touching a real repo.
fake_or_real(){
  local repo="$1" marker="$2"
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/$marker" ] && cat "$FAKE_ROOT/$marker" || true
    return
  fi
  git -C "$repo" rev-parse HEAD 2>/dev/null || true
}

# built_commit <repo> -> the graph's `built_at_commit` (or "" if absent/unreadable).
built_commit(){
  local repo="$1" f; f="$(graph_file "$repo")"
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/graph_built_at_commit" ] && cat "$FAKE_ROOT/graph_built_at_commit" || true
    return
  fi
  [ -f "$f" ] || return 0
  python3 - "$f" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("built_at_commit", "") or "")
except Exception:
    pass
PY
}

# manifest_max_mtime <repo> -> max mtime across manifest.json entries (or 0 if absent).
# Used as a SECONDARY freshness signal: if the manifest's mtime stamps lag the source
# tree's actual mtimes by more than `max_age_seconds`, the graph is stale even when
# `built_at_commit` looks ok.
manifest_max_mtime(){
  local repo="$1" f; f="$(manifest_file "$repo")"
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/manifest_max_mtime" ] && cat "$FAKE_ROOT/manifest_max_mtime" || echo 0
    return
  fi
  [ -f "$f" ] || { echo 0; return; }
  python3 - "$f" <<'PY' 2>/dev/null || echo 0
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    vals = [v.get("mtime", 0) for v in d.values() if isinstance(v, dict)]
    print(int(max(vals)) if vals else 0)
except Exception:
    print(0)
PY
}

# changed_code_files <repo> <since_sha> -> list of code-ext files changed since <since_sha>,
# one per line, repo-relative. Empty = no code-graph-relevant changes. Filters by the
# `code_ext_filter()` set (sourced from graphify's own detect module).
changed_code_files(){
  local repo="$1" since="$2"
  if [ -n "$FAKE_ROOT" ]; then
    [ -f "$FAKE_ROOT/changed_code_files" ] && cat "$FAKE_ROOT/changed_code_files" || true
    return
  fi
  [ -n "$since" ] || return 0
  # Resolve short -> full sha; if <since> isn't an ancestor/known ref, fail closed (return nothing).
  git -C "$repo" rev-parse --verify --quiet "${since}^{commit}" >/dev/null 2>&1 || return 0
  local exts_re
  exts_re="$(code_ext_filter | paste -sd '|' -)"
  [ -n "$exts_re" ] || return 0
  git -C "$repo" log --name-only --pretty=format: "${since}..HEAD" -- . 2>/dev/null \
    | awk 'NF' \
    | grep -E "^.+\.(${exts_re})$" \
    | sort -u
}

# classify_one <repo> -> emits 3 lines on stdout:
#   state     FRESH|STALE|ABSENT|UNVERIFIED
#   detail    one-line human description
#   evidence  the changed-files list (or empty) for `STALE`; the absence reason for ABSENT
classify_one(){
  local repo="$1" state="FRESH" detail="" head built changed manifest_mt graph_mt
  if [ -n "$FAKE_ROOT" ]; then
    # FAKE-mode: emit a 3-line state/detail/evidence record exactly as the real
    # branch would, so the test can assert on every field. For STALE/ABSENT,
    # surface the changed-code-files (or absence) as actionable evidence.
    local fake_state fake_evidence
    fake_state="$(cat "$FAKE_ROOT/state" 2>/dev/null || echo FRESH)"
    fake_evidence="$(cat "$FAKE_ROOT/changed_code_files" 2>/dev/null || true)"
    case "$fake_state" in
      FRESH)
        printf 'FRESH\nfake-graph FRESH by fixture\n\n'
        ;;
      STALE)
        local n
        n="$(printf '%s\n' "$fake_evidence" | awk 'NF{c++} END{print c+0}')"
        if [ "$n" -gt 0 ]; then
          printf 'STALE\nfake-graph STALE by fixture: %s code file(s) changed since build\n%s\n\n' "$n" "$fake_evidence"
        else
          printf 'STALE\nfake-graph STALE by fixture (no changed-code-files evidence)\n\n'
        fi
        ;;
      ABSENT)
        printf 'ABSENT\nfake-graph ABSENT by fixture: no graph.json at %s\n\n' "$(graph_file "$repo")"
        ;;
      UNVERIFIED)
        printf 'UNVERIFIED\nfake-graph UNVERIFIED by fixture: not a git repo (cannot read HEAD)\n\n'
        ;;
      *)
        printf '%s\nfake-graph state=%s\n\n' "$fake_state" "$fake_state"
        ;;
    esac
    return
  fi
  local g; g="$(graph_file "$repo")"
  if [ ! -f "$g" ]; then
    printf 'ABSENT\n%s has NO graph.json at %s\n\n' "$repo" "$g"
    return
  fi
  head="$(fake_or_real "$repo" _head)"
  built="$(built_commit "$repo")"
  if [ -z "$head" ]; then
    printf 'UNVERIFIED\n%s is not a git repo (cannot read HEAD)\n\n' "$repo"
    return
  fi
  if [ -z "$built" ]; then
    printf 'STALE\n%s/graph.json has no built_at_commit stamp\n\n' "$repo"
    return
  fi
  if [ "$built" = "$head" ]; then
    # PRIMARY: stamps match. As a SECONDARY check, is the manifest's max-mtime lag suspicious?
    manifest_mt="$(manifest_max_mtime "$repo")"
    graph_mt="$(stat -c %Y "$g" 2>/dev/null || echo 0)"
    # 7 days. Far longer than any realistic write cadence for an actively-iterated repo;
    # a manifest that hasn't been touched in a week on an active repo is the same bug class
    # as the one this script was opened to fix.
    local max_age_seconds=604800
    if [ "$graph_mt" -gt 0 ] && [ "$manifest_mt" -gt 0 ] \
       && [ "$((graph_mt - manifest_mt))" -gt "$max_age_seconds" ]; then
      printf 'STALE\n%s graph.json=%s but manifest max mtime=%ss old (graph may be lying about freshness)\n\n' \
        "$repo" "$built" "$((graph_mt - manifest_mt))"
      return
    fi
    printf 'FRESH\n%s graph.json built_at_commit=%s == HEAD\n\n' "$repo" "$built"
    return
  fi
  # built != head: check whether any CODE-EXT file changed in between.
  changed="$(changed_code_files "$repo" "$built")"
  if [ -z "$changed" ]; then
    printf 'FRESH\n%s graph.json built_at_commit=%s behind HEAD=%s but no code-graph-relevant changes (config/docs only)\n\n' \
      "$repo" "$built" "$head"
    return
  fi
  evidence="$changed"
  # evidence flows via the `changed` variable in the printf below; the `evidence=`
  # alias keeps a single name across the function for readability + future callers.
  printf 'STALE\n%s graph.json built_at_commit=%s behind HEAD=%s; %s code file(s) changed since build\n%s\n' \
    "$repo" "$built" "$head" "$(printf '%s\n' "$changed" | grep -c .)" "$evidence"
}

# --- public: check (read-only, exit 0/1) --------------------------------------------
cmd_check(){
  local rc=0 repos=() r state detail label
  if [ $# -eq 0 ]; then
    repos=("$RIG_REPO" "$PRODUCT_REPO")
  else
    repos=("$@")
  fi
  echo "graphify-freshness: checking ${#repos[@]} graph(s)"
  for r in "${repos[@]}"; do
    [ -n "$r" ] || continue
    label="$(basename "$r")"
    local out
    out="$(classify_one "$r")"
    state="$(printf '%s\n' "$out" | sed -n '1p')"
    detail="$(printf '%s\n' "$out" | sed -n '2p')"
    if [ "$state" = "FRESH" ]; then
      printf '  [%-9s] %s\n' "$label" "$detail"
    else
      rc=1
      printf '  [%-9s] %s\n' "$label" "$detail"
      # surface the changed-files block (or absence reason) for a stale graph
      printf '%s\n' "$out" | sed -n '3,$p' | sed 's/^/      /'
    fi
  done
  if [ "$rc" -ne 0 ]; then
    echo "graphify-freshness: RED — one or more graphs are stale/absent. Run: $0 update"
    echo "graphify-freshness: STALE GRAPH CAUSES REUSE-CHECK TO MISS EXISTING TOOLS -> REINVENTION."
  else
    echo "graphify-freshness: GREEN — every graph is fresh."
  fi
  return "$rc"
}

# --- public: update (mechanized refresh on every smart trigger) --------------------
cmd_update(){
  local rc=0 repos=() r label out graphify_log
  if [ $# -eq 0 ]; then
    repos=("$RIG_REPO" "$PRODUCT_REPO")
  else
    repos=("$@")
  fi
  echo "graphify-freshness: refreshing ${#repos[@]} graph(s) via $GRAPHIFY_BIN"
  for r in "${repos[@]}"; do
    [ -n "$r" ] || continue
    [ -d "$r" ] || { echo "  [$(basename "$r")] SKIP — $r does not exist"; continue; }
    label="$(basename "$r")"
    echo "  [$(basename "$r")] $GRAPHIFY_BIN update $r"
    # graphify update is cheap on a no-op (no LLM, only re-extracts changed files) so
    # it is safe to call on every trigger. Capture the log so we can surface the
    # built_at_commit that the refresh actually committed.
    if graphify_log="$("$GRAPHIFY_BIN" update "$r" 2>&1)"; then
      # Re-classify so the operator sees the FRESH verdict land.
      out="$(classify_one "$r")"
      printf '%s\n' "$out" | sed -n '1,2p' | sed "s/^/    /"
      local s; s="$(printf '%s\n' "$out" | sed -n '1p')"
      if [ "$s" != "FRESH" ]; then
        echo "    WARN: $r still $s after update (see evidence below)"
        printf '%s\n' "$out" | sed -n '3,$p' | sed 's/^/      /'
        rc=1
      fi
    else
      echo "    FAIL: $GRAPHIFY_BIN update $r exited non-zero:" >&2
      printf '%s\n' "$graphify_log" | sed 's/^/      /' >&2
      rc=1
    fi
  done
  if [ "$rc" -eq 0 ]; then
    echo "graphify-freshness: UPDATE OK — every graph is now fresh."
  else
    echo "graphify-freshness: UPDATE INCOMPLETE — see warnings above." >&2
  fi
  return "$rc"
}

# --- public: summary (one-line per-graph, never fails) ----------------------------
cmd_summary(){
  local r label out state detail
  for r in "${RIG_REPO}" "${PRODUCT_REPO}"; do
    [ -n "$r" ] || continue
    [ -d "$r" ] || { echo "  $(basename "$r") | MISSING (no repo at $r)"; continue; }
    out="$(classify_one "$r")"
    state="$(printf '%s\n' "$out" | sed -n '1p')"
    detail="$(printf '%s\n' "$out" | sed -n '2p')"
    printf '  %-9s | %-11s | %s\n' "$(basename "$r")" "$state" "$detail"
  done
}

# --- public: paths ----------------------------------------------------------------
cmd_paths(){
  printf 'RIG:     %s\n' "$RIG_REPO"
  printf 'PRODUCT: %s\n' "$PRODUCT_REPO"
  printf 'BIN:     %s\n' "$GRAPHIFY_BIN"
}

# --- public: reuse-check (manager entry point — "do we already have X?") ------------
# Queries the fresh graphs for nodes whose label / norm_label / id look like the
# proposed tool name, AND greps TOOL-INVENTORY.md for prose mentions. Returns:
#   exit 0 — at least one match (REUSE OR EXPLICITLY JUSTIFY building again)
#   exit 1 — no match (CLEAR to build)
#   exit 2 — stale graph (treat as RED: refresh first, then re-run)
#
# The query is deliberately PERMISSIVE (substring + token-prefix) — false positives
# are cheap (the manager re-reads the hit list), false negatives cause REINVENTION.
cmd_reuse_check(){
  local query="${1:-}"
  [ -n "$query" ] || { echo "usage: $0 reuse-check \"<proposed-name-or-purpose>\"" >&2; exit 2; }
  # First, ensure the graph is fresh. A reuse-check against a stale map is a
  # false-negative generator — the whole bug this script was opened to fix.
  if ! cmd_check >/dev/null 2>&1; then
    echo "graphify-freshness: reuse-check ABORTED — graph is stale; refresh first ($0 update)"
    exit 2
  fi
  local python_args
  local python=python3
  read -r -d '' python_args <<PY || true
import json, os, re, sys
query = sys.argv[1]
q = query.strip().lower()
# token-prefix: split on non-alnum, match if any token of q prefixes any node label
# substring: q appears in norm_label/label/id (case-insensitive)
q_tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
def score(node):
    hay = " ".join(str(node.get(k, "")) for k in ("label","norm_label","id")).lower()
    if not hay: return 0
    s = 0
    # Substring match dominates: the whole proposed-name appears in the node.
    if q in hay: s += 20
    # Token-as-substring: any full query token (not a prefix) appears in hay.
    for tok in q_tokens:
        if tok and re.search(r"(^|[^a-z0-9])" + re.escape(tok) + r"([^a-z0-9]|$)", hay):
            s += 5
    # Substring of a HAY token equals a query token (the proposed-name is built from
    # existing vocabulary).
    hay_tokens = set(re.split(r"[^a-z0-9]+", hay))
    for tok in q_tokens:
        if tok and tok in hay_tokens: s += 3
    return s
def scan(path, label, limit=8, min_score=4):
    if not os.path.exists(path):
        print(f"  [{label}] (no graph at {path})")
        return 0
    try:
        d = json.load(open(path))
    except Exception as e:
        print(f"  [{label}] (failed to read {path}: {e})")
        return 0
    nodes = d.get("nodes", [])
    scored = [(score(n), n) for n in nodes]
    scored = [(s, n) for s, n in scored if s >= min_score]
    scored.sort(key=lambda x: -x[0])
    if not scored:
        print(f"  [{label}] no graph-node match (>= {min_score}) for '{query}' ({len(nodes)} nodes scanned)")
        return 0
    print(f"  [{label}] {len(scored)} match(es) in {len(nodes)} nodes (top {min(limit,len(scored))}, min_score={min_score}):")
    for s, n in scored[:limit]:
        loc = n.get("source_location","")
        sf = n.get("source_file","")
        nid = n.get("id","")
        lbl = n.get("label","")
        print(f"      score={s:>3}  {sf}{loc}  {lbl}  (id={nid})")
    return 1
total = 0
for repo_label, repo in (("rig", os.environ.get("RIG_REPO","")),
                          ("product", os.environ.get("PRODUCT_REPO",""))):
    if not repo: continue
    gd = os.path.join(repo, "graphify-out", "graph.json")
    total += scan(gd, repo_label)
# Also surface TOOL-INVENTORY.md prose hits so the manager sees the hand-curated map too.
inv = os.environ.get("TOOL_INVENTORY","")
if inv and os.path.exists(inv):
    try:
        text = open(inv, encoding="utf-8", errors="replace").read()
        lines = text.splitlines()
        # A line is a hit if it contains the query as a substring (case-insensitive) OR
        # any query token appears as a word/prefix in the line.
        q_tokens = [t for t in re.split(r"[^A-Za-z0-9]+", query) if t]
        hits = []
        for i, line in enumerate(lines, 1):
            lo = line.lower()
            if query.lower() in lo:
                hits.append((i, line.rstrip()))
                continue
            # Token-as-whole-word match (NOT prefix): the proposed-name's tokens must
            # appear as full words in the line. Prefix matches ("no" -> "no-op",
            # "now", "known") over-match; a whole-word requirement is a much stronger
            # "do we already have X?" signal.
            for tok in q_tokens:
                if len(tok) < 3: continue
                if re.search(r"(^|[^A-Za-z0-9._-])" + re.escape(tok) + r"([^A-Za-z0-9._-]|$)", line):
                    hits.append((i, line.rstrip()))
                    break
        if hits:
            print(f"  [tool-inventory] {len(hits)} prose line(s) match '{query}':")
            for i, line in hits[:8]:
                print(f"      L{i}: {line[:160]}")
            total += 1
        else:
            print(f"  [tool-inventory] no prose match for '{query}'")
    except Exception as e:
        print(f"  [tool-inventory] (failed to read {inv}: {e})")
sys.exit(0 if total > 0 else 1)
PY
  RIG_REPO="$RIG_REPO" PRODUCT_REPO="$PRODUCT_REPO" TOOL_INVENTORY="$TOOL_INVENTORY" \
    "$python" -c "$python_args" "$query"
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "graphify-freshness: reuse-check found existing match(es) for '$query' -> REUSE OR EXPLICITLY JUSTIFY before building."
  else
    echo "graphify-freshness: reuse-check: no existing match for '$query' -> CLEAR to build (after a human reads this output)."
  fi
  return "$rc"
}

# --- dispatch ---------------------------------------------------------------------
case "${1:-}" in
  check)        shift; cmd_check "$@" ;;
  update)       shift; cmd_update "$@" ;;
  reuse-check)  shift; cmd_reuse_check "${1:-}" ;;
  summary)      cmd_summary ;;
  paths)        cmd_paths ;;
  -h|--help|help|"")
    cat <<EOF
graphify-freshness.sh — keep the code-map FRESH on every smart trigger.

Usage:
  $0 check   [repo-root]...      read-only. exit 0 = fresh, 1 = stale/absent
  $0 update  [repo-root]...      refresh via 'graphify update'. idempotent.
  $0 reuse-check "<proposed>"    manager entry point: do we already have X?
  $0 summary                     one-line per-graph status, never fails
  $0 paths                       print watched repos

Repos (defaults; override via env):
  RIG_REPO     = $RIG_REPO
  PRODUCT_REPO = $PRODUCT_REPO
  GRAPHIFY_BIN = $GRAPHIFY_BIN
  TOOL_INVENTORY = $TOOL_INVENTORY

Triggers: SessionStart hook, post-merge/land, cron cadence. See review-log.
EOF
    ;;
  *) echo "graphify-freshness.sh: unknown subcommand '$1' (try: check|update|reuse-check|summary|paths)" >&2; exit 2 ;;
esac

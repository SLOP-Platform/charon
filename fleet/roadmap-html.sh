#!/usr/bin/env bash
# roadmap-html.sh — render ROADMAP.tsv into a self-contained HTML page.
#
# Emits ONE self-contained .html file: inline CSS only (NO external fonts/scripts/CDN),
# responsive, works in light AND dark mode.
#
# Usage:
#   fleet/roadmap-html.sh [output.html]
#
# Data: fleet/state/ROADMAP.tsv (override with ROADMAP_TSV=/path)
# The output path defaults to stdout if not given.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROADMAP="${ROADMAP_TSV:-$SELF_DIR/state/ROADMAP.tsv}"
OUTFILE="${1:-}"

[ -f "$ROADMAP" ] || { echo "roadmap-html.sh: ROADMAP not found: $ROADMAP" >&2; exit 1; }

html="$(awk -F'\t' -v genby="roadmap-html.sh" '
function esc(s) {
  gsub(/&/, "\\&amp;", s)
  gsub(/</, "\\&lt;", s)
  gsub(/>/, "\\&gt;", s)
  return s
}
function status_label(s) {
  if (s=="done")        return "Done"
  if (s=="in-review")   return "In Review"
  if (s=="building")    return "Building"
  if (s=="queued")      return "Queued"
  if (s=="designed")    return "Designed"
  if (s=="parked")      return "Parked"
  if (s=="not-started") return "Not Started"
  return s
}
function status_class(s) {
  if (s=="done")        return "st-done"
  if (s=="in-review")   return "st-review"
  if (s=="building")    return "st-building"
  if (s=="queued")      return "st-queued"
  if (s=="designed")    return "st-designed"
  if (s=="parked")      return "st-parked"
  if (s=="not-started") return "st-notstarted"
  return "st-default"
}
/^[[:space:]]*#/ { next }
/^[[:space:]]*$/ { next }
{
  proj=$1; id=$2; st=$3; phase=$4; name=$5; goal=$6; wave=$7
  if (!(proj in seen)) { seen[proj]=1; order[++np]=proj }
  n = ++cnt[proj]
  P[proj,n,"id"]=id; P[proj,n,"st"]=st; P[proj,n,"name"]=name; P[proj,n,"goal"]=goal; P[proj,n,"wave"]=wave
  if (wave != "") haswave[proj]=1
  tally[st]++
  ptally[proj,st]++
}
END {
  if (np == 0) { print "roadmap-html.sh: ROADMAP has no rows" > "/dev/stderr"; exit 1 }
  nrows = 0
  for (i=1; i<=np; i++) { nrows += cnt[order[i]] }

  print "<!DOCTYPE html>"
  print "<html lang=\"en\">"
  print "<head>"
  print "  <meta charset=\"utf-8\">"
  print "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
  print "  <title>Charon Fleet Roadmap</title>"
  print "  <style>"
  print "    :root {"
  print "      --bg: #ffffff; --fg: #111827; --muted: #6b7280; --border: #e5e7eb;"
  print "      --card-bg: #f9fafb; --chip-fg: #111827;"
  print "      --st-done-bg: #d1fae5; --st-done-fg: #065f46;"
  print "      --st-review-bg: #dbeafe; --st-review-fg: #1e40af;"
  print "      --st-build-bg: #ffedd5; --st-build-fg: #9a3412;"
  print "      --st-queue-bg: #fef9c3; --st-queue-fg: #854d0e;"
  print "      --st-design-bg: #f3e8ff; --st-design-fg: #6b21a8;"
  print "      --st-park-bg: #f3f4f6; --st-park-fg: #374151;"
  print "      --st-not-bg: #f9fafb; --st-not-fg: #6b7280; --st-not-border: #e5e7eb;"
  print "      --project-bg: #ffffff; --project-border: #e5e7eb;"
  print "      --wave-bg: #f3f4f6; --wave-fg: #374151;"
  print "    }"
  print "    @media (prefers-color-scheme: dark) {"
  print "      :root {"
  print "        --bg: #0b0f19; --fg: #e5e7eb; --muted: #9ca3af; --border: #374151;"
  print "        --card-bg: #111827; --chip-fg: #e5e7eb;"
  print "        --st-done-bg: #064e3b; --st-done-fg: #6ee7b7;"
  print "        --st-review-bg: #1e3a8a; --st-review-fg: #93c5fd;"
  print "        --st-build-bg: #7c2d12; --st-build-fg: #fdba74;"
  print "        --st-queue-bg: #713f12; --st-queue-fg: #fde047;"
  print "        --st-design-bg: #581c87; --st-design-fg: #d8b4fe;"
  print "        --st-park-bg: #1f2937; --st-park-fg: #9ca3af;"
  print "        --st-not-bg: #111827; --st-not-fg: #9ca3af; --st-not-border: #374151;"
  print "        --project-bg: #111827; --project-border: #374151;"
  print "        --wave-bg: #1f2937; --wave-fg: #d1d5db;"
  print "      }"
  print "    }"
  print "    *, *::before, *::after { box-sizing: border-box; }"
  print "    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--fg); line-height: 1.45; }"
  print "    .wrap { max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }"
  print "    h1 { font-size: 1.6rem; margin: 0 0 6px; }"
  print "    .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 18px; }"
  print "    .totals-bar { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-bottom: 22px; }"
  print "    .chip { display: inline-block; font-size: 0.85rem; padding: 4px 8px; border-radius: 999px; background: var(--card-bg); border: 1px solid var(--border); white-space: nowrap; }"
  print "    .project { background: var(--project-bg); border: 1px solid var(--project-border); border-radius: 12px; padding: 16px; margin-bottom: 18px; }"
  print "    .project-header { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }"
  print "    .project-title { font-size: 1.15rem; font-weight: 700; margin: 0; }"
  print "    .project-totals { display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 0.82rem; color: var(--muted); }"
  print "    .wave { margin-top: 10px; }"
  print "    .wave-title { font-size: 0.95rem; font-weight: 600; color: var(--wave-fg); background: var(--wave-bg); padding: 6px 10px; border-radius: 8px; margin: 0 0 8px; }"
  print "    .ticket { display: grid; grid-template-columns: 90px 1fr auto; gap: 10px; align-items: start; padding: 8px 6px; border-bottom: 1px solid var(--border); }"
  print "    .ticket:last-child { border-bottom: none; }"
  print "    .id { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.9rem; font-weight: 600; color: var(--muted); }"
  print "    .name { font-weight: 600; }"
  print "    .goal { font-size: 0.88rem; color: var(--muted); }"
  print "    .status-badge { display: inline-block; font-size: 0.78rem; font-weight: 600; padding: 3px 8px; border-radius: 999px; white-space: nowrap; }"
  print "    .st-done { background: var(--st-done-bg); color: var(--st-done-fg); }"
  print "    .st-review { background: var(--st-review-bg); color: var(--st-review-fg); }"
  print "    .st-building { background: var(--st-build-bg); color: var(--st-build-fg); }"
  print "    .st-queued { background: var(--st-queue-bg); color: var(--st-queue-fg); }"
  print "    .st-designed { background: var(--st-design-bg); color: var(--st-design-fg); }"
  print "    .st-parked { background: var(--st-park-bg); color: var(--st-park-fg); }"
  print "    .st-notstarted { background: var(--st-not-bg); color: var(--st-not-fg); border: 1px solid var(--st-not-border); }"
  print "    .grand { margin-top: 22px; padding-top: 14px; border-top: 2px solid var(--border); }"
  print "    .grand-title { font-size: 1rem; font-weight: 700; margin: 0 0 8px; }"
  print "    @media (max-width: 640px) {"
  print "      .ticket { grid-template-columns: 1fr; gap: 4px; }"
  print "      .project-header { flex-direction: column; align-items: flex-start; }"
  print "    }"
  print "  </style>"
  print "</head>"
  print "<body>"
  print "  <div class=\"wrap\">"
  print "    <h1>Charon Fleet Roadmap</h1>"
  print "    <div class=\"meta\">" genby " &middot; " nrows " tickets &middot; " np " projects</div>"
  print "    <div class=\"totals-bar\">"

  split("done in-review building queued designed parked not-started", ord, " ")
  for (k=1; k<=7; k++) {
    s = ord[k]
    c = (s in tally) ? tally[s] : 0
    print "      <span class=\"chip\">" status_label(s) ": " c "</span>"
  }
  print "    </div>"

  for (i=1; i<=np; i++) {
    proj = order[i]
    print "    <section class=\"project\">"
    print "      <div class=\"project-header\">"
    print "        <h2 class=\"project-title\">" esc(proj) "</h2>"
    print "        <div class=\"project-totals\">"
    for (k=1; k<=7; k++) {
      s = ord[k]
      c = (s in ptally[proj]) ? ptally[proj,s] : 0
      if (c > 0) {
        print "          <span>" status_label(s) ": " c "</span>"
      }
    }
    print "        </div>"
    print "      </div>"

    if (proj in haswave) {
      wc = 0
      delete worder
      delete wseen
      for (n=1; n<=cnt[proj]; n++) {
        w = P[proj,n,"wave"]
        label = (w=="") ? "Unscheduled" : w
        if (!(label in wseen)) { wseen[label]=1; worder[++wc]=label }
      }
      for (wi=1; wi<=wc; wi++) {
        label = worder[wi]
        print "      <div class=\"wave\">"
        print "        <div class=\"wave-title\">" esc(label) "</div>"
        for (n=1; n<=cnt[proj]; n++) {
          w = P[proj,n,"wave"]; il = (w=="") ? "Unscheduled" : w
          if (il == label) {
            idv = P[proj,n,"id"]
            st = P[proj,n,"st"]
            nm = P[proj,n,"name"]
            gl = P[proj,n,"goal"]
            print "        <div class=\"ticket\">"
            print "          <div class=\"id\">" esc(idv) "</div>"
            print "          <div>"
            print "            <div class=\"name\">" esc(nm) "</div>"
            print "            <div class=\"goal\">" esc(gl) "</div>"
            print "          </div>"
            print "          <div class=\"status-badge " status_class(st) "\">" status_label(st) "</div>"
            print "        </div>"
          }
        }
        print "      </div>"
      }
    } else {
      for (n=1; n<=cnt[proj]; n++) {
        idv = P[proj,n,"id"]
        st = P[proj,n,"st"]
        nm = P[proj,n,"name"]
        gl = P[proj,n,"goal"]
        print "      <div class=\"ticket\">"
        print "        <div class=\"id\">" esc(idv) "</div>"
        print "        <div>"
        print "          <div class=\"name\">" esc(nm) "</div>"
        print "          <div class=\"goal\">" esc(gl) "</div>"
        print "        </div>"
        print "        <div class=\"status-badge " status_class(st) "\">" status_label(st) "</div>"
        print "      </div>"
      }
    }
    print "    </section>"
  }

  print "    <section class=\"grand\">"
  print "      <div class=\"grand-title\">Grand Totals</div>"
  print "      <div class=\"totals-bar\">"
  for (k=1; k<=7; k++) {
    s = ord[k]
    c = (s in tally) ? tally[s] : 0
    cls = status_class(s)
    print "        <span class=\"chip " cls "\">" status_label(s) ": " c "</span>"
  }
  print "      </div>"
  print "    </section>"

  print "  </div>"
  print "</body>"
  print "</html>"
}
' "$ROADMAP")"

if [ -n "$OUTFILE" ]; then
  printf '%s\n' "$html" > "$OUTFILE"
  echo "roadmap-html.sh: wrote $OUTFILE"
else
  printf '%s\n' "$html"
fi

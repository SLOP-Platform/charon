#!/usr/bin/env python3
"""Detect which model the CURRENT opencode session is running as.

METHOD CHOSEN (primary): read opencode's own local session-state store,
``~/.local/share/opencode/opencode.db`` (SQLite), read-only. Every opencode
session persists a `model` column on its `session` row (JSON
`{"providerID": ..., "id": <model-id>}`), updated live the moment the
operator runs `/model` in that tab. We take the single MOST-RECENTLY-UPDATED
session system-wide. This is reliable for the target UX specifically
*because* of the workflow it's built for: the operator runs `/model` and
then IMMEDIATELY pastes the bench kickoff into that SAME tab, so that tab's
session row is, by construction, the freshest one in the whole DB at the
moment this script runs (it executes from inside a bash-tool call made BY
that tab, an instant after the paste). A staleness guard (default 900s)
refuses to trust a row that isn't fresh, rather than silently reporting an
unrelated idle tab's model.

ALTERNATIVES INVESTIGATED AND REJECTED:
- ``~/.local/state/opencode/model.json`` ("recent" list) is GLOBAL across
  every open tab and is only updated at the instant of a `/model` switch -
  it goes stale/wrong the moment a *different* tab switches models after
  this one did, which is exactly the multi-tab fleet workflow this rig
  runs. The SQLite `session.model` column is authoritative PER-SESSION and
  is what backs that UI in the first place, so read it directly instead.
- No opencode CLI subcommand exposes "what is THIS session's active model"
  (`opencode models` lists what's *available*, not what's selected;
  checked `opencode --help` / `opencode models --help` on 1.17.13).
- No env var is injected into the bash-tool's subprocess (`env | grep -i
  opencode` inside a live tab's shell is empty).
- Cost: one read-only, `time_updated`-ordered SQLite query via stdlib
  `sqlite3`, no network, sub-10ms. Cheapest option that is also reliable.

FALLBACK (per the build ticket, and what bench.sh does when this prints
nothing / exits 1): the DB is missing, locked, or has no session fresher
than the staleness guard (e.g. a brand-new machine, or the operator waited
too long between `/model` and pasting) -> bench.sh asks the AGENT to
self-report its own model name as the announced first step instead of
guessing.
"""
import json
import os
import sqlite3
import sys
import time

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
STALENESS_SEC = 900  # 15 min - operator just ran /model + pasted; must be fresh


def detect(staleness=STALENESS_SEC):
    if not os.path.exists(DB_PATH):
        return None
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT model, time_updated FROM session "
            "WHERE model IS NOT NULL ORDER BY time_updated DESC LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        con.close()
    if not row:
        return None
    model_json, time_updated = row
    age_s = time.time() - (time_updated / 1000.0)
    if age_s > staleness or age_s < 0:
        return None
    try:
        data = json.loads(model_json)
    except (TypeError, ValueError):
        return None
    model_id = data.get("id")
    if not model_id:
        return None
    return model_id, age_s


def main():
    try:
        result = detect()
    except Exception:
        result = None
    if result is None:
        print("", end="")
        sys.exit(1)
    model_id, age_s = result
    print(json.dumps({"model": model_id, "age_s": round(age_s, 1)}))


if __name__ == "__main__":
    main()

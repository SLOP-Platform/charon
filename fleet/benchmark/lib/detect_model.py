#!/usr/bin/env python3
"""Detect which model the CURRENT opencode session is running as.

METHOD CHOSEN (primary): read opencode's own local session-state store,
``~/.local/share/opencode/opencode.db`` (SQLite), read-only. Every opencode
session persists a `model` column on its `session` row (JSON
`{"providerID": ..., "id": <model-id>}`), updated live the moment the
operator runs `/model` in that tab. The original version of this script took
the single MOST-RECENTLY-UPDATED session system-wide, reasoning that the
operator runs `/model` and then IMMEDIATELY pastes the bench kickoff into
that SAME tab, so that tab's session row would, by construction, be the
freshest one in the whole DB at the moment this script runs.

BENCH-MODEL-MISDETECT (P1, fleet/reds.tsv) - why "take rank 1" is WRONG:
`session.time_updated` bumps on ANY session activity, not only a `/model`
switch (every message/tool-call touches the row). In this rig's normal
multi-tab operating mode (manager session + several concurrent droid/bench
tabs), some OTHER, entirely unrelated tab is very likely to be more
recently *touched* than the operator's own freshly-`/model`-picked bench
tab, even many minutes after the real pick - that other tab's `model`
column reflects whatever it was set to ages ago, not anything the operator
just chose. Confirmed incident: operator exited opencode, restarted,
`/model` -> glm-5.2, ran the bench - but the freshest row belonged to a
DIFFERENT, concurrently-active tab still sitting on hy3-preview-or from a
prior session (restored/continued, so its row kept getting touched without
a fresh `/model` call). `detect()` announced hy3-preview-or, saw it already
fully finalized, and silently SKIPPED the run - no error, no benchmark.

FIX: never trust rank-1 alone. Collect every session with a `model` set
that was updated within the staleness window, and look at the DISTINCT set
of model ids among them:
  - 0 candidates  -> nothing fresh enough; caller falls back (unchanged).
  - 1 distinct id -> unambiguous even if several tabs/sessions share it;
                     return it (this is the common single-tab case, and the
                     fast path stays exactly as reliable as before).
  - 2+ distinct ids -> AMBIGUOUS: more than one tab set a DIFFERENT model
                     within the window, so "most recent" cannot be trusted
                     to mean "the one the operator just picked". Refuse to
                     guess (raises `Ambiguous`, exit code 2) rather than
                     silently reporting whichever one happened to be
                     touched last - exactly the bench-model-misdetect
                     failure mode. The caller MUST pass `--model` instead.
This directly implements "if there are multiple recently-updated sessions
or any ambiguity, REFUSE to guess" rather than trying to out-guess the
ambiguity with a narrower time window - a narrower window does not help
here (the wrong candidate above was touched at age ~0s, i.e. it would win
under ANY window short of excluding it entirely), so ambiguity detection
across the existing window is the actual fix, not a smaller staleness
constant.

ALTERNATIVES INVESTIGATED AND REJECTED (unchanged from the original design):
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
nothing / exits 1, OR reports ambiguity / exits 2): the DB is missing,
locked, has no session fresher than the staleness guard, or is ambiguous
between two-or-more differing models -> bench.sh asks the AGENT to
self-report its own model name (it already knows this from its own
conversation) and re-invoke explicitly with `--model <id>` instead of
guessing.

MODEL-ID-NORMALIZE (fleet ticket): opencode's `session.model` JSON `id`
field is sometimes provider-namespaced (e.g. `charon/glm-5.2` when the
session is routed through the `charon` opencode provider) rather than the
bare curated id (`glm-5.2`) the rest of the harness (model-scorecard.tsv,
runs/<id>/, tier_chart.py's cross-model ranking) keys everything on. Left
unnormalized, this silently fragments ONE model into TWO scorecard
identities (`glm-5.2` and `charon/glm-5.2`), splitting its history and
corrupting tier/rank comparisons. `normalize_model_id()` below mirrors
charon's own `proxy.py::_normalize_model_id` EXACTLY (rsplit on the final
`/` segment; a bare id with no `/` is returned unchanged) so opencode's
provider-namespaced form collapses to the same bare id charon itself
normalizes to. Applied here, at the single earliest point the raw id is
read out of the DB, so every caller downstream (detect()'s own
ambiguity-dedup, bench.sh's ANNOUNCE banner, its runs/<id>/ path
construction, and the scorecard `model` column) sees only the normalized
form without having to normalize again itself. bench.sh's `--model`
override path does not flow through this module, so it re-normalizes via
this SAME function (see bench.sh's `normalize_model_id` shell helper) -
never a re-implementation of the rsplit logic.
"""
import json
import os
import sqlite3
import sys
import time

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
STALENESS_SEC = 900  # 15 min - operator just ran /model + pasted; must be fresh
CANDIDATE_LIMIT = 50  # rows to scan looking for the staleness cutoff; plenty
                       # for any realistic number of concurrently-open tabs


def normalize_model_id(model_id):
    """Mirror charon's src/charon/proxy.py::_normalize_model_id EXACTLY:
    take the FINAL '/'-delimited path segment. A bare id with no '/' is
    returned unchanged (no-op). Falsy input passes through unchanged (the
    caller decides what to do with None/"" - this never fabricates a value).
    See the MODEL-ID-NORMALIZE module note above for why this exists."""
    if not model_id:
        return model_id
    return model_id.rsplit("/", 1)[-1]


class Ambiguous(Exception):
    """Raised when 2+ DISTINCT models were set within the staleness window -
    see BENCH-MODEL-MISDETECT above for why this must not be guessed."""

    def __init__(self, candidates):
        self.candidates = candidates  # sorted list of distinct model ids
        super().__init__(f"ambiguous: {candidates}")


def detect(staleness=STALENESS_SEC):
    if not os.path.exists(DB_PATH):
        return None
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT model, time_updated FROM session "
            "WHERE model IS NOT NULL ORDER BY time_updated DESC LIMIT ?",
            (CANDIDATE_LIMIT,),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    if not rows:
        return None

    now = time.time()
    candidates = []  # (model_id, age_s) for every row inside the window
    for model_json, time_updated in rows:
        age_s = now - (time_updated / 1000.0)
        if age_s > staleness or age_s < 0:
            # rows are ORDER BY time_updated DESC, so once one row falls
            # outside the window every subsequent row does too - stop.
            break
        try:
            data = json.loads(model_json)
        except (TypeError, ValueError):
            continue
        model_id = normalize_model_id(data.get("id"))
        if model_id:
            candidates.append((model_id, age_s))

    if not candidates:
        return None

    distinct = sorted({model_id for model_id, _ in candidates})
    if len(distinct) > 1:
        raise Ambiguous(distinct)

    model_id, age_s = candidates[0]  # freshest row (rows were DESC-ordered)
    return model_id, age_s


def main():
    try:
        result = detect()
    except Ambiguous as amb:
        # Distinct exit code so bench.sh can tell "ambiguous, don't guess"
        # apart from "nothing fresh found" and give a specific message.
        print(json.dumps({"error": "ambiguous", "candidates": amb.candidates}))
        sys.exit(2)
    except Exception:
        result = None

    if result is None:
        print("", end="")
        sys.exit(1)

    model_id, age_s = result
    print(json.dumps({"model": model_id, "age_s": round(age_s, 1)}))


if __name__ == "__main__":
    main()

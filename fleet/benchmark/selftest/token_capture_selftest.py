#!/usr/bin/env python3
"""TOKEN-CAPTURE self-test: proves tokens_in/tokens_out can be captured
alongside cost_usd (lib/charon_cost.py `snapshot_usage()`/`int_delta_str()`)
and threaded through to the scorecard ledger (model-scorecard.sh `append`)
WITHOUT breaking any existing reader on either a legacy (pre-fix,
13-column) row or a new (15-column) one.

Runs entirely against SCRATCH copies (a temp dir + temp TSV) - never reads
or writes the real benchmark/runs/ tree or the real model-scorecard.tsv, so
it's safe to run alongside a live benchmark session.

Usage: python3 selftest/token_capture_selftest.py
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH_DIR = HERE.parent
LIB_DIR = BENCH_DIR / "lib"
FLEET_DIR = BENCH_DIR.parent

sys.path.insert(0, str(LIB_DIR))
sys.path.insert(0, str(BENCH_DIR.parent))  # not required, kept symmetric with other selftests

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


# --------------------------------------------------------------------------
# Part 1: charon_cost.snapshot_usage() / int_delta_str() parsing
# --------------------------------------------------------------------------

class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_RESPONSE_BODY = {"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}


class _MockGateway(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_GET(self) -> None:
        payload = json.dumps({"usage": _RESPONSE_BODY}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def part1_snapshot_parsing() -> None:
    import charon_cost  # noqa: E402

    server = _Threaded(("127.0.0.1", 0), _MockGateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[0], server.server_address[1]
    status_url = f"http://{host}:{port}/charon/status"

    os.environ["CHARON_BENCH_STATUS_URL"] = status_url
    os.environ["CHARON_BENCH_STATUS_TOKEN"] = "unused"
    os.environ.pop("CHARON_BENCH_SESSION_ID", None)

    try:
        # (a) full body: cost + both token fields present.
        _RESPONSE_BODY.clear()
        _RESPONSE_BODY.update({"cost_usd": 1.5, "tokens_in": 100, "tokens_out": 40})
        usage = charon_cost.snapshot_usage()
        check(usage is not None, "snapshot_usage() returned None for a full response body")
        if usage is not None:
            check(usage.get("cost_usd") == 1.5, f"cost_usd parsed wrong: {usage}")
            check(usage.get("tokens_in") == 100, f"tokens_in parsed wrong: {usage}")
            check(usage.get("tokens_out") == 40, f"tokens_out parsed wrong: {usage}")
        cost_only = charon_cost.snapshot_cost_usd()
        check(cost_only == 1.5, f"snapshot_cost_usd() wrapper drifted from snapshot_usage(): {cost_only}")

        # (b) older/other-provider body: cost present, tokens MISSING entirely
        # (not a failure - graceful None per-field, never a crash).
        _RESPONSE_BODY.clear()
        _RESPONSE_BODY.update({"cost_usd": 2.25})
        usage2 = charon_cost.snapshot_usage()
        check(usage2 is not None, "snapshot_usage() returned None for a token-less (legacy) response")
        if usage2 is not None:
            check(usage2.get("cost_usd") == 2.25, f"cost_usd parsed wrong on token-less body: {usage2}")
            check(usage2.get("tokens_in") is None, f"tokens_in should be None when absent, got {usage2.get('tokens_in')}")
            check(usage2.get("tokens_out") is None, f"tokens_out should be None when absent, got {usage2.get('tokens_out')}")

        # (c) garbage token values (non-numeric) - graceful None, no crash.
        _RESPONSE_BODY.clear()
        _RESPONSE_BODY.update({"cost_usd": 3.0, "tokens_in": "not-a-number", "tokens_out": None})
        usage3 = charon_cost.snapshot_usage()
        check(usage3 is not None, "snapshot_usage() returned None for a body with garbage token fields")
        if usage3 is not None:
            check(usage3.get("tokens_in") is None, f"garbage tokens_in should become None, got {usage3.get('tokens_in')}")
            check(usage3.get("tokens_out") is None, f"null tokens_out should become None, got {usage3.get('tokens_out')}")
    finally:
        server.shutdown()
        for var in ("CHARON_BENCH_STATUS_URL", "CHARON_BENCH_STATUS_TOKEN"):
            os.environ.pop(var, None)

    # unreachable gateway -> None, never raises.
    os.environ["CHARON_BENCH_STATUS_URL"] = "http://127.0.0.1:1/charon/status"
    os.environ["CHARON_BENCH_STATUS_TOKEN"] = "unused"
    try:
        check(charon_cost.snapshot_usage() is None, "snapshot_usage() should return None when gateway is unreachable")
    finally:
        os.environ.pop("CHARON_BENCH_STATUS_URL", None)
        os.environ.pop("CHARON_BENCH_STATUS_TOKEN", None)

    # int_delta_str semantics
    check(charon_cost.int_delta_str(10, 25) == "15", "int_delta_str normal delta wrong")
    check(charon_cost.int_delta_str(None, 25) == "-", "int_delta_str should be '-' when start is None")
    check(charon_cost.int_delta_str(10, None) == "-", "int_delta_str should be '-' when end is None")
    check(charon_cost.int_delta_str(30, 10) == "-", "int_delta_str should be '-' when counter went backwards")
    check(charon_cost.int_delta_str(0, 0) == "0", "int_delta_str should allow a zero delta")


# --------------------------------------------------------------------------
# Part 2: model-scorecard.sh cmd_append / cmd_render, on a SCRATCH TSV -
# proves both a legacy (no-token) append call and a new (with-token) one
# produce rows `render` can parse without error, and that a hand-written
# genuine legacy 13-column row (simulating pre-existing ledger data)
# doesn't crash it either.
# --------------------------------------------------------------------------

def part2_scorecard_sh() -> None:
    real_sh = FLEET_DIR / "model-scorecard.sh"
    check(real_sh.exists(), f"model-scorecard.sh not found at {real_sh}")
    if not real_sh.exists():
        return

    with tempfile.TemporaryDirectory(prefix="token-capture-selftest-") as td:
        tmp = Path(td)
        scratch_sh = tmp / "model-scorecard.sh"
        shutil.copy(real_sh, scratch_sh)
        scratch_sh.chmod(0o755)
        scratch_tsv = tmp / "model-scorecard.tsv"
        # header only - mirrors the real file's leading comment lines, no data rows.
        scratch_tsv.write_text(
            "# model-scorecard.tsv — per-model x per-work-class performance ledger (SCRATCH COPY, selftest only)\n"
            "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\ttime_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\n"
        )

        def run_sh(*args, env_extra=None):
            env = os.environ.copy()
            if env_extra:
                env.update(env_extra)
            return subprocess.run(
                ["bash", str(scratch_sh), *args],
                cwd=tmp, capture_output=True, text=True, env=env, timeout=30)

        # (1) legacy-style append call: no token env vars set at all -
        # simulates a caller written before TOKEN-CAPTURE (or run.sh, which
        # this fix deliberately left untouched).
        r1 = run_sh("append", "2026-07-06", "bench", "S1", "tests", "1",
                    "token-selftest-model", "MERGE", "pass", "95", "12.3", "0.002100", "0", "legacy call no tokens")
        check(r1.returncode == 0, f"legacy append failed: rc={r1.returncode} stderr={r1.stderr!r}")

        # (2) new-style append call: token env vars set (mirrors bench.sh).
        r2 = run_sh("append", "2026-07-06", "bench", "S2", "tests", "1",
                    "token-selftest-model", "MERGE", "pass", "88", "9.1", "0.001500", "0", "with tokens",
                    env_extra={"CHARON_SCORECARD_TOKENS_IN": "1200", "CHARON_SCORECARD_TOKENS_OUT": "340"})
        check(r2.returncode == 0, f"with-tokens append failed: rc={r2.returncode} stderr={r2.stderr!r}")

        rows = [ln for ln in scratch_tsv.read_text().splitlines() if ln and not ln.startswith("#")]
        check(len(rows) == 2, f"expected 2 data rows after two appends, got {len(rows)}: {rows}")
        if len(rows) == 2:
            cols1 = rows[0].split("\t")
            cols2 = rows[1].split("\t")
            check(len(cols1) == 15, f"legacy-call row should still get 15 cols (tokens default '-'), got {len(cols1)}: {cols1}")
            check(cols1[-2:] == ["-", "-"], f"legacy-call row tokens should default to '-','-', got {cols1[-2:]}")
            check(len(cols2) == 15, f"with-tokens row should have 15 cols, got {len(cols2)}: {cols2}")
            check(cols2[-2:] == ["1200", "340"], f"with-tokens row should end in 1200,340 got {cols2[-2:]}")

        # (3) hand-write a genuine legacy 13-column row (as if it predates
        # this fix entirely - no trailing tokens columns at all) and confirm
        # render still doesn't crash.
        with scratch_tsv.open("a") as fh:
            fh.write("2026-06-01\tbench\tS3\ttests\t1\ttoken-selftest-model\tFIXES\tpass\t70\t20.0\t0.0030\t1\tpre-fix legacy row\n")

        r3 = run_sh("render")
        check(r3.returncode == 0, f"render crashed on mixed legacy+new rows: rc={r3.returncode} stderr={r3.stderr!r}")
        check("token-selftest-model" in r3.stdout, f"render output missing expected model: {r3.stdout!r}")


# --------------------------------------------------------------------------
# Part 3: tier_chart.py against the SAME mixed legacy+new-column TSV -
# proves the tier chart (which unpacks cols[:13]) tolerates a genuine
# 13-column legacy row and a new 15-column row for the SAME model side by
# side without error.
# --------------------------------------------------------------------------

def part3_tier_chart() -> None:
    sys.path.insert(0, str(LIB_DIR))
    import tier_chart  # noqa: E402

    with tempfile.TemporaryDirectory(prefix="token-capture-selftest-tierchart-") as td:
        tsv = Path(td) / "model-scorecard.tsv"
        tsv.write_text(
            "# scratch\n"
            # legacy 13-col row (S0, sanity gate, must be 100)
            "2026-06-01\tbench\tS0\ttests\t0\ttc-model\tMERGE\tpass\t100\t5.0\t0.0001\t0\tlegacy sanity row\n"
            # new 15-col row with real token data (S1)
            "2026-07-06\tbench\tS1\ttests\t1\ttc-model\tMERGE\tpass\t92\t10.0\t0.0021\t0\tnew row with tokens\t1500\t410\n"
            # new 15-col row with '-','-' tokens (S2, gateway had no token data)
            "2026-07-06\tbench\tS2\ttests\t1\ttc-model\tMERGE\tpass\t88\t8.0\t0.0018\t0\tnew row no tokens\t-\t-\n"
        )
        try:
            rows = tier_chart.load_rows(tsv)
            check(len(rows) == 3, f"tier_chart.load_rows should see all 3 rows regardless of column count, got {len(rows)}")
            sc = tier_chart.bench_rows_for(rows, "tc-model")
            check(set(sc.keys()) == {"S0", "S1", "S2"}, f"bench_rows_for missed a section: {sc.keys()}")
            check(sc.get("S1", {}).get("note") == "new row with tokens", f"S1 note misparsed (extra cols must not shift note): {sc.get('S1')}")
            tier, comp = tier_chart.overall_tier(sc)
            check(tier is not None, "overall_tier() returned None unexpectedly on a fully-graded mini-run")
            # render() must not raise on this mixed-width file.
            tier_chart.render("tc-model", tsv_path=tsv)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"tier_chart crashed on mixed legacy/new-column TSV: {exc!r}")


def main() -> None:
    part1_snapshot_parsing()
    part2_scorecard_sh()
    part3_tier_chart()

    if failures:
        print(f"TOKEN-CAPTURE SELF-TEST FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("TOKEN-CAPTURE SELF-TEST PASS: snapshot_usage()/int_delta_str() parse "
          "full, token-less, and garbage gateway responses without crashing; "
          "model-scorecard.sh append/render handle both a legacy-style "
          "(no-token) call and a new with-token call, plus a genuine "
          "hand-written 13-column legacy row, side by side; tier_chart.py "
          "tolerates the mixed column widths without misreading `note` or "
          "crashing. All against scratch copies - the real ledger/runs/ "
          "tree was never touched.")


if __name__ == "__main__":
    main()

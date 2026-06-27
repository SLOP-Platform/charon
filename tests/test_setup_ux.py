"""First-run setup-UX (SETUP-UX-A): three fixes that all live in ``_cmd_setup``.

1. the "model served by '<provider>'" prompt surfaces the provider's already-imported
   catalog and offers a one-shot "serve all N" (TIER-RECS Phase A);
2. a 0-models-served WARN guard so the wizard never finishes cheerily on a silently
   non-serving gateway, and offers to fix it in place;
3. the "Presets:" line is colorized with a NO_COLOR / non-TTY plain fallback.

Dogfood-driven (charon-vm 2026-06-27: imported 49 models, served 0, blank serve prompt).
The wizard is driven through ``cli.main(["setup"])`` with ``input``/``getpass`` monkey-
patched and an isolated ``$CHARON_HOME`` (mirrors ``tests/test_config.py``).
"""
from __future__ import annotations

import sys

from charon import cli, config


def _drive(monkeypatch, inputs, keys=()):
    """Feed a fixed script to ``input`` and ``getpass`` and run the wizard."""
    it_in = iter(inputs)
    it_key = iter(keys)
    monkeypatch.setattr("builtins.input", lambda *a: next(it_in))
    import getpass
    monkeypatch.setattr(getpass, "getpass", lambda *a: next(it_key))
    return cli.main(["setup"])


# ── Deliverable 2: the 0-models-served warn guard ───────────────────────────────

def test_warns_when_nothing_served(monkeypatch, tmp_path, capsys):
    """Add a provider, skip the key, serve nothing → loud '0 models served' on stderr
    (NOT the cheery 'Done. 0 model(s) configured'). Exit stays 0 — wizard completed."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # provider 'openrouter', (key skipped via getpass), serve loop blank, finish providers
    rc = _drive(monkeypatch, ["openrouter", "", ""], keys=[""])
    cap = capsys.readouterr()
    assert rc == 0
    assert "0 models served" in cap.err
    assert "Done. 0 model(s) configured" not in cap.out


# ── Deliverable 1: surface the imported catalog + one-shot "serve all" ───────────

def test_serve_prompt_surfaces_catalog_and_serve_all(monkeypatch, tmp_path, capsys):
    """Pre-seed the catalog for a provider; the wizard SHOWS those ids and 'serve all'
    wires every one into the served set (the final count reflects them)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_models_bulk(
        [{"id": "alpha-1", "free": True}, {"id": "beta-2", "free": False}],
        provider="openrouter")
    # provider 'openrouter', (key skipped), 'serve all' → y, finish providers, decline pool
    rc = _drive(monkeypatch, ["openrouter", "y", "", "n"], keys=[""])
    out = capsys.readouterr().out
    assert rc == 0
    assert "alpha-1" in out and "beta-2" in out          # the catalog is surfaced
    assert "2 model(s) imported for 'openrouter'" in out
    assert "Done. 2 model(s) configured" in out          # serve-all fed the count


def test_serve_all_skips_per_model_reprompt(monkeypatch, tmp_path, capsys):
    """'serve all' must NOT re-prompt per model — the script provides no manual ids,
    so the run only completes if serve-all consumed the whole catalog in one shot."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_models_bulk([{"id": f"m-{i}"} for i in range(5)], provider="openrouter")
    rc = _drive(monkeypatch, ["openrouter", "y", "", "n"], keys=[""])
    assert rc == 0
    assert "Done. 5 model(s) configured" in capsys.readouterr().out


# ── Deliverable 2 (in-place fix): offer "serve all N now?" at the end ─────────────

def test_zero_served_guard_offers_in_place_fix(monkeypatch, tmp_path, capsys):
    """Decline serve-all up front and enter no manual id, but the catalog is non-empty:
    the end-guard offers 'serve all N now?' and accepting populates the served set."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_models_bulk(
        [{"id": "alpha-1"}, {"id": "beta-2"}], provider="openrouter")
    # provider, decline catalog serve-all ('n'), blank manual id, finish providers,
    # ACCEPT the end-guard 'serve all 2 now?' ('y'), decline pool ('n')
    rc = _drive(monkeypatch, ["openrouter", "n", "", "", "y", "n"], keys=[""])
    out = capsys.readouterr().out
    assert rc == 0
    # the catalog serve-all was DECLINED (no "… from 'openrouter'"), so reaching a
    # non-empty served set proves the end-guard's in-place "serve all now?" fired.
    assert "serving 2 model(s) from 'openrouter'" not in out
    assert "serving 2 model(s)" in out
    assert "Done. 2 model(s) configured" in out          # and was accepted


# ── Deliverable 3: colorize the presets line (with the plain fallback) ───────────

def test_presets_line_plain_on_non_tty(monkeypatch, tmp_path, capsys):
    """Under pytest capture stdout is non-TTY, so the presets line must stay plain —
    no raw ANSI escape leaks into the wizard output."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _drive(monkeypatch, ["openrouter", "", ""], keys=[""])
    out = capsys.readouterr().out
    assert "Presets:" in out
    assert "\x1b[" not in out


def test_ansi_emph_plain_when_no_color(monkeypatch):
    """NO_COLOR set to ANY value (incl. empty) → plain, even on a forced TTY."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    for val in ("1", ""):
        monkeypatch.setenv("NO_COLOR", val)
        assert cli._ansi_emph("Presets: x") == "Presets: x"


def test_ansi_emph_plain_on_dumb_terminal(monkeypatch):
    """TERM=dumb degrades to plain even on a TTY with no NO_COLOR."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb")
    assert cli._ansi_emph("Presets: x") == "Presets: x"


def test_ansi_emph_colors_on_tty(monkeypatch):
    """A real interactive TTY (no NO_COLOR, sane TERM) gets the ANSI emphasis."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm-256color")
    out = cli._ansi_emph("Presets: x")
    assert out.startswith("\x1b[") and "Presets: x" in out and out.endswith("\x1b[0m")

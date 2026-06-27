"""Propose-default gated landing (ADR-0007 D4/D6) + the consumer-supplied units
loader (D3).

`charon land` takes a *completed* unit's result — its ledger (the single source
of progress truth, INV-1) plus the worktree/branch the existing
``run_parallel``/``coordinator`` loop produced — runs a **tiered, fast-first
gate**, and then **PROPOSES**. It NEVER auto-merges (D4 reverses the first plan's
auto-land default; D5 batch-atomic auto-land is a later opt-in, deliberately NOT
built here). Default = open a PR (base ``master``) per unit; a *human* merges,
which is the only thing that advances anything downstream. `land` itself only
reads + proposes — it never advances lkg or touches the worktree.

The gate (all-green or HOLD), cheapest checks first so a hold costs nothing:
  1. diff-scope guard — any write outside the unit's *declared* owned-paths holds
     (and an undeclared scope holds too: fail-closed, you must declare what you
     touch).
  2. sensitive-path HOLD — ALWAYS holds, even when everything else is green, for
     the paths the gate/CI/tooling itself executes (D5's hold set).
  3. the unit's executable acceptance checks (from the ledger) + an optional test
     command.
  4. gitleaks — runs if installed; a detected leak holds (secrets are never
     proposed); missing-but-*expected* fails closed (hold), otherwise advisory.

The privileged core stays stdlib-only: git and the secret scanner are invoked as
external subprocesses, never imported.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from .acceptance import AcceptanceCheck
from .config import AutoLandConfig
from .ledger import Ledger
from .scanners import run_scanners


class LandError(RuntimeError):
    """Raised when the landing gate cannot be evaluated (e.g. git failed). Loud —
    a gate that cannot run must never read as 'green'."""


# --------------------------------------------------------------- sensitive paths
# D5's hold set: every path the gate / git / CI / tooling *executes* or trusts.
# Touching one forces a human review even when the unit is otherwise green,
# because the diff-scope + acceptance gate cannot model "in-scope but hostile".
_SENSITIVE_DIR_PREFIXES = (
    ".github/workflows/",
    ".git/hooks/",
    ".claude/",
)
# A path component equal to one of these → sensitive (matches nested dirs too,
# e.g. ``pkg/tests/test_x.py``).
_SENSITIVE_DIR_COMPONENTS = ("tests",)
_SENSITIVE_BASENAMES = {
    "dockerfile",
    ".pre-commit-config.yaml",
    "conftest.py",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "makefile",
    "gnumakefile",
    "justfile",
    "codeowners",
    ".envrc",
    # dependency manifests / lockfiles
    "pipfile",
    "pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "cargo.toml",
    "cargo.lock",
    "go.mod",
    "go.sum",
    "gemfile",
    "gemfile.lock",
}
# install / setup / bootstrap scripts of any common shell/script extension.
_INSTALL_SETUP_RE = re.compile(
    r"(?:^|[._-])(install|setup|bootstrap)\.(sh|bash|py|ps1|cmd|bat)$"
)
# requirements.txt and its dev/test variants (requirements-dev.txt, …).
_REQUIREMENTS_RE = re.compile(r"^requirements(?:[-_.][\w-]+)?\.txt$")


def is_sensitive(path: str) -> str | None:
    """Return a short label for *why* ``path`` is sensitive, or ``None`` if it is
    not. The label is surfaced in the gate report so a held unit says exactly
    which file tripped the hold."""
    p = path.replace("\\", "/").removeprefix("./")
    parts = [seg for seg in p.split("/") if seg]
    if not parts:
        return None
    base = parts[-1].lower()
    for prefix in _SENSITIVE_DIR_PREFIXES:
        if (p + "/").startswith(prefix) or ("/" + prefix) in ("/" + p + "/"):
            return prefix.rstrip("/")
    # a sensitive directory anywhere in the path (the file's parent chain)
    for comp in _SENSITIVE_DIR_COMPONENTS:
        if comp in parts[:-1]:
            return comp + "/"
    if base in _SENSITIVE_BASENAMES:
        return parts[-1]
    if _INSTALL_SETUP_RE.search(base) or _REQUIREMENTS_RE.match(base):
        return parts[-1]
    return None


def matches_prefix(path: str, prefixes: Sequence[str]) -> bool:
    """True iff ``path`` is the same as, or nested under, one of ``prefixes`` —
    the matcher behind ``AutoLandConfig.extra_sensitive`` (a config-supplied
    always-hold path widens, never shrinks, the built-in sensitive set)."""
    p = path.replace("\\", "/").removeprefix("./")
    for raw in prefixes:
        pref = _norm_owned(raw)
        if pref and (p == pref or p.startswith(pref + "/")):
            return True
    return False


# --------------------------------------------------------------- scope matching
def _norm_owned(owned: str) -> str:
    return owned.replace("\\", "/").strip().removeprefix("./").rstrip("/")


def in_scope(path: str, owned_paths: Sequence[str]) -> bool:
    """True iff ``path`` is the same as, or nested under, one of the declared
    ``owned_paths``. An empty owned set means nothing is in scope (fail-closed:
    a unit that declares no owned paths can land nothing)."""
    p = path.replace("\\", "/").removeprefix("./")
    for raw in owned_paths:
        owned = _norm_owned(raw)
        if not owned:
            continue
        if p == owned or p.startswith(owned + "/"):
            return True
    return False


# ------------------------------------------------------------------ gate result
@dataclass(frozen=True)
class GateOutcome:
    """The land gate's verdict for one unit. ``decision`` is ``"propose"`` only
    when ``holds`` is empty; any hold reason makes it ``"hold"``."""

    task_id: str
    goal: str
    decision: str  # "propose" | "hold"
    holds: list[str] = field(default_factory=list)
    base_ref: str = ""
    tip_ref: str = ""
    changed_files: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    sensitive: list[str] = field(default_factory=list)
    acceptance_failed: list[str] = field(default_factory=list)
    tests_passed: bool | None = None
    gitleaks: str = "skipped"  # clean | leaks | unavailable | skipped
    pr: str | None = None  # set by the CLI when a PR is actually opened
    scanner_advisory: list[dict] = field(default_factory=list)  # Tier B/C advisory (D4)

    @property
    def proposed(self) -> bool:
        return self.decision == "propose"

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "decision": self.decision,
            "holds": self.holds,
            "base_ref": self.base_ref,
            "tip_ref": self.tip_ref,
            "changed_files": self.changed_files,
            "out_of_scope": self.out_of_scope,
            "sensitive": self.sensitive,
            "acceptance_failed": self.acceptance_failed,
            "tests_passed": self.tests_passed,
            "gitleaks": self.gitleaks,
            "pr": self.pr,
            "scanner_advisory": self.scanner_advisory,
        }


# --------------------------------------------------------------------- git glue
def _git(repo: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def changed_files(repo: str, base: str, tip: str) -> list[str]:
    """Files differing between ``base`` and ``tip`` in ``repo`` (the unit's
    proposed diff). Raises ``LandError`` if git cannot answer — a gate that
    cannot see the diff must hold, never silently pass."""
    proc = _git(repo, "diff", "--name-only", base, tip)
    if proc.returncode != 0:
        raise LandError(f"git diff {base}..{tip} failed: {proc.stderr.strip()}")
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


# ------------------------------------------------------------------- gitleaks
@dataclass(frozen=True)
class GitleaksResult:
    status: str  # clean | leaks | unavailable
    note: str = ""


def run_gitleaks(repo: str) -> GitleaksResult:
    """Run gitleaks over ``repo`` if it is installed. Optional external scanner
    (never imported): ``unavailable`` when the binary is absent or errors,
    ``leaks`` on a positive detection (exit 1), ``clean`` otherwise."""
    try:
        proc = subprocess.run(
            ["gitleaks", "detect", "--source", repo, "--no-banner", "--redact"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return GitleaksResult("unavailable", note=f"{type(exc).__name__}")
    if proc.returncode == 0:
        return GitleaksResult("clean")
    if proc.returncode == 1:
        return GitleaksResult("leaks", note="gitleaks reported findings")
    return GitleaksResult("unavailable", note=f"gitleaks exit {proc.returncode}")


# --------------------------------------------------------------------- the gate
def _default_scanner_runner(repo: str, files: list[str]) -> list[dict]:
    try:
        return [r.to_dict() for r in run_scanners(repo, files)]
    except Exception:  # noqa: BLE001
        return []


def _required_scanner_runner(repo: str, files: list[str]) -> list[dict]:
    """Auto-land scanner runner (ADR-0012 D6): unlike the advisory default, a
    catastrophic scanner-matrix failure is surfaced as an ``error`` row rather
    than swallowed to ``[]`` — so ``scanners_required`` can fail closed on it
    (a check that cannot run must never read as green)."""
    try:
        return [r.to_dict() for r in run_scanners(repo, files)]
    except Exception as exc:  # noqa: BLE001
        return [{
            "name": "scanner-matrix",
            "tier": "?",
            "status": "error",
            "findings": [],
            "note": f"runner error: {exc}",
        }]


def land_unit(
    ledger: Ledger,
    owned_paths: Sequence[str],
    *,
    tip_ref: str | None = None,
    base_ref: str | None = None,
    tests_cmd: str | None = None,
    run_acceptance: bool = True,
    gitleaks_expected: bool = False,
    gitleaks_runner: Callable[[str], GitleaksResult] = run_gitleaks,
    scanner_runner: Callable[[str, list[str]], list[dict]] = _default_scanner_runner,
    allowlist: Sequence[str] | None = None,
    extra_sensitive: Sequence[str] = (),
    scanners_required: bool = False,
) -> GateOutcome:
    """Evaluate the tiered land gate for one completed unit and return a PROPOSE
    or HOLD verdict (D4/D6). Read-only: never advances lkg, never mutates the
    worktree, never merges.

    ``tip_ref`` defaults to the ledger's ``lkg_ref`` (the blessed completion
    commit for an L1+ unit); ``base_ref`` to the ledger's ``base_ref`` (the floor
    the unit was cut from).

    The last three parameters arm the **auto-land** posture (ADR-0012); their
    defaults preserve the propose-default behavior byte-for-byte:
      - ``allowlist`` (when not ``None``) — a changed file must ALSO be within this
        engine-owned allowlist to land; anything else HOLDS (D3). An empty
        allowlist holds everything (fail-closed).
      - ``extra_sensitive`` — additional always-hold path prefixes layered on the
        built-in sensitive set (D4); widen-only.
      - ``scanners_required`` — flip D007: a scanner finding HOLDS and an
        eligible-but-unavailable/timeout scanner fails closed (D6)."""
    repo = ledger.target_repo
    base = base_ref or ledger.base_ref
    tip = tip_ref or ledger.lkg_ref
    holds: list[str] = []

    files = changed_files(repo, base, tip)
    if not files:
        holds.append("no committed changes between base and tip — nothing to land")

    # 1. diff-scope guard (cheapest): writes outside the declared owned-paths hold.
    if not owned_paths:
        if files:
            holds.append("no declared owned_paths — cannot scope this unit (fail-closed)")
        out_of_scope: list[str] = list(files)
    else:
        out_of_scope = [f for f in files if not in_scope(f, owned_paths)]
        if out_of_scope:
            holds.append(f"out-of-scope writes: {out_of_scope}")

    # 1b. auto-land path-allowlist (ADR-0012 D3): even an in-scope file must be on
    #     the engine-owned allowlist to auto-land; everything else HOLDS. ``None``
    #     means "not armed" (propose-default); an empty allowlist holds all files.
    out_of_allowlist: list[str] = []
    if allowlist is not None:
        out_of_allowlist = [f for f in files if not in_scope(f, allowlist)]
        if out_of_allowlist:
            holds.append(f"out-of-allowlist writes (auto-land): {out_of_allowlist}")

    # 2. sensitive-path HOLD — always, even if everything else is green. The
    #    config-supplied ``extra_sensitive`` set widens (never shrinks) the built-in.
    sensitive = [
        f for f in files
        if is_sensitive(f) is not None or matches_prefix(f, extra_sensitive)
    ]
    if sensitive:
        labels = sorted({is_sensitive(f) or "extra-sensitive" for f in sensitive})
        holds.append(f"sensitive paths require human review: {sensitive} ({labels})")

    # 3. the unit's executable acceptance checks + optional tests.
    acceptance_failed: list[str] = []
    if run_acceptance:
        for chk in ledger.acceptance:
            if not chk.verify(repo):
                acceptance_failed.append(chk.id)
        if acceptance_failed:
            holds.append(f"acceptance checks failed: {acceptance_failed}")

    tests_passed: bool | None = None
    if tests_cmd:
        tests_passed = _run_tests(repo, tests_cmd)
        if not tests_passed:
            holds.append(f"tests failed: {tests_cmd!r}")

    # 4. gitleaks — advisory unless it finds a leak (never propose a secret) or it
    #    is missing-but-expected (fail-closed).
    gl = gitleaks_runner(repo)
    if gl.status == "leaks":
        holds.append("gitleaks detected secrets — never proposed")
    elif gl.status == "unavailable" and gitleaks_expected:
        holds.append("gitleaks expected but unavailable (fail-closed)")

    # 5. Advisory scanner matrix (ADR-0010 D4) — Tier B/C, change-scoped, parallel.
    #    Findings are NEVER added to holds; required/fail-closed is reserved for
    #    auto-land (deferred).  A scanner error produces "unavailable", never a hold.
    advisory = scanner_runner(repo, files)

    # 5b. auto-land flips D007: scanners become REQUIRED / fail-closed (ADR-0012 D6).
    #     A finding HOLDS; an eligible-but-unavailable/timeout/errored scanner fails
    #     closed (a check that cannot run must never read as green). "skipped" means
    #     the file-domain is not in the diff — genuinely nothing to scan, not a hold.
    if scanners_required:
        for s in advisory:
            status = s.get("status")
            if status == "finding":
                holds.append(
                    f"required scanner {s.get('name')} reported findings: "
                    f"{s.get('findings')}"
                )
            elif status in ("unavailable", "timeout", "error"):
                holds.append(
                    f"required scanner {s.get('name')} {status} (fail-closed): "
                    f"{s.get('note', '')}".rstrip()
                )

    decision = "propose" if not holds else "hold"
    return GateOutcome(
        task_id=ledger.task_id,
        goal=ledger.goal,
        decision=decision,
        holds=holds,
        base_ref=base,
        tip_ref=tip,
        changed_files=files,
        out_of_scope=out_of_scope + out_of_allowlist,
        sensitive=sensitive,
        acceptance_failed=acceptance_failed,
        tests_passed=tests_passed,
        gitleaks=gl.status,
        scanner_advisory=advisory,
    )


def _run_tests(repo: str, cmd: str, timeout: int = 1800) -> bool:
    try:
        proc = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


# ----------------------------------------------------------------- propose (PR)
def open_pr(
    ledger: Ledger,
    outcome: GateOutcome,
    branch: str,
    *,
    base: str = "master",
    repo_slug: str | None = None,
    draft: bool = True,
    runner: Callable[[list[str]], str] = lambda argv: _default_pr_runner(argv),
) -> str:
    """Propose the unit by opening a PR (``base`` ← ``branch``). NEVER merges.
    The PR command is built here; ``runner`` actually invokes it (injected in
    tests). Returns the runner's output (typically the PR URL gh prints)."""
    if outcome.decision != "propose":
        raise LandError(f"refusing to open a PR for a held unit (decision={outcome.decision})")
    argv = [
        "gh", "pr", "create",
        "--base", base,
        "--head", branch,
        "--title", f"land: {ledger.goal}",
        "--body", _pr_body(outcome),
    ]
    if draft:
        argv.append("--draft")
    if repo_slug:
        argv += ["--repo", repo_slug]
    return runner(argv)


def _pr_body(outcome: GateOutcome) -> str:
    lines = [
        "Proposed by `charon land` (propose-default; not auto-merged).",
        "",
        f"- task: `{outcome.task_id}`",
        f"- base..tip: `{outcome.base_ref[:12]}..{outcome.tip_ref[:12]}`",
        f"- changed files: {outcome.changed_files}",
        f"- gitleaks: {outcome.gitleaks}",
    ]
    if outcome.scanner_advisory:
        lines.append("")
        lines.append("Advisory scanners (never blocking in propose-mode):")
        for s in outcome.scanner_advisory:
            note = f" — {s['note']}" if s.get("note") else ""
            lines.append(f"  - {s['name']} ({s['tier']}): {s['status']}{note}")
    lines.extend([
        "",
        "Gate is green; a human merge is the only thing that lands this.",
    ])
    return "\n".join(lines)


def _default_pr_runner(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise LandError(f"`{' '.join(argv[:3])} …` failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# ------------------------------------------------------- consumer-supplied units
# D3: a unit is {goal, accept, tier, owned_paths}. Until auto-decomposition ships
# (its own ADR) the unit list is consumer-supplied — a TOML/JSON file fed to the
# existing run path. tier/owned_paths are carried for the land gate; the run loop
# itself only needs goal + accept (+ optional autonomy/decompose).
_RUNNABLE_KEYS = {"goal", "accept", "tier", "owned_paths", "autonomy", "decompose"}


def load_units(path: str) -> list[dict]:
    """Load a consumer-supplied unit list from a TOML or JSON file. Accepts either
    a top-level array (JSON) / ``[[units]]`` array-of-tables (TOML) or an object
    with a ``units`` key. Validates each unit has a non-empty ``goal`` and a
    non-empty ``accept`` list; ``tier``/``owned_paths``/``autonomy``/``decompose``
    are optional. Raises ``ValueError`` (loud) on anything malformed."""
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"units file not found: {path}")
    text = p.read_text(encoding="utf-8")
    data = _parse_units_text(text, p.suffix.lower())

    if isinstance(data, dict):
        raw = data.get("units")
    else:
        raw = data
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            f"units file {path!r} must hold a non-empty list of units "
            "(a top-level array, or a 'units' array/table)"
        )

    units: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"unit #{i} is not a table/object: {item!r}")
        goal = item.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError(f"unit #{i} is missing a non-empty 'goal'")
        accept = item.get("accept")
        if not isinstance(accept, list) or not accept or not all(
            isinstance(a, str) and a.strip() for a in accept
        ):
            raise ValueError(f"unit #{i} ({goal!r}) needs a non-empty 'accept' list of commands")
        owned = item.get("owned_paths", [])
        if not isinstance(owned, list) or not all(isinstance(o, str) for o in owned):
            raise ValueError(f"unit #{i} ({goal!r}) 'owned_paths' must be a list of strings")
        unit: dict = {"goal": goal, "accept": list(accept), "owned_paths": list(owned)}
        if "tier" in item:
            unit["tier"] = item["tier"]
        if "autonomy" in item:
            unit["autonomy"] = item["autonomy"]
        if item.get("decompose"):
            unit["decompose"] = True
        units.append(unit)
    return units


def _parse_units_text(text: str, suffix: str):
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        import tomllib
        return tomllib.loads(text)
    # unknown suffix: try TOML first (the documented default), fall back to JSON.
    import tomllib
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return json.loads(text)


def units_to_run(unit_dicts: Sequence[dict]):
    """Map consumer-supplied unit dicts onto the existing ``parallel.Unit`` the
    run path consumes. ``tier``/``owned_paths`` are NOT run inputs (the mock/ACP
    run loop does not consume them) — they are carried in the file for the land
    gate; only ``goal``/``accept``/``autonomy``/``decompose`` reach ``Unit``."""
    from .parallel import Unit
    units = []
    for d in unit_dicts:
        units.append(
            Unit(
                goal=d["goal"],
                accept=list(d["accept"]),
                autonomy=str(d.get("autonomy", "L0")),
                decompose=bool(d.get("decompose", False)),
            )
        )
    return units


def owned_from_units(path: str, goal: str) -> list[str]:
    """Pull the declared ``owned_paths`` for the unit whose ``goal`` matches, from
    a consumer-supplied units file — the convenience that lets ``charon land``
    scope a unit by reusing the same file that drove the run."""
    for unit in load_units(path):
        if unit["goal"] == goal:
            return list(unit.get("owned_paths", []))
    return []


def acceptance_from(accept: Sequence[str]) -> list[AcceptanceCheck]:
    """Helper mirroring the run path's id scheme, for callers that build checks
    from a raw command list."""
    return [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(accept)]


# ===================================================================== auto-land
# ADR-0012 — the opt-in, batch-atomic auto-land path layered ON TOP of the
# propose-default gate above. NEVER the default: off unless the engine-owned
# config explicitly enables it, and fail-closed in every ambiguous branch.

@dataclass(frozen=True)
class AutoLandResult:
    """Verdict for one auto-land batch (ADR-0012). ``landed`` is True only when the
    base branch was actually fast-forwarded; otherwise the batch HELD and NOTHING
    was merged (batch-atomic — never partial)."""

    decision: str  # "auto-landed" | "hold"
    landed: bool
    holds: list[str] = field(default_factory=list)
    outcomes: list[GateOutcome] = field(default_factory=list)
    base_ref: str = ""
    integrated_ref: str = ""
    landed_ref: str = ""

    @property
    def held(self) -> bool:
        return not self.landed

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "landed": self.landed,
            "holds": self.holds,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "base_ref": self.base_ref,
            "integrated_ref": self.integrated_ref,
            "landed_ref": self.landed_ref,
        }


def _git_ok(repo: str, *args: str, timeout: int = 120) -> str:
    proc = _git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        raise LandError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _ff_update_ref(repo: str, branch: str, new_ref: str, expected_old: str) -> None:
    """Compare-and-swap the base branch to ``new_ref`` — succeeds only if the
    branch still points at ``expected_old`` (atomic; rejects a concurrently-moved
    branch, fail-closed). ``base`` must be an ancestor of ``new_ref``, so this only
    ever fast-forwards, never rewrites history."""
    _git_ok(repo, "update-ref", f"refs/heads/{branch}", new_ref, expected_old)


def auto_land_batch(
    units: Sequence[tuple[Ledger, Sequence[str]]],
    cfg: AutoLandConfig,
    *,
    tests_cmd: str | None = None,
    run_acceptance: bool = True,
    gitleaks_runner: Callable[[str], GitleaksResult] = run_gitleaks,
    scanner_runner: Callable[[str, list[str]], list[dict]] = _required_scanner_runner,
) -> AutoLandResult:
    """Evaluate + (only if fully green) atomically land one decomposition.

    A *batch* is a list of ``(ledger, owned_paths)`` units cut from ONE shared
    base. The contract (ADR-0012):
      - **Opt-in:** if ``cfg.enabled`` is False the batch HOLDS and NO git mutation
        happens — the default is always propose.
      - **Per-unit strict gate:** every unit is gated with the auto-land posture
        (allowlist + extra-sensitive + scanners-required + gitleaks-expected). If
        ANY unit holds, the batch lands NOTHING (batch-atomic).
      - **Integrated gate ONCE:** the unit tips are merged on a throwaway worktree
        off base, the integrated tip is re-checked (scope/allowlist/sensitive +
        gitleaks), and only a green integration fast-forwards the base branch in a
        single CAS update-ref. Any conflict / mismatch / ambiguity → discard, HOLD.

    Read-only on every HOLD path; the ONLY mutation is the final fast-forward of
    ``cfg.base_branch`` when everything is green."""
    holds: list[str] = []

    # Master switch (ADR-0012 D1). Off → propose-default, never touch git.
    if not cfg.enabled:
        return AutoLandResult(
            decision="hold", landed=False,
            holds=["auto-land disabled (opt-in OFF) — propose-default"],
        )
    if not cfg.allowlist:
        # An armed-but-empty allowlist can land nothing; say so loudly rather than
        # silently holding every file one-by-one.
        holds.append("auto-land enabled but allowlist is empty (fail-closed)")
    if not units:
        return AutoLandResult(decision="hold", landed=False,
                              holds=holds + ["empty batch — nothing to land"])

    # One batch == one decomposition off ONE base in ONE repo. A mismatch means the
    # caller mixed floors/repos — fail closed rather than guess.
    repo = units[0][0].target_repo
    base = units[0][0].base_ref
    for led, _owned in units:
        if led.target_repo != repo:
            holds.append(f"batch spans repos ({led.target_repo} != {repo})")
        if led.base_ref != base:
            holds.append(f"batch spans bases ({led.base_ref[:12]} != {base[:12]})")

    # Per-unit strict gate, each in its OWN sandbox worktree checked out at the
    # unit's tip (ADR-0012 D5) — acceptance + tests therefore run against the unit's
    # proposed code, isolated from the live checkout, never executed in-place.
    outcomes: list[GateOutcome] = []
    for led, owned in units:
        outcome = _gate_unit_sandboxed(
            repo, led, owned,
            tests_cmd=tests_cmd, run_acceptance=run_acceptance,
            gitleaks_runner=gitleaks_runner, scanner_runner=scanner_runner,
            cfg=cfg,
        )
        outcomes.append(outcome)
        if outcome.decision != "propose":
            holds.append(f"unit {led.task_id} held: {outcome.holds}")

    # ANY hold → land NOTHING (batch-atomic). No git mutation has happened yet.
    if holds:
        return AutoLandResult(decision="hold", landed=False, holds=holds,
                              outcomes=outcomes, base_ref=base)

    tips = [led.lkg_ref for led, _ in units]
    integrated_ref, landed_ref, integ_holds = _integrate_and_land(
        repo, base, tips, cfg, gitleaks_runner,
    )
    if integ_holds:
        return AutoLandResult(decision="hold", landed=False, holds=integ_holds,
                              outcomes=outcomes, base_ref=base,
                              integrated_ref=integrated_ref)
    return AutoLandResult(
        decision="auto-landed", landed=True, holds=[], outcomes=outcomes,
        base_ref=base, integrated_ref=integrated_ref, landed_ref=landed_ref,
    )


def _gate_unit_sandboxed(
    repo: str,
    led: Ledger,
    owned: Sequence[str],
    *,
    tests_cmd: str | None,
    run_acceptance: bool,
    gitleaks_runner: Callable[[str], GitleaksResult],
    scanner_runner: Callable[[str, list[str]], list[dict]],
    cfg: AutoLandConfig,
) -> GateOutcome:
    """Run the strict auto-land gate for one unit inside a disposable worktree
    checked out at the unit's tip (D5 sandbox). If the sandbox cannot be staged,
    fail closed with a synthetic HOLD outcome — never fall back to the live tree."""
    sandbox = tempfile.mkdtemp(prefix="charon-unit-")
    try:
        try:
            _git_ok(repo, "worktree", "add", "--detach", sandbox, led.lkg_ref)
        except LandError as exc:
            return GateOutcome(
                task_id=led.task_id, goal=led.goal, decision="hold",
                holds=[f"could not stage unit sandbox (fail-closed): {exc}"],
                base_ref=led.base_ref, tip_ref=led.lkg_ref,
            )
        sandboxed = replace(led, target_repo=sandbox)
        return land_unit(
            sandboxed, owned,
            tests_cmd=tests_cmd,
            run_acceptance=run_acceptance,
            gitleaks_expected=True,
            gitleaks_runner=gitleaks_runner,
            scanner_runner=scanner_runner,
            allowlist=cfg.allowlist,
            extra_sensitive=cfg.extra_sensitive,
            scanners_required=True,
        )
    finally:
        _git(repo, "worktree", "remove", "--force", sandbox)
        _git(repo, "worktree", "prune")
        shutil.rmtree(sandbox, ignore_errors=True)


def _integrate_and_land(
    repo: str,
    base: str,
    tips: Sequence[str],
    cfg: AutoLandConfig,
    gitleaks_runner: Callable[[str], GitleaksResult],
) -> tuple[str, str, list[str]]:
    """Merge ``tips`` onto a disposable integration worktree off ``base``, gate the
    integrated tip ONCE, and fast-forward ``cfg.base_branch`` iff green. Returns
    ``(integrated_ref, landed_ref, holds)``; a non-empty ``holds`` means the
    integration was discarded and the base branch is untouched (land NOTHING)."""
    workdir = tempfile.mkdtemp(prefix="charon-autoland-")
    integrated_ref = ""
    try:
        # Disposable worktree off base — never the live checkout (D2). Detached so
        # the fast-forward of the real branch is the only ref we ever move.
        try:
            _git_ok(repo, "worktree", "add", "--detach", workdir, base)
        except LandError as exc:
            return "", "", [f"could not stage integration worktree: {exc}"]

        for tip in tips:
            proc = _git(workdir, "merge", "--no-ff", "--no-edit", tip)
            if proc.returncode != 0:
                _git(workdir, "merge", "--abort")
                return "", "", [
                    f"integration conflict merging {tip[:12]} — batch lands nothing"
                ]
        integrated_ref = _git_ok(workdir, "rev-parse", "HEAD")

        # Gate ONCE on the integrated tip (per-unit green != integrated green).
        integ_files = changed_files(repo, base, integrated_ref)
        bad_scope = [f for f in integ_files if not in_scope(f, cfg.allowlist)]
        bad_sensitive = [
            f for f in integ_files
            if is_sensitive(f) is not None or matches_prefix(f, cfg.extra_sensitive)
        ]
        gl = gitleaks_runner(workdir)
        holds: list[str] = []
        if bad_scope:
            holds.append(f"integrated diff escapes allowlist: {bad_scope}")
        if bad_sensitive:
            holds.append(f"integrated diff touches sensitive paths: {bad_sensitive}")
        if gl.status == "leaks":
            holds.append("gitleaks detected secrets in integrated tip")
        elif gl.status == "unavailable":
            holds.append("gitleaks unavailable on integrated tip (fail-closed)")
        if holds:
            return integrated_ref, "", holds

        # All green → the ONE mutation: CAS fast-forward of the base branch.
        try:
            _ff_update_ref(repo, cfg.base_branch, integrated_ref, base)
        except LandError as exc:
            return integrated_ref, "", [
                f"base branch {cfg.base_branch!r} moved or unavailable; "
                f"refusing non-atomic land ({exc})"
            ]
        return integrated_ref, integrated_ref, []
    finally:
        _git(repo, "worktree", "remove", "--force", workdir)
        _git(repo, "worktree", "prune")
        shutil.rmtree(workdir, ignore_errors=True)

#!/usr/bin/env python3
"""substrate_first_gate.py — the RULE ENGINE behind fleet/checks/substrate-first-gate.sh.

=============================== WHY THIS IS PYTHON ==============================
v1 of this gate hand-rolled ~285 lines of sed/case/awk frontmatter and markdown-table
parsing under a ~30-line EVAL-REGISTRY cross-check. An adversarial review found NINE
working evasions; every parser-class one (unrecognised-alignment defaulting to "aligned",
prefix tool matching, escaped-pipe field shift, CRLF skip, trailing-space skip) lived in
the hand-rolled 285 lines, and ZERO findings landed against the 30-line cross-check.

That is doctrine [[adopt-substrate-build-only-novel-slice]] playing out literally: the
hand-rolled commodity part is where the defects were. So the parser is now PyYAML (a real
YAML parser, pinned) and the markdown-table reader is a fence-aware, escape-aware,
field-count-checked Python routine. The registry cross-check — the genuinely novel slice —
is preserved, and hardened.

The stdlib-only-no-dependencies constraint belongs to the PRODUCT's privileged core
(code/charon, `pyproject.toml` `dependencies = []`). It does NOT apply to this rig, which
runs on ubuntu-latest with network and a Python toolchain. v1's EVAL-REGISTRY row asserted
otherwise; that row is corrected in fleet/state/EVAL-REGISTRY.md.

================================= FAIL CLOSED ===================================
Every unknown is a RED. Unparseable frontmatter, an unreadable registry, a malformed
registry row, an unrecognised alignment class, a missing difficulty, an unresolvable
evidence link — all RED. Nothing in this file may exit 0 on "I could not tell".

============================ REENTRANCY [[fleet-selfcheck-forkbomb-class]] ======
This module invokes NO gate, no preflight, no land script, no gh. The only subprocess it
runs is `git` (read-only: rev-parse / merge-base / diff), which cannot re-trigger CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:  # FAIL CLOSED — a missing parser is not a pass.
    sys.stderr.write(
        "substrate-gate: PyYAML is REQUIRED and is not importable. This gate refuses to\n"
        "run without a real YAML parser (fail-closed). Install it: pip install 'PyYAML==6.0.3'\n"
    )
    sys.exit(1)

# ------------------------------------------------------------------ policy tables
# work_class -> is a `substrate:` answer required?
ALWAYS = {
    "money-path", "routing", "ci-infra", "refactor",
    "greenfield-feature", "frontend", "rig-meta", "generalist",
}
BY_DIFFICULTY = {"bugfix", "tests"}
EXEMPT = {"docs", "design-review"}

# An `owns:` entry with one of these extensions, or under one of these roots, is CODE.
# A work_class claiming to dispatch no implementation may not own any of it (S7/B2).
CODE_EXT = (
    ".py", ".sh", ".bash", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb",
    ".java", ".c", ".h", ".cpp", ".sql", ".yml", ".yaml", ".toml",
)
CODE_ROOTS = ("src/", "fleet/checks/", "fleet/hooks/", "fleet/tests/", "tools/", "tests/", ".github/")

# Alignment classes the registry schema defines. ANYTHING ELSE IS MALFORMED, never "aligned".
ALIGNMENTS = ("aligned", "drifted", "mixed", "n-a")
SEVERITY = {"drifted": 3, "mixed": 2, "n-a": 1, "aligned": 0}

# Placeholder evidence cells that do NOT constitute a citation (S3).
EVIDENCE_PLACEHOLDERS = {"", "-", "--", "—", "–", "none", "n/a", "na", "tbd", "todo", "x", "?"}

# Frontmatter ends at the first markdown heading / horizontal rule / raw HTML-ish tag.
_HALT = re.compile(r"^(#{1,6}\s|---\s*$|</?[A-Za-z][\w-]*\s*/?>)")
# Split a markdown table row on pipes that are NOT backslash-escaped (kills the F1 field shift).
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SEP_CELL = re.compile(r"^:?-{2,}:?$")


class TicketError(Exception):
    """Raised when a ticket cannot be parsed. ALWAYS surfaces as a RED, never a skip."""


# ------------------------------------------------------------------ ticket parsing
def read_frontmatter(path: str) -> dict:
    """Parse a board ticket's frontmatter with a REAL YAML parser. Fail closed.

    S5: CRLF and lone-CR line endings are normalised BEFORE parsing, and trailing
    whitespace can no longer leak into a field value, so a Windows-saved ticket can no
    longer make the gate skip. A ticket that still does not parse is a RED, never a skip.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            raw = fh.read()
    except OSError as exc:
        raise TicketError(f"ticket file is unreadable ({exc.strerror}) — cannot verify (fail-closed)")
    except UnicodeDecodeError as exc:
        raise TicketError(f"ticket file is not valid UTF-8 ({exc}) — cannot verify (fail-closed)")

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    head = []
    for line in text.split("\n"):
        if _HALT.match(line):
            break
        head.append(line)
    try:
        data = yaml.safe_load("\n".join(head))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        raise TicketError(
            f"frontmatter does not parse as YAML{where}: {getattr(exc, 'problem', exc)}. "
            "A ticket the gate cannot parse is a RED, never a silent skip — quote the value or "
            "make it a block scalar (`key: |`)."
        )
    if data is None:
        raise TicketError("frontmatter is EMPTY — a ticket with no fields cannot be verified (fail-closed)")
    if not isinstance(data, dict):
        raise TicketError(
            f"frontmatter parsed as {type(data).__name__}, not a key/value mapping (fail-closed)"
        )
    return data


def field(fm: dict, key: str) -> str:
    """A frontmatter value as a trimmed string. Absent -> ''. Present-but-null -> ''."""
    if key not in fm:
        return ""
    val = fm[key]
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val).strip()


def has_field(fm: dict, key: str) -> bool:
    return key in fm


def is_parked(fm: dict) -> bool:
    """S8: parked is a REAL FIELD, never a substring.

    v1 skipped any ticket that had a `note:` field and the word PARKED anywhere in the
    file — so `note: active work, do not park` plus an unrelated line mentioning a PARKED
    sibling ticket skipped the gate entirely. Only an explicit boolean field parks a ticket.
    """
    for key in ("parked", "status"):
        val = field(fm, key).lower()
        if key == "parked" and val in ("true", "yes", "1"):
            return True
        if key == "status" and val == "parked":
            return True
    return False


# ------------------------------------------------------------- EVAL-REGISTRY reader
class Row:
    __slots__ = ("tool", "align", "reason", "evidence", "lineno", "raw", "malformed")

    def __init__(self, tool, align, reason, evidence, lineno, raw, malformed=""):
        self.tool = tool
        self.align = align
        self.reason = reason
        self.evidence = evidence
        self.lineno = lineno
        self.raw = raw
        self.malformed = malformed


def _clean(cell: str) -> str:
    return cell.replace("*", "").replace("`", "").replace("\\|", "|").strip()


def parse_registry(path: str) -> list[Row]:
    """Read EVAL-REGISTRY.md's table into rows. Fence-aware, escape-aware, field-counted.

    Every defect S1 exposed is closed structurally here rather than by an awk patch:
      * lines inside a ``` / ~~~ fence are NOT rows (D4);
      * the header row and the |---| separator row are recognised and dropped (G3);
      * a row is split on UNESCAPED pipes only, so `Vendored\\|Copy` no longer shifts the
        alignment column by one and launders a drifted row (F1);
      * a row whose cell count is not exactly 8 is MALFORMED, not silently short-read (G2);
      * an alignment cell that is not one of aligned/drifted/mixed/n-a is MALFORMED (G1).
    A MALFORMED row that a ticket cites is a hard RED. It is never treated as "aligned".
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    rows: list[Row] = []
    in_fence = False
    for lineno, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not line.lstrip().startswith("|"):
            continue
        parts = _UNESCAPED_PIPE.split(line.strip())
        # a well-formed row is `| a | b | ... |` -> leading and trailing empties
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
        cells = [_clean(c) for c in parts]
        if not cells:
            continue
        if all(_SEP_CELL.match(c) for c in cells if c != ""):
            continue  # |---|---| separator
        if len(cells) >= 5 and cells[0].lower() == "tool" and cells[4].lower() == "alignment":
            continue  # the schema header row — matched as data by v1, which is S1's entry point
        raw = line.strip()
        if len(cells) != 8:
            rows.append(Row(cells[0].lower(), "", "", "", lineno, raw,
                            malformed=f"has {len(cells)} cells, the schema requires 8"))
            continue
        tool, _scope, _date, _verdict, align_cell, reason, evidence, _sup = cells
        cls = re.split(r"[\s(/]", align_cell.strip().lower(), maxsplit=1)[0]
        if cls not in ALIGNMENTS:
            rows.append(Row(tool.lower(), "", reason, evidence, lineno, raw,
                            malformed=f"alignment cell {align_cell!r} is not one of "
                                      f"{'/'.join(ALIGNMENTS)}"))
            continue
        rows.append(Row(tool.lower(), cls, reason, evidence, lineno, raw))
    return rows


def match_rows(rows: list[Row], want: str) -> list[Row]:
    """S2: EXACT tool-name match, case-insensitive. Never a prefix.

    v1 accepted `index(cell, want) == 1`, i.e. any prefix — so `substrate: Feath` resolved
    to Featherless's ALIGNED row and `substrate: check` to check-jsonschema's, with no
    existence check whatsoever. Any short made-up token was "settled substrate".
    A registry cell may legitimately name several tools (`a / b / c`); those alternatives
    are split and each must match EXACTLY.
    """
    needle = want.strip().lower()
    if not needle:
        return []
    out = []
    for row in rows:
        names = [n.strip() for n in row.tool.split("/")] if "/" in row.tool else [row.tool.strip()]
        if needle in names or needle == row.tool.strip():
            out.append(row)
    return out


def evidence_resolves(cell: str, repo_root: str) -> tuple[bool, str]:
    """S3 mitigation: an `evidence-link` must actually cite something.

    A row whose evidence is `none` / `—` / `x` is a claim with no receipt — exactly the
    shape of the fabricated row the review appended in a single line. Accepted citation
    shapes: an http(s) URL, a `PR #N` reference, a commit sha, or a repo-relative path
    with an extension.

    Path VERIFICATION is deliberately conservative, and the reason is measured, not a
    preference: real rows legitimately cite `fleet/state/...` (gitignored — absent from any
    CI checkout) and `code/charon/docs/...` (the product repo — a different checkout).
    Demanding existence for those would RED honest rows in CI, which is how a gate gets
    disabled. So a path is only rejected when its TOP-LEVEL DIRECTORY exists in this
    checkout but the file itself does not — i.e. the citation is checkably wrong. Anything
    pointing outside this checkout is accepted unverified, and that is the residual gap.
    """
    text = cell.strip()
    if text.lower().strip("`") in EVIDENCE_PLACEHOLDERS:
        return False, "is a placeholder, not a citation"
    if re.search(r"https?://\S+", text):
        return True, ""
    if re.search(r"\bPR\s*#\d+\b", text, re.I) or re.search(r"\b[0-9a-f]{7,40}\b", text):
        return True, ""
    paths = [p.strip("`,;") for p in re.findall(r"[\w./-]+\.[A-Za-z0-9]{1,6}", text)]
    paths = [p for p in paths if "/" in p]
    if not paths:
        return False, "contains no path, URL, PR reference or commit sha"
    for p in paths:
        if os.path.exists(os.path.join(repo_root, p)):
            return True, ""
        top = p.split("/", 1)[0]
        if not os.path.isdir(os.path.join(repo_root, top)):
            return True, ""  # outside this checkout (e.g. the product repo) — unverifiable
        if _git_ignored(repo_root, p):
            return True, ""  # gitignored by design (fleet/state/…) — absent from every checkout
    return False, f"cites {paths[0]!r}, which does not exist in this checkout"


_IGNORE_CACHE: dict[str, bool] = {}


def _git_ignored(root: str, path: str) -> bool:
    """True when `path` is gitignored, i.e. legitimately absent from a fresh checkout.

    Asked of git rather than pattern-matched here, so the answer can never drift from
    .gitignore. Unknown (no git, no repo) is treated as ignored — the placeholder rule
    above is what carries the S3 weight; path existence is a bonus, not the control.
    """
    key = root + "\0" + path
    if key not in _IGNORE_CACHE:
        try:
            res = subprocess.run(["git", "-C", root, "check-ignore", "-q", "--no-index", path],
                                 capture_output=True, timeout=15)
            _IGNORE_CACHE[key] = res.returncode != 1
        except (OSError, subprocess.SubprocessError):
            _IGNORE_CACHE[key] = True
    return _IGNORE_CACHE[key]


# --------------------------------------------------------------------- git helpers
def _git(root: str, *args: str) -> str | None:
    try:
        res = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


def diff_range(root: str) -> tuple[str, str] | None:
    """Resolve the PR range from RIG_CI_BASE/RIG_CI_HEAD. None when there is no range."""
    base, head = os.environ.get("RIG_CI_BASE"), os.environ.get("RIG_CI_HEAD", "HEAD")
    if not base:
        return None
    b = _git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}")
    h = _git(root, "rev-parse", "--verify", "--quiet", head + "^{commit}")
    if not b or not h:
        return None
    mb = _git(root, "merge-base", b.strip(), h.strip())
    return ((mb or b).strip(), h.strip())


def registry_rows_added_in_range(root: str, rel_registry: str) -> set[str]:
    """The registry row TEXT added between base..head, for the S3 same-PR provenance check."""
    rng = diff_range(root)
    if not rng:
        return set()
    out = _git(root, "diff", "-U0", f"{rng[0]}..{rng[1]}", "--", rel_registry)
    if not out:
        return set()
    return {ln[1:].strip() for ln in out.split("\n") if ln.startswith("+") and not ln.startswith("+++")}


def changed_files(root: str) -> list[str] | None:
    rng = diff_range(root)
    if not rng:
        return None
    out = _git(root, "diff", "--name-only", f"{rng[0]}..{rng[1]}")
    return [f for f in (out or "").split("\n") if f.strip()]


# --------------------------------------------------------------- reason substance
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")


def substance(text: str) -> str:
    """S6: a reason must be PROSE, not padding. '' when acceptable, else why not.

    v1's only test was `len >= 40`, which 48 `x` characters and 50 `a` characters both
    satisfy — the review passed the gate with literally both. Length alone cannot
    distinguish an argument from filler, so this measures vocabulary instead: distinct
    words and distinct characters. It still cannot judge whether the reason is TRUE
    (that is an adversarial-review job, stated in the header), only that it is an attempt.
    """
    text = text.strip()
    if len(text) < 60:
        return f"is {len(text)} chars — too thin to be a reason (need >=60)"
    words = _WORD.findall(text.lower())
    distinct = set(words)
    if len(words) < 10:
        return f"is {len(words)} words — too thin to be a reason (need >=10)"
    if len(distinct) < 8:
        return f"uses only {len(distinct)} distinct word(s) — that is padding, not an argument"
    if len(set(text.replace(" ", ""))) < 15:
        return "uses fewer than 15 distinct characters — that is filler, not an argument"
    return ""


# ------------------------------------------------------------------ the rule engine
class Gate:
    def __init__(self, registry: str, root: str, advisory: bool = False):
        self.registry = registry
        self.root = root
        self.advisory = advisory
        self.red_rc = 0
        self.out: list[str] = []
        self._rows: list[Row] | None = None
        self._added: set[str] | None = None

    def red(self, msg: str) -> None:
        if self.advisory:
            self.out.append(f"  SUBSTRATE-ADVISORY {msg}")
        else:
            self.out.append(f"  RED  substrate: {msg}")
            self.red_rc = 1

    def info(self, msg: str) -> None:
        self.out.append(f"  INFO substrate: {msg}")

    def _reg_label(self) -> str:
        rel = os.path.relpath(self.registry, self.root)
        return self.registry if rel.startswith("..") else rel

    def rows(self) -> list[Row]:
        if self._rows is None:
            self._rows = parse_registry(self.registry)
        return self._rows

    def added_rows(self) -> set[str]:
        if self._added is None:
            rel = os.path.relpath(self.registry, self.root)
            self._added = registry_rows_added_in_range(self.root, rel)
        return self._added

    # ---------------------------------------------------------------- per ticket
    def check_ticket(self, path: str, name: str) -> None:
        try:
            fm = read_frontmatter(path)
        except TicketError as exc:
            self.red(f"{name}: {exc}")
            return

        if is_parked(fm):
            self.info(f"skip {name} (parked — `parked: true` field, staged not live)")
            return

        wc = field(fm, "work_class").lower()
        raw_diff = field(fm, "difficulty")
        owns = field(fm, "owns")

        # S7/B2 — an EXEMPT class may not own code. `work_class: docs` owning
        # src/charon/whole_new_subsystem.py is the class declaration lying about the diff.
        if wc in EXEMPT:
            code = [p for p in _owns_entries(owns) if _is_code(p)]
            if code:
                self.red(
                    f"{name}: work_class '{wc}' is exempt because it dispatches no implementation, but "
                    f"'owns:' names CODE: {', '.join(code[:3])}. Either the class is wrong or the owns "
                    f"list is — an exempt class cannot own the files it claims not to write."
                )
                return
            self.info(f"skip {name} (work_class '{wc}' dispatches no implementation, owns no code)")
            return

        # S7/B4 — a MISSING difficulty must never mean "low". Omitting the field was
        # easier than lying about it, and v1's `-n "$diff"` guard rewarded exactly that.
        difficulty = None
        if raw_diff:
            m = re.match(r"^\s*(\d+)", raw_diff)
            if m:
                difficulty = int(m.group(1))
        if difficulty is None:
            self.red(
                f"{name}: work_class '{wc or '(missing)'}' requires a numeric 'difficulty:' and the "
                f"ticket has {'none' if not raw_diff else repr(raw_diff)}. A missing difficulty is NOT "
                f"'low' — it is an unanswered question, and unanswered is RED."
            )
            return

        required = wc in ALWAYS or not wc
        if wc in BY_DIFFICULTY and difficulty >= 3:
            required = True
        if not required:
            self.info(f"skip {name} (work_class '{wc}' difficulty {difficulty} below the code-writing bar)")
            return

        if not has_field(fm, "substrate"):
            self.red(
                f"{name}: work_class '{wc}' writes non-trivial new code but the ticket carries NO "
                "'substrate:' field.\n"
                "       State what ESTABLISHED EXTERNAL tool/library covers this and why NOT adopt it, "
                "before any build\n"
                "       option is chosen [[adopt-substrate-build-only-novel-slice]]. Shapes:\n"
                "         substrate: <tool-name> — <adopt|wrap-as-plugin|reject> — <why>\n"
                "         substrate: N/A         — plus a 'substrate-novel:' field stating why this is "
                "the novel slice"
            )
            return

        val = field(fm, "substrate")
        if not val:
            self.red(f"{name}: 'substrate:' is EMPTY. An empty field is not an answer — it is the question skipped.")
            return

        tool, reason = _split_answer(val)

        if tool.lower() in ("n/a", "na", "none", "n-a"):
            self._check_na(fm, name)
            return

        if not tool:
            self.red(f"{name}: 'substrate: {val}' names no tool before the separator — nothing was consulted.")
            return

        # ---- ANTI-REFRAME: the named candidate must be EXTERNAL -----------------
        # S9 (false positive in v1): `*/*` rejected every npm scoped package and every
        # org/repo reference, while a genuinely in-tree dotted module (charon.foo) sailed
        # through. The shape was backwards. Match in-tree ROOTS and extensions instead.
        why = _in_tree_reason(tool)
        if why:
            self.red(
                f"{name}: 'substrate: {tool}' names an IN-TREE module/path, not external substrate ({why}).\n"
                "       That is a BUILD option wearing the field's name — the exact reframe this gate exists "
                "to catch.\n"
                "       Name a real established third-party tool/library, or use 'substrate: N/A' + "
                "'substrate-novel:'."
            )
            return
        # OWNS-COLLISION — catch a ticket citing a NEW IN-TREE FILE IT IS ABOUT TO WRITE as the
        # substrate that makes writing it unnecessary (self-citation). This is SUPERSEDED by a valid
        # EXACT EVAL-REGISTRY match: a tool with a real registry row is a proven, externally-consulted
        # tool, NOT a file-being-written — even when the wrapper it owns is NAMED AFTER it
        # (`substrate: Semgrep` + `owns: fleet/checks/semgrep.sh`, where "semgrep" ⊂ "semgrep.sh").
        # match_rows() demands the name EXACTLY equal a registry row, so the overlap can only be a
        # coincidence of naming, never a way to launder an in-tree file into "settled substrate".
        # Therefore fire this ONLY when the tool has NO registry backing; the raw in-tree-PATH reframe
        # (`substrate: fleet/checks/foo.sh`) is caught above by _in_tree_reason and is unaffected. A
        # registry that cannot be read is treated as NO backing, so the collision still fires there and
        # the downstream _check_registry surfaces the fail-closed reason.
        try:
            registry_backed = bool(match_rows(self.rows(), tool))
        except OSError:
            registry_backed = False
        if not registry_backed:
            for entry in _owns_entries(owns):
                if tool.lower() in entry.lower():
                    self.red(
                        f"{name}: 'substrate: {tool}' appears in this ticket's own 'owns:' — a ticket cannot "
                        "cite the file\n       it is about to write as the substrate that makes writing it "
                        "unnecessary."
                    )
                    return

        problem = substance(reason)
        if problem:
            self.red(
                f"{name}: substrate reason {problem}. State the ADOPT/WRAP/REJECT verdict for "
                f"'{tool}' and the\n       specific reason it does or does not cover this work — not a label, "
                "not padding."
            )
            return

        self._check_registry(fm, name, tool)

    # ------------------------------------------------------------- the N/A path
    def _check_na(self, fm: dict, name: str) -> None:
        if not has_field(fm, "substrate-novel"):
            self.red(
                f"{name}: 'substrate: N/A' with no 'substrate-novel:' field. N/A is acceptable ONLY with a\n"
                "       stated reason this is genuinely the novel ~30%. Add: substrate-novel: <why nothing "
                "external covers this>"
            )
            return
        nov = field(fm, "substrate-novel")
        problem = substance(nov)
        if problem:
            self.red(
                f"{name}: 'substrate-novel:' {problem}.\n"
                "       Name the closest external tools and say what they specifically do NOT cover."
            )
            return
        self.info(f"{name}: N/A accepted (novel slice justified, {len(nov)} chars)")

    # -------------------------------------------------- the EVAL-REGISTRY consult
    def _check_registry(self, fm: dict, name: str, tool: str) -> None:
        if not os.access(self.registry, os.R_OK) or not os.path.isfile(self.registry):
            self.red(
                f"{name}: cites '{tool}' but EVAL-REGISTRY is unreadable at {self.registry} — the consult\n"
                "       cannot be verified, so this cannot be accepted (fail-closed)."
            )
            return
        try:
            rows = self.rows()
        except OSError as exc:
            self.red(f"{name}: EVAL-REGISTRY could not be read ({exc}) — fail-closed.")
            return

        matched = match_rows(rows, tool)
        if not matched:
            self.red(
                f"{name}: '{tool}' has NO row in {self._reg_label()}. The "
                "consult-first rule requires one.\n"
                "       Evaluate it and APPEND a row (| tool | scope | date | verdict | alignment | reason "
                "| evidence-link | supersedes |)\n"
                "       with alignment honestly classified AND a resolvable evidence-link, in a SEPARATE "
                "commit from this ticket."
            )
            return

        # S1 — a row the parser could not classify is a HARD RED. v1's awk printed
        # "aligned" whenever it could not classify, which made the `*)` arm unreachable
        # and turned the table's own HEADER ROW into a citable ALIGNED row.
        bad = [r for r in matched if r.malformed]
        if bad:
            self.red(
                f"{name}: '{tool}' matches a MALFORMED EVAL-REGISTRY row at line {bad[0].lineno} "
                f"({bad[0].malformed}).\n"
                "       An unparseable row is NOT an aligned row. Fix the row (escape stray pipes as \\| "
                "and use one of\n"
                f"       {'/'.join(ALIGNMENTS)}) before citing it."
            )
            return

        # S3 — evidence must actually cite something.
        for row in matched:
            ok, why = evidence_resolves(row.evidence, self.root)
            if not ok:
                self.red(
                    f"{name}: '{tool}' row at EVAL-REGISTRY line {row.lineno} has an evidence-link that {why}.\n"
                    "       A registry row with no receipt is an assertion, not an eval — it may not be cited.\n"
                    "       Point evidence-link at a real file, URL, PR or commit."
                )
                return
            problem = substance(row.reason)
            if problem:
                self.red(
                    f"{name}: '{tool}' row at EVAL-REGISTRY line {row.lineno} has a reason that {problem}.\n"
                    "       Boilerplate in the registry launders a hand-roll into 'settled'. Write the "
                    "real finding."
                )
                return

        # S3 — same-PR provenance. The strongest available mechanical control: a ticket
        # may not cite a registry row that the SAME PR added. Registry additions must land
        # separately, so a human sees the eval before anything depends on it.
        added = self.added_rows()
        if added:
            self_served = [r for r in matched if r.raw in added]
            if self_served:
                self.red(
                    f"{name}: '{tool}' cites EVAL-REGISTRY line {self_served[0].lineno}, which THIS SAME "
                    "change adds.\n"
                    "       The registry is not self-service: a row and the ticket that relies on it may not "
                    "land together,\n"
                    "       or the consult is the author asserting their own conclusion. Land the registry "
                    "row first."
                )
                return

        align = max((r.align for r in matched), key=lambda a: SEVERITY[a])
        if align == "aligned":
            self.info(f"{name}: '{tool}' has an ALIGNED EVAL-REGISTRY row — citable as settled.")
        elif align in ("drifted", "mixed"):
            if not has_field(fm, "substrate-retest"):
                self.red(
                    f"{name}: '{tool}' has a **{align}** EVAL-REGISTRY row, which MAY NOT be cited as "
                    "settled\n"
                    f"       (a {align} eval used a strawman / is partly unresolved). Re-test it against the "
                    "framing its\n"
                    "       'reason' column says was skipped, then add 'substrate-retest: <how>'."
                )
                return
            rt = field(fm, "substrate-retest")
            problem = substance(rt)
            if problem:
                self.red(
                    f"{name}: '{tool}' has a {align} EVAL-REGISTRY row and 'substrate-retest:' {problem}.\n"
                    "       State how this ticket re-tests the framing that row's 'reason' says was skipped."
                )
                return
            self.info(f"{name}: '{tool}' row is {align}, re-test stated ({len(rt)} chars) — accepted.")
        else:  # n-a
            self.red(
                f"{name}: '{tool}' EVAL-REGISTRY row is alignment 'n-a' — a tangential mention, NOT a "
                "verdict on\n"
                "       adopting it. It cannot be cited as settled. Run a real eval and append an aligned row."
            )


# --------------------------------------------------------------------- small helpers
def _owns_entries(owns: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,\n]", owns) if p.strip()]


def _is_code(path: str) -> bool:
    p = path.strip().lstrip("./")
    return p.endswith(CODE_EXT) or p.startswith(CODE_ROOTS)


def _in_tree_reason(tool: str) -> str:
    """Why this name is an in-tree build option rather than external substrate ('' if it is not).

    Deliberately NOT `*/*`: `@sinclair/typebox` and `org/repo` are real external names.
    """
    t = tool.strip().lstrip("./")
    if tool.strip().startswith(("/", "./", "../")):
        return "a filesystem path"
    if t.startswith(CODE_ROOTS) or t.startswith(("fleet/", "docs/", "scripts/", "benchmark/")):
        return "an in-tree directory"
    if t.endswith(CODE_EXT):
        return "a source filename"
    if re.match(r"^(charon|fleet|tools|tests)\.[A-Za-z_]", t):
        return "an in-tree dotted module"
    return ""


def _split_answer(val: str) -> tuple[str, str]:
    """Split `<name> — <verdict> — <reason>` on the first em/en dash or space-hyphen-space.

    A BARE hyphen must never split, or `pre-commit` becomes `pre` and `check-jsonschema`
    becomes `check` — which then matched nothing and produced a bogus RED for a registered
    tool (v1 case G8, kept pinned).
    """
    m = re.search(r"\s*(—|–|\s-\s)\s*", val)
    if not m:
        return val.strip(), ""
    return val[: m.start()].strip(), val[m.end():].strip()


# --------------------------------------------------------------------------- commands
def _iter(paths):
    for p in paths:
        yield p, os.path.basename(p)[:-3] if p.endswith(".md") else os.path.basename(p)


def cmd_check(gate: Gate, paths: list[str]) -> int:
    for p, n in _iter(paths):
        gate.check_ticket(p, n)
    print("\n".join(gate.out))
    return gate.red_rc


def cmd_scan(gate: Gate, board: str) -> int:
    gate.advisory = True
    for p, n in _iter(sorted(_board_files(board))):
        gate.check_ticket(p, n)
    print("\n".join(gate.out))
    return 0


def cmd_retrofit(gate: Gate, board: str) -> int:
    n = 0
    for p, name in _iter(sorted(_board_files(board))):
        gate.out, gate.red_rc = [], 0
        gate.check_ticket(p, name)
        if gate.red_rc:
            n += 1
            print("\n".join(gate.out))
    print(f"retrofit: {n} live ticket(s) would FAIL the substrate-first gate (report only — nothing edited)")
    return 0


def cmd_pr_has_ticket(gate: Gate) -> int:
    """S6 (partial): a change that touches CODE must carry a board ticket in the same range.

    This is the ONLY diff-aware assertion here, and it is deliberately narrow. It closes
    "land code with no ticket at all" — the cheapest S6 variant, where the gate simply never
    ran. It does NOT close "the ticket names a tool then hand-rolls anyway"; correlating a
    named tool to an actual dependency/import is a separate, larger mechanism. Stated as an
    open limit in the header rather than papered over.
    NOT a duplicate of the live WORK-GATE-UNIVERSAL ticket: that one specs decompose-sizing
    at LAUNCH (Gate A) and inert/unwired-code detection at DONE (Gate B). Neither asserts
    that a code change has a ticket at all. Verified by reading fleet/board/WORK-GATE-UNIVERSAL.md.
    """
    files = changed_files(gate.root)
    if files is None:
        print("  INFO substrate: pr-has-ticket: no diff range resolvable (RIG_CI_BASE unset) — not applicable")
        return 0
    code = [f for f in files if _is_code(f) and not f.startswith("fleet/board/")]
    if not code:
        print("  INFO substrate: pr-has-ticket: change touches no code — nothing to associate")
        return 0
    tickets = [f for f in files if f.startswith("fleet/board/") and f.endswith(".md")]
    if tickets:
        print(f"  INFO substrate: pr-has-ticket: {len(code)} code file(s) associated with "
              f"{len(tickets)} board ticket(s)")
        return 0
    print("  RED  substrate: this change touches CODE "
          f"({', '.join(code[:4])}{'...' if len(code) > 4 else ''}) but changes NO fleet/board/*.md ticket.\n"
          "       Code with no ticket is code the substrate-first question was never asked about "
          "[[adopt-substrate-build-only-novel-slice]].\n"
          "       Add or update the board ticket that owns these files.")
    return 1


def _board_files(board: str) -> list[str]:
    try:
        return [os.path.join(board, f) for f in os.listdir(board) if f.endswith(".md")]
    except OSError:
        return []


USAGE = (
    "usage: substrate_first_gate.py {check <ticket.md>...|scan [dir]|retrofit [dir]|pr-has-ticket}"
)


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    fleet = os.path.dirname(here)
    root = os.path.dirname(fleet)
    registry = os.environ.get("SUBSTRATE_REGISTRY") or os.path.join(fleet, "state", "EVAL-REGISTRY.md")
    gate = Gate(registry, root)

    if not argv:
        sys.stderr.write(USAGE + "\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        if not rest:
            sys.stderr.write("usage: substrate_first_gate.py check <ticket.md> ...\n")
            return 2
        return cmd_check(gate, rest)
    if cmd == "scan":
        return cmd_scan(gate, rest[0] if rest else os.path.join(fleet, "board"))
    if cmd == "retrofit":
        return cmd_retrofit(gate, rest[0] if rest else os.path.join(fleet, "board"))
    if cmd == "pr-has-ticket":
        return cmd_pr_has_ticket(gate)
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

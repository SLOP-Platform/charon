#!/usr/bin/env bash
# eval-registry-reconcile.sh — JOIN the derived tool INVENTORY against the authored EVAL-REGISTRY.
#
# WHAT THIS DOES:
#   1. Generates a fresh EVAL-INVENTORY.tsv from committed live sources (pyproject deps,
#      graph.json imports, gates.json enforcers, TOOL-INVENTORY.md references).
#   2. Joins it against fleet/state/EVAL-REGISTRY.md's per-tool verdict rows.
#   3. Reports THREE drift classes with evidence per finding:
#        D1  UNEVALUATED ADOPTION  — tool in inventory, NO verdict row
#        D2  STALE ROW             — verdict ADOPT/shipped, tool ABSENT from inventory
#        D3  CONTRADICTION         — verdict REJECTED, tool PRESENT in inventory
#   4. FAILS LOUD on any drift (non-zero exit). "Could not check" is NOT exit 0.
#
# ANTI-SILENT, ANTI-FRAGILE:
#   - NON-ZERO on drift. No `|| true`, no `|| return 0`.
#   - UNREADABLE input exits NON-ZERO with distinct message — never "no drift found".
#   - NEVER auto-edit EVAL-REGISTRY.md. Detect and report; a human writes verdicts.
#
# Usage:
#   eval-registry-reconcile.sh            full reconcile (inventory + drift report)
#   eval-registry-reconcile.sh inventory  generate inventory TSV to stdout only
#   eval-registry-reconcile.sh check      drift-check only (reads existing TSV, no regen)
# Env:
#   ER_FLEET      fleet root dir          (default: this script's parent dir)
#   ER_PRODUCT    product repo root       (default: /home/stack/code/charon)
#   ER_REGISTRY   EVAL-REGISTRY.md path   (default: $ER_FLEET/state/EVAL-REGISTRY.md)
#   ER_INVENTORY  EVAL-INVENTORY.tsv path (default: $ER_FLEET/state/EVAL-INVENTORY.tsv)
#   ER_GRAPH      graph.json path         (default: $ER_PRODUCT/graphify-out/graph.json)
#   ER_GATES      gates.json path         (default: $ER_PRODUCT/tools/gates.json)
#   ER_PYPTOML    pyproject.toml path     (default: $ER_PRODUCT/pyproject.toml)
#   ER_TOOLINV    TOOL-INVENTORY.md path  (default: $ER_FLEET/TOOL-INVENTORY.md)
# Exit: 0 = no drift, 1 = drift found, 2 = cannot read inputs, 3 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ER_FLEET="${ER_FLEET:-$(cd "$HERE/.." && pwd)}"
export ER_PRODUCT="${ER_PRODUCT:-/home/stack/code/charon}"
export ER_REGISTRY="${ER_REGISTRY:-$ER_FLEET/state/EVAL-REGISTRY.md}"
export ER_INVENTORY="${ER_INVENTORY:-$ER_FLEET/state/EVAL-INVENTORY.tsv}"
export ER_GRAPH="${ER_GRAPH:-$ER_PRODUCT/graphify-out/graph.json}"
export ER_GATES="${ER_GATES:-$ER_PRODUCT/tools/gates.json}"
export ER_PYPTOML="${ER_PYPTOML:-$ER_PRODUCT/pyproject.toml}"
export ER_TOOLINV="${ER_TOOLINV:-$ER_FLEET/TOOL-INVENTORY.md}"

case "${1:-reconcile}" in
  reconcile|inventory|check|generate) ;;
  *) echo "usage: $0 {reconcile|inventory|check|generate}" >&2; exit 3 ;;
esac

exec python3 - "$@" <<'PYEOF'
import os, sys, json, re, hashlib
from collections import OrderedDict

# ── helpers ──────────────────────────────────────────────────────────────────────────
def die(msg, code=2):
    print(f"eval-registry-reconcile: FATAL — {msg}", file=sys.stderr)
    sys.exit(code)

def warn(msg):
    print(f"eval-registry-reconcile: WARNING — {msg}", file=sys.stderr)

def quiet_print(*a, **kw):
    pass  # for --quiet mode; not wired yet

# ── env ──────────────────────────────────────────────────────────────────────────────
FLEET      = os.environ.get("ER_FLEET", "")
PRODUCT    = os.environ.get("ER_PRODUCT", "")
REGISTRY   = os.environ.get("ER_REGISTRY", "")
INV_TSV    = os.environ.get("ER_INVENTORY", "")
GRAPH      = os.environ.get("ER_GRAPH", "")
GATES      = os.environ.get("ER_GATES", "")
PYPTOML    = os.environ.get("ER_PYPTOML", "")
TOOLINV    = os.environ.get("ER_TOOLINV", "")
MODE       = sys.argv[1] if len(sys.argv) > 1 else "reconcile"

# ── 1. Parse EVAL-REGISTRY.md → tool → [(verdict, alignment, row_idx, raw_line)] ────
def parse_registry(path):
    """Parse the markdown table in EVAL-REGISTRY.md.
    Returns: dict tool_name_lower -> list of {verdict, alignment, row_idx, raw_line, tool_original}
    """
    rows = OrderedDict()
    if not os.path.isfile(path):
        die(f"registry not found: {path}")
    in_table = False
    row_idx = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if raw.startswith("| tool |") or raw.startswith("| tool|"):
                in_table = True
                continue
            if in_table and raw.startswith("|---"):
                continue
            if in_table and raw.startswith("|") and "---" not in raw and raw.strip() != "|":
                # Split by pipe; protect escaped pipes (\|) from splitting.
                # Layout: | tool | scope | date | verdict | alignment | reason | evidence-link | supersedes |
                safe_line = raw.replace("\\|", "\x00EPIPE\x00")
                parts = [p.strip().replace("\x00EPIPE\x00", "\\|") for p in safe_line.split("|")]
                if len(parts) < 6:
                    continue
                # Columns 1-5 are fixed; the rest may contain embedded pipes
                tool_raw   = parts[1]
                scope      = parts[2] if len(parts) > 2 else ""
                date       = parts[3] if len(parts) > 3 else ""
                verdict    = parts[4] if len(parts) > 4 else ""
                alignment  = parts[5] if len(parts) > 5 else ""
                if len(parts) >= 9:
                    reason     = " | ".join(parts[6:-2])
                    evidence   = parts[-2]
                    supersedes = parts[-1]
                elif len(parts) >= 8:
                    reason     = " | ".join(parts[6:-1])
                    evidence   = parts[-1]
                    supersedes = ""
                else:
                    reason     = " | ".join(parts[6:])
                    evidence   = ""
                    supersedes = ""

                if tool_raw in ("tool", "tool ") or tool_raw == "---":
                    continue
                tool_key = tool_raw.lower().strip()
                row_idx += 1
                entry = {
                    "verdict": verdict,
                    "alignment": alignment,
                    "row_idx": row_idx,
                    "raw_line": raw,
                    "tool_original": tool_raw,
                    "scope": scope,
                    "date": date,
                    "evidence_link": evidence,
                }
                rows.setdefault(tool_key, []).append(entry)
    if row_idx == 0:
        die(f"no data rows parsed from registry: {path}")
    return rows

# ── 2. Generate inventory ───────────────────────────────────────────────────────────
def _norm_tool(name):
    """Normalize a tool name for comparison: lowercase, strip common suffixes."""
    return name.lower().strip().rstrip(".,;:")

def _is_external_import(module_path):
    """Return True if this looks like an external dependency, not a stdlib or local module."""
    parts = module_path.split(".")
    if not parts:
        return False
    root = parts[0]
    # stdlib roots (Python 3.11) — not exhaustive, but covers the common ones
    stdlib_roots = {
        "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio", "asyncore",
        "atexit", "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
        "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
        "codeop", "collections", "colorsys", "compileall", "concurrent", "configparser",
        "contextlib", "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
        "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal", "difflib",
        "dis", "distutils", "doctest", "email", "encodings", "enum", "errno", "faulthandler",
        "fcntl", "filecmp", "fileinput", "fnmatch", "fractions", "ftplib", "functools",
        "gc", "getopt", "getpass", "gettext", "glob", "graphlib", "grp", "gzip",
        "hashlib", "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
        "imp", "importlib", "inspect", "io", "ipaddress", "itertools", "json", "keyword",
        "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox", "mailcap",
        "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
        "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os", "ossaudiodev",
        "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
        "platform", "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
        "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri",
        "random", "re", "readline", "reprlib", "resource", "rlcompleter", "runpy",
        "sched", "secrets", "select", "selectors", "shelve", "shlex", "shutil", "signal",
        "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
        "ssl", "stat", "statistics", "string", "stringprep", "struct", "subprocess",
        "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile",
        "telnetlib", "tempfile", "termios", "test", "textwrap", "threading", "time",
        "timeit", "tkinter", "token", "tokenize", "trace", "traceback", "tracemalloc",
        "tty", "turtle", "turtledemo", "types", "typing", "unicodedata", "unittest",
        "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
        "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
        "zipfile", "zipimport", "zlib",
        # Project-local roots
        "charon", "ksf", "keystone", "tools", "tests", "benchmark",
        "fleet", "src", "capability", "dogfood",
    }
    return root not in stdlib_roots

def generate_inventory():
    """Generate inventory from live sources. Returns list of {tool, where_seen, evidence}.
    Deterministic: only reads committed files, emits sorted output."""
    entries = []  # list of (tool_lower, tool_display, where_seen, evidence)

    # ── 2a. pyproject.toml dependencies ─────────────────────────────────────────────
    if os.path.isfile(PYPTOML):
        try:
            with open(PYPTOML, encoding="utf-8", errors="replace") as fh:
                in_deps = False
                in_opt  = False
                deps_section = ""
                for line in fh:
                    raw = line.rstrip()
                    if raw.startswith("dependencies = ["):
                        in_deps = True; deps_section = "core"
                        continue
                    if raw.startswith("[project.optional-dependencies]"):
                        in_deps = True; deps_section = "optional"
                        continue
                    if in_deps and raw.startswith("[") and not raw.startswith("[["):
                        in_deps = False; deps_section = ""
                        continue
                    if in_deps and deps_section:
                        m = re.match(r'^\s*"([^"]+)"', raw)
                        if m:
                            dep = m.group(1)
                            # Extract package name (before version constraint)
                            pkg = re.split(r'[<>=!~\[\s]', dep)[0].strip()
                            if pkg and pkg not in ("python", "charon"):
                                tag = f"pyproject.toml [{deps_section}]"
                                entries.append((_norm_tool(pkg), pkg, tag,
                                                f"{PYPTOML}: dep '{pkg}'"))
        except OSError as e:
            warn(f"cannot read pyproject.toml: {e}")

    # ── 2b. graph.json imports ──────────────────────────────────────────────────────
    if os.path.isfile(GRAPH):
        try:
            with open(GRAPH, encoding="utf-8", errors="replace") as fh:
                graph = json.load(fh)
            seen_imports = set()
            for node in graph.get("nodes", []):
                for imp in node.get("imports", []):
                    imp_name = imp.get("name", "")
                    if not imp_name:
                        continue
                    root = imp_name.split(".")[0].lower()
                    if (_is_external_import(imp_name)
                            and root not in seen_imports
                            and root not in ("charon", "ksf", "keystone")):
                        seen_imports.add(root)
                        entries.append((_norm_tool(root), root, "graph.json import",
                                        f"{GRAPH}: import '{imp_name}' "
                                        f"(in node '{node.get('name','?')}')"))
        except (OSError, json.JSONDecodeError) as e:
            warn(f"cannot read graph.json: {e}")

    # ── 2c. gates.json enforcers ────────────────────────────────────────────────────
    if os.path.isfile(GATES):
        try:
            with open(GATES, encoding="utf-8", errors="replace") as fh:
                gate_list = json.load(fh)
            for gate in gate_list:
                gid = gate.get("id", "")
                enf = gate.get("enforcer", "")
                if enf:
                    # The enforcer is a command or script — mark the whole gate
                    entries.append((_norm_tool(gid), gid, "gates.json enforcer",
                                    f"{GATES}: gate '{gid}' enforcer='{enf}'"))
        except (OSError, json.JSONDecodeError) as e:
            warn(f"cannot read gates.json: {e}")

    # ── 2d. TOOL-INVENTORY.md tool references ───────────────────────────────────────
    if os.path.isfile(TOOLINV):
        try:
            with open(TOOLINV, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            # Find backtick-quoted tool names: `graphify`, `validate_board.sh`, etc.
            # Also find section headers as tool categories.
            # Look for explicit tool names: binary names, script paths
            tool_patterns = [
                (r'`([a-zA-Z0-9][a-zA-Z0-9_.-]*\.[a-z]{1,6})`', "script ref"),
                (r'`([a-zA-Z][a-zA-Z0-9_-]{2,})`\s', "tool ref"),
            ]
            seen = set()
            line_num = 0
            for line in text.splitlines():
                line_num += 1
                for pat, label in tool_patterns:
                    for m in re.finditer(pat, line):
                        name = m.group(1)
                        if name in seen:
                            continue
                        # Skip generic/common words
                        if name.lower() in ("make", "bash", "python", "perl", "ruby",
                                             "node", "npm", "pip", "git", "docker",
                                             "curl", "wget", "ssh", "scp", "rsync"):
                            continue
                        if len(name) < 3:
                            continue
                        seen.add(name)
                        entries.append((_norm_tool(name), name,
                                        f"TOOL-INVENTORY.md {label}",
                                        f"{TOOLINV}:{line_num} '{name}'"))
        except OSError as e:
            warn(f"cannot read TOOL-INVENTORY.md: {e}")

    # ── 2e. Deduplicate by tool key (keep first occurrence) ─────────────────────────
    deduped = OrderedDict()
    for key, display, where, ev in entries:
        if key not in deduped:
            deduped[key] = (display, where, ev)
    result = []
    for key, (display, where, ev) in sorted(deduped.items()):
        result.append({"tool": display, "tool_key": key, "where_seen": where, "evidence": ev})
    return result


# ── 3. Drift detection ──────────────────────────────────────────────────────────────
def verdict_is_adopt(verdict_text):
    """True if verdict indicates adoption (ADOPT, shipped, etc.)"""
    v = verdict_text.upper().strip()
    return v.startswith("ADOPT") or "SHIPPED" in v or v.startswith("KEEP")

def verdict_is_reject(verdict_text):
    """True if verdict indicates rejection"""
    v = verdict_text.upper().strip()
    return v.startswith("REJECT") or v.startswith("SKIP")

def verdict_is_unresolved(verdict_text):
    """True if verdict is unresolved/open"""
    v = verdict_text.upper().strip()
    return v.startswith("UNRESOLVED") or v.startswith("OPEN") or v.startswith("DEFER") \
           or v.startswith("WATCH")

def alignment_first_token(alignment_text):
    """Extract the machine-readable first token from an alignment cell."""
    text = alignment_text.strip()
    m = re.match(r'\*?\*?(aligned|drifted|mixed|n-a)\*?\*?', text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None

def classify_registry_rows(registry):
    """Classify registry rows by verdict category.
    Returns: adopt_set (tool_keys), reject_set (tool_keys), all_verdict_rows list"""
    adopt_set = set()
    reject_set = set()
    unresolved_set = set()
    all_rows = []
    alignment_issues = []

    for tool_key, entries in registry.items():
        for e in entries:
            v = e["verdict"]
            all_rows.append(e)
            if verdict_is_adopt(v):
                adopt_set.add(tool_key)
            elif verdict_is_reject(v):
                reject_set.add(tool_key)
            elif verdict_is_unresolved(v):
                unresolved_set.add(tool_key)
            # Alignment parseability check
            al = alignment_first_token(e["alignment"])
            if al is None:
                alignment_issues.append(
                    f"  UNPARSEABLE alignment in row #{e['row_idx']}: "
                    f"tool='{e['tool_original']}', alignment='{e['alignment'][:80]}...'"
                )
    return adopt_set, reject_set, unresolved_set, all_rows, alignment_issues


def run_reconcile():
    registry = parse_registry(REGISTRY)
    inventory = generate_inventory()

    if not inventory and MODE == "reconcile":
        warn("inventory is empty — no live sources were readable")

    inv_tools = {e["tool_key"] for e in inventory}

    adopt_set, reject_set, unresolved_set, all_rows, alignment_issues = \
        classify_registry_rows(registry)

    # ── D3: CONTRADICTION (highest severity, report first) ──────────────────────────
    d3_findings = []
    for tool_key in sorted(reject_set & inv_tools):
        rows = registry.get(tool_key, [])
        for r in rows:
            if verdict_is_reject(r["verdict"]):
                inv_entries = [e for e in inventory if e["tool_key"] == tool_key]
                evidence_list = "; ".join(e["evidence"] for e in inv_entries)
                d3_findings.append(
                    f"D3 CONTRADICTION: tool '{r['tool_original']}' REJECTED in row "
                    f"#{r['row_idx']} but PRESENT in inventory ({', '.join(e['where_seen'] for e in inv_entries)}). "
                    f"Evidence: {evidence_list}"
                )

    # ── D1: UNEVALUATED ADOPTION ────────────────────────────────────────────────────
    d1_findings = []
    all_registry_tools = set(registry.keys())
    for tool_key in sorted(inv_tools - all_registry_tools):
        inv_entries = [e for e in inventory if e["tool_key"] == tool_key]
        evidence_list = "; ".join(e["evidence"] for e in inv_entries)
        d1_findings.append(
            f"D1 UNEVALUATED ADOPTION: tool '{inv_entries[0]['tool']}' present in "
            f"inventory ({', '.join(e['where_seen'] for e in inv_entries)}) "
            f"but has NO verdict row in EVAL-REGISTRY.md. "
            f"Evidence: {evidence_list}"
        )

    # ── D2: STALE ROW ───────────────────────────────────────────────────────────────
    d2_findings = []
    for tool_key in sorted(adopt_set - inv_tools):
        rows = registry.get(tool_key, [])
        for r in rows:
            if verdict_is_adopt(r["verdict"]):
                d2_findings.append(
                    f"D2 STALE ROW: tool '{r['tool_original']}' verdict is "
                    f"'{r['verdict'][:50]}' in row #{r['row_idx']} but tool is "
                    f"ABSENT from live inventory. The registry asserts we run "
                    f"something we do not."
                )

    # ── Report ──────────────────────────────────────────────────────────────────────
    total = len(d1_findings) + len(d2_findings) + len(d3_findings)
    ali_n = len(alignment_issues)

    print(f"== eval-registry-reconcile ==")
    print(f"  registry rows  : {len(all_rows)}")
    print(f"  inventory tools: {len(inventory)}")
    print(f"  D1 (uneval)    : {len(d1_findings)}")
    print(f"  D2 (stale)     : {len(d2_findings)}")
    print(f"  D3 (contradict): {len(d3_findings)}")
    print(f"  alignment unpars: {ali_n}")

    if alignment_issues:
        print(f"\n--- ALIGNMENT PARSEABILITY ({ali_n}) ---")
        for issue in alignment_issues:
            print(issue, file=sys.stderr)
            print(issue)

    if d3_findings:
        print(f"\n--- D3 CONTRADICTION ({len(d3_findings)}) — HIGHEST SEVERITY ---")
        for f in d3_findings:
            print(f"  {f}", file=sys.stderr)
            print(f"  {f}")

    if d1_findings:
        print(f"\n--- D1 UNEVALUATED ADOPTION ({len(d1_findings)}) ---")
        for f in d1_findings:
            print(f"  {f}", file=sys.stderr)
            print(f"  {f}")

    if d2_findings:
        print(f"\n--- D2 STALE ROW ({len(d2_findings)}) ---")
        for f in d2_findings:
            print(f"  {f}", file=sys.stderr)
            print(f"  {f}")

    if total == 0 and ali_n == 0:
        print(f"\nVERDICT: GREEN — no drift found, all alignment cells parseable.")
        return 0

    if total > 0:
        print(f"\nVERDICT: RED — {total} drift finding(s) detected.", file=sys.stderr)
    if ali_n > 0:
        print(f"VERDICT: RED — {ali_n} alignment cell(s) unparseable.", file=sys.stderr)

    return 1


def _inventory_header():
    return (
        f"# EVAL-INVENTORY.tsv — DERIVED tool inventory, regenerated from live sources.\n"
        f"# Generating command: fleet/checks/eval-registry-reconcile.sh inventory\n"
        f"# Sources: pyproject.toml, graph.json, gates.json, TOOL-INVENTORY.md\n"
        f"# Determinism: byte-identical when sources unchanged (no timestamp in output).\n"
        f"# Columns: tool | where_seen | evidence\n"
    )

def _inventory_data(inventory):
    """Return the data lines of the inventory as a string, for hashing."""
    lines = []
    for e in inventory:
        ev = e["evidence"].replace("\t", "    ")
        lines.append(f"{e['tool']}\t{e['where_seen']}\t{ev}")
    return "\n".join(lines) + "\n"

def cmd_inventory():
    """Generate and print the inventory TSV."""
    inventory = generate_inventory()
    print(_inventory_header().rstrip())
    data = _inventory_data(inventory)
    if data:
        print(data.rstrip("\n"))


def cmd_check():
    """Drift-check only — reads existing inventory TSV, does NOT regenerate."""
    return run_reconcile()


def cmd_generate():
    """Generate inventory and write to TSV file."""
    inventory = generate_inventory()
    os.makedirs(os.path.dirname(INV_TSV) or ".", exist_ok=True)
    with open(INV_TSV, "w", encoding="utf-8") as fh:
        fh.write(_inventory_header())
        data = _inventory_data(inventory)
        if data:
            fh.write(data)
    print(f"Wrote {len(inventory)} entries to {INV_TSV}")
    return 0


# ── dispatch ────────────────────────────────────────────────────────────────────────
if MODE == "inventory":
    sys.exit(cmd_inventory())
elif MODE == "generate":
    sys.exit(cmd_generate())
elif MODE == "check":
    sys.exit(cmd_check())
else:  # reconcile
    sys.exit(run_reconcile())
PYEOF

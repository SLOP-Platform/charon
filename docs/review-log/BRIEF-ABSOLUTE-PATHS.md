# BRIEF-ABSOLUTE-PATHS review log

## Decision
Proceed with the rendered interpolation approach. Bash parameter expansion
(`${var//\$PAT/$VAL}`) is used instead of sed because it handles arbitrary
characters in replacement values without delimiter collision.

## Sweep results
The sweep of `fleet/JOIN-PROMPT.md` found exactly 1 line with `$VAR` references
a model cannot expand: line 52 (`$FLEET/state/judgment/$DROID-$id.md`).
All three variables (`$FLEET`, `$DROID`, `$id`) are now rendered to concrete
absolute values at brief-construction time in `render_join_prompt()`.

No other `$VAR`-in-brief instances were found. The LAUNCHER NOTE block already
fully resolves `$wt`, `$branch`, `$base_ref`, `$REPO` at assignment time.

## Alternatives considered
- **Modifying JOIN-PROMPT.md** to use placeholder syntax (`__FLEET__`):
  rejected because JOIN-PROMPT.md is owned by SESSION-REPORT-WIRE, and this
  ticket's `owns:` does not include it.
- **Using sed**: rejected in favor of bash parameter expansion which handles
  arbitrary characters in replacement values (including `/` and `&`) without
  delimiter collision risk.

## Test coverage
`fleet/tests/brief-absolute-paths.test.sh` — 17 assertions covering all 4
DONE CONTRACT points (a–d), hermetic (`mktemp -d`), offline. PROVED:
- Rendered brief contains absolute path, no unexpanded `$VAR` (a1–a4)
- Judgment file at rendered path is picked up by emit_session_report (b1–b5)
- Failure simulation: `$FLEET` unset + different CWD, file still lands at
  absolute path (c1–c2)
- ANTI-OVER-BLOCK: absent judgment file yields NOT-REPORTED (d1–d5)

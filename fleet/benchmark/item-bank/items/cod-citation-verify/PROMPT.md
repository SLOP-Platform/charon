# Task: audit citations in a code file

You are auditing a small piece of code for unused/incorrect references.
The code file under review is `service.py`. The audit report must be
written to `AUDIT.md`.

For each `name` or `attribute` referenced in `service.py`, the audit
must:
- State the file:line where the symbol is defined (in real code, the
  codebase; in this fixture, the seeded `lib.py`).
- Quote the actual line of the definition.
- Flag if the reference is unused (defined but never imported/referenced
  in `service.py`).

The grader will resolve each citation you emit against the real `lib.py`
on disk; any invented/misnumbered/definition-line ref makes the audit
FAIL. Cite ONLY symbols whose definition is verifiable in `lib.py`.

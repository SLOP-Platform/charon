# Ticket: audit where cost_rank is read

Before we rename `Provider.cost_rank`, we need an accurate inventory of every
place it is **read** (not the line that defines the field).

Produce `AUDIT.md` in the repo root listing each read site, one per line, in the
form:

    <relative/path.py>:<line-number> — <exact source line, trimmed>

Cite only real read sites that exist in this tree, with correct line numbers and
the exact source text. Do not include the field's definition line, and do not
invent or approximate references.

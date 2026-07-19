# METER-DOC-RECONCILE — rig follow-up (moved out of the PUBLIC product repo)

Removed from `docs/review-log/METER-DOC-RECONCILE.md` in product PR #174 before
landing: it leaked rig taxonomy (board path, droid/manager process language)
into the public `SLOP-Platform/charon` repo. Verbatim original below; this is
its correct home.

---

## Manager follow-up (NOT droid work — no file touched)
`fleet/board/METER-MODEL-PROVIDER.md.parked` is a Wave-2 BUILD ticket for
work that has ALREADY SHIPPED (the 8 write sites + live readers above). Its
premise is dead. Recommendation: **retire or rescope** — disposition owned by
the manager; this ticket did not edit/rename/park/unpark that file.

---

Also softened in the public file (rig field name `owns:` removed): the
"Known intentional non-changes" bullet about
`tests/test_meter_model_provider.py:3` now reads "out of scope here" instead of
"outside this ticket's `owns:`". The stale "wiring deferred" note in that test
file is still a live follow-up.

## Open item for the manager
`fleet/board/METER-MODEL-PROVIDER.md.parked` — retire or rescope. Premise dead.

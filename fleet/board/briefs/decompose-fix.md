# BRIEF — FIX REVIEW FINDINGS: GATEWAY-ROUTING-DECOMPOSE (Wave 1)

ROLE: Apply small fixes from an adversarial review of the routing-policy extraction. Behavior-preserving refactor — do NOT change any routing decision. Work on branch `feat/gateway-routing-decompose` in THIS working dir (`/home/stack/code/wt-decompose`).

## FINDINGS TO FIX
### F1 — MEDIUM: `__all__` lists 7 symbols NOT importable at package level
`src/charon/routing_policy/__init__.py` declares names in `__all__` that are not actually bound at the package level → `from charon.routing_policy import <name>` fails and `__all__` is a lie. FIX: make every name in `__all__` actually importable at the package level (add the missing re-exports / imports), OR remove the non-exported names from `__all__`. Prefer re-exporting (that was the extraction's intent) so the package's public API matches `__all__` exactly.
### F2 — LOW: `os` + submodule names leak into the package namespace
Bare `import os` and submodule names are exposed as package attributes. FIX: keep the namespace clean (import what's needed inside functions or via explicit re-export list); don't leak `os`/submodule handles as public package attributes.

## REQUIRED TEST (must FAIL on revert)
Strengthen `tests/test_routing_policy.py::test_routing_policy_exports_public_api` (or add one) so it asserts that EVERY name in `routing_policy.__all__` is importable via `from charon.routing_policy import <name>` AND is not `None`. This must go RED if `__all__` again lists a non-importable symbol. (The review noted the current export test does NOT catch the `__all__` mismatch — fix that.)

## VERIFY BEFORE COMMIT
`cd /home/stack/code/wt-decompose && PYTHONPATH=src python3 -m pytest tests/test_routing_policy.py -q`
All green. Confirm no routing behavior changed (extraction stays byte-for-byte).

## LAST STEP (required)
Commit on `feat/gateway-routing-decompose`: `GATEWAY-ROUTING-DECOMPOSE: fix __all__ export mismatch (F1) + clean package namespace (F2) + export-integrity test`.
Print the new commit SHA. Do NOT push. Do NOT merge. Do NOT touch REVIEW-PACKET.md.

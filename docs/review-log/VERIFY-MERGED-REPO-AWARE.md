# VERIFY-MERGED-REPO-AWARE — Review Log

## Ticket
VERIFY-MERGED-REPO-AWARE: Repo-aware merge verification (root of wrong-repo bug class fix)

## What was done

### fleet/_lib.sh — canonical repo declarations + ticket-aware verify_merged
- **Canonical SSOT**: Declared `PRODUCT_REPO` (/home/stack/code/charon), `PRODUCT_SLUG` (SLOP-Platform/charon), `FLEET_REPO` (/home/stack/charon-private), `FLEET_SLUG` (Nnyan/charon-private) — one home in `_lib.sh`; every consumer reads these instead of re-hardcoding.
- **`_vm_meta` H3 fix**: Changed parser from `awk -F': '` (requiring literal ": " separator) to `index($0,k ":")` prefix match — matches validate_board.sh's `field()` strictly. `repo:charon-private` (no space) was a VALID RIG ticket to the board validator but read as "" here -> PRODUCT default -> product-only sha verified a rig ticket.
- **`_vm_ticket_repo_field` M4 fix**: Returns rc 1 when NO board file exists (orphan marker). Previously returned "" (empty field) indistinguishable from "board file present, no repo: field" -> PRODUCT default -> fail-OPEN on the input most likely to be a lie.
- **`_vm_resolve` H1 fix**: Delegates unknown keys to `repo-registry.sh` (`repo_resolve`) instead of an inline `case` that already diverged (omitted `keystone|ksf`). Unknown keys fail closed (rc 1) — NEVER fall back to PRODUCT.
- **All proof functions** (`_vm_sha_in_master`, `_vm_pr_merged`, `_vm_branch_merged`, `_vm_owns_present`) now accept optional trailing `<id>` arg and resolve the repo per-ticket. No-arg callers keep pre-fix behaviour.
- **`verify_merged`**: Calls `_vm_resolve "$id"` first — unmappable repo = rc 1 immediately (fail closed).

### fleet/done.sh — H2 fix: marker writer repo-aware
- **`sha_in_master`**: Was `git -C "$CHARON_REPO"` (hardcoded PRODUCT). Now uses `$VERIFY_REPO` which is resolved per-ticket via `ticket_repo_path`. A RIG ticket + product sha -> REFUSED (exit 3, no marker written). A RIG ticket + genuine rig sha -> ACCEPTED.
- **Repo->slug map DRY**: Removes the inline `case` (`charon` / `charon-private`) and calls `ticket_repo_slug` from `_lib.sh` — one map, no drift.
- **`DONE_CHARON_REPO` still honoured**: Fed through `VERIFY_MERGED_REPO` so the product arm picks it up at call time.

### fleet/tests/verify-merged-repo-aware.test.sh — FAIL-ON-REVERT test
- Constructs a rig ticket with proof sha existing ONLY in the product repo; asserts verify_merged REJECTS it (the REPO-DECL-CENTRAL false positive).
- Each assertion names the exact revert that turns it RED.
- Tests H3 (no-space repo line), H1 (keystone delegation), M4 (orphan markers), H2 (done.sh marker writer).

## Adversarial review notes
- **H3** (`_vm_meta` tolerant parser): A parser stricter than the board validator is a false-positive generator. Restoring `awk -F': '` makes the H3 assertions go RED.
- **H1** (`repo-registry.sh` delegation): The inline `case` had already diverged (omitted keystone/ksf). Restoring `*) return 1 ;;` makes keystone tickets un-closable.
- **M4** (orphan markers): Changing `|| return 1` to `|| return 0` in `_vm_ticket_repo_field` makes `verify_merged ORPHAN` return 0 against a product sha.
- **H2** (done.sh `sha_in_master`): Restoring `git -C "$CHARON_REPO"` makes a product sha pass for a rig ticket.

## Dependencies
- Zero-dep (root of the REPO-DECL-CENTRAL / REPO-FIELD-REQUIRED / REPO-MAP-CONVERGE chain).
- Unblocks those three tickets which depend_on this one.

You are a SMOKE-TEST droid validating the charon-fleet harness end-to-end. Do the MINIMUM to prove the loop works — nothing more. This is throwaway; do not do real work.

1. Make your worktree per the JOIN-PROMPT step 1, on branch chore/fleet-smoke.
2. Create a single file `FLEET-SMOKE.md` at the repo root containing one line:
   `charon-fleet smoke test OK`
3. Commit it: `git add FLEET-SMOKE.md && git commit -m "chore: fleet smoke test"`.
4. Do NOT run the gate, do NOT open a PR, do NOT push (this is a local-only smoke).
5. Run: `bash /home/stack/charon-private/fleet/submit.sh SMOKE`
6. STOP. Print one line: "SMOKE OK". The operator will delete the worktree + branch.

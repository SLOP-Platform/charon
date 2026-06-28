# OHMYPI-ASSESS — research/assess oh-my-pi as a Charon client (RESEARCH pass, not a build)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Research pass; owns NO product source files → cannot collide with
anything, runs CONCURRENTLY with everything. A fresh Charon can claim it any time.

## Why
The previous HANDOFF flagged oh-my-pi (https://github.com/can1357/oh-my-pi) as "operator wants it
working next." CLIENT-CONNECT (#72) already added `charon connect omp` (writes
`~/.omp/agent/models.yml`), so the wiring is partly solved. This ticket is the REMAINING research:
confirm what oh-my-pi is, whether `charon connect omp` fully wires it, and what (if anything) is
left (e.g. the Windows-vs-WSL PATH gap the operator hit).

## What to produce (a RIG doc, not product code)
A short assessment at `/home/stack/charon-private/dogfood/OHMYPI-ASSESS.md`:
1. What oh-my-pi is (another OpenAI-compatible coding agent? ACP? GUI/CLI?) and whether it points
   at an OpenAI-compatible gateway (Mode A — point it at Charon).
2. Does `charon connect omp` produce a working config for it as-is? Gaps (config schema drift, the
   `omp`-not-on-PATH Windows/WSL issue)?
3. Could it drive `charon work` as an ACP backend (Mode B), or is it gateway-client-only?
4. Recommendation: nothing-to-do / a small CLIENT-CONNECT-GUI-style fix / a real integration ticket.

## CONSTRAINTS
This is a DESIGN/RESEARCH pass (like the DSGN-* tickets): owns NO product src; output is the rig
doc above. No PR to master. Do it in a manager research sub-session (web + repo read), not a droid
build. BACKLOG (parked).

# ADR — Out-of-Band Benchmark Grading (#26) + Reds-Replay (#25)

Status: **DESIGN / build-gated.** Do NOT build until (1) this design is reviewed by the
manager, (2) the #20 finding below is acknowledged, (3) the operator answers **Q2** and **Q3**.
Operator decision **Q1 = A** is locked (dedicated `bench-grader` unix user on the LOCAL WSL box,
answer keys mode `0700`; see memory `charon-bench-grader-substrate`).

Authoritative inputs: `scratch/pivot-implementation-plan.md` §3 (#26) + §4 (#25) + §8 (Q1/Q2/Q3);
`fleet/BENCHMARK-VALIDITY-REVIEW.md`; board tickets `BENCH-OOB-GRADING.md`,
`BENCH-REDS-REPLAY.md.parked`, `BENCH-PROVISIONAL-SCORING.md.parked`.

Scope: **RIG-ONLY.** The daemon, spool, answer-key tree, and ledger must NEVER be referenced by
product code (`/home/stack/code/charon`). Grading is scoped to **reds-replay (#25)** as the
load-bearing signal; the synthetic S0–S6 graders stay agent-readable *on purpose* (see §1.4).

---

## 0. Load-bearing finding up front — #20 is already BUILT (changes deliverable #4)

The task brief and memory both say **#20 (BENCH-PROVISIONAL-SCORING) is PARKED**. That belief is
**stale.** #20 is fully built, committed, merged, and its selftest passes today on master:

- commits `9c5714a bench(#20): provisional-vs-active staging + promotion gate` +
  `facfc23 merge(bench): #20 provisional-vs-active scoring gate`.
- Present on disk and wired end-to-end:
  - `benchmark/units.tsv` (unit registry, S0–S6 grandfathered `active`),
  - `benchmark/promote.py` (v1 gate: `SPREAD_MIN=15.0`, `DISTINCT_MODELS_MIN=2`),
  - `bench.sh::unit_stage()` + `CHARON_SCORECARD_STAGE` plumbing in `do_grade`,
  - `model-scorecard.sh` writes the **16th `stage` column** and its `render` buckets provisional
    rows into a "PROVISIONAL (not counted)" block,
  - `capability/grades.py` (`_stage`, filter `stage==active`) and
    `benchmark/lib/tier_chart.py` (`_stage`, excludes provisional) both filter.
  - `python3 capability/selftest.py` → **ALL CHECKS PASS**.
- Sibling pivot work is ALSO already merged: **A2 BENCH-REGROUND-LIVE** (`4ab02a3`,
  `_REAL_OUTCOME_SOURCES = {"live"}`, synthetic demoted to smoke) and **#16 BENCH-AGGREGATE-N**
  (`da61356`/`36e7b25`, mean ± noise band). Their ticket files are also still `.parked`.

**Consequence for #26:** the "build-after #20" dependency is **already satisfied**. The stage
plumbing #26 was told not to co-write **already exists on master**, so #26 simply rebases onto
current `master`. See §6 for the corrected #20 decision and the bookkeeping fix.

---

## 1. #26 — Out-of-band grading (grader-daemon + drop-spool)

### 1.1 Threat closed (validity review §2, CRITICAL)
Three independent defeats of the instrument, any one of which is fatal:
1. **Answer key readable by the subject** — `graders/*.py`, baseline fixtures, and (for #25) the
   `check_cmd` sit in the stack-owned repo the agent can `cat`.
2. **Grading self-driven** — the graded model runs `bench.sh grade` itself.
3. **Self-report** — `RUN-BENCHMARK.md` tells the agent to paste the tier chart as its own output;
   the subject is scorer AND reporter.

### 1.2 The three invariants the architecture enforces
1. **Answer key out of the subject's reach** — the in-scope keys (reds-replay `check_cmd`s +
   pre-fix expectations, and any hardened grader) live in a `bench-grader`-owned tree at `0700`;
   the graded agent's user cannot read them.
2. **Grading not self-driven** — the agent only *signals done* (drops a request); a separate,
   long-lived **scorer daemon** running as `bench-grader` performs grading. The agent never
   executes a grader or a `check_cmd`.
3. **No self-report** — the ledger (`model-scorecard.tsv`) is owned by `bench-grader` and is
   **not writable by the agent's user**; the daemon is the sole writer. Any score the agent pastes
   or tries to append is discarded / has no path to the ledger.

### 1.3 Users and trust domains
| user | role | can read `$KEYS`? | can write ledger? | can write `req/`? |
|------|------|:---:|:---:|:---:|
| `bench-grader` | scorer daemon (Q1=A) | yes (owner) | yes (owner, sole writer) | reads it |
| `stack` (= graded opencode agent **and** operator/manager) | drives bench.sh; implements in worktree | **no** | **no** | yes (drop-only) |

Note: the graded agent and the operator share the `stack` user. That is acceptable because the
**threat is the graded agent, and the isolation is by file ownership, not by user identity** —
neither the agent nor the operator-as-`stack` can read `$KEYS` or write the `bench-grader`-owned
ledger. The operator appends `source=live` rows via interactive, password-gated
`sudo -u bench-grader …` (NOT a NOPASSWD sudoers rule — see §1.7), so an unattended agent has no
path to it. **Optional hardening (recommended if ever multi-user):** run the graded opencode tab
as a dedicated third user `bench-subject`; the design below needs no change beyond the chowns.

### 1.4 Scope carve-out — why synthetic S0–S6 graders stay agent-readable
A2 (`_REAL_OUTCOME_SOURCES = {"live"}`) already **excludes every `source=bench` row from live
grades**; S0–S6 are demoted to a smoke gate. Reading an S0–S6 grader therefore cannot move any
load-bearing number. So we deliberately **do NOT relocate/chmod the in-repo `benchmark/graders/`**
(doing so would break `stack`'s normal `git` checkout of the fleet repo). Only the **new
reds-replay keys** — which *are* load-bearing — go into the `0700` `bench-grader` tree. This is the
clean resolution of the "keys are in a git-tracked, stack-owned worktree" tension: keep the
neutered synthetic keys in git; keep the live-signal keys private.

### 1.5 Directory layout, ownership, and modes

```
$KEYS = /home/bench-grader/keys/                bench-grader:bench-grader  0700   (answer keys)
  reds-replay.tsv                               unit_id,red_id,prefix_snapshot,check_cmd,
                                                expect_green_exit,work_class,note   0600
  prefix-snapshots/<red-id>.tar                 pre-fix (red) fixture tarballs      0600
  graders/            (FUTURE, optional)        hardened section graders            0700

$SPOOL = /var/lib/bench-grader/spool/
  req/     bench-grader:bench-grader  1733   DROP BOX: stack can create+write a file it names
                                             but cannot `ls`/read the dir (canonical maildrop);
                                             sticky bit => only the file's own creator can
                                             unlink it. Agent writes req/<run>.json here.
  res/     bench-grader:bench-grader  0755   result files 0644: agent polls res/<run>.json
                                             (contains ONLY verdict/score/next-prompt — never a
                                             grader source, baseline, or check_cmd).
  work/    bench-grader:bench-grader  0700   daemon's READ-ONLY snapshots of agent worktrees.

Ledger: /home/stack/charon-private/fleet/model-scorecard.tsv
        chown bench-grader:bench-grader, mode 0644  (world-readable so every rig reader still
        reads it; writable ONLY by bench-grader). Daemon appends with a single O_APPEND write()
        (< PIPE_BUF => atomic, no dir-write / no lock needed — the parent dir stays stack-owned).
```

Isolation boundary in one line: **the agent is write-only on `req/` and read-only on its own
`res/<run>.json`; everything that constitutes the answer or the verdict (`$KEYS`, `work/`, the
ledger) is `bench-grader`-owned and unreadable/unwritable by `stack`.**

### 1.6 Control flow

```
 graded agent (user=stack)                         grader-daemon (user=bench-grader, long-lived)
 ─────────────────────────────                     ─────────────────────────────────────────────
 bench.sh start
   daemon-independent: copies the pre-fix
   fixture into $WORKTREE (agent-owned, rw),
   prints the (fix-free) task prompt
 …implements in $WORKTREE…
 bench.sh grade  ==>
   1. flush: wait_for_worktree_stable($WT)         watches $SPOOL/req/ (inotify, poll fallback)
   2. write req/<run>.json (mode via umask):        on new req/<run>.json:
        {run, model, unit_id, kind, worktree}       a. cp -a --no-preserve=ownership $WT
   3. poll res/<run>.json (timeout)                    -> work/<run>/  (read-only snapshot;
   4. print res.next_prompt / verdict                   agent cannot tamper mid-grade)
      (advisory display only)                        b. wait_for_worktree_stable(work/<run>) too
                                                     c. look up unit stage in units.tsv;
                                                        run the grader/check_cmd FROM $KEYS
                                                        against work/<run>/ (never $WT live)
                                                     d. grade_state.record(model,unit,score,gate)
                                                     e. APPEND row to model-scorecard.tsv
                                                        (sole writer; tags CHARON_SCORECARD_STAGE)
                                                     f. write res/<run>.json atomically
                                                        (write tmp in res/, rename)
```

**What moves out of `bench.sh` into the daemon** (these are exactly the `do_grade` call sites
today, lines ~370–447): `wait_for_worktree_stable`, the `$grader --worktree --baseline` /
`check_cmd` invocation, `grade_state.record`, `unit_stage` lookup, and the `model-scorecard.sh
append`. **`bench.sh` keeps driving** (`start`, worktree prep, the S0..S6 / unit queue, the
premature-grade flush on the agent side) but **`bench.sh grade` becomes**: flush → drop `req` →
poll `res` → print the daemon-returned next-section prompt. It no longer touches graders, keys, or
the ledger. `run.sh` / `run-many.sh` legacy paths get the same treatment or a hard "use the
daemon" refusal.

New file: **`benchmark/grader-daemon.py`** (stdlib only; inotify via `select`/poll fallback so it
runs anywhere). Bring-up safety: a `--in-process` fallback flag lets `bench.sh grade` grade
locally (old behavior) during initial wiring, gated OFF for real runs — the acceptance test asserts
the daemon path is the one in force.

### 1.7 sudoers / how the daemon runs as bench-grader
**No NOPASSWD sudoers rule is required for the grading path** — that is the security win of the
daemon over Q1's rejected option (b) "sudo wrapper." The daemon is already running as
`bench-grader` (started once by root), so the agent never needs to elevate.

- Preferred: a **systemd system service** `User=bench-grader` (WSL2 has systemd when
  `/etc/wsl.conf` has `[boot] systemd=true`).
- Fallback (no systemd): `sudo -u bench-grader nohup python3 …/grader-daemon.py &` at box startup,
  or a `@reboot` cron entry in `bench-grader`'s crontab.
- The only interactive sudo the operator uses is (i) one-time setup (§5) and (ii) appending
  `source=live` rows: `sudo -u bench-grader …/model-scorecard.sh append …` — **password-gated on
  purpose** so an unattended graded agent (same `stack` user) cannot invoke it. Do **not** add a
  NOPASSWD sudoers line for append; that would hand the agent a self-report path.

### 1.8 #26 acceptance criteria
- From the graded-agent user (`stack`): `cat $KEYS/reds-replay.tsv`, `cat $KEYS/prefix-snapshots/*`,
  and (if present) `$KEYS/graders/*` all **fail with permission denied** (hardening test).
- A run where the agent writes a **fabricated score** to its own output *and* attempts
  `echo <row> >> model-scorecard.tsv` produces **no ledger change**; only the daemon's computed row
  lands (no-self-report proof — the ledger is not `stack`-writable).
- Re-grading the same `work/<run>/` snapshot yields the **same** score the daemon recorded
  (determinism).
- The daemon is the **sole** appender of `bench`/`reds` rows (grep the ledger's writers).

---

## 2. #25 — Reds-replay (the primary valid ranking signal)

### 2.1 Intent
Replay real `reds.tsv` bugs as benchmark tasks; the deterministic `check_cmd` is the grader —
real, self-refreshing (grows as reds are filed), and un-memorizable (the model never sees the
`check_cmd`; the #26 daemon runs it out-of-band from `$KEYS`).

### 2.2 The reconstitution problem (core design point)
Every existing `check_cmd` asserts the **current, already-fixed** `origin/master` (or runs a check
script against live state). To replay a red as a *task*, the model must be handed the **pre-fix
(red) state** and asked to make the check pass. So each replayable red needs:
1. a **pre-fix snapshot** = the tree at the **parent of the fix SHA** in `closed_by`
   (e.g. `<sha>^`); for product-repo reds:
   `git -C /home/stack/code/charon archive <sha>^ -- <paths> > $KEYS/prefix-snapshots/<red-id>.tar`
   (rig-side reds: snapshot the relevant fleet files at the pre-fix commit);
2. a **worktree-relative `check_cmd`** — the stored check must target the daemon's snapshot, not
   `origin/master`. Curation rewrites each admitted check to a `{worktree}`-parameterized form the
   daemon substitutes (e.g. `grep -q rsplit {worktree}/tool/charon/proxy.py`, or a behavioral
   script run with `CWD={worktree}`);
3. a **fix-free task prompt** — `reds.tsv.description` often names the fix
   (e.g. "…fix compares final id segment (rsplit)"); curation must author a prompt that states the
   **symptom/red**, never the remedy.

### 2.3 Admissibility gate (curation) — hard requirements
A red is admitted to `reds-replay.tsv` **iff** all hold:
- (a) not `manual:` (unavoidably non-machine-gradable);
- (b) **behavioral check preferred** over bare `grep -q <string>` (string-presence is targetable;
  admit it only where no behavioral check exists — safe because #26 keeps the `check_cmd` out of
  the agent's reach, per Q3);
- (c) a **recoverable pre-fix state** exists (a `closed_by` SHA whose parent is buildable);
- (d) **VERIFY: `check_cmd` FAILS (non-zero) on the pre-fix snapshot AND PASSES (zero) on the
  post-fix snapshot.** This is the anti-false-green guard — a red that is already green pre-fix is
  not a valid task and is rejected. This gate is run *by curation* (as `bench-grader`, in `$KEYS`).

### 2.4 Harness reuse
A replayed red is just another **unit** (`kind=red`) in `units.tsv`, fed to `bench.sh start`; the
worktree machinery (`grade_state.py`, `runs/<model>/<unit>/`) is unchanged. The #26 daemon runs
its `check_cmd` against the read-only snapshot: **exit 0 = pass (MERGE), non-zero = BLOCK**, with
the same correction-round loop as today. New units land **`stage=provisional`** (#20) until
`promote.py` proves they discriminate.

Files owned by #25 (disjoint from #26's `owns`): `reds.tsv` (add a `replayable` column or a
`benchmark/reds-replay.tsv` manifest), `benchmark/reds_replay/` (curation + snapshot tooling), and
the deployed `$KEYS/reds-replay.tsv` + `$KEYS/prefix-snapshots/`.

### 2.5 #25 acceptance criteria
- ≥1 replayed red runs end-to-end through the OOB daemon and records a **provisional** row whose
  MERGE/BLOCK is derived **solely** from `check_cmd` exit status.
- The `check_cmd` is **never** present in the agent-readable worktree or prompt.
- On the **real pre-fix state**: leaving the red unfixed → BLOCK; a correct fix → MERGE.
- Curation refuses any red failing the §2.3(d) pre-fix-fails/post-fix-passes verification.

---

## 3. Q2 and Q3 — surfaced for operator decision (Q1 already = A)

The WCI bench chain is gated on Q1/Q2/Q3. Q1 is locked (=A). Q2 and Q3 gate **#25** specifically
and must be answered before #25 builds (they do not block #26).

### Q2 — reds-replay corpus scope
**Question:** retroactively snapshot the pre-fix state of *all recoverable already-closed reds*
now, versus capture pre-fix fixtures only for *new* reds going forward?
**Trade-off:** retroactive gives corpus mass immediately (there are ~17 closed reds today, of which
the routing/billing product-repo reds with `closed_by` SHAs — e.g. `silent-downgrade-double-bill`,
`failover-401-not-classified`, `gpt55-pool-order`, `cooldown-anchor-demotion` — are the prime
replay candidates; the `bench-*` rig-internal reds are harder to reconstitute meaningfully);
forward-only is cheaper but accrues slowly.
**Recommendation: retroactive for the behavioral, non-`manual:`, recoverable subset (fast corpus
mass), with forward-only as the steady state.** Run one retroactive curation pass now; thereafter
every newly-closed red is a candidate at close time.

### Q3 — `check_cmd` admissibility bar
**Question:** exclude `manual:` (unavoidable) and bare `grep -q <string>` (targetable) reds? Is the
minimum bar "behavioral"?
**Recommendation: yes — prefer behavioral; admit string-presence only where no behavioral check
exists**, and only because #26 keeps the `check_cmd` out of the model's reach. **Add the §2.3(d)
pre-fix-fails / post-fix-passes verification as a hard admissibility criterion** (this is a design
addition beyond the plan's Q3 wording — it is what actually guarantees the replayed unit is a valid
discriminating task rather than a false-green).

---

## 4. #20 (BENCH-PROVISIONAL-SCORING) dependency decision

**Decision: #20 is DONE — do not un-park to rebuild, do not drop. The "build-after #20" dependency
is already satisfied; #26 rebases onto current `master`.**

Justification: §0 shows #20 is built, merged (`9c5714a`/`facfc23`), and green (selftest passes),
with the `stage` column and reader/writer filters all live on `master`. The reason #26 was
"build-after #20" was file-sequencing — both edit `bench.sh` / `grade_state.py` /
`model-scorecard.sh`, and #26 must not co-write the stage plumbing. **That plumbing already exists
on master**, so the collision risk is gone: #26 branches from current `master` and moves the
existing grade path into the daemon. Treating #20 as an un-built blocker would be actively harmful —
a droid told to "build #20 first" would re-implement live, merged code and collide.

**Required bookkeeping fix (stale board state):** rename off `.parked` / move to done:
`BENCH-PROVISIONAL-SCORING.md.parked`, `BENCH-REGROUND-LIVE.md.parked`, `BENCH-AGGREGATE-N.md.parked`
(all three are built + merged). In `BENCH-OOB-GRADING.md`, the `build-after`/`real-dep` note about
"#20 still PARKED" is obsolete — replace with "build-after #20 satisfied on master (`facfc23`);
rebase onto master." This is a manager/bookkeeping action, not a build task.

---

## 5. Operator setup commands (LOCAL WSL box; needs root)

Run these once, as the operator, on the box where `bench.sh` + `graders/` live. `$FLEET` =
`/home/stack/charon-private/fleet`.

```bash
# 1. Create the dedicated grader user (system account, no login shell).
sudo useradd -r -m -d /home/bench-grader -s /usr/sbin/nologin bench-grader

# 2. Answer-key tree (0700 — the graded agent's user cannot read it).
sudo install -d -o bench-grader -g bench-grader -m 0700 /home/bench-grader/keys
sudo install -d -o bench-grader -g bench-grader -m 0700 /home/bench-grader/keys/prefix-snapshots

# 3. Drop-spool: req/ is a maildrop (write+execute, NO read => stack can drop but not list),
#    res/ is world-readable (agent polls its own result), work/ is grader-private.
sudo install -d -o bench-grader -g bench-grader -m 0700 /var/lib/bench-grader
sudo install -d -o bench-grader -g bench-grader -m 1733 /var/lib/bench-grader/spool/req
sudo install -d -o bench-grader -g bench-grader -m 0755 /var/lib/bench-grader/spool/res
sudo install -d -o bench-grader -g bench-grader -m 0700 /var/lib/bench-grader/spool/work

# 4. Hand the ledger to the grader (sole writer; still world-readable for every rig reader).
sudo chown bench-grader:bench-grader "$FLEET/model-scorecard.tsv"
sudo chmod 0644 "$FLEET/model-scorecard.tsv"

# 5. Run the daemon as bench-grader (systemd path; WSL2 needs [boot] systemd=true in /etc/wsl.conf).
sudo tee /etc/systemd/system/bench-grader.service >/dev/null <<'UNIT'
[Unit]
Description=Charon bench out-of-band grader daemon
[Service]
User=bench-grader
Group=bench-grader
ExecStart=/usr/bin/python3 /home/stack/charon-private/fleet/benchmark/grader-daemon.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now bench-grader.service
# Fallback if systemd is unavailable in this WSL distro:
#   sudo -u bench-grader nohup python3 "$FLEET/benchmark/grader-daemon.py" >/tmp/bg.log 2>&1 &
```

No sudoers file is added. `source=live` rows are appended by the operator via interactive
`sudo -u bench-grader bash "$FLEET/model-scorecard.sh" append …` (password-gated on purpose).
Count: **~8 command blocks** (steps 1–5; step 5 is the daemon unit + enable).

Key population is a #25 deploy step (run after curation, as part of the build): `git -C
/home/stack/code/charon archive <sha>^ … > snapshot.tar` then `sudo install -o bench-grader -g
bench-grader -m 0600 reds-replay.tsv /home/bench-grader/keys/` (and the snapshots into
`prefix-snapshots/`).

---

## 6. Build sequence, tickets, model, and WCI fit

### 6.1 Sequence (Track A already complete)
```
DONE (merged):  A2 BENCH-REGROUND-LIVE ─► #20 BENCH-PROVISIONAL-SCORING ─► #16 BENCH-AGGREGATE-N
GATED TRACK B:  #26 BENCH-OOB-GRADING  ─► #25 BENCH-REDS-REPLAY  ─► #17 BENCH-DIFFICULTY-CAL
                                                                └─► #27 ASSIGN-DISCRIM-GATE (dep: A2, done)
```
- **#26 is the immediate next build** once this design is reviewed. It has no unmet dependency
  (its build-after #20 is satisfied on master). Solo wave — it single-owns `bench.sh`,
  `grade_state.py`, `model-scorecard.sh` (+ new `grader-daemon.py`, `RUN-BENCHMARK.md`,
  `START-SESSION.md`, `preflight.sh`), so no parallel co-writer is allowed on those files.
- **#25 follows #26** (real-dep: the daemon must exist to run the `check_cmd` OOB) and is gated on
  operator **Q2 + Q3**. It owns `reds.tsv` / `reds-replay.tsv` / `benchmark/reds_replay/` — disjoint
  from #26's `owns`, so no co-write, but it is *sequenced* after #26.
- **#17 / #27** trail; both are P1, already staged (`.parked`).

### 6.2 Acceptance (human-verifiable invariants — the sign-off gate)
From the graded-agent user, both must hold, demonstrated live:
1. `cat` of any grader source / baseline / `check_cmd` in `$KEYS` → **permission denied**.
2. A fabricated agent-pasted score (and a direct `echo >> model-scorecard.tsv` attempt) → **no
   change to the ledger**; only the daemon's computed row lands.
Plus: re-grading a snapshot is deterministic; the daemon is the sole `bench`/`reds` ledger writer;
(for #25) ≥1 replayed red records a provisional MERGE/BLOCK purely from `check_cmd` exit, with the
`check_cmd` never in the agent worktree/prompt.

### 6.3 Recommended model
`ci-infra` / systems work with unix-permissions correctness + a stdlib daemon + careful bash
rewiring → **frontier-tier** (matches the ticket's `tier: frontier`). Per memory `charon-no-workhorse
-finalized`, no model is asserted as the workhorse; pick the operator's strongest hands-on coding
model for this wave (and let `assign()` choose once it differentiates on `ci-infra` — today it does
not, so this is an operator hand-pick).

### 6.4 WCI Gated Track B fit
#26 + #25 are the **Gated Track B** bench-integrity chain: build-gated behind (i) this design
review, (ii) the #20 finding acknowledged, (iii) operator Q2/Q3 (for #25). Track A (A2/#20/#16) is
the completed, un-gated predecessor. #26 being a single-owner solo wave and #25 owning a disjoint
file set means the WCI contention detector sees **zero co-writers** in this track — the only
constraint is the #26→#25 *sequence* (real build prereq: the daemon), not a file collision. Nothing
in this track ships in the product (`product-vs-build-rig-boundary`): the daemon, spool, `$KEYS`,
ledger, `reds.tsv`, and `capability/*` are rig-only; the sole product-boundary contact remains the
pools Phase-2 grades-table source swap (pivot plan §7), which is out of scope here.

---

## 7. Open items before build
- [ ] Manager review of this design.
- [ ] Acknowledge §0 / §4 (#20 done) and fix the stale `.parked` bookkeeping on
      BENCH-PROVISIONAL-SCORING / BENCH-REGROUND-LIVE / BENCH-AGGREGATE-N.
- [ ] Operator answers **Q2** (corpus scope) and **Q3** (admissibility bar) — gates #25 only.
- [ ] Then: build #26 (solo wave) → deploy §5 → build #25.

# CI action-version bump mechanization — investigation & recommendation

_Investigated 2026-07-03. Read-only on the product repo (`/home/stack/code/charon`); no workflow was modified._

## TL;DR recommendation

**Use GitHub-native Dependabot, `github-actions` ecosystem only, grouped weekly, PR-only (no auto-merge).**
Drop `.github/dependabot.yml` (config below). It keeps every action **SHA-pinned** and rewrites the trailing `# vX` comment to match the new SHA — exactly the posture `docs/SUPPLY-CHAIN.md` requires — with **zero extra infrastructure** and **zero self-hosted-runner exposure from the update job itself** (Dependabot's update computation runs on GitHub's hosted infra for public repos, never on 4-lom).

- **Tool:** Dependabot (not Renovate). Renovate is strictly more powerful but needs an app install / hosted service and a layered preset model — unjustified for a solo-dev, single-repo, propose-default posture. Dependabot is native YAML, understands SHA-pinned actions + version comments out of the box.
- **Scope:** `github-actions` now. **Do not** add the `docker` or `pip` ecosystems (reasons in §6 — they are redundant or near-no-ops here).
- **Merge policy:** PR-only. Humans merge (D006). Optional narrow patch-only auto-merge documented in §5 as the operator's explicit call, with the tripwire noted.

---

## 1. Current inventory (what goes stale)

All six actions in the repo are already SHA-pinned with a trailing `# vX` comment (verified across all four workflow files):

| Action | Pinned SHA | Comment | Files |
|---|---|---|---|
| `actions/checkout` | `34e114876b0b11c390a56381ad16ebd13914f8d5` | `# v4` | ci.yml, heavy.yml, release.yml, windows-exe.yml |
| `actions/setup-python` | `a26af69be951a213d495a4c3e4e4022e16d87065` | `# v5` | ci.yml, heavy.yml, release.yml, windows-exe.yml |
| `actions/upload-artifact` | `6f51ac03d0de2832b07d1c8169dc3f4f7e7e2b0c` | `# v4.3.1` | windows-exe.yml |
| `docker/login-action` | `c94ce9fb468520275223c153574b00df6fe4bcc9` | `# v3` | release.yml |
| `docker/build-push-action` | `10e90e3645eae34f1e60eeb005ba3a3d33f178e8` | `# v6` | release.yml |
| `actions/attest-build-provenance` | `ef244123eb79f2f7a7e75d99086184180e6d0018` | `# v1` | release.yml |

Every comment is of the form `# vN[.N.N]` and sits **at the end of the line** — this matters for Dependabot's comment-updater (see §3). All four workflows trigger on `push` / `pull_request` / `release` / `workflow_dispatch`; **none use `pull_request_target`** (relevant to §4).

The Node-20 deprecation warnings the operator is seeing come from these pins lagging the actions' current major/minor SHAs. This mechanism is exactly what fixes that on an ongoing basis.

---

## 2. Dependabot vs Renovate for SHA-pinned `github-actions` (2026)

Both tools natively understand SHA-pinned actions **and** the `# <ref>` version comment, and both keep the pin a SHA (neither reverts to a floating `@v4` tag):

- **Dependabot** — since the [2022-10-31 changelog](https://github.blog/changelog/2022-10-31-dependabot-now-updates-comments-in-github-actions-workflows-referencing-action-versions/) it "updates the semver version in comments when updating Actions workflows with a commit SHA version," so the comment stays in lockstep with the SHA. Native repo-local YAML, nothing to install. Grouping is by name-pattern / dependency-type / semver bump size. Auto-merge needs an external companion Action.
- **Renovate** — via the `helpers:pinGitHubActionDigests` preset it pins every action to a SHA and maintains the human-readable version in a trailing comment, bumping both together; far richer grouping (`packageRules`) and native auto-merge control. But it needs the Renovate GitHub App (hosted SaaS) or a self-hosted Renovate runner, plus a layered preset config.

**Independent 2026 comparison** ([tenthirtyam.org, 2026-05-13](https://tenthirtyam.org/dispatches/2026/05/13/dependabot-vs-renovate-dependency-management-on-github/)) reaches the same split: **Dependabot is the "strong default for standard GitHub repositories" — native, easy to enable**; reach for Renovate only when you hit custom manifests, monorepos, or fleet-scale throttles. Charon is a single repo, six actions, one maintainer, propose-default. That is squarely Dependabot's lane. Renovate's extra power (fine-grained `packageRules`, native auto-merge) is capability we are deliberately **not** using here, so it would be cost without benefit.

**Verdict: Dependabot.**

---

## 3. SHA-pin preservation proof (why the supply-chain posture stays intact)

A reviewer can trust Dependabot will **not** weaken the `docs/SUPPLY-CHAIN.md §5` posture, because:

1. **It bumps SHA→SHA, never SHA→tag.** Dependabot's github-actions manager reads the existing `uses: owner/action@<sha>` reference and replaces the 40-char SHA with the new commit's SHA for the same version line. It does not rewrite a hash pin into a `@v4` tag. (This was the whole point of [dependabot-core#2835 "Secure updates for GitHub Actions"](https://github.com/dependabot/dependabot-core/issues/2835) and #4691 — pin-by-hash is a first-class, supported input.)
2. **It updates the trailing comment to match.** Per the [2022-10-31 changelog](https://github.blog/changelog/2022-10-31-dependabot-now-updates-comments-in-github-actions-workflows-referencing-action-versions/) and [dependabot-core#5951](https://github.com/dependabot/dependabot-core/pull/5951), the file-updater "searches the comment string for all references to the previous version and replaces them with the new version," so `# v4` becomes `# v4.3.2` (or whatever the new SHA maps to). A stale/lying comment is the exact failure mode this closes.
3. **Comment-update guardrail — and why Charon satisfies it.** To avoid clobbering prose, Dependabot **only** rewrites a comment when the version is **at the end of the line** ([dependabot-core#7912](https://github.com/dependabot/dependabot-core/issues/7912)). Every Charon pin is `…@<sha>  # vN` with the version last, so all six qualify.
4. **Known behavior to be aware of ([dependabot-core#13466](https://github.com/dependabot/dependabot-core/issues/13466), closed/Done).** For a hash pin, Dependabot tracks the moving ref (e.g. the `v4` major tag) and can open a PR whenever that tag's SHA moves — even for a docs-only retag. For Charon this is **the desired behavior** (we want to follow the current `v4`/`v5`/`v3`/`v6`/`v1` head SHA to clear deprecations); weekly + grouping (§below) caps the noise. The trade-off is simply "occasionally a no-op-ish bump PR," which a human dismisses — acceptable under propose-default.

Net: after a Dependabot merge, the pin is still a full SHA and the comment is accurate. The SLSA-provenance / digest-pinned-base posture is untouched (those live in `release.yml` build steps, not in the action refs).

---

## 4. Self-hosted-runner considerations (4-lom)

Two distinct execution surfaces — keep them separate:

**(a) Dependabot's own update job — no 4-lom exposure.** Dependabot computes the update and opens the PR on **GitHub-hosted Dependabot infrastructure**. Per GitHub's docs, **Dependabot updates on self-hosted runners do not run on public repositories** at all — the self-hosted-runner path is a private/enterprise feature. Charon is a public repo, so the bump computation never touches 4-lom. Good.

**(b) The CI that runs _on the resulting PR_ — this is the real caveat.** A Dependabot PR is a **same-repo branch** (not a fork), so `ci.yml`'s `pull_request` trigger resolves `CI_RUNNER` to `["self-hosted","4-lom"]` and runs on your box. That means **the newly-bumped action's code executes on 4-lom during PR CI, before a human has vetted the SHA.** Mitigants already in place and available:
  - Dependabot-authored workflow runs get a **read-only `GITHUB_TOKEN` with no secrets** by default, so a bump PR's CI cannot exfiltrate repo secrets or push. (Secrets/`packages:write` only exist on the `release.yml` publish path, which is `on: release`, never on a PR.)
  - The bumps are same-major SHA moves of **first-party `actions/*` and well-known `docker/*`** actions — low but nonzero risk.
  - **`pull_request_target` is not used anywhere**, so there is no "run untrusted PR with write token" footgun to worry about.
  - **Optional hardening (operator's call, needs a workflow edit — NOT included in the drop-in):** route Dependabot PRs to the ephemeral GitHub-hosted runner instead of 4-lom by making `runs-on` actor-aware, e.g.
    ```yaml
    runs-on: ${{ github.actor == 'dependabot[bot]' && 'ubuntu-latest' || fromJSON(vars.CI_RUNNER || '"ubuntu-latest"') }}
    ```
    This keeps unvetted action code off the self-hosted box entirely (it runs on a throwaway hosted VM), at the cost of a few GitHub minutes per bump PR. Recommended if the 4-lom box shares a network with anything sensitive. Filed as an optional item in the ticket (§7), separate from the dependabot.yml drop-in.

---

## 5. Merge policy (propose-default / D006)

**Default: PR-only. Humans merge. No auto-merge.** Dependabot opens a grouped weekly PR; the full `gate` + smoke run; a maintainer reviews the SHA diff (adversarial-review culture) and merges. This is the make-safe default and what the config below does.

**Optional narrow auto-merge (explicit operator opt-in — tripwire noted):** if bump fatigue sets in, the operator _may_ enable auto-merge for **patch-level action bumps only** that pass the full gate, via a companion workflow using `dependabot/fetch-metadata` gated on `update-type == 'version-update:semver-patch'` + `gh pr merge --auto`. **Tripwire:** auto-merging a hash-pin bump means a SHA lands in `master` **without a human reading it** — that is a direct softening of the SHA-pin trust model and the "a human has read the changelog/source surface" clause in `SUPPLY-CHAIN.md §2.4`. If adopted, it should be minuted as a conscious exception and kept to patch-level `actions/*`/`docker/*` only. **Default answer: leave it off.**

---

## 6. Coverage scope — why `github-actions` only

- **`github-actions` — YES.** This is the actual pain (Node-20 deprecations) and the clean win.
- **`docker` (Dockerfile base) — NO / redundant.** `Dockerfile` deliberately uses a **build-arg floating tag** (`ARG BASE_IMAGE=python:3.12-slim`) and the `release.yml` `publish` job **re-resolves the live digest fresh at build time** (`docker buildx imagetools inspect … --format '{{.Manifest.Digest}}'`) and records it in SLSA provenance. `SUPPLY-CHAIN.md §5` explicitly calls base-digest renewal "manual + intentional… each release pins whatever is current." A Dependabot `docker` pin would hard-code a `@sha256:…` into the Dockerfile, **fighting** that design (the fresh-resolve is the source of truth). Skip it.
- **`pip` (dev/service/packaging extras) — NO / near-no-op here.** These extras are declared with **open lower-bound ranges** (`fastapi>=0.110`, `pytest>=8`, `mypy>=1.9`, `pyinstaller>=6.0`, …) in `pyproject.toml` and there is **no lockfile**. Dependabot's `pip` version-updater only bumps a manifest when a newer version would **violate** the constraint (or for a security advisory) — with open `>=` ranges and no lock, that means it opens essentially **no** version PRs. So the `pip` ecosystem would add config surface for ~zero value. (The `dev`/`service` extras are dev-tooling, not the stdlib-only shipping core, so updating them _would_ be allowed — it's just not useful without pinned versions or a lockfile.) If the operator later pins these or adds a lockfile, revisit. Security-only `pip` alerts are already covered advisorily by `pip-audit` in `heavy.yml`.

---

## 7. Should this be a CI-hygiene ticket? Yes.

Recommend a small standalone ticket, disjoint from the SR/gateway code tickets:

- **Title:** _CI hygiene — mechanize GitHub Actions SHA-pin bumps via Dependabot_
- **`owns:`** `.github/dependabot.yml` (single new file). No collision with any SR/gateway code ticket; no workflow file is touched by the core deliverable.
- **Deliverable:** commit the §8 config; confirm the first weekly Dependabot PR keeps SHA pins + updates comments; a maintainer merges it.
- **Optional follow-on (separate, touches workflows — declare `owns: .github/workflows/*.yml`):** the actor-aware `runs-on` hardening from §4(b) to keep unvetted bump-PR action code off 4-lom.
- **D&S:** no dependency on the SR code tickets (config-only, disjoint owns). Can land any time.

---

## 8. Drop-in config — `.github/dependabot.yml`

```yaml
# Mechanizes GitHub Actions version bumps so pinned action SHAs (and their
# trailing `# vX` comments) never go stale — clears Node-20-style deprecations.
# Dependabot bumps SHA -> new SHA (never reverts to a floating @tag) and rewrites
# the trailing version comment to match (comment must be at end-of-line, which all
# of Charon's pins are). See docs/SUPPLY-CHAIN.md §5 — the SHA-pin posture is
# preserved. PR-only (D006 propose-default): a human reviews the SHA and merges.
#
# Scope is github-actions ONLY, deliberately:
#   - docker: the Dockerfile base is a build-arg re-resolved fresh at release time
#     (release.yml `publish`), so a Dockerfile digest pin would fight that design.
#   - pip: the [dev]/[service]/[packaging] extras use open `>=` ranges with no
#     lockfile, so pip version-updates would be near-no-ops here.
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"                 # scans all of .github/workflows/*.yml
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "Etc/UTC"
    open-pull-requests-limit: 5
    commit-message:
      prefix: "ci"                 # e.g. "ci(deps): bump actions/checkout ..."
    labels:
      - "dependencies"
      - "github-actions"
    # One grouped PR for all action bumps per week -> minimal review churn,
    # keeps the noise from major-tag SHA moves (dependabot-core#13466) in check.
    groups:
      github-actions:
        patterns:
          - "*"
```

That is the entire change: one new file, no workflow edits, no infra.

---

## Sources

- [Dependabot updates comments in GitHub Actions workflows referencing action versions — GitHub Changelog, 2022-10-31](https://github.blog/changelog/2022-10-31-dependabot-now-updates-comments-in-github-actions-workflows-referencing-action-versions/)
- [dependabot-core#5951 — Update version comments for SHA-pinned GitHub Actions](https://github.com/dependabot/dependabot-core/pull/5951)
- [dependabot-core#7912 — version comment only updated when at end of line](https://github.com/dependabot/dependabot-core/issues/7912)
- [dependabot-core#4691 — bump the human-readable version in the code comment for hash-pinned actions](https://github.com/dependabot/dependabot-core/issues/4691)
- [dependabot-core#2835 — Secure updates for GitHub Actions (SHA pinning is first-class)](https://github.com/dependabot/dependabot-core/issues/2835)
- [dependabot-core#13466 — hash pins follow the moving ref (closed/Done)](https://github.com/dependabot/dependabot-core/issues/13466)
- [Renovate github-actions manager + helpers:pinGitHubActionDigests — Renovate Docs](https://docs.renovatebot.com/modules/manager/github-actions/)
- [Dependabot vs Renovate (2026-05-13) — tenthirtyam.org](https://tenthirtyam.org/dispatches/2026/05/13/dependabot-vs-renovate-dependency-management-on-github/)
- [About Dependabot on GitHub Actions runners — GitHub Docs (self-hosted not used on public repos)](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/about-dependabot-on-github-actions-runners)
- [Dependabot on GitHub Actions — GitHub Docs (read-only token, no secrets on PR runs)](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-on-actions)

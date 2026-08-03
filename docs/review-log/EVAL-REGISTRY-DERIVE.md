# EVAL-REGISTRY-DERIVE — review notes

## Implementation decisions

1. **Python3 heredoc pattern**: Followed the existing `reconcile-gate-wired.sh` pattern
   (bash wrapper + Python3 heredoc). Gives us clean JSON/TOML parsing without jq dependency.

2. **Inventory sources**: Generate from committed files only (pyproject.toml, graph.json,
   gates.json, TOOL-INVENTORY.md). `command -v` for installed binaries was excluded from
   the deterministic inventory to guarantee byte-identical regeneration — runtime binary
   presence varies across machines.

3. **Tool name matching**: Case-insensitive. Registry tool names are normalised to lowercase
   for matching. The inventory uses lowercase keys derived from gate IDs, dependency names,
   and tool references.

4. **Markdown table parsing**: Handles escaped pipes (`\|`) in cell content. Rows with
   embedded pipes in reason/evidence columns are correctly parsed by merging excess split
   parts back into the appropriate column.

5. **Alignment parseability**: Extracts the first token from alignment cells using regex
   `(aligned|drifted|mixed|n-a)` with optional bold markup. Currently all 66 rows parse
   cleanly against the current registry.

## Out-of-scope (owns constraint)

The reconciler DETECTS drift but cannot EDIT the registry. The following require
follow-up tickets owning the files they edit:

- **Alignment normalisation**: Needs a ticket owning `fleet/state/EVAL-REGISTRY.md`
- **L1 substrate-first-gate extension**: Needs a ticket owning `fleet/checks/substrate-first-gate.sh`
- **L2 CI_SUITES entry**: Needs a ticket owning `fleet/checks/rig-ci-scope.sh`
- **L3 cron registration**: Needs a ticket owning the crontab management
- **L4 pending.sh escalation**: Needs a ticket owning the escalation caller

## S2-GROUNDING-MECHANIZED.md

The file `fleet/state/S2-GROUNDING-MECHANIZED.md` does not exist in this repository.
Items 4 and 5 cannot be applied from a non-existent source. The LiteLLM row (#35)
referencing it already carries the correction flag inline in EVAL-REGISTRY.md.

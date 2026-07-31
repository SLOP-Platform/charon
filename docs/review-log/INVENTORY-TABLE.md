# INVENTORY-TABLE — Review Log

## Ticket
INVENTORY-TABLE: Foundation ticket for the self-maintaining-supply lens. The shared
price-tracked inventory SPINE that both the discovery leg and the drift leg consume.
"One table, two writers" (FREE-PROVIDER-DISCOVERY-DESIGN §4).

## What was done

- **`fleet/state/price-tracked-inventory.tsv`** — Canonical TSV with the §3c column
  union (19 columns: source, source_url, provider, base_url, model_ids, funding_class,
  cost_in_usd_mtok, cost_out_usd_mtok, rpd, rpm, tpm, tpd, context_cap, trains_on_data,
  personal_only, exhaustion_signal, first_seen, last_seen, status). Seeded with the
  operator's 2026-07-23 inventory rows covering the 13 providers listed in the ticket.
  Writer partition documented in-file.

- **`fleet/inventory-table.sh`** — stdlib accessor with four commands:
  `init` / `read` / `upsert-row` / `list-by-status`. Keyed on (provider,
  normalized_model_id). Model identity via `charon.proxy._normalize_model_id` (reused
  verbatim via embedded Python, PYTHONPATH=$CHARON_SRC). Writer partition documented
  in the script's header docstring.

## Key decisions

1. **Python engine for key identity**: The accessor embeds a Python engine that imports
   `_normalize_model_id` from charon.proxy verbatim. This ensures inventory dedup ==
   router identity. The awk-based comparison approach was considered but discarded —
   awk cannot import Python's regex-based quant suffix stripping, and re-implementing
   `_QUANT_SUFFIX` in awk would drift. One `python3` spawn per accessor call is
   acceptable for a data-table accessor.

2. **Name-based row identity**: The awk-based upsert in an earlier iteration had a bug
   where `exit` inside the `for` loop terminated the entire awk process instead of
   skipping just the matched row. Moved the entire read/upsert logic to Python where
   the control flow is unambiguous.

3. **Seed data**: The seed rows reflect the 13 providers listed in the ticket
   (synthetic, trae, HF, nous, grok, mistral, zai, cerebras, deepinfra, deepseek,
   together, groq, morph) with status=candidate. Model_ids and cost data are populated
   from the operator's known inventory as of 2026-07-23.

## Scope check

`git diff --name-only master...HEAD`:
- fleet/state/price-tracked-inventory.tsv ✓ (owned)
- fleet/inventory-table.sh ✓ (owned)
- docs/review-log/INVENTORY-TABLE.md ✓ (review fragment, per-ticket)

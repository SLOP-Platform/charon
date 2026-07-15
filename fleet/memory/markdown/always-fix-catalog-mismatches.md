---
description: "catalog/routing/config mismatches must ALWAYS be fixed on sight, never left — and mechanize detection"
metadata: 
name: always-fix-catalog-mismatches
node_type: memory
originSessionId: aaf1f929-5adf-4f7f-862d-792cd64617af
type: feedback
tags: [catalog]
last_referenced: 2026-07-13
---
FEEDBACK / DIRECTIVE (operator, 2026-07-08): all catalog mismatches should ALWAYS be fixed — never leave a catalog / routing / config mismatch unreconciled.

**Origin:** `src/charon/model_catalog.py` lists `gpt-5.5` in its high tier while the live workhorse is `gpt-5.4` (routed via nanogpt/openrouter config, not the curated catalog) — a silent mismatch between the catalog's source-of-truth and live routing.

**How to apply:** fix on sight (file a reconcile ticket + fix), AND mechanize detection via the catalog drift detector (#30 `CATALOG-SYNC-DRIFT`) so mismatches surface automatically instead of lurking. A catalog that disagrees with live routing corrupts anything that reads it (tier substitution / P2, recommendations, grades). Relates [[never-ignore-preexisting-issues]].

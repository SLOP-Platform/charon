tier: frontier
work_class: money-path
branch: fix/billing-est-cost
depends_on:
owns: src/charon/forwarder.py, tests/test_forwarder_billing.py
accept: PYTHONPATH=src python3 -m pytest tests/test_forwarder_billing.py -q
prompt: /home/stack/charon-private/scratch/briefs/BILLING-EST-COST-FIX.md
scope: Stop billing the est_cost floor when a provider reports a real $0 (free/flat routes). forwarder.py:315 (non-stream) and :400 (stream) record `cost if cost>0 else est_cost` — the phantom _pre_flight_estimate floor is billed on EVERY free/flat $0 response, inflating spend.json to the fictional ~$223. Record 0.0 for cost_source in {free, provider(0)}; only substitute est_cost when genuinely unpriced. Bonus (same file, fold in): forwarder.py:296-300 feeds the WHOLE JSON body to response_normalizer.normalize — fix so the post-hook only touches choices[0].message.content.
note: Money-path — ADVERSARIAL review before merge. Wave 1. Out-of-band post-merge+deploy step (manager, NOT the droid): reset /data/spend.json spent_usd 223.28 -> 0 on 10.0.1.60.

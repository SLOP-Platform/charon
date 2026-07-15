# Path C dogfood-eval — TOOL-REPAIR-MUTATING (20260714T015426Z)

| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |
|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4-pro | REVIEW-READY(candidate-for-merge; human must still read the diff) | ran-to-completion | 201 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-deepseek-v4-pro-20260714T015426Z.card.md |
| deepseek-v4-flash | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(limit-hit) | 95 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-deepseek-v4-flash-20260714T015426Z.card.md |
| kimi-k2.6 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(limit-hit) | 259 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-kimi-k2.6-20260714T015426Z.card.md |
| phi-4 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(all-exhausted) | 2 | 900 | skipped | pass | early-ditch-no-diff(quality-fail) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-phi-4-20260714T015426Z.card.md |

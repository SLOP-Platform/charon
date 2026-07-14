# Path C dogfood-eval — TOOL-REPAIR-MUTATING (20260714T002000Z)

| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |
|---|---|---|---|---|---|---|---|---|---|
| minimax-m2.7 | REVIEW-READY(candidate-for-merge; human must still read the diff) | ran-to-completion | 171 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-minimax-m2.7-20260714T002000Z.card.md |
| deepseek-v4-pro | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(limit-hit) | 280 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-deepseek-v4-pro-20260714T002000Z.card.md |
| deepseek-v4-flash | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(limit-hit) | 56 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-deepseek-v4-flash-20260714T002000Z.card.md |
| glm-5.2 | REVIEW-READY(candidate-for-merge; human must still read the diff) | ran-to-completion | 320 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-glm-5.2-20260714T002000Z.card.md |
| kimi-k2.6 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(limit-hit) | 782 | 900 | pass | pass | real-diff(files=2) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-kimi-k2.6-20260714T002000Z.card.md |
| phi-4 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(all-exhausted) | 1 | 900 | skipped | pass | early-ditch-no-diff(quality-fail) | in-scope(matches owns:) | dogfood-TOOL-REPAIR-MUTATING-phi-4-20260714T002000Z.card.md |

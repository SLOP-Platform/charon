# Path C dogfood-eval — PROVIDER-URL-HELPER (20260714T002000Z)

| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |
|---|---|---|---|---|---|---|---|---|---|
| minimax-m2.7 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(all-exhausted) | 1 | 1200 | skipped | fail | early-ditch-no-diff(quality-fail) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-minimax-m2.7-20260714T002000Z.card.md |
| deepseek-v4-pro | REVIEW-READY(candidate-for-merge; human must still read the diff) | ran-to-completion | 314 | 1200 | pass | pass | real-diff(files=4) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-deepseek-v4-pro-20260714T002000Z.card.md |
| deepseek-v4-flash | FIXES-NEEDED | ran-to-completion | 96 | 1200 | fail | pass | real-diff(files=4) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-deepseek-v4-flash-20260714T002000Z.card.md |
| glm-5.2 | FIXES-NEEDED | ran-to-completion | 374 | 1200 | fail | fail | real-diff(files=4) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-glm-5.2-20260714T002000Z.card.md |
| kimi-k2.6 | FIXES-NEEDED | ran-to-completion | 583 | 1200 | fail | pass | real-diff(files=4) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-kimi-k2.6-20260714T002000Z.card.md |
| phi-4 | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(all-exhausted) | 2 | 1200 | skipped | fail | early-ditch-no-diff(quality-fail) | in-scope(matches owns:) | dogfood-PROVIDER-URL-HELPER-phi-4-20260714T002000Z.card.md |

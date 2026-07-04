"""Cross-provider consensus routing (ADOPT B3.3).

Opt-in per request via X-Charon-Consensus: N header. Sends to N
providers, computes token-Jaccard similarity, and returns the
majority response when agreement >= threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsensusResult:
    agreed: bool = False
    responses: list[dict] = field(default_factory=list)
    agreement_score: float = 0.0
    majority_index: int = -1


class ConsensusRouter:
    def __init__(self, default_count: int = 3, similarity: float = 0.8,
                 enabled: bool = True):
        self.default_count = default_count
        self.similarity = similarity
        self.enabled = enabled

    def verify(self, provider_responses: list[tuple[str, str]],
               count: int = 0) -> ConsensusResult:
        if not self.enabled or len(provider_responses) < 2:
            return ConsensusResult(responses=[{"provider": p, "content": c}
                                               for p, c in provider_responses])
        n = count or self.default_count
        responses = provider_responses[:n]
        scores: list[float] = []
        tokenised = [_tokenise(c) for _, c in responses]
        for i in range(len(responses)):
            total = 0.0
            for j in range(len(responses)):
                if i != j:
                    total += _jaccard(tokenised[i], tokenised[j])
            scores.append(total / (len(responses) - 1) if len(responses) > 1 else 0.0)
        max_score = max(scores)
        majority_idx = scores.index(max_score)
        return ConsensusResult(
            agreed=max_score >= self.similarity,
            responses=[{"provider": p, "content": c} for p, c in responses],
            agreement_score=max_score,
            majority_index=majority_idx,
        )


def _tokenise(text: str) -> set[str]:
    return set(text.lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

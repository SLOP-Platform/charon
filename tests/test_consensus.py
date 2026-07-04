from __future__ import annotations

from charon.consensus import ConsensusRouter, _jaccard, _tokenise


def test_tokenise_splits_words() -> None:
    assert _tokenise("hello world") == {"hello", "world"}


def test_tokenise_case_insensitive() -> None:
    assert _tokenise("Hello WORLD") == {"hello", "world"}


def test_jaccard_identical() -> None:
    a = _tokenise("the cat sat")
    b = _tokenise("the cat sat")
    assert _jaccard(a, b) == 1.0


def test_jaccard_disjoint() -> None:
    a = _tokenise("hello world")
    b = _tokenise("foo bar")
    assert _jaccard(a, b) == 0.0


def test_jaccard_partial() -> None:
    a = _tokenise("the cat sat on the mat")
    b = _tokenise("the dog sat on the mat")
    score = _jaccard(a, b)
    assert 0.4 < score < 0.9


def test_jaccard_both_empty() -> None:
    assert _jaccard(set(), set()) == 1.0


def test_verify_disabled_bypasses() -> None:
    cr = ConsensusRouter(enabled=False)
    result = cr.verify([("openai", "hello world"), ("together", "hello world")])
    assert result.agreed is False
    assert len(result.responses) == 2


def test_verify_agreed_identical_responses() -> None:
    cr = ConsensusRouter(similarity=0.5)
    result = cr.verify([
        ("openai", "the quick brown fox jumps over the lazy dog"),
        ("together", "the quick brown fox jumps over the lazy dog"),
        ("groq", "the quick brown fox jumps over the lazy dog"),
    ])
    assert result.agreed is True
    assert result.agreement_score == 1.0


def test_verify_disagreed_divergent() -> None:
    cr = ConsensusRouter(similarity=0.5)
    result = cr.verify([
        ("openai", "the quick brown fox"),
        ("together", "completely different response here"),
        ("groq", "something else entirely"),
    ])
    assert result.agreed is False


def test_verify_single_response() -> None:
    cr = ConsensusRouter()
    result = cr.verify([("openai", "hello")])
    assert result.agreed is False
    assert result.majority_index == -1  # single response has no majority


def test_verify_majority_index_correct() -> None:
    cr = ConsensusRouter(similarity=0.3)
    result = cr.verify([
        ("A", "one two three four five"),
        ("B", "one two three four five"),
        ("C", "apple banana cherry date"),
    ])
    assert result.majority_index in (0, 1)

#!/usr/bin/env python3
"""Grader for item `translation-en-fr`.

The grader checks the translation contains specific French vocabulary
corresponding to the key English terms in the source paragraph. We do
NOT use a model grader (no API calls) and we do NOT use string-match on
the literal French — we check that the translation covers the same
semantic content as the source (a faithful rendering must mention each
key term in some form). The vocabulary set is intentionally
multi-acceptable: a faithful French rendering uses one of several valid
translations for each term.

This is the calibration anchor for `translation` work_class: a strong
model produces a faithful French rendering; a weak model produces
either an English answer or a literal word-for-word gloss.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


# Source paragraph: "The gateway receives a request, inspects the message
# for any images, and routes the request to a model that supports
# vision. If no vision-capable model is available, the request fails
# with a clear error."
#
# Each key concept must appear in some French form. The expected
# vocabulary list intentionally includes several acceptable translations
# per concept (e.g. "passerelle", "portail" for "gateway") to avoid
# punishing lexical choice while still requiring semantic coverage.
KEY_CONCEPTS = (
    ("gateway", ("passerelle", "portail", "gateway", "service", "routeur")),
    ("request", ("requête", "demande")),
    ("image", ("image", "images")),
    ("vision", ("vision",)),
    ("model", ("modèle",)),
    ("error", ("erreur",)),
    ("fail", ("échoue", "échec", "erreur", "refuse")),
)


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore").lower()
    if len(text) < 100:
        return fail_closed(f"answer too short ({len(text)} chars; expected a paragraph)")
    missing = []
    for concept, options in KEY_CONCEPTS:
        if not any(opt in text for opt in options):
            missing.append(concept)
    if missing:
        return fail_closed(f"translation missing these concepts: {missing}")
    return pass_result(100, "faithful French translation covering all 7 key concepts")

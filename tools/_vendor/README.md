# Vendored detectors

This directory holds small, verbatim (or near-verbatim) copies of third-party
detector code that Charon depends on for gating, but does not want as a
runtime/install-time dependency (PyPI package or cross-repo local path).

## ksf_inert_code.py / ksf_gate_result.py

Source: KSF (Keystone Framework), a sibling development checkout —
`ksf/gates/inert_code.py` and `ksf/gate_result.py`.

Why vendored instead of `pip install`-ed or imported via a local path
dependency: KSF lives in a sibling repo on the operator's machine. A
`pip install -e ../keystone`-style dependency would break for any fresh clone
of this product repo (the sibling checkout would not exist), and Charon's
product-vs-build-rig boundary rule says local dev infra must never leak into
the shipped product. Vendoring keeps the detector logic (confirmed
best-in-class registration-aware call-graph reachability analysis — see
`tools/check_inert_code.py`'s docstring) while keeping the product
self-contained.

**Changes from the KSF originals**: none, except the single
`from ksf.gate_result import GateResult` import line in `ksf_inert_code.py`,
which now points at the sibling vendored `ksf_gate_result.py` instead of the
`ksf` package. Every other line of logic is untouched.

**Re-syncing**: if KSF's `inert_code.py` changes upstream, re-copy the file
here, re-apply the same one-line import change, and re-apply the vendoring
header comment. Do not hand-edit the detector logic itself in this
directory — fix it upstream in KSF first, then re-sync.

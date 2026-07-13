---
description: "KSF design philosophy — high-level, blast-radius-aware, outside-the-box, KISS-where-logical, clean/cheap/elegant, CLASS-not-individual"
metadata: 
name: ksf-design-philosophy
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: reference
tags: [design, ksf]
last_referenced: 2026-07-13
---
Keystone Framework (KSF) design philosophy (operator, 2026-07-11):
- **High-level** — gates target the general shape of a problem, not a bespoke one-off.
- **Blast-radius aware** — for any gate/change, ask what else it touches / what it would miss.
- **Outside-the-box** — never assume that because something is done a certain way there isn't a cleaner/better way; challenge the default.
- **KISS where logical** — the simplest mechanism that closes the class; don't over-build.
- **Clean / cheap / elegant** — prefer solutions that are inexpensive to run + maintain and cover a whole class.
- **CLASS not individual** — every gate/lens exists to catch a CLASS of issue (e.g. "built-but-inert", "artifact≠source drift", "silent-failure masking"), never a single incident. When a bug is fixed, abstract its CLASS and mechanize the class.
- **META over monolith AND over explosion (Goldilocks)** — prefer META-invariant gates: ONE gate enforces the invariant for a whole class (e.g. "every rule is wired" = coverage-SSOT; "every entrypoint has a test importing it" = production-path=test-path). NOT a handful of giant catch-all gates, and NOT hundreds/thousands of narrow per-instance checks.
- **Registry-driven, scale by DATA not code** — where a class has many instances, make the gate registry-driven: add a data entry (pattern/rule) to a registry file and the ONE gate enforces all entries. Forbid minting narrow per-instance gate scripts (anti-accretion / open-seam); extend a lens or add a registry row instead.

This drives the KSF gate library (KS9–KS19+) and how we mine history for unmechanized classes. Extends [[green-is-not-proof]], [[decomposed-by-design-not-reactive]], [[confirm-dont-trust-documentation]].

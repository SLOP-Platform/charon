---
description: "DECISION — KSF stdlib-only applies to CORE only; PLUGINS wrap INDUSTRY best-in-class tools FIRST (don't reimplement); a \"stdlib-only/adds-a-dep\" objection is INVALID at the plugin layer"
metadata: 
name: ksf-modular-plugin-best-in-class
node_type: memory
originSessionId: e2478a55-c53f-48cc-9378-5c328f54aa8f
type: project
tags: [design, ksf, modularity]
last_referenced: 2026-07-13
---
KSF (Keystone gate framework) is being built as a **modular gate framework with a PLUGIN architecture**. The stdlib-only / self-contained constraint applies **ONLY to KSF's CORE** (the gate engine + integrity gates). **PLUGINS should adopt industry best-in-class external tools FIRST** (ruff, mypy, bandit, vulture, semgrep, etc.) rather than reimplement them in stdlib.

Decided in the session **prior to 2026-07-11**.

**Why:** reimplementing mature tools in stdlib is wasted effort and worse quality; the plugin layer is exactly where third-party deps belong.

**How to apply:** any "should we wrap tool X into KSF" evaluation MUST use this lens. A stdlib-only / "adds a dependency" / "self-contained product" objection is **INVALID for the plugin layer** and warps the verdict — it inverted the 2026-07-11 `fleet/state/KSF-LINTER-TOOLS-REVIEW.md` into a false NO-GO. Core = stdlib; plugins = best-in-class wrappers. Re-run any such review with plugin-first framing.

Related: [[decomposed-by-design-not-reactive]], [[charon-modular-agent-and-provider-agnostic]].

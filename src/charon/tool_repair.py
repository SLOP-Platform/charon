"""Tool-call repair module — schema-only validate-then-repair engine.

Operates on choices[].message.tool_calls[].function.arguments strings against
declared JSON-schema parameters.  All operations are stdlib-only — no network,
no third-party dependencies.  Each rule is small, deterministic, and ordered.

Symmetric to response_normalizer.py: that module repairs content *strings*;
this module repairs tool-call *arguments*.  Same shape: stdlib-only, a public
class + small ordered private helper rules, from __future__ import annotations.

Mutating-call gate
-------------------
The module does NOT classify tool calls as mutating or non-mutating.  The
caller supplies an `is_mutating` marker, either:

  * inline on the tool_call dict (`tool_call["is_mutating"]`), or
  * declared on the JSON-schema dict (top-level `"is_mutating": True/False`).

When `allow_mutating=False` and the call is marked mutating by either source,
the module short-circuits and returns the original arguments unchanged —
no rule fires, no counter increments, the caller passes the call through
untouched.  This gate exists to prevent accidental semantic rewrite of
state-changing calls; the deferred proxy wiring is responsible for
classifying the call and for honoring the policy flag from config.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

# -------------------------------------------------------------------
# Public result type
# -----------------------------------------------------------------


@dataclasses.dataclass
class RepairResult:
    """Result of a repair attempt on a single tool call's arguments string."""

    arguments: str
    """The repaired arguments string (or original if unrepaired)."""

    changed: bool
    """True when one or more repair rules modified the string."""

    fired_rules: list[str]
    """Ordered list of rule names that fired (empty if no repair was done)."""

    unrepaired: bool = False
    """True when repair was attempted but could not produce valid output."""


# -------------------------------------------------------------------
# Private helpers — ordered repair rules
# -------------------------------------------------------------------

_SINGLE_QUOTED_KEY_RE = re.compile(r"""(^|\{|\,)\s*'([^']+)'\s*:""")
_SINGLE_QUOTED_VALUE_RE = re.compile(r""":\s*'([^']*)'\s*([,}\]])""")
_UNQUOTED_KEY_RE = re.compile(r"""(^|\{|\,)\s*([a-zA-Z_]\w*)\s*:""")
_TRAILING_COMMA_RE = re.compile(r""",\s*(\}|\])""")
_NUMERIC_INT_RE = re.compile(r"^[+-]?\d+$")
_NUMERIC_FLOAT_RE = re.compile(r"^[+-]?\d+\.?\d*([eE][+-]?\d+)?$")


def _fix_trailing_commas(arguments: str) -> str:
    """Remove trailing commas before } or ]."""
    return _TRAILING_COMMA_RE.sub(r"\1", arguments)


def _fix_single_quoted_keys(arguments: str) -> str:
    """Convert single-quoted JSON keys to double-quoted."""

    def _replacer(m: re.Match[str]) -> str:
        prefix = m.group(1)
        key = m.group(2)
        return f'{prefix}"{key}":'

    return _SINGLE_QUOTED_KEY_RE.sub(_replacer, arguments)


def _fix_single_quoted_strings(arguments: str) -> str:
    """Convert single-quoted JSON string values to double-quoted."""

    def _replacer(m: re.Match[str]) -> str:
        value = m.group(1)
        suffix = m.group(2)
        escaped = value.replace('"', '\\"')
        return f': "{escaped}"{suffix}'

    return _SINGLE_QUOTED_VALUE_RE.sub(_replacer, arguments)


def _fix_unquoted_keys(arguments: str) -> str:
    """Quote unquoted object keys."""

    def _replacer(m: re.Match[str]) -> str:
        prefix = m.group(1)
        key = m.group(2)
        return f'{prefix}"{key}":'

    return _UNQUOTED_KEY_RE.sub(_replacer, arguments)


def _fix_stringified_json(arguments: str) -> str:
    """Unwrap a JSON-string-wrapped object/array one level.

    When the entire arguments is a JSON string containing another JSON
    object or array, e.g. '"{\\"a\\": 1}"' -> '{"a": 1}'.
    """
    try:
        parsed = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return arguments
    if isinstance(parsed, str) and (
        parsed.strip().startswith("{") or parsed.strip().startswith("[")
    ):
        return parsed
    return arguments


def _coerce_from_schema(arguments: str, schema: dict[str, Any] | None) -> str:
    """Coerce primitive values guided by the JSON schema.

    Only coerces when the schema declares the property type.
    Never coerces without a schema or when type is absent.
    """
    if not schema or "properties" not in schema:
        return arguments
    try:
        obj = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return arguments
    if not isinstance(obj, dict):
        return arguments
    changed = False
    props: dict[str, Any] = schema.get("properties", {})
    for key, prop_schema in props.items():
        if key not in obj:
            continue
        ptype = prop_schema.get("type") if isinstance(prop_schema, dict) else None
        if ptype is None:
            continue
        val = obj[key]
        if ptype == "boolean" and isinstance(val, str) and val in ("true", "false"):
            obj[key] = val == "true"
            changed = True
        elif ptype in ("integer", "number") and isinstance(val, str):
            if ptype == "integer" and _NUMERIC_INT_RE.match(val.strip()):
                obj[key] = int(val)
                changed = True
            elif ptype == "number" and _NUMERIC_FLOAT_RE.match(val.strip()):
                try:
                    obj[key] = float(val)
                except (ValueError, OverflowError):
                    pass
                else:
                    changed = True
        elif ptype in ("object", "array") and isinstance(val, str):
            try:
                parsed_val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                continue
            if (ptype == "object" and isinstance(parsed_val, dict)) or (
                ptype == "array" and isinstance(parsed_val, list)
            ):
                obj[key] = parsed_val
                changed = True
    return json.dumps(obj) if changed else arguments


# -------------------------------------------------------------------
# Rule table — ordered, each (name, function, mutating-safe bool)
# -------------------------------------------------------------------

_RULE_NAME = 0
_RULE_FN = 1
_RULE_MUTATING_SAFE = 2

_RULES: list[tuple[str, Any, bool]] = [
    ("fix_trailing_commas", _fix_trailing_commas, True),
    ("fix_single_quoted_keys", _fix_single_quoted_keys, True),
    ("fix_single_quoted_strings", _fix_single_quoted_strings, True),
    ("fix_unquoted_keys", _fix_unquoted_keys, True),
    ("fix_stringified_json", _fix_stringified_json, True),
    # _coerce_from_schema is special: it needs the schema arg — handled
    # inline in repair_arguments, not in the ordered table.
]


def _light_validate(obj: Any, schema: dict[str, Any] | None) -> bool:
    """Shallow structural validation — no jsonschema, stdlib only.

    Checks: required keys present, top-level type matches, property
    primitive types match.  Does NOT recurse into nested schemas.
    """
    if schema is None:
        return True
    required: list[str] = schema.get("required", []) or []
    if isinstance(obj, dict):
        if schema.get("type") and schema["type"] != "object":
            return False
        for req_key in required:
            if req_key not in obj:
                return False
        props: dict[str, Any] = schema.get("properties", {})
        for key, val in obj.items():
            if key in props and isinstance(props[key], dict):
                ptype = props[key].get("type")
                if ptype == "boolean" and not isinstance(val, bool):
                    return False
                if ptype == "integer" and not isinstance(val, int):
                    return False
                if ptype == "number" and not isinstance(val, (int, float)):
                    return False
                if ptype == "string" and not isinstance(val, str):
                    return False
                if ptype == "array" and not isinstance(val, list):
                    return False
                if ptype == "object" and not isinstance(val, dict):
                    return False
    else:
        stype = schema.get("type")
        if stype == "object" and not isinstance(obj, dict):
            return False
        if stype == "array" and not isinstance(obj, list):
            return False
    return True


# -------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------


class ToolCallRepair:
    """Schema-only tool-call repair engine.

    Each instance tracks its own rule-hit counters.  Stateless otherwise —
    all repair logic operates on the arguments string + schema given to each
    call.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    # ---- primary API ----

    def repair_arguments(
        self,
        arguments: str,
        schema: dict[str, Any] | None = None,
        *,
        allow_mutating: bool = False,
        is_mutating: bool | None = None,
    ) -> RepairResult:
        """Repair a single tool call's arguments string.

        Args:
            arguments: The raw function.arguments string from a tool_call.
            schema: Optional declared JSON-schema parameters dict.  May carry
                a top-level ``is_mutating`` boolean; when set, it is the
                schema-declared mutating marker and overrides the ``is_mutating``
                kwarg (the schema is the registry's declaration of intent).
            allow_mutating: When False (default), repair is short-circuited for
                tool calls marked as state-mutating — the original arguments
                string is returned unchanged, no rules fire, no counters move.
                The caller (deferred proxy wiring) passes this from config.
            is_mutating: Optional caller-supplied mutating marker.  When None
                (default) and the schema has no top-level ``is_mutating`` key,
                the call is treated as non-mutating for gating purposes.

        Returns:
            RepairResult with the repaired string (or original), changed flag,
            and list of rule names that fired.
        """
        if not isinstance(arguments, str):
            return RepairResult(
                arguments=arguments, changed=False, fired_rules=[], unrepaired=True
            )

        # ---- mutating-call gate ----
        # Schema-declared is_mutating wins over the kwarg: the schema is the
        # registry's authoritative declaration of which calls are mutating.
        if isinstance(schema, dict) and "is_mutating" in schema:
            mutating = bool(schema["is_mutating"])
        else:
            mutating = bool(is_mutating) if is_mutating is not None else False
        if mutating and not allow_mutating:
            return RepairResult(
                arguments=arguments, changed=False, fired_rules=[]
            )

        working = arguments
        fired: list[str] = []

        # Unwrap stringified JSON first — a valid JSON string that wraps an
        # object/array is a format error, not a semantic one; unwrap before
        # the validate-then-repair guard so it gets a chance to fire.
        pre_unwrap = working
        working = _fix_stringified_json(working)
        if working != pre_unwrap:
            fired.append("fix_stringified_json")
            self._counters["fix_stringified_json"] = (
                self._counters.get("fix_stringified_json", 0) + 1
            )

        # Validate-then-repair: if it already parses + validates, return unchanged.
        try:
            obj = json.loads(working)
        except (json.JSONDecodeError, TypeError):
            pass
        else:
            if _light_validate(obj, schema):
                if fired:
                    return RepairResult(
                        arguments=working,
                        changed=working != arguments,
                        fired_rules=fired,
                    )
                return RepairResult(
                    arguments=arguments, changed=False, fired_rules=[]
                )

        # Apply ordered formatting rules (skip fix_stringified_json — already
        # applied above before the validate-then-repair guard).
        # Rule table can later be scoped per-(model, provider).
        for name, fn, _m_safe in _RULES:
            if name == "fix_stringified_json":
                continue
            prev = working
            working = fn(working)
            if working != prev:
                fired.append(name)
                self._counters[name] = self._counters.get(name, 0) + 1

        # Schema-guided coercion (has its own validate-then-repair internal guard).
        pre_coerce = working
        working = _coerce_from_schema(working, schema)
        if working != pre_coerce:
            fired.append("coerce_from_schema")
            self._counters["coerce_from_schema"] = (
                self._counters.get("coerce_from_schema", 0) + 1
            )

        # Final validation.
        try:
            obj_final = json.loads(working)
        except (json.JSONDecodeError, TypeError):
            return RepairResult(
                arguments=arguments,
                changed=False,
                fired_rules=fired,
                unrepaired=True,
            )

        if _light_validate(obj_final, schema):
            return RepairResult(
                arguments=working,
                changed=working != arguments,
                fired_rules=fired,
            )
        else:
            return RepairResult(
                arguments=arguments,
                changed=False,
                fired_rules=fired,
                unrepaired=True,
            )

    def repair_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        schemas: dict[str, dict[str, Any]],
        *,
        allow_mutating: bool = False,
    ) -> tuple[list[dict[str, Any]], list[RepairResult]]:
        """Convenience wrapper — repair a list of tool_call dicts in place.

        Args:
            tool_calls: List of tool_call dicts (each has function.name
                and function.arguments).  May carry a top-level
                ``is_mutating`` boolean to mark the call as state-mutating.
            schemas: Dict mapping tool name -> JSON schema for its parameters.
                Each schema may also declare a top-level ``is_mutating``.
            allow_mutating: Forwarded to repair_arguments.

        Returns:
            (repaired tool_calls, list of RepairResults one per call).
        """
        results: list[RepairResult] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            schema = schemas.get(name)
            # Per-call is_mutating marker on the tool_call dict, so the
            # caller can flag a single call mutating even when the schema
            # is shared across many calls.
            tc_is_mutating = tc.get("is_mutating")
            result = self.repair_arguments(
                fn.get("arguments", ""),
                schema,
                allow_mutating=allow_mutating,
                is_mutating=tc_is_mutating,
            )
            if result.changed:
                fn["arguments"] = result.arguments
            results.append(result)
        return tool_calls, results

    # ---- observability ----

    def counters(self) -> dict[str, int]:
        """Return a copy of rule-hit counters — which rules fired, how often."""
        return dict(self._counters)

    def reset_counters(self) -> None:
        """Reset all counters to zero."""
        self._counters.clear()

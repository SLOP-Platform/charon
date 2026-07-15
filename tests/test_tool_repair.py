"""Tests for tool_repair.py — hermetic, no network."""
from __future__ import annotations

import json

from charon.tool_repair import ToolCallRepair

# -------------------------------------------------------------------
# Already-valid — unchanged
# -----------------------------------------------------------------


def test_valid_unchanged():
    rep = ToolCallRepair()
    args = '{"a": 1}'
    result = rep.repair_arguments(args, {"properties": {"a": {"type": "integer"}}})
    assert result.arguments == args
    assert result.changed is False
    assert result.fired_rules == []
    assert result.unrepaired is False


def test_valid_no_schema_unchanged():
    rep = ToolCallRepair()
    args = '{"a": 1}'
    result = rep.repair_arguments(args)
    assert result.arguments == args
    assert result.changed is False
    assert result.fired_rules == []
    assert result.unrepaired is False


# -------------------------------------------------------------------
# Trailing commas
# -----------------------------------------------------------------


def test_trailing_comma_repaired():
    rep = ToolCallRepair()
    args = '{"a": 1,}'
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_trailing_commas" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"a": 1}


def test_trailing_comma_in_array():
    rep = ToolCallRepair()
    args = '{"items": [1, 2,]}'
    result = rep.repair_arguments(args)
    assert result.changed is True
    parsed = json.loads(result.arguments)
    assert parsed == {"items": [1, 2]}


# -------------------------------------------------------------------
# Single-quoted keys
# -----------------------------------------------------------------


def test_single_quoted_keys_repaired():
    rep = ToolCallRepair()
    args = "{'name': 'test'}"
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_single_quoted_keys" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"name": "test"}


# -------------------------------------------------------------------
# Single-quoted string values
# -----------------------------------------------------------------


def test_single_quoted_string_values_repaired():
    rep = ToolCallRepair()
    args = '{"a": \'hello\', "b": \'world\'}'
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_single_quoted_strings" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"a": "hello", "b": "world"}


# -------------------------------------------------------------------
# Unquoted keys
# -----------------------------------------------------------------


def test_unquoted_keys_repaired():
    rep = ToolCallRepair()
    args = "{name: 'test', age: 42}"
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_unquoted_keys" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"name": "test", "age": 42}


# -------------------------------------------------------------------
# Stringified JSON unwrap
# -----------------------------------------------------------------


def test_stringified_json_unwrapped():
    rep = ToolCallRepair()
    args = '"{\\"a\\": 1}"'
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_stringified_json" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"a": 1}


def test_stringified_json_array_unwrapped():
    rep = ToolCallRepair()
    args = '"[1, 2, 3]"'
    result = rep.repair_arguments(args)
    assert result.changed is True
    assert "fix_stringified_json" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == [1, 2, 3]


# -------------------------------------------------------------------
# Schema-guided coercion
# -----------------------------------------------------------------


def test_coerce_integer_from_string():
    rep = ToolCallRepair()
    args = '{"n": "5"}'
    schema = {"properties": {"n": {"type": "integer"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    assert "coerce_from_schema" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"n": 5}
    assert isinstance(parsed["n"], int)


def test_coerce_boolean_from_string():
    rep = ToolCallRepair()
    args = '{"flag": "true"}'
    schema = {"properties": {"flag": {"type": "boolean"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    assert "coerce_from_schema" in result.fired_rules
    parsed = json.loads(result.arguments)
    assert parsed == {"flag": True}
    assert isinstance(parsed["flag"], bool)


def test_coerce_false_from_string():
    rep = ToolCallRepair()
    args = '{"flag": "false"}'
    schema = {"properties": {"flag": {"type": "boolean"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    parsed = json.loads(result.arguments)
    assert parsed == {"flag": False}


def test_coerce_float_from_string():
    rep = ToolCallRepair()
    args = '{"val": "3.14"}'
    schema = {"properties": {"val": {"type": "number"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    parsed = json.loads(result.arguments)
    assert parsed == {"val": 3.14}
    assert isinstance(parsed["val"], float)


def test_no_coerce_without_schema():
    rep = ToolCallRepair()
    args = '{"n": "5"}'
    result = rep.repair_arguments(args)
    assert result.changed is False


def test_no_coerce_when_type_unspecified():
    rep = ToolCallRepair()
    args = '{"n": "5"}'
    schema = {"properties": {"n": {}}}  # no type
    result = rep.repair_arguments(args, schema)
    assert result.changed is False


def test_coerce_object_from_string():
    rep = ToolCallRepair()
    args = '{"data": "{\\"inner\\": 1}"}'
    schema = {"properties": {"data": {"type": "object"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    parsed = json.loads(result.arguments)
    assert parsed == {"data": {"inner": 1}}


def test_coerce_array_from_string():
    rep = ToolCallRepair()
    args = '{"items": "[1, 2, 3]"}'
    schema = {"properties": {"items": {"type": "array"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is True
    parsed = json.loads(result.arguments)
    assert parsed == {"items": [1, 2, 3]}


# -------------------------------------------------------------------
# Safety — semantic values never altered
# -----------------------------------------------------------------


def test_missing_required_not_fabricated():
    rep = ToolCallRepair()
    args = "{}"
    schema = {"required": ["name"], "properties": {"name": {"type": "string"}}}
    result = rep.repair_arguments(args, schema)
    assert result.unrepaired is True
    assert result.changed is False
    # The missing key is not invented.
    assert "name" not in json.loads(result.arguments)


def test_semantic_values_not_altered():
    rep = ToolCallRepair()
    args = '{"op": "delete"}'
    schema = {"properties": {"op": {"type": "string"}}}
    result = rep.repair_arguments(args, schema)
    assert result.changed is False
    parsed = json.loads(result.arguments)
    assert parsed["op"] == "delete"


# -------------------------------------------------------------------
# State-mutating gate
# -------------------------------------------------------------------


def test_mutating_flag_passes_when_flag_off_and_call_non_mutating():
    """Non-mutating calls repair normally even with allow_mutating=False.

    The gate is per-call: when the call is not marked mutating, the
    allow_mutating policy has no effect.
    """
    rep = ToolCallRepair()
    args = '{"cmd": "ls -la",}'
    schema = {"properties": {"cmd": {"type": "string"}}}
    result = rep.repair_arguments(args, schema, allow_mutating=False)
    assert result.changed is True
    assert "fix_trailing_commas" in result.fired_rules


def test_mutating_call_short_circuited_when_policy_off():
    """A mutating call with allow_mutating=False is passed through unchanged."""
    rep = ToolCallRepair()
    args = '{"cmd": "rm -rf /",}'
    schema = {
        "is_mutating": True,
        "properties": {"cmd": {"type": "string"}},
    }
    result = rep.repair_arguments(args, schema, allow_mutating=False)
    assert result.changed is False
    assert result.fired_rules == []
    assert result.unrepaired is False
    assert result.arguments == args


def test_mutating_call_repairs_when_policy_on():
    """A mutating call with allow_mutating=True still gets repaired."""
    rep = ToolCallRepair()
    args = '{"cmd": "rm -rf /",}'
    schema = {
        "is_mutating": True,
        "properties": {"cmd": {"type": "string"}},
    }
    result = rep.repair_arguments(args, schema, allow_mutating=True)
    assert result.changed is True
    assert "fix_trailing_commas" in result.fired_rules


def test_per_call_is_mutating_kwarg_overrides_default():
    """is_mutating kwarg (call-site marker) drives the gate when no schema marker."""
    rep = ToolCallRepair()
    args = '{"cmd": "rm -rf /",}'
    schema = {"properties": {"cmd": {"type": "string"}}}
    # No schema is_mutating — kwarg drives the gate.
    result = rep.repair_arguments(
        args, schema, allow_mutating=False, is_mutating=True
    )
    assert result.changed is False
    assert result.fired_rules == []
    assert result.arguments == args


def test_schema_is_mutating_overrides_call_kwarg():
    """Schema-declared is_mutating is the registry's authoritative source."""
    rep = ToolCallRepair()
    args = '{"cmd": "ls",}'
    schema = {
        "is_mutating": True,  # schema says mutating
        "properties": {"cmd": {"type": "string"}},
    }
    # kwarg says non-mutating — schema wins.
    result = rep.repair_arguments(
        args, schema, allow_mutating=False, is_mutating=False
    )
    assert result.changed is False
    assert result.arguments == args


def test_mutating_gate_does_not_increment_counters():
    """Short-circuited mutating calls do NOT increment repair-rule counters."""
    rep = ToolCallRepair()
    args = '{"cmd": "rm -rf /",}'
    schema = {
        "is_mutating": True,
        "properties": {"cmd": {"type": "string"}},
    }
    rep.repair_arguments(args, schema, allow_mutating=False)
    assert rep.counters() == {}


def test_repair_tool_calls_honors_per_call_is_mutating():
    """repair_tool_calls plumbs is_mutating from each tool_call dict."""
    rep = ToolCallRepair()
    tcs = [
        {
            "function": {"name": "rm", "arguments": '{"path": "/",}'},
            "is_mutating": True,
        },
        {
            "function": {"name": "ls", "arguments": '{"path": "/",}'},
            # no is_mutating marker — non-mutating
        },
    ]
    schemas = {
        "rm": {
            "is_mutating": True,
            "properties": {"path": {"type": "string"}},
        },
        "ls": {"properties": {"path": {"type": "string"}}},
    }
    repaired, results = rep.repair_tool_calls(tcs, schemas, allow_mutating=False)
    # rm short-circuited; ls repaired.
    assert results[0].changed is False
    assert results[0].fired_rules == []
    assert results[1].changed is True
    assert "fix_trailing_commas" in results[1].fired_rules
    assert repaired[0]["function"]["arguments"] == '{"path": "/",}'
    assert repaired[1]["function"]["arguments"] == '{"path": "/"}'


# -------------------------------------------------------------------
# counters()
# -------------------------------------------------------------------
# counters()
# -----------------------------------------------------------------


def test_counters_reflect_which_rules_fired():
    rep = ToolCallRepair()
    # Fire trailing comma rule
    rep.repair_arguments('{"a": 1,}')
    # Fire single-quoted keys
    rep.repair_arguments("{'b': 2}")
    cnt = rep.counters()
    assert cnt.get("fix_trailing_commas", 0) == 1
    assert cnt.get("fix_single_quoted_keys", 0) == 1


def test_reset_counters():
    rep = ToolCallRepair()
    rep.repair_arguments('{"a": 1,}')
    assert rep.counters().get("fix_trailing_commas") == 1
    rep.reset_counters()
    assert rep.counters() == {}


# -------------------------------------------------------------------
# repair_tool_calls convenience wrapper
# -----------------------------------------------------------------


def test_repair_tool_calls_wraps_correctly():
    rep = ToolCallRepair()
    tcs = [
        {
            "function": {
                "name": "foo",
                "arguments": '{"a": 1,}',
            }
        }
    ]
    schemas = {"foo": {"properties": {"a": {"type": "integer"}}}}
    repaired, results = rep.repair_tool_calls(tcs, schemas)
    assert results[0].changed is True
    assert repaired[0]["function"]["arguments"] == '{"a": 1}'


# -------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------


def test_non_string_arguments_unrepaired():
    rep = ToolCallRepair()
    result = rep.repair_arguments(None)  # type: ignore[arg-type]
    assert result.changed is False
    assert result.unrepaired is True


def test_empty_arguments_unrepaired():
    rep = ToolCallRepair()
    result = rep.repair_arguments("")
    assert result.changed is False
    assert result.unrepaired is True


def test_completely_garbled_unrepaired():
    rep = ToolCallRepair()
    args = "not json at all!!!"
    result = rep.repair_arguments(args)
    assert result.unrepaired is True
    assert result.changed is False


# -------------------------------------------------------------------
# Stdlib-only audit
# -----------------------------------------------------------------


def test_stdlib_only_no_jsonschema():
    """Verify that tool_repair does not import jsonschema or any third-party lib."""
    import importlib
    import sys

    mod = importlib.import_module("charon.tool_repair")
    # Get the set of all modules used by tool_repair
    used: set[str] = set()
    for _name, val in vars(mod).items():
        if hasattr(val, "__module__"):
            used.add(val.__module__.split(".")[0])
    # Check no forbidden third-party imports
    forbidden = {"jsonschema", "requests", "httpx", "urllib3", "aiohttp"}
    for fb in forbidden:
        assert fb not in used, f"forbidden import: {fb}"
    # verify it's in sys.modules (we imported it)
    assert "charon.tool_repair" in sys.modules

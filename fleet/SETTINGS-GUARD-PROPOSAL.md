# SETTINGS-GUARD-PROPOSAL — SessionStart auto-compact guard

**For the OPERATOR to apply.** The manager session cannot edit `~/.claude/**` (deny-listed),
so this is a proposal you paste into your own settings.

## Why

The manager session's high token/context burn was diagnosed as Claude Code running with
`"autoCompactEnabled": false` in `~/.claude/settings.json`. With auto-compact OFF the
transcript never compacts, so per-turn token cost climbs for the whole session (amplified by
full sub-session reports, whole-file reads of big handoffs, and long dialogues — all resident
forever). Fix already applied: auto-compact flipped back ON.

This guard makes the failure mode **loud** instead of silent: at every session start it checks
the setting and prints a warning if auto-compact is not enabled, so it can never quietly drift
OFF again.

## Apply

Merge this `hooks` block into `~/.claude/settings.json` (add to the existing `hooks` object if
you already have one; otherwise add the whole `"hooks": { ... }` key at the top level):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "grep -Eq '\"autoCompactEnabled\"[[:space:]]*:[[:space:]]*true' ~/.claude/settings.json || echo '!!!! WARNING: autoCompactEnabled is NOT true in ~/.claude/settings.json — the transcript will never compact and per-turn token cost will climb all session. Set it to true. !!!!'"
          }
        ]
      }
    ]
  }
}
```

A SessionStart hook's stdout is injected into the session context, so if the guard fires both
you AND the manager Claude see the warning at startup.

## The one-line hook command (copy-paste target)

```
grep -Eq '"autoCompactEnabled"[[:space:]]*:[[:space:]]*true' ~/.claude/settings.json || echo '!!!! WARNING: autoCompactEnabled is NOT true in ~/.claude/settings.json — the transcript will never compact and per-turn token cost will climb all session. Set it to true. !!!!'
```

## Notes

- **Simplest tooling on purpose** — plain `grep`, no `jq` dependency.
- The check warns when the key is **not explicitly `true`** (i.e. `false`, or absent). Note that
  when the key is *absent* Claude Code defaults auto-compact ON, so an absent-key warning is a
  belt-and-suspenders false alarm. If you'd rather warn **only when it is explicitly `false`**
  (the exact failure we hit), swap the command to:
  ```
  grep -Eq '"autoCompactEnabled"[[:space:]]*:[[:space:]]*false' ~/.claude/settings.json && echo '!!!! WARNING: autoCompactEnabled is explicitly FALSE — set it to true. !!!!' || true
  ```
- To verify by hand any time: `grep autoCompactEnabled ~/.claude/settings.json` should show `true`.

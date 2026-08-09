/**
 * session-bridge-watch — opencode plugin (v2)
 *
 * Injects unread-bridge-message warnings into every tool output (PostToolUse).
 * Advisory nudge on session.idle (never blocking — session.stop/end don't exist).
 *
 * v2 changes from plo-koon's original:
 *   - Dropped dead Stop hook (session.stop/end are NOT in opencode's event bus)
 *   - Added session.idle advisory nudge (stderr only, never throws)
 *   - Persists lastUnread via env for cross-turn durability
 *   - Override removed (was cosmetic — never checked)
 *
 * The gap is closed by: tool.execute.after (every tool warns) + bridge ack enforcement.
 */
const { execSync } = require("child_process");
const os = require("os");
const DB = os.homedir() + "/.charon/session-bridge-v2.db";

// ⚠ INTERIM SAFETY FIX (manager, 2026-08-07) — this function was flooding every
// tab with a Python traceback on EVERY tool call. Two defects, both fixed here:
//
//   1. stderr LEAKED. execSync inherits stderr, so even though the catch below
//      swallowed the exception, the child's traceback still printed straight
//      into the TUI. `stdio` is now explicit: stdin/stderr discarded, stdout
//      piped. A plugin must never be able to write to the operator's screen.
//   2. `os.path.exists(db)` is the WRONG GUARD. The configured store
//      (~/.charon/session-bridge-v2.db) is a 0-BYTE, SCHEMA-LESS file — it
//      exists, so the early-exit never fired and `SELECT ... FROM messages`
//      raised `no such table: messages` (that is the "File \"<string>\", line 6"
//      traceback seen on the live tabs). Guard on the TABLE, not the file.
//
// ⛔ STILL WRONG, AND DELIBERATELY NOT FIXED HERE — owned by ONE-TAB-METHOD
// (bultar-swan). Do not patch around it; fix it there:
//   * WRONG STORE. This reads a LOCAL sqlite that nothing else writes. The real
//     board is the Roci coordinator at ~/.charon/coordinator-charon.sock. So
//     even when this does not crash it returns 0 forever — INERT, a gate
//     reporting green while enforcing nothing.
//   * FORKS python3 ON EVERY TOOL CALL, across every session. Needs throttling.
//   * Should also ENFORCE REGISTRATION: this hook already fires on every tool
//     call, which makes it the natural place to detect "this session is not on
//     the board" and say so loudly — mechanized enforcement that costs zero
//     model turns.
function unreadCount() {
  try {
    const out = execSync(
      `python3 -c "
import sqlite3,os
db='${DB}'
if not os.path.exists(db) or os.path.getsize(db)==0: print(0); raise SystemExit
c=sqlite3.connect(db)
t=c.execute(\\"SELECT name FROM sqlite_master WHERE type='table' AND name='messages'\\").fetchone()
if t is None: print(0); c.close(); raise SystemExit
n=c.execute('SELECT COUNT(*) FROM messages WHERE acked=0').fetchone()[0]
c.close()
print(n)
"`,
      { encoding: "utf8", timeout: 2000, stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
    return parseInt(out) || 0;
  } catch {
    return 0;
  }
}

export default async () => ({
  "tool.execute.after": async (_input, output) => {
    const n = unreadCount();
    process.env.CHARON_LAST_UNREAD = String(n);
    if (n > 0) {
      output.text =
        (output.text || "") +
        `\n\n⚠ ${n} unread bridge messages — call board() to check and ack() to clear.\n`;
    }
  },

  "event": (evt) => {
    if (evt && evt.type === "session.idle") {
      const n = parseInt(process.env.CHARON_LAST_UNREAD || "0");
      if (n > 0) {
        console.error(
          `session-bridge-watch: ${n} unread bridge messages at idle. ` +
          `Call board() and ack() before the session ends.`
        );
      }
    }
  },
});

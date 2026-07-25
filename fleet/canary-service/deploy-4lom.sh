#!/usr/bin/env bash
# deploy-4lom.sh — operator-driven deploy of the gate-test canary onto 4-LOM (10.0.1.60).
#
# SCOPE (from the ticket): the BUILD is rig-side; the systemd deploy is an OPERATOR step, exactly
# like the grader/monit. This script therefore produces the units + the exact commands and never
# assumes privilege. It:
#   * NEVER runs sudo,
#   * NEVER installs or enables monit,
#   * NEVER enables/starts a unit by itself — `install` only WRITES files; the operator runs the
#     two printed `systemctl --user` lines.
#
# WHY A --user UNIT: user units need no root at all, and `loginctl enable-linger` makes them
# reboot-persistent — which is the whole point (the OOB grader died on a reboot with no
# supervisor and nothing noticed for 9 days). The service is a long-lived `run-canary.sh loop`
# with Restart=always, so BOTH watchdog dimensions are real: the pgrep alive_probe sees the
# process and the freshness_probe ages fleet/state/canary-report.tsv.
#
# USAGE
#   deploy-4lom.sh unit            print the systemd unit to stdout (review before installing)
#   deploy-4lom.sh install [dir]   write the unit file (default ~/.config/systemd/user) + print
#                                  the exact enable commands. Writes files only.
#   deploy-4lom.sh remote-cmd      print the exact copy-pasteable command to deploy ON 4-LOM
#   deploy-4lom.sh wire-surface    idempotently add the SessionStart canary line to
#                                  ~/.claude/settings.json (operator-invoked; prints a dry-run
#                                  diff unless --apply is passed)
#   deploy-4lom.sh verify          report what is actually deployed/running here (no changes)
#
# ENV
#   CANARY_REPO_DIR   checkout the unit runs from   (default /home/stack/charon-private)
#   CANARY_UNIT_NAME  unit name                     (default charon-canary)
#   CANARY_INTERVAL_S cadence baked into the unit   (default 900 — the suite is ~100s wall,
#                     measured 2026-07-24 at 68 pass/9 fail, plus the serial adjudication pass)
#   CANARY_TTL_S      freshness bound baked in      (default 3600 — ~4 missed cycles)
#   CANARY_SETTINGS   settings.json path            (default ~/.claude/settings.json)
set -euo pipefail

REPO_DIR="${CANARY_REPO_DIR:-/home/stack/charon-private}"
UNIT_NAME="${CANARY_UNIT_NAME:-charon-canary}"
INTERVAL_S="${CANARY_INTERVAL_S:-900}"
TTL_S="${CANARY_TTL_S:-3600}"
SETTINGS="${CANARY_SETTINGS:-$HOME/.claude/settings.json}"
RUNNER="$REPO_DIR/fleet/canary-service/run-canary.sh"

# Hard refusal: this script must never acquire privilege or touch monit. Kept as an executable
# assertion rather than a comment so a later edit that adds `sudo` fails loudly in review/tests.
if [ "${EUID:-$(id -u)}" = "0" ]; then
  echo "deploy-4lom: REFUSING to run as root — this deploy is unprivileged by design (--user units)." >&2
  exit 2
fi

cmd_unit(){
  cat <<UNIT
[Unit]
Description=Charon gate-test canary (always-on suite sensor with SLOW-vs-BROKEN attribution)
Documentation=file://$REPO_DIR/fleet/board/4LOM-CANARY-SERVICE.md
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=CANARY_INTERVAL_S=$INTERVAL_S
Environment=CANARY_TTL_S=$TTL_S
Environment=CANARY_GIT_PULL=1
ExecStart=/usr/bin/env bash $RUNNER loop
# A RED cycle is a REPORT, not a crash — the loop keeps running and the cached report carries the
# verdict. Restart=always exists for the process actually dying (the reboot/OOM case).
Restart=always
RestartSec=30
Nice=10
# The suite is the box's heaviest periodic load; keep it off the operator's interactive path.
CPUWeight=30
IOWeight=30

[Install]
WantedBy=default.target
UNIT
}

cmd_install(){
  local dest="${1:-$HOME/.config/systemd/user}"
  mkdir -p "$dest"
  cmd_unit > "$dest/$UNIT_NAME.service"
  echo "deploy-4lom: wrote $dest/$UNIT_NAME.service"
  echo
  echo "OPERATOR — run these two lines (no sudo needed, nothing else was enabled for you):"
  echo "  loginctl enable-linger \"\$USER\"          # survive logout + reboot"
  echo "  systemctl --user daemon-reload && systemctl --user enable --now $UNIT_NAME.service"
  echo
  echo "Then confirm:  bash $RUNNER status"
}

cmd_remote_cmd(){
  cat <<CMD
# OPERATOR — deploy the canary ON 4-LOM (10.0.1.60). Run from this box, verbatim:

ssh -i ~/.ssh/4lom stack@10.0.1.60 'set -e
  git -C $REPO_DIR pull --ff-only
  bash $REPO_DIR/fleet/canary-service/deploy-4lom.sh install
  loginctl enable-linger "\$USER"
  systemctl --user daemon-reload
  systemctl --user enable --now $UNIT_NAME.service
  sleep 5; systemctl --user --no-pager status $UNIT_NAME.service | head -5'

# Verify (after one cadence, ~$((INTERVAL_S/60)) min):
ssh -i ~/.ssh/4lom stack@10.0.1.60 'bash $RUNNER status'

# NOTE: monit is NOT installed and is NOT installed by this script. The canary is registered in
# fleet/state/service-registry.tsv, so it is supervised the moment monit is enabled separately;
# until then fleet/watchdog/discover-services.sh evaluates the same registry monit-independently.
CMD
}

# The SessionStart surface. Wiring settings.json is an OPERATOR action (it is the operator's own
# harness config), so this prints the exact entry and only edits with an explicit --apply.
cmd_wire_surface(){
  local apply=0
  [ "${1:-}" = "--apply" ] && apply=1
  local entry_cmd="bash $RUNNER status 2>&1 || true"
  if [ ! -f "$SETTINGS" ]; then
    echo "deploy-4lom: settings file not found: $SETTINGS" >&2
    echo "Add a SessionStart hook whose command is:  $entry_cmd" >&2
    return 1
  fi
  APPLY="$apply" ENTRY_CMD="$entry_cmd" SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os, shutil, sys
settings = os.environ["SETTINGS"]; entry_cmd = os.environ["ENTRY_CMD"]; apply = os.environ["APPLY"] == "1"
with open(settings) as fh:
    doc = json.load(fh)
groups = doc.setdefault("hooks", {}).setdefault("SessionStart", [])
if not groups:
    groups.append({"hooks": []})
hooks = groups[0].setdefault("hooks", [])
if any("run-canary.sh" in (h.get("command") or "") for h in hooks):
    print("deploy-4lom: SessionStart canary surface ALREADY wired — nothing to do.")
    sys.exit(0)
hooks.append({"type": "command", "command": entry_cmd, "statusMessage": "Canary: cached gate-suite verdict..."})
if not apply:
    print("deploy-4lom: DRY-RUN. Would append this SessionStart hook entry to " + settings + ":")
    print(json.dumps(hooks[-1], indent=2))
    print("\nRe-run with --apply to write it (a .bak is kept).")
    sys.exit(0)
shutil.copyfile(settings, settings + ".bak")
with open(settings, "w") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
print("deploy-4lom: wired the SessionStart canary surface into " + settings + " (backup: " + settings + ".bak)")
PY
}

cmd_verify(){
  local rc=0
  echo "runner:   $RUNNER"
  if [ -f "$RUNNER" ]; then echo "          present"; else echo "          MISSING"; rc=1; fi
  echo "unit:     $HOME/.config/systemd/user/$UNIT_NAME.service"
  if [ -f "$HOME/.config/systemd/user/$UNIT_NAME.service" ]; then echo "          installed"; else echo "          not installed"; rc=1; fi
  if command -v systemctl >/dev/null 2>&1; then
    echo "active:   $(systemctl --user is-active "$UNIT_NAME.service" 2>&1 || true)"
    echo "enabled:  $(systemctl --user is-enabled "$UNIT_NAME.service" 2>&1 || true)"
  else
    echo "active:   systemctl unavailable on this box"
  fi
  echo "surface:  $(grep -c 'run-canary.sh' "$SETTINGS" 2>/dev/null || echo 0) SessionStart reference(s) in $SETTINGS"
  echo "report:"
  bash "$RUNNER" status || rc=$?
  return "$rc"
}

usage(){ sed -n '1,40p' "${BASH_SOURCE[0]}" | grep -E '^#( |$)' | sed 's/^# \{0,1\}//'; }

case "${1:-usage}" in
  unit)        cmd_unit ;;
  install)     shift; cmd_install "$@" ;;
  remote-cmd)  cmd_remote_cmd ;;
  wire-surface) shift; cmd_wire_surface "$@" ;;
  verify)      cmd_verify ;;
  -h|--help|help|usage) usage ;;
  *) echo "deploy-4lom: unknown command '${1:-}'" >&2; usage >&2; exit 2 ;;
esac

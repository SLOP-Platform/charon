# fleet/watchdog/units — systemd units the rig AUTHORS but cannot INSTALL

The rig has no sudo. These units are authored, version-controlled and **validated by
`fleet/watchdog/verify-restart-cmds.sh`** (ExecStart binary executable, script operand present,
`User=` exists on the box) so they cannot rot — but installing them is an **operator** step.

## Why the registry does not already point at them

`fleet/state/service-registry.tsv` column 6 must be a command that **actually works on this box
right now**. A `systemctl restart bench-grader-daemon` for a unit nobody has installed is exactly
the defect WATCHDOG-RESTART-CMDS-VERIFY exists to kill (that was the literal seed value). So the
registry uses the direct, root-safe relaunch that works today, and this unit is the **optional
durable upgrade**.

## Operator install step (needs sudo — the rig must not run this)

```sh
sudo install -m 0644 -o root -g root \
  /home/stack/charon-private/fleet/watchdog/units/bench-grader-daemon.service \
  /etc/systemd/system/bench-grader-daemon.service
sudo systemctl daemon-reload
sudo systemctl enable --now bench-grader-daemon
systemctl cat bench-grader-daemon        # must resolve — this is what verify checks
```

## AFTER installing, flip the registry (do not skip — two supervisors is a bug)

`Restart=always` in the unit and monit's `restart` action are two independent supervisors for one
process. Once the unit is installed, set the `grader-daemon` row's `restart_cmd` to:

```
/usr/bin/systemctl restart bench-grader-daemon
```

then re-render and re-verify:

```sh
fleet/watchdog/generate-monit-config.sh      # registry is the SSOT; monit.d is generated
fleet/watchdog/verify-restart-cmds.sh        # must be GREEN before enabling monit
```

`verify-restart-cmds.sh` requires `systemctl cat <unit>` to resolve for any `systemctl restart`
restart_cmd, so making that flip **before** the install goes RED and blocks the monit enable —
which is the intended fail-closed order.

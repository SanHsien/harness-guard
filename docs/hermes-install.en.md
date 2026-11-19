> English | [中文版](hermes-install.md)

# Installing for Hermes

Hermes has no "pipe JSON into a script on stdin" hook protocol. It calls a plugin inside its own process:

```
Hermes is about to run a tool
      |
      v
pre_tool_call(tool_name="terminal", args={"command": "..."}, session_id=..., ...)
      |
      +-- returns None                                   -> the call runs
      +-- returns {"action": "block", "message": "..."}  -> it does not; the message goes back to the model
```

So what this repo gives Hermes is a plugin folder, not a set of hook files.

## What gets installed

```
<Hermes home>/plugins/harness-guard/
  __init__.py            the adapter (hooks/hermes-plugin/__init__.py)
  plugin.yaml
  danger_zone_guard.py   the file from hooks/danger-zone-guard/claude-code/, unchanged
  test_gate_guard.py     the file from hooks/test-gate-guard/claude-code/, unchanged
  fork_pr_guard.py       optional. Not part of this repo; called when present, never created or overwritten here
```

The adapter imports the two files beside it and calls their `inspect_command()` and `verdict()`. There is one
copy of the detection rules: these are the same two files Claude Code, Antigravity and Cursor run.

Only `danger-zone-guard` and `test-gate-guard` are covered. `claim-guard`, `lint-gate`, `no-emoji-guard` and
`anti-doom-loop-guard` need events or data Hermes does not provide, and were not ported.

## Install

```bash
python scripts/install.py --dry-run --agent hermes
python scripts/install.py --agent hermes
python scripts/verify-install.py --agent hermes
```

The Hermes home defaults to the `HERMES_HOME` environment variable, then `~/AppData/Local/hermes` (Windows) or
`~/.hermes`. Use `--hermes-dir` for anywhere else.

What the installer does:

1. Backs up any existing file whose content differs to `<Hermes home>/backups/harness-guard-plugin/`.
2. Copies the four files.
3. Runs `hooks/hermes-plugin/probe.py`, which loads the **installed** plugin in a separate process and calls it
   the way Hermes does, checking that what should be blocked is blocked and what should pass passes. If the probe
   is red the previous files are put back and the exit code is 1.
4. Reads `plugins.enabled` from `config.yaml` and prints a warning when `harness-guard` is not listed.

**`config.yaml` is never written.** The plugin is loaded only when it is listed under `plugins.enabled`; add it
yourself. The installer neither reads nor changes Hermes' approval settings (`command_allowlist`, `approvals`).

## How it fails

- A shared file is missing or does not load: **every** tool call that carries a command is blocked, and the
  message names the missing file and how to reinstall.
- A check raises: that command is blocked, and the message carries the exception.
- Tool calls that carry no command (reading a file, searching) are not affected.

Blocking is the deliberate choice. The previous version of this plugin quietly failed to block five command
shapes, and that went unnoticed until an audit on 2026-11-19.

## Limits

- Hermes loads plugins **when it starts**. After an install, a running gateway keeps using the old files until
  it is restarted.
- `verify-install.py` and the probe show that the installed files decide correctly. They do not show that a
  running Hermes has loaded them. To confirm that, watch it block something in a real session.
- Only `command`, `cmd` and `CommandLine` in the arguments are read. Other Hermes tools that execute code (a tool
  that runs a code snippet directly, scripts inside a scheduled job) do not pass through here.
- Hermes has its own approval layer (`command_allowlist` in `config.yaml`). A command class permanently allowed
  there is still blocked by this plugin; a command this plugin allows still goes through that layer.

## Remove

Delete `<Hermes home>/plugins/harness-guard/`, take `harness-guard` out of `plugins.enabled`, and restart Hermes.
To go back to the previous version, copy the backup from `backups/harness-guard-plugin/` (named
`<original name>.bak-<time>-<random>`) back into place.

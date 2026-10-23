import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import install as installer_module


REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "scripts" / "install.py"
VERIFIER = REPO / "scripts" / "verify-install.py"


class HookCopyTests(unittest.TestCase):
    def test_shell_hook_is_normalized_to_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.sh"
            target = Path(tmp) / "target.sh"
            source.write_bytes(b"#!/usr/bin/env bash\r\nset -u\r\nprintf ok\r\n")

            installer_module.copy_hook_file(source, target)

            self.assertNotIn(b"\r\n", target.read_bytes())


class InstallDryRunTests(unittest.TestCase):
    def test_all_agents_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ)
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--dry-run",
                    "--agent",
                    "all",
                    "--hooks",
                    "all",
                    "--skills",
                    "all",
                ],
                cwd=str(REPO),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse((home / ".claude").exists())
            self.assertFalse((home / ".gemini").exists())
            self.assertFalse((home / ".cursor").exists())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".agents").exists())


class SkillReplacementTests(unittest.TestCase):
    """Replacing an existing skill folder must either finish or say it did not.

    A skill folder can hold files that resist deletion: read-only bits from a
    checkout, or a file another process still has open. The first is fixable and
    must be fixed. The second is not, and must be reported -- copying the new
    version over the remains leaves files that no longer exist upstream while
    printing "copied", which is the false completion claim this kit exists to
    prevent.
    """

    def _install_over(self, prepare):
        """Seed a stale skill folder, run --force, return (proc, stale_path)."""
        tmp = tempfile.mkdtemp()
        target = Path(tmp) / "skills" / "explain"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("stale content", encoding="utf-8")
        stale = target / "obsolete.md"
        stale.write_text("no longer in the repo", encoding="utf-8")

        handle = prepare(stale)
        try:
            proc = subprocess.run(
                [
                    sys.executable, str(INSTALLER),
                    "--claude-dir", tmp,
                    "--hooks", "",
                    "--skills", "explain",
                    "--force",
                ],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            return proc, stale, target
        finally:
            if handle is not None:
                handle.close()
            if stale.exists():
                try:
                    os.chmod(stale, stat.S_IWRITE)
                except OSError:
                    pass

    def test_read_only_leftover_is_replaced(self):
        def make_read_only(path):
            os.chmod(path, stat.S_IREAD)
            return None

        proc, stale, target = self._install_over(make_read_only)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(stale.exists(), "read-only leftover should have been removed")
        self.assertNotIn(
            "stale content",
            (target / "SKILL.md").read_text(encoding="utf-8"),
            "the skill should have been replaced with the repo version",
        )

    @unittest.skipUnless(
        platform.system() == "Windows",
        "only Windows refuses to delete a file another process holds open",
    )
    def test_undeletable_folder_is_reported_not_claimed(self):
        proc, stale, target = self._install_over(
            lambda path: open(path, "r+", encoding="utf-8")
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FAILED to replace", proc.stdout)
        self.assertNotIn("copied", proc.stdout.split("FAILED to replace")[0][-40:])
        self.assertNotIn("Installation finished", proc.stdout)
        self.assertTrue(stale.exists(), "the folder should have been left alone")


class CursorAndCodexInstallTests(unittest.TestCase):
    def _run(self, home, extra):
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        cmd = [sys.executable, str(INSTALLER)] + extra
        return subprocess.run(
            cmd,
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def test_cursor_install_merges_flat_hooks_json_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cursor_dir = home / ".cursor"
            (cursor_dir / "hooks.json").parent.mkdir(parents=True)
            (cursor_dir / "hooks.json").write_text(
                json.dumps({
                    "version": 1,
                    "hooks": {
                        "sessionStart": [{"command": "keep-me.py"}],
                    },
                }),
                encoding="utf-8",
            )
            proc = self._run(home, [
                "--agent", "cursor",
                "--cursor-dir", str(cursor_dir),
                "--hooks", "test-gate-guard,danger-zone-guard",
                "--skills", "none",
            ])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            settings = json.loads((cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["version"], 1)
            self.assertEqual(settings["hooks"]["sessionStart"][0]["command"], "keep-me.py")
            self.assertTrue(settings["hooks"]["beforeShellExecution"])
            first_count = len(settings["hooks"]["beforeShellExecution"])
            self.assertGreaterEqual(first_count, 2)
            self.assertTrue((cursor_dir / "hooks" / "test_gate_guard.py").exists())
            self.assertTrue((cursor_dir / "hooks" / "danger_zone_guard.py").exists())

            again = self._run(home, [
                "--agent", "cursor",
                "--cursor-dir", str(cursor_dir),
                "--hooks", "test-gate-guard,danger-zone-guard",
                "--skills", "none",
            ])
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            settings2 = json.loads((cursor_dir / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(
                len(settings2["hooks"]["beforeShellExecution"]),
                first_count,
                "re-running must not duplicate Cursor hook entries",
            )

    def test_codex_install_merges_nested_hooks_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_dir = home / ".codex"
            (codex_dir / "hooks.json").parent.mkdir(parents=True)
            (codex_dir / "hooks.json").write_text(
                json.dumps({
                    "hooks": {
                        "SessionStart": [{
                            "hooks": [{"type": "command", "command": "keep-me.sh"}],
                        }],
                    },
                }),
                encoding="utf-8",
            )
            proc = self._run(home, [
                "--agent", "codex",
                "--codex-dir", str(codex_dir),
                "--hooks", "test-gate-guard",
                "--skills", "none",
            ])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            settings = json.loads((codex_dir / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(
                settings["hooks"]["SessionStart"][0]["hooks"][0]["command"],
                "keep-me.sh",
            )
            self.assertTrue(settings["hooks"]["PreToolUse"])
            self.assertTrue((codex_dir / "hooks" / "test_gate_guard.py").exists())

    def test_codex_installs_skills_to_official_user_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_dir = home / ".codex"

            proc = self._run(home, [
                "--agent", "codex",
                "--codex-dir", str(codex_dir),
                "--hooks", "",
                "--skills", "explain",
            ])

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(
                (home / ".agents" / "skills" / "explain" / "SKILL.md").exists()
            )
            self.assertFalse(
                (codex_dir / "skills" / "explain").exists(),
                "new installs must not create the undocumented legacy location",
            )

    def test_all_agents_replaces_shared_skills_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            shared = home / ".agents" / "skills"
            stale = shared / "explain" / "SKILL.md"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale", encoding="utf-8")

            proc = self._run(home, [
                "--agent", "all",
                "--claude-dir", str(home / ".claude"),
                "--cursor-dir", str(home / ".cursor"),
                "--codex-dir", str(home / ".codex"),
                "--hooks", "",
                "--skills", "explain",
                "--force",
            ])

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotEqual(stale.read_text(encoding="utf-8"), "stale")
            self.assertEqual(
                proc.stdout.count("skills -> %s" % shared),
                1,
                "--agent all must not replace the shared Codex skill twice",
            )

    def test_codex_preserves_legacy_skill_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_dir = home / ".codex"
            legacy = codex_dir / "skills" / "explain" / "SKILL.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("user legacy copy", encoding="utf-8")

            proc = self._run(home, [
                "--agent", "codex",
                "--codex-dir", str(codex_dir),
                "--hooks", "",
                "--skills", "explain",
                "--force",
            ])

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(legacy.read_text(encoding="utf-8"), "user legacy copy")
            self.assertTrue(
                (home / ".agents" / "skills" / "explain" / "SKILL.md").exists()
            )

class StaleRegistrationTests(unittest.TestCase):
    """Re-registering the same script with new arguments must replace, not add.

    Adding `--codex` to two hooks turned their commands into new strings, so
    the installer registered them alongside the old ones. Both then ran on
    every event, one of them with the behaviour the flag exists to change.
    Observed on a real machine on 2026-08-20.
    """

    def _codex_config(self, tmp):
        return json.loads((Path(tmp) / "hooks.json").read_text(encoding="utf-8"))

    def test_same_script_different_args_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp)
            if platform.system() == "Windows":
                stale = str(codex / "hooks" / "lint_gate.py")
                stale_command = 'python "%s"' % stale
            else:
                stale = str(codex / "hooks" / "lint-gate.sh")
                stale_command = '"%s" --legacy' % stale
            (codex / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": stale_command, "timeout": 60},
                {"type": "command", "command": "the-user-own-hook"},
            ]}]}}), encoding="utf-8")

            for _ in range(2):  # also proves a second run stays idempotent
                proc = subprocess.run(
                    [sys.executable, str(INSTALLER), "--codex-dir", str(codex),
                     "--agent", "codex", "--hooks", "lint-gate"],
                    cwd=str(REPO), capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            config = self._codex_config(codex)
            commands = [h["command"] for e in config["hooks"]["Stop"]
                        for h in e.get("hooks", [])]
            script_name = "lint_gate.py" if platform.system() == "Windows" else "lint-gate.sh"
            lint = [c for c in commands if script_name in c]
            self.assertEqual(len(lint), 1, commands)
            if platform.system() == "Windows":
                self.assertTrue(lint[0].endswith("--codex"), lint)
            else:
                self.assertNotIn("--legacy", lint[0])
            self.assertIn("the-user-own-hook", commands)


class CodexVerifierTests(unittest.TestCase):
    def _installed_codex(self, home):
        codex_dir = home / ".codex"
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        proc = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--agent", "codex",
                "--codex-dir", str(codex_dir),
                "--hooks", "all",
                "--skills", "none",
            ],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return codex_dir, env

    def _verify(self, env):
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--agent", "codex"],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def test_codex_hooks_are_live_fired(self):
        with tempfile.TemporaryDirectory() as tmp:
            _codex_dir, env = self._installed_codex(Path(tmp))

            proc = self._verify(env)

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Live fire (Codex payload shape)", proc.stdout)
            self.assertIn("Codex claim-guard blocks", proc.stdout)
            self.assertIn(
                "PASS Codex claim tracker matcher accepts exec_command and shell_command",
                proc.stdout,
            )
            self.assertIn("Codex lint-gate blocks", proc.stdout)
            self.assertIn("Codex test-gate-guard blocks", proc.stdout)
            self.assertIn("Codex danger-zone-guard blocks", proc.stdout)
            self.assertIn("Codex no-emoji-guard blocks", proc.stdout)
            self.assertIn(
                "PASS Codex anti-doom-loop-guard blocks the third identical command in a row",
                proc.stdout,
            )

    def test_codex_claim_tracker_alias_matcher_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir, env = self._installed_codex(Path(tmp))
            hooks_path = codex_dir / "hooks.json"
            with hooks_path.open(encoding="utf-8") as fh:
                settings = json.load(fh)
            for entry in settings["hooks"]["PostToolUse"]:
                commands = [hook.get("command", "") for hook in entry.get("hooks", [])]
                if any(
                    "claim_ledger_tracker" in command
                    or "claim-ledger-tracker" in command
                    for command in commands
                ):
                    entry["matcher"] = "Bash|Grep|Glob|exec|shell"
            with hooks_path.open("w", encoding="utf-8") as fh:
                json.dump(settings, fh)

            proc = self._verify(env)

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn(
                "FAIL Codex claim tracker matcher accepts exec_command and shell_command",
                proc.stdout,
            )

    def test_codex_registered_missing_hook_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir, env = self._installed_codex(Path(tmp))
            (codex_dir / "hooks" / "test_gate_guard.py").unlink()

            proc = self._verify(env)

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("FAIL Codex test-gate-guard script exists", proc.stdout)


HOOK_NAME = "anti-doom-loop-guard"
HOOK_FILE = "anti_doom_loop_guard.py"


def _snapshot(*roots):
    """Every file under the roots with its bytes and mtime, to prove a dry run wrote nothing."""
    found = {}
    for root in roots:
        root = Path(root)
        if root.is_file():
            found[str(root)] = (root.read_bytes(), root.stat().st_mtime_ns)
            continue
        for path in sorted(root.rglob("*")) if root.exists() else []:
            if path.is_file():
                found[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
    return found


class AntiDoomLoopGuardInstallTests(unittest.TestCase):
    """`--hooks anti-doom-loop-guard` installs this hook and nothing else, per agent."""

    def _run(self, home, extra):
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
        env.pop("CODEX_HOME", None)
        return subprocess.run(
            [sys.executable, str(INSTALLER)] + extra,
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def _fire(self, command_script, payload, *args, env_extra=None):
        env = dict(os.environ)
        env["ANTI_DOOM_LOOP_STATE_FILE"] = str(Path(command_script).parent / "state.json")
        env["ANTI_DOOM_LOOP_LOG_FILE"] = str(Path(command_script).parent / "audit.jsonl")
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, str(command_script), *args],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=30,
        )

    # -- Claude Code ---------------------------------------------------------

    def _manual_settings(self, command):
        return {
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [{"type": "command", "command": command, "timeout": 10}],
                }],
            },
        }

    def test_claude_recognises_the_manual_install_and_adds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            script = claude / "hooks" / HOOK_FILE
            manual = 'python "%s"' % script
            variants = [
                manual,
                'python %s' % str(script).replace("\\", "/"),
                'PYTHON "%s"' % str(script).upper().replace("HOOKS", "hooks"),
            ]
            for command in variants:
                with self.subTest(command=command):
                    claude.mkdir(parents=True, exist_ok=True)
                    settings_path = claude / "settings.json"
                    settings_path.write_text(
                        json.dumps(self._manual_settings(command)), encoding="utf-8")
                    before = settings_path.read_bytes()

                    dry = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME, "--dry-run"])
                    self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
                    self.assertIn("already registered", dry.stdout)
                    self.assertIn("keep", dry.stdout)

                    real = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME])
                    self.assertEqual(real.returncode, 0, real.stdout + real.stderr)
                    self.assertIn("nothing new to register", real.stdout)
                    self.assertEqual(settings_path.read_bytes(), before,
                                     "settings.json must be byte-identical when the hook is already there")
                    self.assertTrue(script.exists())

    def test_claude_installs_only_this_hook_with_the_documented_matcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(json.dumps({
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep-me"}]}]},
            }), encoding="utf-8")

            proc = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME])

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["command"], "keep-me")
            pre = settings["hooks"]["PreToolUse"]
            self.assertEqual(len(pre), 1)
            self.assertEqual(pre[0]["matcher"], "Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit")
            self.assertEqual(len(pre[0]["hooks"]), 1)
            self.assertEqual(sorted(p.name for p in (claude / "hooks").iterdir()), [HOOK_FILE])
            self.assertTrue(list((claude / "backups").glob("settings.json.bak-*")))

    # -- Codex ---------------------------------------------------------------

    def test_codex_installs_only_this_hook_and_names_the_caller(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "hooks.json").write_text(json.dumps({
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "keep-me"}]}]},
            }), encoding="utf-8")
            args = ["--agent", "codex", "--codex-dir", str(codex), "--hooks", HOOK_NAME, "--skills", "none"]

            first = self._run(home, args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            settings = json.loads((codex / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["hooks"]["SessionStart"][0]["hooks"][0]["command"], "keep-me")
            pre = settings["hooks"]["PreToolUse"]
            self.assertEqual(len(pre), 1)
            matchers = pre[0]["matcher"].split("|")
            for tool in ("Bash", "exec_command", "shell_command", "apply_patch"):
                self.assertIn(tool, matchers)
            command = pre[0]["hooks"][0]["command"]
            self.assertTrue(command.endswith("--agent codex"), command)
            self.assertEqual(sorted(p.name for p in (codex / "hooks").iterdir()), [HOOK_FILE])

            again = self._run(home, args)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            settings2 = json.loads((codex / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(settings2, settings, "re-running must not duplicate the registration")

            script = codex / "hooks" / HOOK_FILE
            patch = {"command": "*** Begin Patch\n*** End Patch"}
            shell = {"session_id": "s", "turn_id": "t", "hook_event_name": "PreToolUse",
                     "tool_name": "Bash", "tool_input": {"command": "pytest"}}
            outcomes = [self._fire(script, shell, "--agent", "codex") for _ in range(3)]
            self.assertEqual([p.returncode for p in outcomes], [0, 0, 0])
            self.assertEqual(json.loads(outcomes[2].stdout)["decision"], "block")
            edit = dict(shell, tool_name="apply_patch", tool_input=patch)
            self._fire(script, edit, "--agent", "codex")
            self.assertNotIn("block", self._fire(script, shell, "--agent", "codex").stdout.decode())

    # -- Cursor --------------------------------------------------------------

    def test_cursor_installs_only_this_hook_on_pretooluse(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cursor = home / ".cursor"
            cursor.mkdir()
            (cursor / "hooks.json").write_text(json.dumps({
                "version": 1, "hooks": {"sessionStart": [{"command": "keep-me.py"}]},
            }), encoding="utf-8")
            args = ["--agent", "cursor", "--cursor-dir", str(cursor), "--hooks", HOOK_NAME, "--skills", "none"]

            first = self._run(home, args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            settings = json.loads((cursor / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["version"], 1)
            self.assertEqual(settings["hooks"]["sessionStart"], [{"command": "keep-me.py"}])
            self.assertEqual(set(settings["hooks"]), {"sessionStart", "preToolUse"})
            entry = settings["hooks"]["preToolUse"]
            self.assertEqual(len(entry), 1)
            self.assertEqual(entry[0]["matcher"], "Shell|Read|Write|Delete")
            self.assertIn(HOOK_FILE, entry[0]["command"])
            self.assertEqual(sorted(p.name for p in (cursor / "hooks").iterdir()), [HOOK_FILE])

            again = self._run(home, args)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertEqual(json.loads((cursor / "hooks.json").read_text(encoding="utf-8")), settings)

            script = cursor / "hooks" / HOOK_FILE
            shell = {"hook_event_name": "preToolUse", "cursor_version": "1.7.2", "conversation_id": "c",
                     "tool_name": "Shell", "tool_input": {"command": "pytest"}}
            outcomes = [self._fire(script, shell) for _ in range(3)]
            self.assertEqual([p.returncode for p in outcomes], [0, 0, 0])
            self.assertEqual(json.loads(outcomes[2].stdout)["permission"], "deny")

    # -- Antigravity ---------------------------------------------------------

    def _agy_args(self, gemini, *extra):
        return ["--agent", "antigravity", "--gemini-dir", str(gemini), *extra]

    def _skip_if_space(self, path):
        if any(ch.isspace() for ch in str(path)):
            self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")

    def test_antigravity_merges_a_named_hook_and_leaves_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            gemini = home / ".gemini"
            config = gemini / "config"
            config.mkdir(parents=True)
            existing = {
                "danger-zone-guard": {"PreToolUse": [{"matcher": "run_command", "hooks": [
                    {"type": "command", "command": "python keep-me.py", "timeout": 10}]}]},
                "hooks": {"PreToolUse": [{"hooks": [{"command": "claude-shaped"}], "matcher": "run_command"}]},
            }
            (config / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")
            args = self._agy_args(gemini, "--hooks", HOOK_NAME)

            first = self._run(home, args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            merged = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["danger-zone-guard"], existing["danger-zone-guard"])
            self.assertEqual(merged["hooks"], existing["hooks"])
            mine = merged[HOOK_NAME]["PreToolUse"]
            self.assertEqual(len(mine), 1)
            matchers = mine[0]["matcher"].split("|")
            for tool in ("run_command", "view_file", "write_to_file", "replace_file_content",
                         "multi_replace_file_content"):
                self.assertIn(tool, matchers)
            handler = mine[0]["hooks"][0]
            self.assertEqual(handler["type"], "command")
            self.assertEqual(handler["timeout"], 10)
            self.assertNotIn('"', handler["command"], "Antigravity cannot unquote a command")
            self.assertNotIn("'", handler["command"])
            self.assertEqual(handler["command"].split(" ")[0], "python" if platform.system() == "Windows" else "python3")
            self.assertTrue(handler["command"].endswith(HOOK_FILE))
            self.assertEqual(sorted(p.name for p in (config / "hooks").iterdir()), [HOOK_FILE])
            self.assertTrue(list((gemini / "backups").glob("hooks.json.bak-*")))

            again = self._run(home, args)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("nothing new to register", again.stdout)
            self.assertEqual(json.loads((config / "hooks.json").read_text(encoding="utf-8")), merged)

            script = config / "hooks" / HOOK_FILE
            call = {"toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
                    "stepIdx": 1, "conversationId": "agy-1"}
            outcomes = [self._fire(script, call) for _ in range(3)]
            self.assertEqual([p.returncode for p in outcomes], [0, 0, 0])
            self.assertEqual(json.loads(outcomes[2].stdout)["decision"], "deny")

    def test_antigravity_without_hooks_flag_installs_no_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            gemini = home / ".gemini"

            proc = self._run(home, self._agy_args(gemini, "--skills", "explain"))

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("(none)", proc.stdout)
            self.assertFalse((gemini / "config" / "hooks.json").exists())
            self.assertFalse((gemini / "config" / "hooks").exists())
            self.assertTrue((gemini / "config" / "skills" / "explain" / "SKILL.md").exists())

    def test_antigravity_skips_hooks_it_has_no_registration_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            gemini = home / ".gemini"

            proc = self._run(home, self._agy_args(gemini, "--hooks", "claim-guard,%s" % HOOK_NAME))

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("no Antigravity registration for claim-guard", proc.stdout)
            merged = json.loads((gemini / "config" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(list(merged), [HOOK_NAME])

    def test_antigravity_refuses_a_path_it_cannot_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            gemini = home / "has space" / ".gemini"

            proc = self._run(home, self._agy_args(gemini, "--hooks", HOOK_NAME))

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("cannot quote", proc.stdout)
            self.assertFalse((home / "has space").exists())

    # -- every agent: dry run writes nothing -------------------------------------

    def test_dry_run_per_agent_writes_nothing_and_says_what_it_would_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            # Real-looking configs that must come out byte-for-byte and mtime-for-mtime unchanged.
            (home / ".claude").mkdir()
            (home / ".claude" / "settings.json").write_text('{"hooks": {}}', encoding="utf-8")
            (home / ".codex").mkdir()
            (home / ".codex" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
            (home / ".gemini" / "config").mkdir(parents=True)
            (home / ".gemini" / "config" / "hooks.json").write_text('{}', encoding="utf-8")
            before = _snapshot(home)

            for agent in ("claude", "codex", "cursor", "antigravity"):
                with self.subTest(agent=agent):
                    proc = self._run(home, [
                        "--dry-run", "--agent", agent, "--hooks", HOOK_NAME,
                        "--claude-dir", str(home / ".claude"),
                        "--codex-dir", str(home / ".codex"),
                        "--cursor-dir", str(home / ".cursor"),
                        "--gemini-dir", str(home / ".gemini"),
                    ])
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertIn(HOOK_FILE, proc.stdout)
                    self.assertIn("will register", proc.stdout)
                    self.assertIn("would write (dry run, nothing was written)", proc.stdout)
                    self.assertEqual(_snapshot(home), before, "a dry run must not touch anything")
            self.assertFalse((home / ".cursor").exists())


class AntiDoomLoopGuardVerifierTests(unittest.TestCase):
    """verify-install.py must live-fire this hook for every agent that has it installed."""

    def _env(self, home):
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
        env.pop("CODEX_HOME", None)
        return env

    def _install(self, home, env):
        proc = subprocess.run(
            [sys.executable, str(INSTALLER), "--agent", "all", "--hooks", HOOK_NAME, "--skills", "none"],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _verify(self, env, agent):
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--agent", agent],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )

    def test_every_agent_is_live_fired(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            if any(ch.isspace() for ch in str(home)):
                self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")
            env = self._env(home)
            self._install(home, env)

            for agent, label in (("claude", "Claude Code"), ("codex", "Codex"),
                                 ("cursor", "Cursor"), ("antigravity", "Antigravity")):
                with self.subTest(agent=agent):
                    proc = self._verify(env, agent)
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertIn(
                        "PASS %s anti-doom-loop-guard allows a command repeated with edits in between" % label,
                        proc.stdout)
                    self.assertIn(
                        "PASS %s anti-doom-loop-guard blocks the third identical command in a row" % label,
                        proc.stdout)

    def test_antigravity_command_with_quotes_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            if any(ch.isspace() for ch in str(home)):
                self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")
            env = self._env(home)
            self._install(home, env)
            path = home / ".gemini" / "config" / "hooks.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            handler = config[HOOK_NAME]["PreToolUse"][0]["hooks"][0]
            handler["command"] = handler["command"].replace("python ", 'python "') + '"'
            path.write_text(json.dumps(config), encoding="utf-8")

            proc = self._verify(env, "antigravity")

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("FAIL Antigravity hook command has no quotes", proc.stdout)

    def test_codex_registration_without_the_agent_flag_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = self._env(home)
            self._install(home, env)
            path = home / ".codex" / "hooks.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            handler = config["hooks"]["PreToolUse"][0]["hooks"][0]
            handler["command"] = handler["command"].replace(" --agent codex", "")
            path.write_text(json.dumps(config), encoding="utf-8")

            proc = self._verify(env, "codex")

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("FAIL Codex anti-doom-loop-guard is registered with --agent codex", proc.stdout)


if __name__ == "__main__":
    unittest.main()

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
                "PASS Codex claim tracker matcher accepts exec_command, shell_command and apply_patch",
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
                "FAIL Codex claim tracker matcher accepts exec_command, shell_command and apply_patch",
                proc.stdout,
            )

    def test_codex_claim_tracker_matcher_without_apply_patch_fails(self):
        # Without apply_patch the tracker never sees an edit, so a test run
        # followed by more edits would still count as current evidence.
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir, env = self._installed_codex(Path(tmp))
            hooks_path = codex_dir / "hooks.json"
            settings = json.loads(hooks_path.read_text(encoding="utf-8"))
            for entry in settings["hooks"]["PostToolUse"]:
                if any("claim" in hook.get("command", "") for hook in entry.get("hooks", [])):
                    entry["matcher"] = "Bash|Grep|Glob|exec|exec_command|shell|shell_command"
            hooks_path.write_text(json.dumps(settings), encoding="utf-8")

            proc = self._verify(env)

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("FAIL Codex claim tracker matcher accepts", proc.stdout)

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
            # The installer writes `python` on Windows and `python3` elsewhere, so a
            # manual install it should recognise uses that interpreter. Quoting, slash
            # direction and case are what may differ, not the interpreter.
            interpreter = "python" if platform.system() == "Windows" else "python3"
            manual = '%s "%s"' % (interpreter, script)
            variants = [
                manual,
                '%s %s' % (interpreter, str(script).replace("\\", "/")),
                '%s "%s"' % (interpreter.upper(), str(script).upper().replace("HOOKS", "hooks")),
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

    def test_claude_replaces_a_manual_install_that_uses_another_interpreter(self):
        # The same script under a different interpreter is not "already registered",
        # but it must be replaced rather than left beside the new entry (a double run).
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            claude.mkdir()
            script = claude / "hooks" / HOOK_FILE
            settings_path = claude / "settings.json"
            settings_path.write_text(json.dumps(
                self._manual_settings('some-other-python "%s"' % script)), encoding="utf-8")

            real = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME])

            self.assertEqual(real.returncode, 0, real.stdout + real.stderr)
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            commands = [h["command"] for entry in settings["hooks"]["PreToolUse"]
                        for h in entry["hooks"]]
            self.assertEqual(len(commands), 1, commands)
            self.assertNotIn("some-other-python", commands[0])
            self.assertTrue(commands[0].endswith('%s"' % HOOK_FILE), commands[0])

    def test_claude_moves_a_registration_under_an_outdated_matcher(self):
        # The pre-c38bfd7 matcher left edits out, so the count never reset.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude = home / ".claude"
            claude.mkdir()
            script = claude / "hooks" / HOOK_FILE
            interpreter = "python" if platform.system() == "Windows" else "python3"
            settings = self._manual_settings('%s "%s"' % (interpreter, script))
            settings["hooks"]["PreToolUse"][0]["matcher"] = "Bash|Read"
            settings["hooks"]["PreToolUse"][0]["hooks"].append(
                {"type": "command", "command": "keep-me"})
            settings_path = claude / "settings.json"
            settings_path.write_text(json.dumps(settings), encoding="utf-8")

            dry = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME, "--dry-run"])
            self.assertIn("will register", dry.stdout)
            for _ in range(2):
                real = self._run(home, ["--agent", "claude", "--hooks", HOOK_NAME])
                self.assertEqual(real.returncode, 0, real.stdout + real.stderr)
            self.assertIn("nothing new to register", real.stdout)

            pre = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
            by_matcher = {g["matcher"]: [h["command"] for h in g["hooks"]] for g in pre}
            self.assertEqual(by_matcher["Bash|Read"], ["keep-me"])
            current = by_matcher["Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit"]
            self.assertEqual(len(current), 1)
            self.assertIn(HOOK_FILE, current[0])

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

    def test_cursor_moves_an_entry_under_an_outdated_matcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cursor = home / ".cursor"
            cursor.mkdir()
            script = cursor / "hooks" / HOOK_FILE
            interpreter = "python" if platform.system() == "Windows" else "python3"
            (cursor / "hooks.json").write_text(json.dumps({"version": 1, "hooks": {"preToolUse": [
                {"command": '%s "%s"' % (interpreter, script), "timeout": 10, "matcher": "Shell|Read"},
            ]}}), encoding="utf-8")
            args = ["--agent", "cursor", "--cursor-dir", str(cursor), "--hooks", HOOK_NAME, "--skills", "none"]

            for _ in range(2):
                proc = self._run(home, args)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("nothing new to register", proc.stdout)
            entries = json.loads((cursor / "hooks.json").read_text(encoding="utf-8"))["hooks"]["preToolUse"]
            self.assertEqual([e["matcher"] for e in entries], ["Shell|Read|Write|Delete"])

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
                "my-own-hook": {"PreToolUse": [{"matcher": "run_command", "hooks": [
                    {"type": "command", "command": "python keep-me.py", "timeout": 10}]}]},
            }
            (config / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")
            args = self._agy_args(gemini, "--hooks", HOOK_NAME)

            first = self._run(home, args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            merged = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["my-own-hook"], existing["my-own-hook"])
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

    def test_antigravity_unknown_hook_name_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            gemini = home / ".gemini"

            proc = self._run(home, self._agy_args(gemini, "--hooks", "no-such-hook,%s" % HOOK_NAME))

            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("Unknown hook(s): no-such-hook", proc.stdout)
            self.assertFalse(gemini.exists())

    def test_antigravity_selection_skips_a_name_without_a_registration(self):
        import argparse
        from unittest import mock

        args = argparse.Namespace(hooks="claim-guard,%s" % HOOK_NAME, hooks_explicit=True)
        only_doom = {HOOK_NAME: installer_module.ANTIGRAVITY_HOOKS[HOOK_NAME]}
        with mock.patch.dict(installer_module.ANTIGRAVITY_HOOKS, only_doom, clear=True):
            self.assertEqual(installer_module.antigravity_selection(args), [HOOK_NAME])

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


AGY_GUARDS = ("danger-zone-guard", "test-gate-guard", "no-emoji-guard", "claim-guard", "lint-gate")
AGY_GUARD_FILES = {
    "danger-zone-guard": ["danger_zone_guard.py"],
    "test-gate-guard": ["test_gate_guard.py"],
    "no-emoji-guard": ["no-emoji-guard.py"],
    "claim-guard": ["claim_ledger_tracker.py", "claim_evidence_guard.py"],
    "lint-gate": ["lint_gate.py"],
}


class AntigravityGuardInstallTests(unittest.TestCase):
    """`--agent antigravity --hooks <guards>`: named entries in Antigravity's own layout."""

    def _run(self, home, extra):
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--agent", "antigravity",
             "--gemini-dir", str(home / ".gemini"), *extra],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )

    def _skip_if_space(self, path):
        if any(ch.isspace() for ch in str(path)):
            self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")

    def _doom_entry(self, config_dir, matcher=None):
        script = config_dir / "hooks" / HOOK_FILE
        command = "%s %s" % ("python" if platform.system() == "Windows" else "python3", script)
        if matcher is None:
            matcher = installer_module.ANTIGRAVITY_HOOKS[HOOK_NAME][0]["matcher"]
        return {"PreToolUse": [{"matcher": matcher, "hooks": [
            {"type": "command", "command": command, "timeout": 10}]}]}

    def test_a_registration_under_an_outdated_matcher_is_moved_not_kept(self):
        # Before c38bfd7 the doom-loop guard was registered for run_command and
        # view_file only, so it never saw an edit reset its count. A re-run must
        # move it to the current matcher, not report it as already registered.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            config = home / ".gemini" / "config"
            config.mkdir(parents=True)
            (config / "hooks.json").write_text(json.dumps(
                {"anti-doom-loop-guard": self._doom_entry(config, "run_command|view_file")}),
                encoding="utf-8")

            dry = self._run(home, ["--dry-run", "--hooks", "anti-doom-loop-guard"])
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            self.assertIn("will register", dry.stdout)

            for _ in range(2):  # the second run must find it registered and add nothing
                proc = self._run(home, ["--hooks", "anti-doom-loop-guard"])
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            merged = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(merged["anti-doom-loop-guard"], self._doom_entry(config))
            self.assertIn("nothing new to register", proc.stdout)

    def _fire(self, script, payload, **env_extra):
        env = dict(os.environ)
        env["HARNESS_GUARD_STATE_DIR"] = str(Path(script).parent / "state")
        env["CLAIM_GUARD_LEDGER_DIR"] = str(Path(script).parent / "ledger")
        env.update(env_extra)
        return subprocess.run([sys.executable, str(script)], input=json.dumps(payload).encode("utf-8"),
                              capture_output=True, env=env, timeout=30)

    def test_registers_every_guard_in_antigravitys_layout_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            config = home / ".gemini" / "config"
            config.mkdir(parents=True)
            keep = {"my-own-hook": {"PostToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": "python keep-me.py"}]}]},
                    "anti-doom-loop-guard": self._doom_entry(config)}
            (config / "hooks.json").write_text(json.dumps(keep), encoding="utf-8")
            args = ["--hooks", ",".join(("anti-doom-loop-guard",) + AGY_GUARDS)]

            first = self._run(home, args)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            merged = json.loads((config / "hooks.json").read_text(encoding="utf-8"))
            self.assertNotIn("hooks", merged)
            self.assertEqual(merged["my-own-hook"], keep["my-own-hook"])
            self.assertEqual(merged["anti-doom-loop-guard"], keep["anti-doom-loop-guard"],
                             "the doom-loop entry that was already there is left exactly as it is")
            self.assertEqual(installer_module.antigravity_config_problems(merged), [])

            for name in ("danger-zone-guard", "test-gate-guard"):
                group = merged[name]["PreToolUse"]
                self.assertEqual([g["matcher"] for g in group], ["run_command"])
            self.assertEqual(set(merged["no-emoji-guard"]["PreToolUse"][0]["matcher"].split("|")),
                             {"write_to_file", "replace_file_content", "multi_replace_file_content"})
            tracker = merged["claim-guard"]["PostToolUse"]
            self.assertEqual(set(tracker[0]["matcher"].split("|")),
                             {"run_command", "grep_search", "find_by_name", "list_dir",
                              "write_to_file", "replace_file_content", "multi_replace_file_content"})
            # Stop is a flat list of handlers: no matcher group around them.
            for name in ("claim-guard", "lint-gate"):
                stop = merged[name]["Stop"]
                self.assertEqual(len(stop), 1)
                self.assertNotIn("hooks", stop[0])
                self.assertNotIn("matcher", stop[0])
                self.assertEqual(stop[0]["type"], "command")
            self.assertEqual(merged["lint-gate"]["Stop"][0]["timeout"], 60)
            for name, entry in merged.items():
                for event, value in entry.items():
                    for handler in ([h for g in value for h in g["hooks"]]
                                    if event in ("PreToolUse", "PostToolUse") else value):
                        self.assertNotIn('"', handler["command"], name)
                        self.assertNotIn("'", handler["command"], name)
            installed = sorted(p.name for p in (config / "hooks").iterdir())
            expected = sorted([HOOK_FILE] + [f for n in AGY_GUARDS for f in AGY_GUARD_FILES[n]])
            self.assertEqual(installed, expected)
            self.assertTrue(list((home / ".gemini" / "backups").glob("hooks.json.bak-*")))
            self.assertIn("herdr", first.stdout)
            self.assertIn("transcriptPath", first.stdout, "the claim-guard limit has to be said out loud")

            again = self._run(home, args)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("nothing new to register", again.stdout)
            self.assertEqual(json.loads((config / "hooks.json").read_text(encoding="utf-8")), merged)

    def test_all_resolves_to_every_registered_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            proc = self._run(home, ["--hooks", "all"])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            merged = json.loads((home / ".gemini" / "config" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(set(merged), {HOOK_NAME, *AGY_GUARDS})

    def test_installed_guards_answer_in_antigravitys_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            self.assertEqual(self._run(home, ["--hooks", ",".join(AGY_GUARDS)]).returncode, 0)
            hooks = home / ".gemini" / "config" / "hooks"
            common = {"conversationId": "agy-install-1", "workspacePaths": [str(home)],
                      "transcriptPath": str(home / "transcript.jsonl"), "modelName": "auto"}

            def pre(command):
                return dict(common, toolCall={"name": "run_command", "args": {"CommandLine": command}}, stepIdx=3)

            denied = self._fire(hooks / "danger_zone_guard.py", pre("rm -rf /"))
            self.assertEqual(denied.returncode, 0)
            self.assertEqual(json.loads(denied.stdout)["decision"], "deny")
            allowed = self._fire(hooks / "danger_zone_guard.py", pre("rm -rf dist/"))
            self.assertEqual(json.loads(allowed.stdout), {"decision": "ask"},
                             "an allow defers to the permission flow: {} reads as a deny, allow auto-approves")
            gated = self._fire(hooks / "test_gate_guard.py", pre("pytest ; git push"))
            self.assertEqual(json.loads(gated.stdout)["decision"], "deny")
            emoji = self._fire(hooks / "no-emoji-guard.py", dict(common, toolCall={
                "name": "write_to_file", "args": {"TargetFile": str(home / "a.md"), "CodeContent": "hi \U0001F680"}}))
            self.assertEqual(json.loads(emoji.stdout)["decision"], "deny")

            (home / "transcript.jsonl").write_text(json.dumps(
                {"type": "PLANNER_RESPONSE", "text": "All tests pass, verified."}) + "\n", encoding="utf-8")
            stop = dict(common, executionNum=1, terminationReason="NO_TOOL_CALL", fullyIdle=True)
            claim = self._fire(hooks / "claim_evidence_guard.py", stop)
            self.assertEqual(json.loads(claim.stdout)["decision"], "continue")

    def test_dry_run_with_every_guard_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            config = home / ".gemini" / "config"
            config.mkdir(parents=True)
            (config / "hooks.json").write_text(json.dumps({"anti-doom-loop-guard": self._doom_entry(config)}),
                                               encoding="utf-8")
            before = _snapshot(home)

            proc = self._run(home, ["--dry-run", "--hooks", ",".join(("anti-doom-loop-guard",) + AGY_GUARDS)])

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(_snapshot(home), before, "a dry run must not touch anything")
            self.assertEqual(proc.stdout.count("will register"), 6)  # 5 guards, claim-guard has 2 handlers
            self.assertEqual(proc.stdout.count("already registered"), 1)
            self.assertIn("would write (dry run, nothing was written)", proc.stdout)

    def test_refuses_to_write_next_to_a_claude_layout_hooks_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            config = home / ".gemini" / "config"
            config.mkdir(parents=True)
            legacy = {"hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "x.py"}]}]}}
            (config / "hooks.json").write_text(json.dumps(legacy), encoding="utf-8")
            before = _snapshot(home)

            for extra in (["--dry-run"], []):
                with self.subTest(extra=extra):
                    proc = self._run(home, [*extra, "--hooks", "danger-zone-guard"])
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertIn("REFUSED", proc.stdout)
                    self.assertIn('top-level "hooks" key', proc.stdout)
                    self.assertEqual(_snapshot(home), before, "a refusal writes nothing, not even a backup")

    def test_refuses_a_user_entry_that_antigravity_would_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._skip_if_space(home)
            config = home / ".gemini" / "config"
            config.mkdir(parents=True)
            # Stop wrapped in a matcher group: the shape the Claude-layout file used.
            broken = {"mine": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "x.py"}]}]}}
            (config / "hooks.json").write_text(json.dumps(broken), encoding="utf-8")
            before = _snapshot(home)

            proc = self._run(home, ["--hooks", "lint-gate"])

            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("mine.Stop must be a flat list of handlers", proc.stdout)
            self.assertEqual(_snapshot(home), before)

    def test_config_problems_accepts_what_the_installer_writes_and_the_docs_example(self):
        docs_example = {
            "lint-checker": {"PostToolUse": [{"matcher": "run_command", "hooks": [
                {"type": "command", "command": "./scripts/lint.sh", "timeout": 10}]}]},
            "safety-gate": {"enabled": False, "PreToolUse": [{"matcher": "run_command", "hooks": [
                {"command": "./scripts/safety-check.sh"}]}]},
            "reminder": {"PreInvocation": [{"type": "command", "command": "./scripts/reminder.sh"}]},
        }
        self.assertEqual(installer_module.antigravity_config_problems(docs_example), [])
        self.assertTrue(installer_module.antigravity_config_problems({"hooks": {}}))
        self.assertTrue(installer_module.antigravity_config_problems({"a": {"PreToolUse": [{"hooks": [{}]}]}}))
        self.assertTrue(installer_module.antigravity_config_problems([]))


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

    def test_claude_claim_tracker_must_see_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = self._env(home)
            proc = subprocess.run(
                [sys.executable, str(INSTALLER), "--agent", "claude", "--hooks", "claim-guard",
                 "--skills", "none"],
                cwd=str(REPO), env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            ok = self._verify(env, "claude")
            self.assertIn("PASS claim-ledger-tracker matcher covers Edit and Write", ok.stdout)

            settings_path = home / ".claude" / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            settings["hooks"]["PostToolUse"][0]["matcher"] = "Bash|Grep|Glob"  # the old one
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            old = self._verify(env, "claude")
            self.assertEqual(old.returncode, 1, old.stdout + old.stderr)
            self.assertIn("FAIL claim-ledger-tracker matcher covers Edit and Write", old.stdout)

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

    def test_every_antigravity_guard_is_live_fired(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            if any(ch.isspace() for ch in str(home)):
                self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")
            env = self._env(home)
            proc = subprocess.run(
                [sys.executable, str(INSTALLER), "--agent", "antigravity", "--hooks", "all", "--skills", "none"],
                cwd=str(REPO), env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            verified = self._verify(env, "antigravity")

            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            for line in (
                'PASS Antigravity hooks.json has no Claude Code layout top-level "hooks" key',
                "PASS Antigravity danger-zone-guard denies `rm -rf /`",
                "PASS Antigravity danger-zone-guard allows `rm -rf dist/` (decision ask)",
                "PASS Antigravity test-gate-guard denies `pytest ; git push`",
                "PASS Antigravity test-gate-guard allows `pytest && git push` (decision ask)",
                "PASS Antigravity no-emoji-guard denies a write containing emoji",
                "PASS Antigravity no-emoji-guard allows a clean write (decision ask)",
                "PASS Antigravity claim-guard continues 'tests pass' with an empty ledger",
                "PASS Antigravity claim-guard allows the same claim once the ledger has a test run",
                "PASS Antigravity lint-gate continues when the project's check fails",
                "PASS Antigravity lint-gate lets the identical failure through the second time",
                "PASS Antigravity anti-doom-loop-guard blocks the third identical command in a row",
            ):
                self.assertIn(line, verified.stdout)

    def test_antigravity_stop_in_a_matcher_group_or_a_hooks_key_fails_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            if any(ch.isspace() for ch in str(home)):
                self.skipTest("Antigravity cannot quote a hook command; the temp path has a space")
            env = self._env(home)
            subprocess.run(
                [sys.executable, str(INSTALLER), "--agent", "antigravity", "--hooks", "lint-gate", "--skills", "none"],
                cwd=str(REPO), env=env, capture_output=True, text=True, timeout=60, check=True)
            path = home / ".gemini" / "config" / "hooks.json"
            config = json.loads(path.read_text(encoding="utf-8"))
            config["lint-gate"]["Stop"] = [{"matcher": "*", "hooks": config["lint-gate"]["Stop"]}]
            path.write_text(json.dumps(config), encoding="utf-8")

            proc = self._verify(env, "antigravity")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("FAIL Antigravity lint-gate uses Antigravity's event layout", proc.stdout)

            config["hooks"] = {"Stop": []}
            path.write_text(json.dumps(config), encoding="utf-8")
            proc = self._verify(env, "antigravity")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn('FAIL Antigravity hooks.json has no Claude Code layout top-level "hooks" key', proc.stdout)

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

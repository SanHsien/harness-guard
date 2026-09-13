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


if __name__ == "__main__":
    unittest.main()

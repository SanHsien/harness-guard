import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "scripts" / "install.py"


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


if __name__ == "__main__":
    unittest.main()

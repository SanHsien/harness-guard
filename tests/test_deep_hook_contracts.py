"""Regression cases from the line-by-line hooks/installer audit."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import install

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("HARNESS_TEST_BASH") or shutil.which("bash")


class BackupTests(unittest.TestCase):
    def test_same_second_backups_preserve_both_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "settings.json"
            backups = Path(tmp) / "backups"
            source.write_text('{"value": 1}', encoding="utf-8")
            with patch.object(install.time, "strftime", return_value="20261028-120000"):
                first = install.backup_json(source, backups)
                source.write_text('{"value": 2}', encoding="utf-8")
                second = install.backup_json(source, backups)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads(first.read_text()), {"value": 1})
            self.assertEqual(json.loads(second.read_text()), {"value": 2})


class PatchEmojiTests(unittest.TestCase):
    def test_raw_and_named_patch_payloads_are_scanned(self):
        script = ROOT / "hooks/no-emoji-guard/codex/no-emoji-guard.py"
        body = "*** Begin Patch\n*** Add File: probe.md\n+ship it \U0001f680\n*** End Patch"
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text('{"enabled": true}', encoding="utf-8")
            for value in (body, {"patch": body}, {"input": body}, {"command": body}):
                with self.subTest(value=type(value).__name__ + str(value)[:15]):
                    result = subprocess.run(
                        [sys.executable, str(script)],
                        input=json.dumps({"tool_name": "apply_patch", "tool_input": value}),
                        text=True, encoding="utf-8", capture_output=True,
                        env={**os.environ, "NO_EMOJI_GUARD_CONFIG": str(config)}, timeout=15,
                    )
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_added_content_starting_with_two_pluses_is_not_a_diff_header(self):
        script = ROOT / "hooks/no-emoji-guard/codex/no-emoji-guard.py"
        body = "*** Begin Patch\n*** Add File: probe.md\n+++ \U0001f680\n*** End Patch"
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text('{"enabled": true}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script)],
                input=json.dumps({"tool_name": "apply_patch", "tool_input": {"command": body}}),
                text=True, encoding="utf-8", capture_output=True,
                env={**os.environ, "NO_EMOJI_GUARD_CONFIG": str(config)}, timeout=15,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


@unittest.skipUnless(BASH and shutil.which("jq"), "POSIX shell contracts require bash and jq")
class ShellLedgerTests(unittest.TestCase):
    def invoke(self, agent, name, payload, env):
        script = ROOT / "hooks/claim-guard" / agent / name
        result = subprocess.run([BASH, str(script)], input=json.dumps(payload),
                                text=True, encoding="utf-8", capture_output=True, env=env, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_tracker_respects_isolated_ledger_directory(self):
        for agent in ("claude-code", "codex"):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ledger = root / "isolated"
                env = {**os.environ, "HOME": root.as_posix(), "CLAIM_GUARD_LEDGER_DIR": ledger.as_posix()}
                self.invoke(agent, "claim-ledger-tracker.sh", {
                    "session_id": "isolation", "tool_name": "Bash",
                    "tool_input": {"command": "pytest -q"},
                }, env)
                self.assertTrue((ledger / "isolation.verify").is_file())
                self.assertFalse((root / ".cache").exists())

    def test_session_id_cannot_escape_ledger_and_delete_a_sibling_file(self):
        for agent in ("claude-code", "codex"):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ledger = root / ".cache" / ("claude-guard-hooks" if agent == "claude-code" else "codex-guard-hooks")
                ledger.mkdir(parents=True)
                victim = ledger.parent / "victim.verify"
                victim.write_text("must survive", encoding="utf-8")
                env = {**os.environ, "HOME": root.as_posix()}
                env.pop("CLAIM_GUARD_LEDGER_DIR", None)
                self.invoke(agent, "claim-evidence-guard.sh", {
                    "session_id": "../victim", "stop_hook_active": True,
                    "last_assistant_message": "Finished editing.",
                }, env)
                self.assertTrue(victim.is_file(), "cleanup escaped its ledger directory")


if __name__ == "__main__":
    unittest.main()

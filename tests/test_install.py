import os
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


if __name__ == "__main__":
    unittest.main()

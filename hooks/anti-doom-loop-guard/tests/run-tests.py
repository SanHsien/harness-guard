#!/usr/bin/env python3
"""run-tests.py -- regression suite for anti-doom-loop-guard."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "claude-code" / "anti_doom_loop_guard.py"
sys.path.insert(0, str(HOOK.parent))
import anti_doom_loop_guard as guard  # noqa: E402


def run_hook(payload: dict, state_file: Path, log_file: Path, threshold: int = 3) -> tuple[int, str]:
    env = os.environ.copy()
    env["ANTI_DOOM_LOOP_STATE_FILE"] = str(state_file)
    env["ANTI_DOOM_LOOP_LOG_FILE"] = str(log_file)
    env["ANTI_DOOM_LOOP_THRESHOLD"] = str(threshold)

    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=30,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def main():
    passed = 0
    total = 0

    def assert_eq(actual, expected, desc):
        nonlocal passed, total
        total += 1
        if actual == expected:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            print(f"  [FAIL] {desc}: expected {expected!r}, got {actual!r}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        state_file = tmp / "state.json"
        log_file = tmp / "audit.jsonl"

        print("==> Testing repeating Bash command detection")
        bash_payload = {
            "tool_name": "Bash",
            "session_id": "test-session",
            "tool_input": {"command": "git status --short"},
        }

        # 1st time -> Allow
        code, err = run_hook(bash_payload, state_file, log_file, threshold=3)
        assert_eq(code, 0, "First execution allows")

        # 2nd time -> Allow
        code, err = run_hook(bash_payload, state_file, log_file, threshold=3)
        assert_eq(code, 0, "Second execution allows")

        # 3rd time -> Block
        code, err = run_hook(bash_payload, state_file, log_file, threshold=3)
        assert_eq(code, 2, "Third execution blocks")
        assert_eq("Detected repeating command loop" in err, True, "Error mentions repeating command loop")

        # 4th time: Alternate command resets loop
        alt_payload = {
            "tool_name": "Bash",
            "session_id": "test-session",
            "tool_input": {"command": "git diff"},
        }
        code, err = run_hook(alt_payload, state_file, log_file, threshold=3)
        assert_eq(code, 0, "Different command resets and allows")

        print("==> Testing repeating Read file query detection")
        read_payload = {
            "tool_name": "Read",
            "session_id": "test-session",
            "tool_input": {"file_path": "src/main.py", "offset": 0, "limit": 100},
        }

        # 1st read -> Allow
        code, err = run_hook(read_payload, state_file, log_file, threshold=3)
        assert_eq(code, 0, "First read allows")

        # 2nd read -> Allow
        code, err = run_hook(read_payload, state_file, log_file, threshold=3)
        assert_eq(code, 0, "Second read allows")

        # 3rd read -> Block
        code, err = run_hook(read_payload, state_file, log_file, threshold=3)
        assert_eq(code, 2, "Third read blocks")
        assert_eq("read src/main.py" in err, True, "Error mentions target file")

        print("==> Testing audit logging")
        assert_eq(log_file.is_file(), True, "Audit log file was created")
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert_eq(len(lines), 2, "Audit log has 2 blocked events recorded")
        first_event = json.loads(lines[0])
        assert_eq(first_event["action"], "blocked", "Logged event marked as blocked")
        assert_eq(first_event["threshold"], 3, "Logged event recorded correct threshold")

        print("==> Testing robustness & fail-open")
        # Malformed stdin
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=b"{invalid-json",
            capture_output=True,
            timeout=30,
        )
        assert_eq(proc.returncode, 0, "Invalid JSON input fails open (exit 0)")

        # Empty payload
        code, err = run_hook({}, state_file, log_file, threshold=3)
        assert_eq(code, 0, "Empty payload fails open (exit 0)")

    print(f"\nResults: {passed}/{total} tests passed.")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

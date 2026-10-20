#!/usr/bin/env python3
"""run-tests.py -- regression suite for checkout-guard (Claude Code build)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "claude-code" / "checkout_guard.py"
sys.path.insert(0, str(HOOK.parent))
import checkout_guard as guard  # noqa: E402


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def run(payload, home, holder=None):
    env = {k: v for k, v in os.environ.items() if k != "AGENT_RELAY_HOLDER"}
    env["AGENT_RELAY_HOME"] = str(home)
    if holder:
        env["AGENT_RELAY_HOLDER"] = holder
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True, env=env, timeout=60)
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        repo = tmp / "repo"
        repo.mkdir()
        git("init", "-q", cwd=repo)
        git("remote", "add", "origin", "https://user:secret@github.com/Example/Demo.git", cwd=repo)
        home, store = tmp / "home", tmp / "store"
        home.mkdir()
        (home / "config.json").write_text(json.dumps({"store": str(store), "agent": "commander"}), encoding="utf-8")
        rid = guard.repo_id(repo)
        assert rid == "https://github.com/example/demo", rid
        claims = store / "claims" / guard.repo_key(rid)
        claims.mkdir(parents=True)
        now = time.time()
        for cid, holder, paths, expires in (
            ("c1", "relay:task-a", ["calc.py", "src/"], now + 600),
            ("c2", f"manual:commander@{socket.gethostname().lower()}", ["mine.py"], now + 600),
            ("c3", "relay:old", ["stale.py"], now - 1),
        ):
            (claims / f"{cid}.json").write_text(json.dumps({"schema": "agent-relay/claim@1", "id": cid, "holder": holder, "paths": paths,
                                                            "expires": expires, "expires_at": "later"}), encoding="utf-8")

        def edit(rel, tool="Edit"):
            return {"tool_name": tool, "cwd": str(repo), "session_id": "s",
                    "tool_input": {"file_path": str(repo / rel)}}

        cases = [
            (edit("calc.py"), None, home, 2, "file checked out by another agent"),
            (edit("src/deep/x.py", "Write"), None, home, 2, "folder claim covers nested new file"),
            (edit("CALC.PY"), None, home, 2, "case-insensitive on Windows paths"),
            (edit("calc.py"), "relay:task-a", home, 0, "the holder itself may edit"),
            (edit("mine.py"), None, home, 0, "my own manual claim does not block me"),
            (edit("stale.py"), None, home, 0, "expired claim does not block"),
            (edit("other.py"), None, home, 0, "unclaimed file"),
            ({"tool_name": "Read", "tool_input": {"file_path": str(repo / "calc.py")}}, None, home, 0, "reads are not blocked"),
            (edit("calc.py"), None, tmp / "no-relay", 0, "agent-relay not set up"),
            ({"tool_name": "Edit", "tool_input": {"file_path": str(tmp / "outside.txt")}}, None, home, 0, "outside any repo"),
        ]
        for payload, holder, use_home, want, label in cases:
            code, err = run(payload, use_home, holder)
            ok = code == want and (want == 0 or "relay:task-a" in err)
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {label}  (exit {code})")

        # a broken claim (expires null) and one without schema are skipped; the good claim still blocks
        (claims / "bad.json").write_text(json.dumps({"schema": "agent-relay/claim@1", "id": "bad", "holder": "x",
                                                     "paths": ["calc.py"], "expires": None}), encoding="utf-8")
        (claims / "noschema.json").write_text(json.dumps({"id": "noschema", "holder": "y", "paths": ["free.py"],
                                                          "expires": now + 600}), encoding="utf-8")
        for payload, want, label in ((edit("calc.py"), 2, "broken claim file does not switch the guard off"),
                                     (edit("free.py"), 0, "claim without schema is ignored")):
            code, _ = run(payload, home)
            failures += code != want
            print(f"{'PASS' if code == want else 'FAIL'}  {label}  (exit {code})")

        # store given only through AGENT_RELAY_STORE (no config.json), like relay dispatch --store
        env_home = tmp / "env-home"
        env_home.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "AGENT_RELAY_HOLDER"}
        env.update({"AGENT_RELAY_HOME": str(env_home), "AGENT_RELAY_STORE": str(store)})
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(edit("calc.py")).encode("utf-8"),
                              capture_output=True, env=env, timeout=60)
        failures += proc.returncode != 2
        print(f"{'PASS' if proc.returncode == 2 else 'FAIL'}  store from AGENT_RELAY_STORE  (exit {proc.returncode})")

        log = (home / "touch-log.jsonl").read_text(encoding="utf-8").splitlines()
        decisions = [json.loads(line)["decision"] for line in log]
        ok = "deny" in decisions and "allow" in decisions
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  touch log records allow and deny ({len(log)} entries)")

        code, _ = run({"tool_name": "Edit", "tool_input": "not-a-dict"}, home)
        failures += code != 0
        print(f"{'PASS' if code == 0 else 'FAIL'}  malformed payload allows")
    print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

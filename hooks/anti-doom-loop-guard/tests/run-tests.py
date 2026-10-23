#!/usr/bin/env python3
"""run-tests.py -- regression suite for anti-doom-loop-guard.

    python hooks/anti-doom-loop-guard/tests/run-tests.py

One file serves four agents, so every agent gets the same three questions asked
in its own words, with a payload shaped like the real thing:

  1. An edit between two identical commands never blocks (the normal fix loop).
  2. Three identical calls in a row block, in that agent's deny format.
  3. Malformed input fails open.

Payload shapes come from each agent's hook documentation (Claude Code and Codex
PreToolUse, Cursor preToolUse / beforeShellExecution / afterFileEdit, Antigravity
PreToolUse with toolCall). Cursor and Claude Code both send `hook_event_name`,
so the Cursor cases also pin that the two are not confused.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "claude-code" / "anti_doom_loop_guard.py"
sys.path.insert(0, str(HOOK.parent))
import anti_doom_loop_guard as guard  # noqa: E402


def run_raw(payload, state_file: Path, log_file: Path, threshold: int = 3, args=()):
    env = os.environ.copy()
    env["ANTI_DOOM_LOOP_STATE_FILE"] = str(state_file)
    env["ANTI_DOOM_LOOP_LOG_FILE"] = str(log_file)
    env["ANTI_DOOM_LOOP_THRESHOLD"] = str(threshold)

    data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return subprocess.run(
        [sys.executable, str(HOOK), *args],
        input=data,
        capture_output=True,
        env=env,
        timeout=30,
    )


def run_hook(payload: dict, state_file: Path, log_file: Path, threshold: int = 3, args=()) -> tuple[int, str]:
    proc = run_raw(payload, state_file, log_file, threshold, args)
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def stdout_json(proc):
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return None


# -- realistic payloads, one family per agent ----------------------------------


def claude_bash(command, session="claude-s1"):
    return {
        "session_id": session,
        "transcript_path": "C:\\Users\\dev\\.claude\\projects\\p\\t.jsonl",
        "cwd": "C:\\work\\proj",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "toolu_01ABC",
    }


def claude_edit(session="claude-s1"):
    return {
        "session_id": session,
        "cwd": "C:\\work\\proj",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.py", "old_string": "a", "new_string": "b"},
        "tool_use_id": "toolu_01DEF",
    }


def codex_event(tool_name, tool_input, session="codex-s1"):
    return {
        "session_id": session,
        "turn_id": "turn-7",
        "transcript_path": None,
        "cwd": "C:\\work\\proj",
        "hook_event_name": "PreToolUse",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "tool_name": tool_name,
        "tool_use_id": "call_abc",
        "tool_input": tool_input,
    }


def cursor_base(event, conversation="cursor-c1"):
    return {
        "conversation_id": conversation,
        "generation_id": "gen-1",
        "model": "claude-opus-4-7",
        "hook_event_name": event,
        "cursor_version": "1.7.2",
        "workspace_roots": ["C:\\work\\proj"],
        "user_email": None,
        "transcript_path": None,
    }


def cursor_pre_tool(tool_name, tool_input, conversation="cursor-c1"):
    payload = cursor_base("preToolUse", conversation)
    payload.update({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "abc123",
        "cwd": "C:\\work\\proj",
        "agent_message": "working on it",
    })
    return payload


def cursor_shell(command, conversation="cursor-c1"):
    payload = cursor_base("beforeShellExecution", conversation)
    payload.update({"command": command, "cwd": "C:\\work\\proj", "sandbox": False})
    return payload


def cursor_edit(conversation="cursor-c1"):
    payload = cursor_base("afterFileEdit", conversation)
    payload.update({
        "file_path": "C:\\work\\proj\\src\\app.py",
        "edits": [{"old_string": "a", "new_string": "b"}],
    })
    return payload


def agy_event(name, args, conversation="agy-conv-1"):
    return {
        "toolCall": {"name": name, "args": args},
        "stepIdx": 19,
        "conversationId": conversation,
        "workspacePaths": ["C:\\work\\proj"],
        "transcriptPath": "C:\\work\\proj\\.gemini\\antigravity-cli\\transcript.jsonl",
        "artifactDirectoryPath": "C:\\work\\proj\\.gemini\\antigravity-cli\\artifacts",
        "modelName": "auto",
    }


# -- per-agent "is this a deny, in my words" ------------------------------------


def denied_claude(proc):
    err = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode == 2 and "Detected repeating command loop" in err and not proc.stdout.strip()


def denied_codex(proc):
    data = stdout_json(proc)
    return (proc.returncode == 0 and isinstance(data, dict) and data.get("decision") == "block"
            and "Detected repeating command loop" in data.get("reason", ""))


def denied_cursor(proc):
    data = stdout_json(proc)
    return (proc.returncode == 0 and isinstance(data, dict) and data.get("permission") == "deny"
            and "Detected repeating command loop" in data.get("agent_message", "")
            and "Detected repeating command loop" in data.get("user_message", ""))


def denied_antigravity(proc):
    data = stdout_json(proc)
    return (proc.returncode == 0 and isinstance(data, dict) and data.get("decision") == "deny"
            and "Detected repeating command loop" in data.get("reason", ""))


def not_a_deny(proc):
    """Allowed: exit 0 and no deny / block in whatever was printed."""
    if proc.returncode != 0:
        return False
    data = stdout_json(proc)
    if data is None:
        return False
    return (data.get("decision") not in ("block", "deny") and data.get("permission") != "deny")


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
        assert_eq(first_event["agent"], "claude", "Logged event names the agent")

        print("==> Testing that another tool call between repeats resets the count")
        reset_state = tmp / "reset-state.json"
        test_cmd = {"tool_name": "Bash", "session_id": "edit-loop",
                    "tool_input": {"command": "python -m unittest discover -s tests"}}
        edit = {"tool_name": "Edit", "session_id": "edit-loop",
                "tool_input": {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}}
        codes = []
        for _ in range(4):  # test -> edit -> test -> edit ... the normal fix loop
            codes.append(run_hook(test_cmd, reset_state, log_file, threshold=3)[0])
            run_hook(edit, reset_state, log_file, threshold=3)
        assert_eq(codes, [0, 0, 0, 0], "Test runs separated by edits are never blocked")
        for _ in range(2):
            run_hook(test_cmd, reset_state, log_file, threshold=3)
        assert_eq(run_hook(test_cmd, reset_state, log_file, threshold=3)[0], 2,
                  "Three identical runs with nothing in between are still blocked")

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

        # -- Claude Code, realistic payload ------------------------------------
        print("==> Claude Code (PreToolUse, exit 2 + stderr)")
        st = tmp / "claude.json"
        outcomes = []
        for _ in range(4):
            outcomes.append(run_raw(claude_bash("pytest -q"), st, log_file))
            run_raw(claude_edit(), st, log_file)
        assert_eq([p.returncode for p in outcomes], [0, 0, 0, 0], "Claude: alternating command/edit never blocks")
        assert_eq(all(not_a_deny(p) for p in outcomes), True, "Claude: allowed calls print no deny")
        runs = [run_raw(claude_bash("npm run build"), st, log_file) for _ in range(3)]
        assert_eq([p.returncode for p in runs], [0, 0, 2], "Claude: third identical command blocks")
        assert_eq(denied_claude(runs[2]), True, "Claude: deny is exit 2 with the reason on stderr only")
        proc = run_raw(b"\xff\xfe{not json", st, log_file)
        assert_eq((proc.returncode, proc.stdout), (0, b""), "Claude: malformed input fails open silently")
        proc = run_raw(["not", "an", "object"], st, log_file)
        assert_eq(proc.returncode, 0, "Claude: a JSON array instead of an object fails open")
        proc = run_raw({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": "oops"}, st, log_file)
        assert_eq(proc.returncode, 0, "Claude: tool_input of the wrong type fails open")

        # -- Codex -------------------------------------------------------------
        print("==> Codex (PreToolUse with --agent codex, exit 0 + decision block)")
        st = tmp / "codex.json"
        patch = {"command": "*** Begin Patch\n*** Update File: src/app.py\n@@\n-a\n+b\n*** End Patch"}
        outcomes = []
        for _ in range(4):
            outcomes.append(run_raw(codex_event("Bash", {"command": "cargo test"}), st, log_file, args=("--agent", "codex")))
            run_raw(codex_event("apply_patch", patch), st, log_file, args=("--agent", "codex"))
        assert_eq([p.returncode for p in outcomes], [0, 0, 0, 0], "Codex: alternating command/apply_patch never blocks")
        assert_eq(all(not_a_deny(p) for p in outcomes), True, "Codex: allowed calls are not blocks")
        assert_eq(outcomes[0].stdout.decode().strip(), "{}", "Codex: allowing prints {} like the other Codex hooks")
        runs = [run_raw(codex_event("Bash", {"command": "cargo build"}), st, log_file, args=("--agent", "codex"))
                for _ in range(3)]
        assert_eq([p.returncode for p in runs], [0, 0, 0], "Codex: a block is exit 0 ...")
        assert_eq(denied_codex(runs[2]), True, "Codex: ... with {\"decision\":\"block\",\"reason\":...} on stdout")
        assert_eq(denied_codex(runs[1]), False, "Codex: the second identical command is still allowed")
        # apply_patch carries its patch text in tool_input.command; it must never be counted as a command.
        st_patch = tmp / "codex-patch.json"
        patches = [run_raw(codex_event("apply_patch", patch), st_patch, log_file, args=("--agent", "codex"))
                   for _ in range(4)]
        assert_eq(all(not_a_deny(p) for p in patches), True, "Codex: repeated apply_patch is an edit, not a loop")
        st_exec = tmp / "codex-exec.json"
        execs = [run_raw(codex_event("exec_command", {"cmd": "ls -la"}), st_exec, log_file, args=("--agent", "codex"))
                 for _ in range(3)]
        assert_eq(denied_codex(execs[2]), True, "Codex: exec_command with `cmd` is counted too")
        st_alias = tmp / "codex-alias.json"
        legacy = [run_raw(codex_event("Bash", {"command": "ls"}), st_alias, log_file, args=("--codex",))
                  for _ in range(3)]
        assert_eq(denied_codex(legacy[2]), True, "Codex: the older --codex spelling selects the same adapter")
        unflagged = [run_raw(codex_event("Bash", {"command": "ls -R"}), tmp / "codex-bare.json", log_file)
                     for _ in range(3)]
        assert_eq(unflagged[2].returncode, 2, "Codex without the flag still blocks (exit 2 + stderr is also valid for Codex)")
        proc = run_raw(b"{invalid-json", st, log_file, args=("--agent", "codex"))
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Codex: malformed input fails open")
        assert_eq(proc.stdout.decode().strip(), "{}", "Codex: malformed input still answers in Codex's protocol")

        # -- Cursor ------------------------------------------------------------
        print("==> Cursor (preToolUse / beforeShellExecution / afterFileEdit, exit 0 + permission deny)")
        st = tmp / "cursor.json"
        outcomes = []
        for _ in range(4):
            outcomes.append(run_raw(cursor_pre_tool("Shell", {"command": "npm test", "working_directory": "C:\\work\\proj"}),
                                    st, log_file))
            run_raw(cursor_pre_tool("Write", {"path": "C:\\work\\proj\\src\\app.py", "contents": "x"}), st, log_file)
        assert_eq([p.returncode for p in outcomes], [0, 0, 0, 0], "Cursor preToolUse: alternating Shell/Write never blocks")
        assert_eq(all(stdout_json(p) == {"permission": "allow"} for p in outcomes), True,
                  "Cursor preToolUse: allowing prints permission allow")
        runs = [run_raw(cursor_pre_tool("Shell", {"command": "npm run lint"}), st, log_file) for _ in range(3)]
        assert_eq([p.returncode for p in runs], [0, 0, 0], "Cursor: a deny is exit 0, not exit 2 ...")
        assert_eq(denied_cursor(runs[2]), True, "Cursor: ... with {\"permission\":\"deny\",...} JSON on stdout")
        assert_eq(denied_cursor(runs[1]), False, "Cursor: the second identical command is still allowed")

        st = tmp / "cursor-before-shell.json"
        outcomes = []
        for _ in range(4):
            outcomes.append(run_raw(cursor_shell("pytest -q"), st, log_file))
            run_raw(cursor_edit(), st, log_file)
        assert_eq([p.returncode for p in outcomes], [0, 0, 0, 0], "Cursor beforeShellExecution: alternating command/afterFileEdit never blocks")
        runs = [run_raw(cursor_shell("pytest -q"), st, log_file) for _ in range(3)]
        assert_eq(denied_cursor(runs[2]), True, "Cursor beforeShellExecution: third identical command denies")
        edit_proc = run_raw(cursor_edit(), st, log_file)
        assert_eq((edit_proc.returncode, stdout_json(edit_proc)), (0, {}), "Cursor afterFileEdit: resets and answers {}")

        st = tmp / "cursor-read.json"
        pages = [run_raw(cursor_pre_tool("Read", {"path": "C:\\work\\proj\\big.log", "offset": n * 200, "limit": 200}),
                         st, log_file) for n in range(4)]
        assert_eq(all(not_a_deny(p) for p in pages), True, "Cursor: paging through one file is not a loop")
        same = [run_raw(cursor_pre_tool("Read", {"path": "C:\\work\\proj\\big.log", "offset": 0, "limit": 200}),
                        st, log_file) for _ in range(3)]
        assert_eq(denied_cursor(same[2]), True, "Cursor: three identical reads deny")
        assert_eq("big.log" in json.loads(same[2].stdout)["agent_message"], True, "Cursor: the deny names the file")
        # beforeReadFile has the path but no range, so it cannot tell paging from a retry: never counted.
        read_file = cursor_base("beforeReadFile")
        read_file.update({"file_path": "C:\\work\\proj\\big.log", "content": "...", "attachments": []})
        st_br = tmp / "cursor-beforeread.json"
        outs = [run_raw(read_file, st_br, log_file) for _ in range(4)]
        assert_eq(all(stdout_json(p) == {"permission": "allow"} for p in outs), True,
                  "Cursor beforeReadFile: never counted, answers permission allow")

        # Cursor and Claude Code both send hook_event_name; only Cursor writes it in camelCase.
        claude_like = claude_bash("echo same")
        runs = [run_raw(claude_like, tmp / "not-cursor.json", log_file) for _ in range(3)]
        assert_eq(denied_claude(runs[2]), True, "A Claude payload with hook_event_name is not mistaken for Cursor")
        proc = run_raw(b"not json at all", st, log_file, args=("--agent", "cursor"))
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Cursor: malformed input fails open")
        proc = run_raw({"hook_event_name": "preToolUse", "cursor_version": "1.7.2", "tool_name": "Shell",
                        "tool_input": ["wrong"]}, st, log_file)
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Cursor: tool_input of the wrong type fails open")
        proc = run_raw(cursor_base("stop"), st, log_file)
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Cursor: an event it does not handle is allowed")

        # -- Antigravity -------------------------------------------------------
        print("==> Antigravity (PreToolUse toolCall, exit 0 + decision deny)")
        st = tmp / "agy.json"
        outcomes = []
        for _ in range(4):
            outcomes.append(run_raw(agy_event("run_command", {"CommandLine": "npm test", "Cwd": "C:\\work\\proj"}),
                                    st, log_file))
            run_raw(agy_event("replace_file_content", {"TargetFile": "C:\\work\\proj\\src\\app.py"}), st, log_file)
        assert_eq([p.returncode for p in outcomes], [0, 0, 0, 0], "Antigravity: alternating run_command/replace_file_content never blocks")
        assert_eq(all(json.loads(p.stdout.decode()) == {"decision": "ask"} for p in outcomes), True,
                  "Antigravity: allowing prints decision ask -- {} reads as a deny, \"allow\" would auto-approve")
        runs = [run_raw(agy_event("run_command", {"CommandLine": "go build ./..."}), st, log_file) for _ in range(3)]
        assert_eq([p.returncode for p in runs], [0, 0, 0], "Antigravity: a deny is exit 0 ...")
        assert_eq(denied_antigravity(runs[2]), True, "Antigravity: ... with {\"decision\":\"deny\",\"reason\":...} on stdout")
        assert_eq(denied_antigravity(runs[1]), False, "Antigravity: the second identical command is still allowed")

        st = tmp / "agy-read.json"
        pages = [run_raw(agy_event("view_file", {"AbsolutePath": "C:\\work\\proj\\big.log", "StartLine": n * 100 + 1,
                                                 "EndLine": n * 100 + 100}), st, log_file) for n in range(4)]
        assert_eq(all(not_a_deny(p) for p in pages), True, "Antigravity: paging through one file is not a loop")
        same = [run_raw(agy_event("view_file", {"AbsolutePath": "C:\\work\\proj\\big.log", "StartLine": 1, "EndLine": 100}),
                        st, log_file) for _ in range(3)]
        assert_eq(denied_antigravity(same[2]), True, "Antigravity: three identical view_file calls deny")

        pre_invocation = {"invocationNum": 3, "initialNumSteps": 10, "conversationId": "agy-conv-9",
                          "workspacePaths": ["C:\\work\\proj"], "modelName": "auto"}
        proc = run_raw(pre_invocation, st, log_file)
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Antigravity: a PreInvocation payload is not a tool call and is allowed")
        proc = run_raw(b"{invalid-json", st, log_file, args=("--agent", "antigravity"))
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Antigravity: malformed input fails open")
        proc = run_raw({"toolCall": {"name": "run_command", "args": "oops"}, "conversationId": "x"}, st, log_file)
        assert_eq((proc.returncode, not_a_deny(proc)), (0, True), "Antigravity: args of the wrong type fail open")

        # -- shared core -------------------------------------------------------
        print("==> Shared core")
        st = tmp / "shared.json"
        a = [run_raw(claude_bash("make", session="one"), st, log_file) for _ in range(2)]
        b = run_raw(claude_bash("make", session="two"), tmp / "shared-two.json", log_file)
        assert_eq(all(p.returncode == 0 for p in a + [b]), True, "Separate sessions keep separate counts")
        os.environ.pop("ANTI_DOOM_LOOP_STATE_FILE", None)
        assert_eq(guard.get_state_path("a/b\\c:d").parent == guard.get_state_path("x").parent, True,
                  "A session id with path characters still maps to a file in the temp directory")
        assert_eq(guard.forced_agent(["--agent=Codex"]), "codex", "--agent=NAME is understood")
        assert_eq(guard.detect_agent({"hook_event_name": "PreToolUse", "tool_name": "Bash"}), "claude",
                  "Detection: Claude's capitalised PreToolUse is Claude")
        assert_eq(guard.detect_agent({"hook_event_name": "beforeShellExecution"}), "cursor",
                  "Detection: Cursor's camelCase event name is Cursor")
        assert_eq(guard.detect_agent({"toolCall": {"name": "run_command"}}), "antigravity",
                  "Detection: toolCall is Antigravity")

    print(f"\nResults: {passed}/{total} tests passed.")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()

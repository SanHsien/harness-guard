#!/usr/bin/env python3
"""checkout_guard.py -- blocks an edit to a file another agent has checked out.

PreToolUse hook for Edit, Write, MultiEdit and NotebookEdit. Reads the check-out
locks that agent-relay keeps in its store (https://github.com/SanHsien/agent-relay,
SPEC section 9):

    <store>/claims/<repo key>/<claim id>.json   {"holder", "paths": [...], "expires", ...}

If the file being edited matches a live claim held by someone else, the call is
blocked (exit 2, reason on stderr) and the attempt is logged. Every decision is
also appended to ~/.agent-relay/touch-log.jsonl -- the per-machine check-in
record of who touched what.

Who "I" am: $AGENT_RELAY_HOLDER (agent-relay sets it for the workers it starts),
else "manual:<agent>@<host>" from ~/.agent-relay/config.json -- the same default
`relay claim` uses, so a person's own claims never block them. Two interactive
sessions on one machine share that identity; give each its own
AGENT_RELAY_HOLDER if they must block each other.

No agent-relay set up, no claims, a file outside any git repo, or any error:
allow (exit 0). This is a coordination guard, not a sandbox; it only sees the
claims already pulled into the local store.

Pure Python standard library; the same file serves Windows, macOS and Linux.
"""
import fnmatch
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WILDCARDS = set("*?[")


def relay_home():
    return Path(os.environ.get("AGENT_RELAY_HOME") or Path.home() / ".agent-relay")


def load_config():
    """Same rules as agent_relay/config.py: config.json, then AGENT_RELAY_STORE / AGENT_RELAY_AGENT,
    store defaulting to <home>/store. None when agent-relay is not set up at all."""
    path = relay_home() / "config.json"
    cfg = {}
    if path.is_file():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    elif not os.environ.get("AGENT_RELAY_STORE"):
        return None
    if not isinstance(cfg, dict):
        return None
    if os.environ.get("AGENT_RELAY_STORE"):
        cfg["store"] = os.environ["AGENT_RELAY_STORE"]
    if os.environ.get("AGENT_RELAY_AGENT"):
        cfg["agent"] = os.environ["AGENT_RELAY_AGENT"]
    cfg.setdefault("store", str(relay_home() / "store"))
    return cfg


def holder(cfg):
    """Same rule as agent_relay.locks.default_holder."""
    return os.environ.get("AGENT_RELAY_HOLDER") or f"manual:{cfg.get('agent', '?')}@{socket.gethostname().lower()}"


def live_claim(claim, stem, now):
    try:
        return (isinstance(claim, dict) and claim.get("schema") == "agent-relay/claim@1" and claim.get("id") == stem
                and isinstance(claim.get("paths"), list) and all(isinstance(p, str) for p in claim["paths"])
                and float(claim.get("expires", 0)) > now)
    except (TypeError, ValueError):
        return False


def git(cwd, *args):
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


# Same identity rules as agent_relay/locks.py, so both sides name a repo the same way.
def repo_id(repo):
    url = git(repo, "config", "--get", "remote.origin.url")
    if url:
        url = re.sub(r"^([a-z+]+://)[^/@]*@", r"\1", url.strip())
        url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
        return re.sub(r"\.git$", "", url.rstrip("/")).lower()
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return ("local:" + str(Path(common).resolve()).lower()) if common else None


def repo_key(rid):
    slug = re.sub(r"[^a-z0-9]+", "-", rid.split("/")[-1].lower()).strip("-")[:40] or "repo"
    return f"{slug}-{hashlib.sha1(rid.encode('utf-8')).hexdigest()[:12]}"


def match_path(path, pattern):
    path = path.replace("\\", "/").strip("/")
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/") + "/**"
    return _match(path.split("/"), pattern.replace("\\", "/").strip("/").split("/"))


def _match(parts, pats):
    if not pats:
        return not parts
    head, rest = pats[0], pats[1:]
    if head == "**":
        return any(_match(parts[i:], rest) for i in range(len(parts) + 1))
    return bool(parts) and fnmatch.fnmatchcase(parts[0].lower(), head.lower()) and _match(parts[1:], rest)


def target_file(payload):
    tool_input = payload.get("tool_input") or {}
    return tool_input.get("file_path") or tool_input.get("notebook_path")


def log(entry):
    try:
        home = relay_home()
        home.mkdir(parents=True, exist_ok=True)
        with open(home / "touch-log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def decide(payload, cfg, now=None):
    """Return (allowed, message). Anything unknown allows."""
    if payload.get("tool_name") not in EDIT_TOOLS or not cfg or not cfg.get("store"):
        return True, None
    raw = target_file(payload)
    if not raw:
        return True, None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(payload.get("cwd") or ".") / path
    folder = path.parent
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    top = git(folder, "rev-parse", "--show-toplevel")
    if not top:
        return True, None
    try:
        rel = path.resolve().relative_to(Path(top).resolve()).as_posix()
    except ValueError:
        return True, None
    rid = repo_id(Path(top))
    if not rid:
        return True, None
    me = holder(cfg)
    now = now or time.time()
    folder = Path(cfg["store"]) / "claims" / repo_key(rid)
    blockers = []
    for claim_file in (folder.glob("*.json") if folder.is_dir() else []):
        try:
            claim = json.loads(claim_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not live_claim(claim, claim_file.stem, now) or claim.get("holder") == me:
            continue  # a broken claim file is skipped, not allowed to switch the guard off
        if any(match_path(rel, p) for p in claim["paths"]):
            blockers.append(claim)
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "holder": me, "repo": rid, "file": rel,
             "tool": payload.get("tool_name"), "decision": "deny" if blockers else "allow",
             "blocked_by": [b.get("holder") for b in blockers]}
    log(entry)
    if not blockers:
        return True, None
    who = "；".join(f"{b.get('holder')}（{', '.join(b.get('paths', []))}，到 {b.get('expires_at', '?')}）" for b in blockers)
    return False, (f"checkout-guard：{rel} 已被別的 agent 簽出：{who}。"
                   "等它簽入（relay claims 可查），或改做沒被簽出的檔案。")


def main():
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        allowed, message = decide(payload, load_config())
    except Exception:  # noqa: BLE001 - a broken guard must not block every edit
        return 0
    if allowed:
        return 0
    sys.stderr.buffer.write(message.encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())

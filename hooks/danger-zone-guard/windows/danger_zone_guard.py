#!/usr/bin/env python3
"""danger_zone_guard.py -- Windows build of danger-zone-guard.

PreToolUse hook. Blocks catastrophic commands, dangerous git force pushes,
and sensitive credential exfiltrations on Windows and cross-platform environments.
"""
from pathlib import Path
import sys

# Inherit directly from claude-code implementation
HOOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOK_DIR / "claude-code"))

import danger_zone_guard

if __name__ == "__main__":
    sys.exit(danger_zone_guard.main())

"""Minimal statusline for HANDOVER status display.

Fallback for environments without statusline.py.
Reads ~/.claude/handover-status.json and outputs status to the status bar.

Usage in settings.json (only when statusline.py is NOT installed):
  "statusLine": {
    "type": "command",
    "command": "python -X utf8 C:\\Users\\smbc0\\.claude\\hooks\\handover_statusline.py"
  }

When statusline.py IS installed, this script is not needed —
statusline.py reads the same JSON file directly.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

STATUS_FILE = Path.home() / ".claude" / "handover-status.json"

YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def main():
    if not STATUS_FILE.exists():
        return

    try:
        hs = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return

    phase = hs.get("phase", "")
    step = hs.get("step", 0)
    total = hs.get("total", 0)
    updated = hs.get("updated_at", "")
    progress = f" ({step}/{total})" if total else ""

    if phase == "pass1":
        print(f"{YELLOW}\U0001f4ddHANDOVER extracting{progress}{RESET}")
    elif phase == "pass2":
        print(f"{YELLOW}\U0001f4ddHANDOVER merging{progress}{RESET}")
    elif phase == "error":
        print(f"{RED}\U0001f4ddHANDOVER failed{RESET}")
    elif phase == "done" and updated:
        try:
            done_dt = datetime.fromisoformat(updated)
            elapsed = (datetime.now(done_dt.tzinfo) - done_dt).total_seconds()
            if elapsed < 60:
                print(f"{GREEN}\U0001f4ddHANDOVER ready{RESET}")
        except Exception:
            pass


if __name__ == "__main__":
    main()

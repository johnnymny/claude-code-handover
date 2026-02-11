"""UserPromptSubmit hook: inject HANDOVER path when ready.

Checks for .handover-ready-{session_id} marker on every prompt.
If found, outputs the HANDOVER file path so the agent reads it.
Silent when no marker exists (normal prompts).
"""

import json
import sys
from pathlib import Path


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")

    if not session_id or not transcript_path:
        return

    ready_marker = Path.home() / ".claude" / f".handover-ready-{session_id}"
    if not ready_marker.exists():
        return

    handover_path = Path(transcript_path).parent / f"HANDOVER-{session_id}.md"
    if not handover_path.exists():
        ready_marker.unlink(missing_ok=True)
        return

    print(f"[HANDOVER] Read this file: {handover_path}")
    ready_marker.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

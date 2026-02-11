"""SessionStart(compact) hook: launch background HANDOVER generation.

Fires AFTER compaction completes.
Launches worker to generate HANDOVER via claude -p.
"""

import json
import subprocess
import sys
from pathlib import Path


def main():
    raw = sys.stdin.read()
    data = json.loads(raw)

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")

    if not session_id or not transcript_path:
        return

    # Launch background HANDOVER generation
    worker = Path(__file__).parent / "handover_worker.py"
    if not worker.exists():
        return

    subprocess.Popen(
        [sys.executable, "-X", "utf8", str(worker), session_id, transcript_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


if __name__ == "__main__":
    main()

"""Background HANDOVER generator. Called by handover_generate.py.

Two-pass architecture:
  Pass 1: Extract new HANDOVER fragment from raw conversation diff
  Pass 2: Merge existing HANDOVER + new fragment (distilled + distilled)

This keeps processed content separate from raw transcript noise.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

STATUS_FILE = Path.home() / ".claude" / "handover-status.json"


def write_status(phase: str, step: int = 0, total: int = 0, session_id: str = "", error: str = ""):
    """Write current status to JSON file for external display (e.g., statusline.py)."""
    STATUS_FILE.write_text(
        json.dumps({
            "phase": phase,  # pass1, pass2, done, error
            "step": step,
            "total": total,
            "session_id": session_id,
            "updated_at": datetime.now().isoformat(),
            "error": error,
        }),
        encoding="utf-8",
    )


def extract_text(msg: dict) -> str:
    """Extract text content from a message, skipping tool_use/tool_result blocks."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def has_tool_use(msg: dict) -> bool:
    """Check if a message contains tool_use blocks."""
    content = msg.get("content", [])
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict) and block.get("type") == "tool_use"
        for block in content
    )


def parse_jsonl(transcript_path: str):
    """Parse jsonl and return conversation entries + compaction info."""
    lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()

    # Find all compact_boundary positions
    compact_boundaries = []
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "system" and obj.get("subtype") == "compact_boundary":
            compact_boundaries.append(i)

    if not compact_boundaries:
        return None, None

    last_boundary = compact_boundaries[-1]

    # Compaction summary: first user message after compact_boundary
    compaction_summary = ""
    for i in range(last_boundary + 1, min(last_boundary + 5, len(lines))):
        try:
            obj = json.loads(lines[i])
        except json.JSONDecodeError:
            continue
        msg = obj.get("message", {})
        if msg.get("role") == "user":
            text = extract_text(msg)
            if "continued from a previous conversation" in text:
                compaction_summary = text
                break

    # Determine conversation range (diff-based)
    if len(compact_boundaries) >= 2:
        start_idx = compact_boundaries[-2]  # From previous compact to current
    else:
        start_idx = 0  # First compaction: process everything

    # Extract conversation between start_idx and last_boundary
    # Strategy: skip assistant tool-operation messages (noise), keep conversation
    conversation = []
    for i in range(start_idx, last_boundary):
        try:
            obj = json.loads(lines[i])
        except json.JSONDecodeError:
            continue

        entry_type = obj.get("type", "")
        if entry_type not in ("user", "assistant"):
            continue

        msg = obj.get("message", {})
        role = msg.get("role", entry_type)

        # Assistant messages with tool_use → skip (operational noise)
        # Decision rationale and discussion happen in pure-text assistant turns
        if role == "assistant" and has_tool_use(msg):
            continue

        text = extract_text(msg)

        if not text.strip():
            continue

        # Skip very short system-injected messages
        if role == "user" and len(text) < 10:
            continue

        # Truncate: user messages (directives/corrections) get more room
        max_len = 2000 if role == "user" else 2000
        if len(text) > max_len:
            text = text[:max_len] + "\n[...truncated...]"

        conversation.append(f"[{role}]: {text}")

    return compaction_summary, conversation


def call_claude(prompt: str, timeout: int = 180) -> str | None:
    """Call claude -p --model sonnet with Read tool access."""
    result = subprocess.run(
        ["claude", "-p", "--model", "sonnet", "--allowedTools", "Read"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def pass1_extract(compaction_summary: str, conversation: list, work_dir: Path) -> str | None:
    """Pass 1: Extract HANDOVER fragment from raw conversation diff.

    Data is written to temp files and sonnet reads them via Read tool.
    This prevents sonnet from treating inline transcript as conversation to continue.
    """
    transcript_text = "\n\n".join(conversation)

    if len(transcript_text) > 150_000:
        transcript_text = transcript_text[-150_000:]

    if len(compaction_summary) > 20_000:
        compaction_summary = compaction_summary[:20_000] + "\n[...truncated...]"

    transcript_file = work_dir / "transcript.txt"
    summary_file = work_dir / "compaction_summary.txt"
    transcript_file.write_text(transcript_text, encoding="utf-8")
    summary_file.write_text(compaction_summary, encoding="utf-8")

    prompt = f"""You are creating a HANDOVER document that supplements a compaction summary.

Read these two files:
1. Compaction summary (what is already preserved): {summary_file}
2. Conversation transcript (raw source): {transcript_file}

Read both files. Then write a HANDOVER document containing what the compaction summary is MISSING.

Focus on these four categories ONLY:
1. **Decision rationale**: Why choice A was made over B. Include the reasoning chain, not just the conclusion.
2. **Failed approaches**: What was tried and didn't work. Include WHY it failed so the same mistake isn't repeated.
3. **User directives**: Session-specific policy decisions and scope boundaries for the current task.
4. **Corrections given during session**: Mistakes the agent made that the user explicitly corrected. Include what was wrong and what the correct behavior is, so the same mistake is not repeated after compaction.

Do NOT include:
- Code snippets, file paths, or configuration examples (the agent can read source files directly)
- Technical details that are already documented in code or config
- Test procedures or verification steps
- Anything the compaction summary already covers

Rules:
- Write in English
- Max 1500 words
- Use markdown headers
- Output ONLY the HANDOVER document"""

    return call_claude(prompt)


def pass2_merge(existing_handover: str, new_fragment: str, work_dir: Path) -> str | None:
    """Pass 2: Merge two distilled HANDOVER documents.

    Both inputs are already refined — merge as peer-level documents.
    """
    existing_file = work_dir / "existing_handover.md"
    fragment_file = work_dir / "new_fragment.md"
    existing_file.write_text(existing_handover, encoding="utf-8")
    fragment_file.write_text(new_fragment, encoding="utf-8")

    prompt = f"""You are merging two HANDOVER documents into one.

Read these two files:
1. Existing HANDOVER (older, from previous compaction cycles): {existing_file}
2. New HANDOVER fragment (from latest compaction cycle): {fragment_file}

Both are already distilled summaries (not raw conversation). Merge them into a single coherent document.

Merge rules:
- Deduplicate: if both cover the same decision/event, keep the more detailed version
- User directives and policy decisions never expire — always preserve them
- For technical details, prefer the newer document when conflicting
- Compress older sections if total exceeds 3000 words, but never drop user directives
- Maintain chronological structure where possible
- Write in English, use markdown headers
- Output ONLY the merged HANDOVER document"""

    return call_claude(prompt, timeout=120)


def main():
    if len(sys.argv) < 3:
        return

    session_id = sys.argv[1]
    transcript_path = sys.argv[2]

    if not Path(transcript_path).exists():
        return

    # Determine output path (same directory as jsonl)
    transcript_dir = Path(transcript_path).parent
    handover_path = transcript_dir / f"HANDOVER-{session_id}.md"
    error_log = transcript_dir / f"HANDOVER-{session_id}.error.log"

    # Read existing HANDOVER if any
    existing_handover = ""
    if handover_path.exists():
        existing_handover = handover_path.read_text(encoding="utf-8")

    # Parse jsonl
    compaction_summary, conversation = parse_jsonl(transcript_path)

    if compaction_summary is None:
        return  # No compaction found

    if not conversation:
        return  # No conversation to analyze

    work_dir = Path(tempfile.mkdtemp(prefix="handover_"))

    try:
        has_merge = bool(existing_handover)

        # Pass 1: Extract new fragment from raw conversation
        write_status("pass1", 1 if has_merge else 0, 2 if has_merge else 0, session_id)
        new_fragment = pass1_extract(compaction_summary, conversation, work_dir)

        if not new_fragment:
            write_status("error", 0, 0, session_id, "Pass 1 returned no output")
            error_log.write_text(
                f"{datetime.now().isoformat()}: Pass 1 failed (no output from claude -p)\n",
                encoding="utf-8",
            )
            return

        # Pass 2: Merge with existing (only if existing HANDOVER exists)
        if existing_handover:
            write_status("pass2", 2, 2, session_id)
            merged = pass2_merge(existing_handover, new_fragment, work_dir)
            if merged:
                handover_path.write_text(merged, encoding="utf-8")
            else:
                # Pass 2 failed — still save Pass 1 output (better than nothing)
                handover_path.write_text(new_fragment, encoding="utf-8")
                error_log.write_text(
                    f"{datetime.now().isoformat()}: Pass 2 failed, saved Pass 1 output only\n",
                    encoding="utf-8",
                )
        else:
            # First compaction — Pass 1 output is the HANDOVER
            handover_path.write_text(new_fragment, encoding="utf-8")

        write_status("done", 0, 0, session_id)

        # Signal inject hook that HANDOVER is ready
        ready_marker = Path.home() / ".claude" / f".handover-ready-{session_id}"
        ready_marker.write_text(session_id, encoding="utf-8")

    except subprocess.TimeoutExpired:
        write_status("error", 0, 0, session_id, "claude -p timed out")
        error_log.write_text(
            f"{datetime.now().isoformat()}: claude -p timed out\n",
            encoding="utf-8",
        )
    except Exception as e:
        write_status("error", 0, 0, session_id, str(e))
        error_log.write_text(
            f"{datetime.now().isoformat()}: {type(e).__name__}: {e}\n",
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

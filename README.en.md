# claude-code-handover

Auto-generate HANDOVER documents when Claude Code compacts your conversation context.

[日本語](README.md)

## What is this?

When Claude Code runs out of context, it **compacts** the conversation — compressing everything into a summary. This works well for preserving the current state, but loses:

- **Decision rationale** — why you chose approach A over B
- **Failed approaches** — what was tried and didn't work
- **Concrete examples** — actual code snippets, commands, file paths
- **User directives** — exact policy decisions and instructions

**claude-code-handover** automatically generates a supplementary HANDOVER document that captures what compaction misses, so your agent recovers with full context.

The HANDOVER adds only ~4K tokens (2% of the context window) while restoring decision rationale, concrete examples, and user directives that compaction loses.

## How it works

```
Compaction triggers
  → SessionStart(compact) hook fires
  → Background worker extracts conversation diff from jsonl
  → Calls claude -p --model sonnet to analyze transcript
  → Writes HANDOVER-{session_id}.md

Next user prompt
  → UserPromptSubmit hook detects ready marker
  → Injects file path into agent context
  → Agent reads the HANDOVER document
```

### Two-pass architecture

When a previous HANDOVER already exists (2nd+ compaction in the same session):

- **Pass 1**: Extract new fragment from raw conversation diff
- **Pass 2**: Merge existing HANDOVER + new fragment (both are refined documents)

This keeps processed content separate from raw transcript noise.

### Status display

The status bar shows generation progress in real time.

```
📝HANDOVER extracting        ← Extracting
📝HANDOVER extracting (1/2)  ← Extracting (merge pending)
📝HANDOVER merging (2/2)     ← Merging
📝HANDOVER ready             ← Done (auto-hides after 60s)
```

## Installation

### 1. Copy hook scripts

Copy the 4 files from `hooks/` to `~/.claude/hooks/`:

```bash
mkdir -p ~/.claude/hooks
cp hooks/* ~/.claude/hooks/
```

On Windows:
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\hooks"
Copy-Item hooks\* "$env:USERPROFILE\.claude\hooks\"
```

### 2. Add hook configuration

Add the following to your `~/.claude/settings.json`. If the file doesn't exist, create it.

If you already have a `hooks` section, merge the entries:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "python -X utf8 ~/.claude/hooks/handover_generate.py"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python -X utf8 ~/.claude/hooks/handover_inject.py"
          }
        ]
      }
    ]
  }
}
```

**Windows users**: Replace `~/.claude/hooks/` with the full path:
```json
"command": "python -X utf8 C:\\Users\\YourName\\.claude\\hooks\\handover_generate.py"
```

### 3. Verify Python

The hooks require Python 3.10+. Verify it's available:

```bash
python --version
```

No additional packages needed — only standard library modules are used.

## Files

| File | Hook | Purpose |
|------|------|---------|
| `handover_generate.py` | SessionStart (compact) | Launches background worker after compaction |
| `handover_worker.py` | — (background process) | Parses jsonl, calls sonnet, writes HANDOVER |
| `handover_inject.py` | UserPromptSubmit | Detects ready marker, injects file path |
| `handover_statusline.py` | — (optional statusline) | Standalone status display fallback |

## Output

HANDOVER files are saved alongside session jsonl files:

```
~/.claude/projects/{project-path}/HANDOVER-{session_id}.md
```

## How status display works

`handover_worker.py` writes progress to `~/.claude/handover-status.json`:

```json
{
  "phase": "pass1",
  "step": 1,
  "total": 2,
  "session_id": "abc-123",
  "updated_at": "2026-02-12T01:48:32"
}
```

Phases: `pass1` (extracting) → `pass2` (merging) → `done` | `error`

If you have a custom statusline, read this JSON to display progress. Otherwise, use `handover_statusline.py` as a standalone statusline command:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python -X utf8 ~/.claude/hooks/handover_statusline.py"
  }
}
```

## Requirements

- Claude Code CLI with hooks support
- Python 3.10+
- `claude -p --model sonnet` must work (valid authentication)

## Cost

Generation runs in the background, triggering 1-2 sonnet calls only when compaction occurs. It does not run on regular messages.

## License

MIT

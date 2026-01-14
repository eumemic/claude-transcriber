# claude-transcriber

Transcribe Claude Code JSONL logs to human-readable text.

## Installation

```bash
pip install claude-transcriber
```

## CLI Usage

```bash
# Transcribe a session log
claude-transcriber ~/.claude/projects/-Users-you-code-myproject/SESSION_ID.jsonl

# Save to file
claude-transcriber session.jsonl -o transcript.txt

# From stdin
cat session.jsonl | claude-transcriber
```

## Library Usage

```python
from claude_transcriber import Transcriber, transcribe_file

# Transcribe a whole file
text = transcribe_file("session.jsonl")

# Or record by record
t = Transcriber()
for record in records:
    result = t.transcribe(record)
    if result:
        print(result)
```

## Output Format

The output matches Claude Code's `/export` format:

- `⏺` prefix for assistant messages
- `❯` prefix for user messages
- Tool calls shown as `⏺ ToolName(args...)`
- Tool output shown with `⎿` continuation markers

## License

MIT

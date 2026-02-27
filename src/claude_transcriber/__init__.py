#!/usr/bin/env python3
"""
Claude Code log transcriber.

Converts JSONL log records into human-readable text matching /export output.
"""

import json
import re
from typing import Any

__all__ = ["Transcriber", "transcribe_file", "main"]


class Transcriber:
    """Transcribes Claude Code log records to human-readable format."""

    def __init__(self, timestamps: bool = True):
        self._pending_tool_use: dict | None = None
        self._timestamps = timestamps

    def transcribe(self, record: dict[str, Any]) -> str | None:
        """Transcribe a single record.

        Returns formatted text, or None if the record shouldn't be rendered.
        """
        rtype = record.get("type")

        # Skip non-message types
        if rtype not in ("user", "assistant"):
            return None

        # Skip compaction summaries
        if record.get("isCompactSummary"):
            return None

        if rtype == "assistant":
            result = self._transcribe_assistant(record)
        elif rtype == "user":
            result = self._transcribe_user(record)
        else:
            return None

        if result is not None and self._timestamps:
            ts = record.get("timestamp", "")
            if ts:
                result = f"[{ts}] {result}"

        return result

    def _transcribe_assistant(self, record: dict[str, Any]) -> str | None:
        """Transcribe an assistant message."""
        msg = record.get("message", {})
        if not isinstance(msg, dict):
            return None

        content = msg.get("content")
        if not isinstance(content, list):
            return None

        parts = []
        text_parts = []

        for block in content:
            if not isinstance(block, dict):
                continue

            btype = block.get("type")

            if btype == "thinking":
                thinking = block.get("thinking", "").strip()
                if thinking:
                    indented = self._indent_text(
                        thinking, first_prefix="  💭 ", cont_prefix="     "
                    )
                    parts.append(indented)

            elif btype == "text":
                text = block.get("text", "").strip()
                if text:
                    text_parts.append(text)

            elif btype == "tool_use":
                # Flush accumulated text before tool use
                if text_parts:
                    combined_text = "\n\n".join(text_parts)
                    indented = self._indent_text(combined_text, first_prefix="⏺ ", cont_prefix="  ")
                    parts.append(indented)
                    text_parts = []

                tool_str = self._format_tool_use(block)
                parts.append(tool_str)
                self._pending_tool_use = block

        # Flush any remaining text
        if text_parts:
            combined_text = "\n\n".join(text_parts)
            indented = self._indent_text(combined_text, first_prefix="⏺ ", cont_prefix="  ")
            parts.append(indented)

        if not parts:
            return None

        return "\n\n".join(parts)

    def _transcribe_user(self, record: dict[str, Any]) -> str | None:
        """Transcribe a user message."""
        msg = record.get("message", {})
        if not isinstance(msg, dict):
            return None

        content = msg.get("content")

        # Check if this is a tool result
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return self._format_tool_result(block)

        # Handle string content
        if isinstance(content, str):
            text = self._clean_user_text(content)
            if not text.strip():
                return None
            return self._indent_text(text, first_prefix="❯ ", cont_prefix="  ")

        # Handle array content with text blocks
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text.strip():
                        text_parts.append(text)

            if text_parts:
                combined = "\n\n".join(text_parts)
                cleaned = self._clean_user_text(combined)
                if cleaned.strip():
                    return self._indent_text(cleaned, first_prefix="❯ ", cont_prefix="  ")

        return None

    def _clean_user_text(self, text: str) -> str:
        """Clean system noise from user text."""
        text = text.strip()

        # Skip task notifications entirely
        if text.startswith("<task-notification>"):
            return ""

        # Skip system context blocks
        if text.startswith("## Context"):
            return ""

        # Strip system-reminder blocks (MEMORY.md injections, hook output, etc.)
        text = re.sub(
            r"<system-reminder>\s*.*?\s*</system-reminder>",
            "",
            text,
            flags=re.DOTALL,
        ).strip()
        if not text:
            return ""

        # Check for command XML and extract command
        cmd = self._parse_command_xml(text)
        if cmd is not None:
            return cmd

        # Remove caveat boilerplate
        caveat_pattern = re.compile(
            r"^(<local-command-caveat>)?Caveat: The messages below were generated.*?"
            r"unless the user explicitly asks you to\.(</local-command-caveat>)?\s*",
            re.DOTALL,
        )
        text = caveat_pattern.sub("", text)

        # After stripping caveat, check again for command XML
        cmd = self._parse_command_xml(text.strip())
        if cmd is not None:
            return cmd

        # Clean local-command-stdout tags
        stdout_pattern = re.compile(
            r"<local-command-stdout>([^<]*)</local-command-stdout>",
            re.DOTALL,
        )

        def replace_stdout(m):
            content = m.group(1).strip()
            if not content or content == "(no content)":
                return ""
            return content

        text = stdout_pattern.sub(replace_stdout, text)

        # Clean remaining tags
        text = re.sub(r"<local-command-caveat>|</local-command-caveat>", "", text)

        return text.strip()

    def _parse_command_xml(self, text: str) -> str | None:
        """Parse command XML and return command string if this is a command."""
        text = text.strip()
        if not text.startswith("<"):
            return None

        # Look for command-name tag
        match = re.search(r"<command-name>(/[^<]+)</command-name>", text)
        if match:
            cmd_name = match.group(1)
            # Look for args
            args_match = re.search(r"<command-args>([^<]*)</command-args>", text)
            if args_match and args_match.group(1).strip():
                return f"{cmd_name} {args_match.group(1).strip()}"
            return cmd_name

        return None

    def _format_tool_use(self, tool: dict[str, Any]) -> str:
        """Format a tool use block."""
        name = tool.get("name", "Unknown")
        input_data = tool.get("input", {})

        args_str = self._format_tool_args(name, input_data)

        if not args_str:
            return f"⏺ {name}"

        if len(input_data) == 1:
            return f"⏺ {name}(\n{args_str}\n  )"

        return f"⏺ {name}(\n{args_str}\n  )"

    def _format_tool_args(self, name: str, input_data: dict[str, Any]) -> str:
        """Format tool input as key=value lines, one per argument."""
        if not input_data:
            return ""

        max_value_len = 200
        lines = []
        for key, value in input_data.items():
            if isinstance(value, str):
                serialized = value
                if len(serialized) > max_value_len:
                    serialized = serialized[:max_value_len] + "…"
                formatted = f'    {key}="{serialized}"'
            else:
                serialized = json.dumps(value, default=str)
                if len(serialized) > max_value_len:
                    serialized = serialized[:max_value_len] + "…"
                formatted = f"    {key}={serialized}"
            lines.append(formatted)

        return "\n".join(lines)

    def _format_tool_result(self, block: dict[str, Any]) -> str:
        """Format a tool result block."""
        content = block.get("content", "")

        # Handle array content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = "\n".join(text_parts)

        if not isinstance(content, str):
            content = str(content)

        # Format with indentation
        lines = content.split("\n")

        max_lines = 5
        max_line_len = 200
        truncated_lines = lines[:max_lines]

        result_lines = []
        for i, line in enumerate(truncated_lines):
            if len(line) > max_line_len:
                line = line[:max_line_len] + "…"
            prefix = "  ⎿ " if i == 0 else "    "
            result_lines.append(prefix + line)

        if len(lines) > max_lines:
            result_lines.append(f"    … +{len(lines) - max_lines} lines")

        return "\n".join(result_lines)

    def _indent_text(self, text: str, first_prefix: str, cont_prefix: str) -> str:
        """Indent text with given prefixes."""
        lines = text.split("\n")
        result = []
        for i, line in enumerate(lines):
            if i == 0:
                result.append(first_prefix + line)
            else:
                result.append(cont_prefix + line)
        return "\n".join(result)


def transcribe_file(path: str, timestamps: bool = True) -> str:
    """Transcribe all records in a JSONL file."""
    transcriber = Transcriber(timestamps=timestamps)
    parts = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                result = transcriber.transcribe(record)
                if result:
                    parts.append(result)
            except json.JSONDecodeError:
                pass

    return "\n\n".join(parts)


def main():
    """CLI entry point."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Transcribe Claude Code logs to human-readable text"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="JSONL file to transcribe (reads from stdin if not provided)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file (prints to stdout if not provided)",
    )
    parser.add_argument(
        "-s", "--stream",
        action="store_true",
        help="Stream output immediately (for live transcription)",
    )
    parser.add_argument(
        "-t", "--timestamps",
        action="store_true",
        help="Include timestamps before each message",
    )

    args = parser.parse_args()

    # Streaming mode: print immediately as lines come in
    if args.stream or (not args.file and not args.output):
        transcriber = Transcriber(timestamps=args.timestamps)
        first_output = True
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                out = transcriber.transcribe(record)
                if out:
                    if not first_output:
                        print()  # blank line between outputs
                    print(out, flush=True)
                    first_output = False
            except json.JSONDecodeError:
                pass
        return

    # Batch mode: collect all then output
    if args.file:
        result = transcribe_file(args.file, timestamps=args.timestamps)
    else:
        # Read from stdin
        transcriber = Transcriber(timestamps=args.timestamps)
        parts = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                out = transcriber.transcribe(record)
                if out:
                    parts.append(out)
            except json.JSONDecodeError:
                pass
        result = "\n\n".join(parts)

    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        print(f"Wrote to {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()

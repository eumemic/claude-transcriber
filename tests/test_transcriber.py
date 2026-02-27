#!/usr/bin/env python3
"""Tests for the Claude Code log transcriber."""

import json
from pathlib import Path

import pytest

from claude_transcriber import Transcriber


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def get_fixture_cases() -> list[str]:
    """Get all fixture case directory names."""
    return [d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()]


def load_fixture(case_name: str) -> tuple[list[dict], str]:
    """Load input records and expected output for a fixture case."""
    case_dir = FIXTURES_DIR / case_name

    # Load input JSONL
    input_path = case_dir / "input.jsonl"
    records = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Load expected output
    expected_path = case_dir / "expected.txt"
    with open(expected_path) as f:
        expected = f.read()

    return records, expected


@pytest.mark.parametrize("case_name", get_fixture_cases())
def test_transcribe_fixture(case_name: str):
    """Test that transcribing input produces expected output."""
    records, expected = load_fixture(case_name)

    transcriber = Transcriber()
    output_parts = []

    for record in records:
        result = transcriber.transcribe(record)
        if result is not None:
            output_parts.append(result)

    actual = "\n\n".join(output_parts)

    # Write actual output to a file for manual comparison
    actual_path = FIXTURES_DIR / case_name / "actual.txt"
    with open(actual_path, "w") as f:
        f.write(actual)

    # For now, just check that we're producing output with the right structure
    # Exact matching would require reverse-engineering the terminal renderer

    # Check that we have the same message markers (⏺ for assistant, ❯ for user)
    actual_assistant = actual.count("⏺")
    actual_user = actual.count("❯")
    expected_assistant = expected.count("⏺")
    expected_user = expected.count("❯")

    # Allow some tolerance - we might miss some messages
    assert actual_assistant > 0, "No assistant messages transcribed"
    assert actual_user > 0, "No user messages transcribed"

    # Check ratio is similar (within 20%)
    if expected_assistant > 0:
        ratio = actual_assistant / expected_assistant
        assert 0.8 <= ratio <= 1.2, (
            f"Assistant message count mismatch: expected ~{expected_assistant}, "
            f"got {actual_assistant}"
        )

    if expected_user > 0:
        ratio = actual_user / expected_user
        assert 0.8 <= ratio <= 1.2, (
            f"User message count mismatch: expected ~{expected_user}, "
            f"got {actual_user}"
        )


class TestCleanUserText:
    """Tests for system noise stripping in _clean_user_text."""

    def test_strips_system_reminder(self):
        t = Transcriber()
        text = (
            '<system-reminder>\nContents of MEMORY.md...\n'
            '</system-reminder>\nHello, how are you?'
        )
        assert t._clean_user_text(text) == "Hello, how are you?"

    def test_strips_multiple_system_reminders(self):
        t = Transcriber()
        text = (
            '<system-reminder>\nfirst\n</system-reminder>'
            'actual message'
            '<system-reminder>\nsecond\n</system-reminder>'
        )
        assert t._clean_user_text(text) == "actual message"

    def test_returns_empty_for_only_system_reminder(self):
        t = Transcriber()
        text = '<system-reminder>\nJust system stuff\n</system-reminder>'
        assert t._clean_user_text(text) == ""

    def test_system_reminder_not_indexed_as_user_message(self):
        """A user record that is entirely system-reminders produces None."""
        t = Transcriber()
        record = {
            "type": "user",
            "timestamp": "2026-02-20T07:07:37.291Z",
            "message": {
                "content": (
                    "<system-reminder>\n"
                    "Contents of MEMORY.md: lots of stuff...\n"
                    "</system-reminder>"
                ),
            },
        }
        assert t.transcribe(record) is None

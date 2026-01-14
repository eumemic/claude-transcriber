#!/usr/bin/env python3
"""
Split a Claude Code JSONL log into clean test cases.

Given a transcript JSONL:
1. Follow ancestor chain from head (eliminates reverts)
2. Split at compaction boundaries
3. Output N separate JSONL files, each starting at a compaction event

Each output file can then be opened in Claude Code and /export-ed to get
the ground truth expected output.
"""

import json
import uuid
from pathlib import Path


def load_records(jsonl_path: Path) -> tuple[list[dict], dict[str, dict]]:
    """Load all records and build UUID lookup."""
    records = []
    by_uuid = {}

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
                if 'uuid' in record:
                    by_uuid[record['uuid']] = record
            except json.JSONDecodeError:
                pass

    return records, by_uuid


def find_head(records: list[dict]) -> str | None:
    """Find the head UUID (last non-compaction message)."""
    for record in reversed(records):
        # Skip non-message types
        if record.get('type') not in ('user', 'assistant'):
            continue
        # Skip compaction summaries
        if record.get('isCompactSummary'):
            continue
        return record.get('uuid')
    return None


def is_compaction_marker(record: dict) -> bool:
    """Check if record is a compaction boundary marker."""
    if record.get('isCompactSummary'):
        return True
    if record.get('type') == 'system' and record.get('subtype') == 'compact_boundary':
        return True
    return False


def extract_all_segments(
    head_uuid: str, by_uuid: dict[str, dict], records: list[dict]
) -> list[list[dict]]:
    """Extract all segments by following chains through compaction boundaries.

    Starting from head, follows parentUuid chain. When hitting a compaction
    boundary, that segment is complete. To find the previous chain's head,
    we look at the record immediately preceding the compaction boundary in
    the file (not its parentUuid, which is None).

    Returns segments in chronological order (oldest first).
    """
    # Build index of record position in file by UUID
    uuid_to_index = {}
    for i, r in enumerate(records):
        if 'uuid' in r:
            uuid_to_index[r['uuid']] = i

    segments = []
    current_head = head_uuid

    while current_head:
        # Follow chain from current head until we hit a compaction or None
        chain = []
        current = current_head
        prev_chain_head = None

        while current:
            record = by_uuid.get(current)
            if not record:
                break

            if is_compaction_marker(record):
                # Found compaction boundary - this ends the segment
                # Look at the record immediately before this in the file
                idx = uuid_to_index.get(record.get('uuid'))
                if idx is not None and idx > 0:
                    prev_record = records[idx - 1]
                    prev_chain_head = prev_record.get('uuid')
                break
            else:
                chain.append(record)
                current = record.get('parentUuid')

        # Reverse to get chronological order
        chain.reverse()

        if chain:
            segments.append(chain)

        # Continue to previous chain (if any)
        current_head = prev_chain_head

    # Reverse segments so oldest is first
    segments.reverse()
    return segments


def rewrite_uuids(segment: list[dict], new_session_id: str) -> list[dict]:
    """Rewrite UUIDs and session IDs in a segment to form a fresh log."""
    old_to_new = {}
    rewritten = []

    for record in segment:
        old_uuid = record.get('uuid')
        new_uuid = str(uuid.uuid4())
        if old_uuid:
            old_to_new[old_uuid] = new_uuid

        new_record = record.copy()
        new_record['uuid'] = new_uuid
        new_record['sessionId'] = new_session_id

        # Update parentUuid
        old_parent = record.get('parentUuid')
        if old_parent and old_parent in old_to_new:
            new_record['parentUuid'] = old_to_new[old_parent]
        else:
            # First record in segment has no parent (or parent was compaction)
            new_record['parentUuid'] = None

        rewritten.append(new_record)

    return rewritten


def write_segment(segment: list[dict], output_path: Path):
    """Write segment to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        for record in segment:
            f.write(json.dumps(record) + '\n')


def split_log(input_path: Path, output_dir: Path) -> list[tuple[str, Path]]:
    """Split a log into test case segments.

    Returns list of (session_id, jsonl_path) tuples.
    """
    print(f"Loading {input_path}...")
    records, by_uuid = load_records(input_path)
    print(f"  Loaded {len(records)} records, {len(by_uuid)} with UUIDs")

    head = find_head(records)
    if not head:
        print("  ERROR: No head found")
        return []
    print(f"  Head: {head}")

    segments = extract_all_segments(head, by_uuid, records)
    print(f"  Extracted {len(segments)} segments (following compaction chain)")

    results = []
    for i, segment in enumerate(segments):
        session_id = str(uuid.uuid4())
        rewritten = rewrite_uuids(segment, session_id)

        output_path = output_dir / f"{session_id}.jsonl"
        write_segment(rewritten, output_path)

        print(f"  Segment {i}: {len(segment)} records -> {output_path.name}")
        results.append((session_id, output_path))

    return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Split Claude Code log into test case segments'
    )
    parser.add_argument('input', type=Path, help='Input JSONL file')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='Output directory for segment JSONL files')

    args = parser.parse_args()

    results = split_log(args.input, args.output_dir)

    print(f"\nCreated {len(results)} test case logs:")
    for session_id, path in results:
        print(f"  {session_id}")

    print(f"\nNext steps:")
    print(f"1. For each session, cd to a project dir and run:")
    print(f"   claude --resume <session-id>")
    print(f"2. Use /export to save the transcript")
    print(f"3. Strip the header from each export")

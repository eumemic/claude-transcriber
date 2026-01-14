#!/usr/bin/env python3
"""Build a synthetic JSONL log from categorized examples for /export testing."""

import json
import uuid
from pathlib import Path

# Categories to include (these should render in /export)
INCLUDE_CATEGORIES = [
    'user:text_string',
    'user:text_blocks',
    'user:command_xml',
    'user:continuation',
    'user:local_stdout',
    'user:with_image',
    'user:blocks:[\'document\']',
    'assistant:text_only',
    'assistant:tool_only',
    'assistant:text+tool',
    'assistant:thinking_only',
]

# Categories to skip (shouldn't render or are noise)
SKIP_CATEGORIES = [
    'user:tool_result',
    'user:with_caveat',
    'system:',  # all system types
]


def should_include(category: str) -> bool:
    """Check if category should be included."""
    for skip in SKIP_CATEGORIES:
        if category.startswith(skip):
            return False
    return category in INCLUDE_CATEGORIES


def build_synthetic_log(examples_path: Path, output_path: Path):
    """Build a synthetic log from categorized examples."""

    # Load examples
    examples = []
    with open(examples_path) as f:
        for line in f:
            record = json.loads(line)
            cat = record.get('_category', '')
            if should_include(cat):
                examples.append(record)

    print(f"Found {len(examples)} examples to include")

    # Generate new UUIDs and build chain
    session_id = str(uuid.uuid4())
    records = []
    parent_uuid = None

    for i, example in enumerate(examples):
        new_uuid = str(uuid.uuid4())

        # Copy and modify the record
        record = {
            'uuid': new_uuid,
            'parentUuid': parent_uuid,
            'type': example.get('type'),
            'message': example.get('message'),
            'sessionId': session_id,
            'isSidechain': False,
            'userType': 'external',
            'cwd': '/Users/tom/code/claude-transcriber/test-session',
            'version': '2.1.5',
            'gitBranch': '',
            'timestamp': f'2026-01-13T{10+i//60:02d}:{i%60:02d}:00.000Z',
            # Include category for debugging
            '_category': example.get('_category'),
        }

        # Copy any special fields
        for field in ['toolUseResult', 'isCompactSummary', 'isMeta', 'agentId']:
            if field in example:
                record[field] = example[field]

        records.append(record)
        parent_uuid = new_uuid

    # Write output - filename must be {session_id}.jsonl
    output_dir = output_path if output_path.is_dir() else output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{session_id}.jsonl"

    with open(output_file, 'w') as f:
        for record in records:
            f.write(json.dumps(record) + '\n')

    print(f"Wrote {len(records)} records to {output_file}")
    print(f"Session ID: {session_id}")
    print(f"\nCategories included:")
    for r in records:
        print(f"  - {r.get('_category')}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--examples', type=Path, default=Path('categorized_examples.jsonl'))
    parser.add_argument('--output', type=Path, required=True)

    args = parser.parse_args()
    build_synthetic_log(args.examples, args.output)

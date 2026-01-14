#!/usr/bin/env python3
"""Categorize log records by their transcription-relevant characteristics."""

import json
import os
from collections import defaultdict
from pathlib import Path


def categorize_record(record: dict) -> str | None:
    """Return a category string describing how this record should be transcribed.

    Returns None for records that shouldn't be transcribed.
    """
    rtype = record.get('type')

    # Skip non-message types entirely
    if rtype in ('file-history-snapshot', 'queue-operation', 'summary'):
        return None

    if rtype == 'system':
        subtype = record.get('subtype', '')
        return f'system:{subtype}'

    msg = record.get('message', {})
    if not isinstance(msg, dict):
        return None

    content = msg.get('content')

    if rtype == 'user':
        # Check if it's a tool result (skip these)
        if record.get('toolUseResult'):
            return 'user:tool_result'

        # Check content type
        if isinstance(content, str):
            # Check for special patterns
            if '<command-name>' in content or '<command-message>' in content:
                return 'user:command_xml'
            if content.startswith('Caveat:') or '<local-command-caveat>' in content:
                return 'user:with_caveat'
            if '<local-command-stdout>' in content:
                return 'user:local_stdout'
            if content.startswith('This session is being continued'):
                return 'user:continuation'
            return 'user:text_string'

        if isinstance(content, list):
            block_types = set()
            for block in content:
                if isinstance(block, dict):
                    btype = block.get('type', 'unknown')
                    block_types.add(btype)

            if 'tool_result' in block_types:
                return 'user:tool_result_block'
            if 'image' in block_types:
                return 'user:with_image'
            if 'text' in block_types:
                return 'user:text_blocks'
            return f'user:blocks:{sorted(block_types)}'

    if rtype == 'assistant':
        if not isinstance(content, list):
            return 'assistant:non_list_content'

        block_types = set()
        tool_names = []
        has_text = False

        for block in content:
            if isinstance(block, dict):
                btype = block.get('type', 'unknown')
                block_types.add(btype)
                if btype == 'tool_use':
                    tool_names.append(block.get('name', 'unknown'))
                if btype == 'text' and block.get('text', '').strip():
                    has_text = True

        # Categorize based on content
        if 'thinking' in block_types:
            if has_text:
                return 'assistant:thinking+text'
            return 'assistant:thinking_only'

        if 'tool_use' in block_types and not has_text:
            # Tool-only (no text) - these get batched
            return 'assistant:tool_only'

        if 'tool_use' in block_types and has_text:
            return 'assistant:text+tool'

        if has_text and 'tool_use' not in block_types:
            return 'assistant:text_only'

        return f'assistant:blocks:{sorted(block_types)}'

    return f'unknown:{rtype}'


def analyze_categories(projects_dir: Path, max_files: int = 100, max_lines: int = 2000):
    """Analyze logs and categorize records."""

    categories = defaultdict(lambda: {'count': 0, 'examples': []})

    for project in sorted(os.listdir(projects_dir)):
        project_path = projects_dir / project
        if not project_path.is_dir():
            continue

        for f in sorted(os.listdir(project_path)):
            if not f.endswith('.jsonl'):
                continue

            path = project_path / f
            try:
                with open(path) as fp:
                    for i, line in enumerate(fp):
                        if i >= max_lines:
                            break
                        try:
                            record = json.loads(line)
                            cat = categorize_record(record)
                            if cat:
                                categories[cat]['count'] += 1
                                if len(categories[cat]['examples']) < 2:
                                    categories[cat]['examples'].append(record)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                pass

    return categories


def print_categories(categories):
    """Print categorization report."""

    # Group by prefix
    groups = defaultdict(list)
    for cat, data in categories.items():
        prefix = cat.split(':')[0]
        groups[prefix].append((cat, data))

    total_renderable = 0
    total_skip = 0

    for prefix in ['user', 'assistant', 'system', 'unknown']:
        if prefix not in groups:
            continue

        print(f"\n{'='*60}")
        print(f"=== {prefix.upper()} ===")
        print('='*60)

        for cat, data in sorted(groups[prefix], key=lambda x: -x[1]['count']):
            count = data['count']

            # Determine if this should be rendered
            skip = 'tool_result' in cat or cat == 'user:with_caveat'
            marker = '  [SKIP]' if skip else ''

            if skip:
                total_skip += count
            else:
                total_renderable += count

            print(f"\n{cat}: {count}{marker}")

            # Show abbreviated example
            if data['examples']:
                ex = data['examples'][0]
                msg = ex.get('message', {})
                content = msg.get('content') if isinstance(msg, dict) else None

                if isinstance(content, str):
                    preview = content[:200].replace('\n', '\\n')
                    print(f"  Content: {preview}...")
                elif isinstance(content, list):
                    blocks = []
                    for b in content[:3]:
                        if isinstance(b, dict):
                            btype = b.get('type')
                            if btype == 'text':
                                txt = b.get('text', '')[:100].replace('\n', '\\n')
                                blocks.append(f'text:"{txt}..."')
                            elif btype == 'tool_use':
                                blocks.append(f"tool_use:{b.get('name')}")
                            elif btype == 'tool_result':
                                blocks.append('tool_result')
                            elif btype == 'thinking':
                                blocks.append(f"thinking:{len(b.get('thinking', ''))}chars")
                            elif btype == 'image':
                                blocks.append('image')
                            else:
                                blocks.append(btype)
                    print(f"  Blocks: {blocks}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_renderable} renderable, {total_skip} skip")
    print('='*60)


def export_examples(categories, output_path: Path):
    """Export one example of each category to a JSONL file."""
    with open(output_path, 'w') as f:
        for cat, data in sorted(categories.items()):
            if data['examples']:
                # Add category marker for reference
                ex = data['examples'][0].copy()
                ex['_category'] = cat
                f.write(json.dumps(ex) + '\n')
    print(f"\nExported {len(categories)} category examples to {output_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Categorize Claude Code logs')
    parser.add_argument('--max-files', type=int, default=100)
    parser.add_argument('--max-lines', type=int, default=2000)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--projects-dir', type=Path,
                        default=Path.home() / '.claude' / 'projects')

    args = parser.parse_args()

    categories = analyze_categories(args.projects_dir, args.max_files, args.max_lines)
    print_categories(categories)

    if args.export:
        export_examples(categories, args.export)

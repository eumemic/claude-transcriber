#!/usr/bin/env python3
"""Analyze Claude Code logs to discover all message structure variants."""

import json
import os
import hashlib
from collections import defaultdict
from pathlib import Path


def structure_signature(obj, path=""):
    """Create a signature representing the structure of a JSON object."""
    if isinstance(obj, dict):
        parts = []
        for k, v in sorted(obj.items()):
            # Skip volatile fields that don't affect structure
            if k in ('uuid', 'parentUuid', 'timestamp', 'sessionId', 'requestId',
                     'id', 'messageId', 'leafUuid', 'cwd', 'gitBranch', 'version',
                     'usage', 'snapshot', 'durationMs', 'stop_reason', 'stop_sequence'):
                parts.append(f"{k}:*")
            else:
                parts.append(f"{k}:{structure_signature(v, f'{path}.{k}')}")
        return "{" + ",".join(parts) + "}"
    elif isinstance(obj, list):
        if not obj:
            return "[]"
        # Use first element as representative
        return f"[{structure_signature(obj[0], f'{path}[0]')}]"
    elif isinstance(obj, str):
        # For certain fields, capture the value (like type fields)
        if path.endswith('.type') or path == '.type':
            return f'str:{obj}'
        return "str"
    elif isinstance(obj, bool):
        return "bool"
    elif isinstance(obj, int):
        return "int"
    elif isinstance(obj, float):
        return "float"
    elif obj is None:
        return "null"
    else:
        return type(obj).__name__


def analyze_logs(projects_dir: Path, max_files: int = 50, max_lines_per_file: int = 1000):
    """Analyze logs and return unique structure variants."""

    structures = {}  # signature -> (count, example_record, example_path)
    type_counts = defaultdict(int)
    content_block_types = defaultdict(int)
    tool_names = defaultdict(int)
    special_fields = defaultdict(int)

    files_scanned = 0
    records_scanned = 0

    for project in sorted(os.listdir(projects_dir)):
        project_path = projects_dir / project
        if not project_path.is_dir():
            continue

        for f in sorted(os.listdir(project_path)):
            if not f.endswith('.jsonl'):
                continue
            if files_scanned >= max_files:
                break

            files_scanned += 1
            path = project_path / f

            try:
                with open(path) as fp:
                    for i, line in enumerate(fp):
                        if i >= max_lines_per_file:
                            break
                        try:
                            record = json.loads(line)
                            records_scanned += 1

                            # Track record type
                            rtype = record.get('type', 'NO_TYPE')
                            type_counts[rtype] += 1

                            # Track special fields
                            for field in ['isCompactSummary', 'toolUseResult', 'isSidechain',
                                         'isCompletedToolBlock', 'isMeta', 'agentId']:
                                if record.get(field):
                                    special_fields[field] += 1

                            # Track content blocks
                            msg = record.get('message', {})
                            if isinstance(msg, dict):
                                content = msg.get('content', [])
                                if isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict):
                                            btype = block.get('type', 'unknown')
                                            content_block_types[btype] += 1
                                            if btype == 'tool_use':
                                                tool_names[block.get('name', 'unknown')] += 1
                                elif isinstance(content, str):
                                    content_block_types['STRING_CONTENT'] += 1

                            # Track unique structures
                            sig = structure_signature(record)
                            if sig not in structures:
                                structures[sig] = (1, record, str(path))
                            else:
                                count, ex, ex_path = structures[sig]
                                structures[sig] = (count + 1, ex, ex_path)

                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"Error reading {path}: {e}")

    return {
        'files_scanned': files_scanned,
        'records_scanned': records_scanned,
        'type_counts': dict(type_counts),
        'content_block_types': dict(content_block_types),
        'tool_names': dict(tool_names),
        'special_fields': dict(special_fields),
        'structures': structures,
    }


def print_report(analysis):
    """Print a human-readable report."""
    print(f"Scanned {analysis['files_scanned']} files, {analysis['records_scanned']} records\n")

    print("=== Record Types ===")
    for t, count in sorted(analysis['type_counts'].items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")

    print("\n=== Content Block Types ===")
    for t, count in sorted(analysis['content_block_types'].items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")

    print("\n=== Tool Names ===")
    for t, count in sorted(analysis['tool_names'].items(), key=lambda x: -x[1])[:20]:
        print(f"  {t}: {count}")

    print("\n=== Special Fields ===")
    for f, count in sorted(analysis['special_fields'].items(), key=lambda x: -x[1]):
        print(f"  {f}: {count}")

    print(f"\n=== Unique Structure Variants: {len(analysis['structures'])} ===")
    # Group by record type
    by_type = defaultdict(list)
    for sig, (count, example, path) in analysis['structures'].items():
        rtype = example.get('type', 'NO_TYPE')
        by_type[rtype].append((sig, count, example, path))

    for rtype in sorted(by_type.keys()):
        variants = by_type[rtype]
        print(f"\n--- {rtype} ({len(variants)} variants) ---")
        for sig, count, example, path in sorted(variants, key=lambda x: -x[1]):
            # Create a short hash for the signature
            sig_hash = hashlib.md5(sig.encode()).hexdigest()[:8]
            print(f"\n  [{sig_hash}] count={count}")
            print(f"  Source: {path}")
            # Show abbreviated example
            abbrev = json.dumps(example, indent=2)
            if len(abbrev) > 500:
                abbrev = abbrev[:500] + "\n    ..."
            for line in abbrev.split('\n'):
                print(f"    {line}")


def export_examples(analysis, output_path: Path):
    """Export one example of each structure to a JSONL file."""
    with open(output_path, 'w') as f:
        for sig, (count, example, source_path) in analysis['structures'].items():
            f.write(json.dumps(example) + '\n')
    print(f"\nExported {len(analysis['structures'])} examples to {output_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Analyze Claude Code logs')
    parser.add_argument('--max-files', type=int, default=100,
                        help='Maximum files to scan')
    parser.add_argument('--max-lines', type=int, default=2000,
                        help='Maximum lines per file')
    parser.add_argument('--export', type=Path,
                        help='Export examples to JSONL file')
    parser.add_argument('--projects-dir', type=Path,
                        default=Path.home() / '.claude' / 'projects',
                        help='Claude projects directory')

    args = parser.parse_args()

    analysis = analyze_logs(args.projects_dir, args.max_files, args.max_lines)
    print_report(analysis)

    if args.export:
        export_examples(analysis, args.export)

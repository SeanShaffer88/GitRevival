"""Headless static inspection and comparison; uses no GUI or network."""
import argparse
import json
from pathlib import Path
import sys
from .analyzer import inspect
from .planning_data import compare_reports


def read_report(path):
    with Path(path).open('rb') as stream:
        data = stream.read(20_000_001)
    if len(data) > 20_000_000:
        raise ValueError('Report exceeds 20 MB')
    data = json.loads(data)
    if not isinstance(data, dict) or not isinstance(data.get('findings'), list):
        raise ValueError('Expected a GitRevival JSON report')
    fields = ('id', 'title', 'severity', 'category', 'file', 'line', 'evidence', 'action', 'confidence')
    if any(not isinstance(f, dict) or any(k not in f for k in fields) for f in data['findings']):
        raise ValueError('Invalid finding record')
    if len({f['id'] for f in data['findings']}) != len(data['findings']):
        raise ValueError('Duplicate finding IDs')
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description='GitRevival bounded static inspection (never executes project code)')
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('inspect'); scan.add_argument('repository'); scan.add_argument('--output', required=True)
    diff = commands.add_parser('compare'); diff.add_argument('before'); diff.add_argument('after'); diff.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            data = inspect(args.repository).to_dict(); result = 0
        else:
            data = compare_reports(read_report(args.before), read_report(args.after))
            result = int(any(data[k] for k in ('added', 'removed', 'changed')))
        with Path(args.output).open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'GitRevival: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

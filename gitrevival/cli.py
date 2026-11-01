"""Headless GitRevival operations; uses no GUI and no network.

`inspect` and `compare` work on folders and report files only. The other
commands work on the local workspace database (the same one the window
uses), so headless and window work share one set of operations. List
commands print JSON to standard output; file outputs must be new files.
Exit codes: 0 success, 1 only for a comparison that found differences,
2 for any error.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from .analyzer import inspect
from .planning_data import compare_reports
from .store import Store, export_report, export_shortlist


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


def default_workspace():
    return Path(__file__).resolve().parent.parent / '.local' / 'workspace.sqlite3'


def open_store(args):
    return Store(args.workspace or default_workspace())


def find_project(store, key):
    """Resolve a project by exact root, resolved path, or unique name."""
    rows = store.projects()
    for root, name, payload in rows:
        if key in (root, name):
            return root, name, payload
    try:
        resolved = str(Path(key).resolve())
    except (OSError, RuntimeError):
        resolved = None
    if resolved:
        for root, name, payload in rows:
            try:
                if str(Path(root).resolve()) == resolved:
                    return root, name, payload
            except (OSError, RuntimeError):
                continue
    matches = [row for row in rows if row[1].casefold() == key.casefold()]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f'No saved project matches {key!r}. List saved projects with the `projects` command.')


def require_new_file(path):
    if Path(path).exists():
        raise ValueError(f'Output already exists and will not be overwritten: {path}')


def write_json_new_file(data, path):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description='GitRevival headless operations (never executes project code)')
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('inspect', help='Bounded static inspection of a repository folder')
    scan.add_argument('repository'); scan.add_argument('--output', required=True)
    diff = commands.add_parser('compare', help='Compare two GitRevival JSON report files')
    diff.add_argument('before'); diff.add_argument('after'); diff.add_argument('--output', required=True)
    deps = commands.add_parser('deps', help='Inspect a repository and print its internal dependency edges and license-text detections as JSON')
    deps.add_argument('repository')
    listing = commands.add_parser('projects', help='List projects saved in the workspace as JSON')
    listing.add_argument('--workspace')
    export = commands.add_parser('export', help='Inspect a repository, save the scan to the workspace, and export its report (Markdown/JSON/CSV by file extension)')
    export.add_argument('repository'); export.add_argument('--output', required=True); export.add_argument('--workspace')
    backup = commands.add_parser('backup', help='Create a checked workspace backup (the destination must not exist)')
    backup.add_argument('--output', required=True); backup.add_argument('--workspace')
    scans = commands.add_parser('scans', help='List the saved scan snapshots of a workspace project as JSON')
    scans.add_argument('project'); scans.add_argument('--workspace')
    snap_diff = commands.add_parser('diff-scans', help='Compare two saved scan snapshots of a workspace project')
    snap_diff.add_argument('project'); snap_diff.add_argument('older', type=int); snap_diff.add_argument('newer', type=int)
    snap_diff.add_argument('--output', required=True); snap_diff.add_argument('--workspace')
    shortlist = commands.add_parser('shortlist', help='Export the saved revival shortlist (Markdown or JSON by file extension)')
    shortlist.add_argument('--output', required=True); shortlist.add_argument('--workspace')
    audit = commands.add_parser('audit', help='Online audit of a local repository: registry state, namespace variants and published advisories for its declared dependencies (read-only network use, only on this command)')
    audit.add_argument('repository'); audit.add_argument('--json', action='store_true')
    kickstart = commands.add_parser('kickstart', help='Generate revival draft files (ADOPTERS, OUTREACH, MODERNIZATION, BACKLINK) into an output folder; never overwrites and never touches the repository')
    kickstart.add_argument('repository'); kickstart.add_argument('--output', required=True); kickstart.add_argument('--workspace')
    discover_cmd = commands.add_parser('discover', help='Online GitHub discovery with strict filters, one JSON object per line (read-only; uses the network only on this command). Set GITREVIVAL_GITHUB_TOKEN for a higher rate limit.')
    discover_cmd.add_argument('words', nargs='*', help='Plain words: a topic, a language, or both')
    discover_cmd.add_argument('--hunt', choices=['explore', 'loved', 'licensed', 'small'], default='explore')
    discover_cmd.add_argument('--min-stars', type=int)
    discover_cmd.add_argument('--inactive-months', help='Months since the last push, e.g. 24 or a range like 18-36')
    discover_cmd.add_argument('--license', dest='license_id', help='SPDX id, e.g. MIT')
    discover_cmd.add_argument('--lang', help='Language name, e.g. Rust')
    discover_cmd.add_argument('--has-passing-ci', action='store_true')
    discover_cmd.add_argument('--limit', type=int, default=30)
    discover_cmd.add_argument('--json', action='store_true', help='Wrap results in one JSON object instead of NDJSON lines')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            write_json_new_file(inspect(args.repository).to_dict(), args.output)
            return 0
        if args.command == 'compare':
            data = compare_reports(read_report(args.before), read_report(args.after))
            write_json_new_file(data, args.output)
            return int(any(data[k] for k in ('added', 'removed', 'changed')))
        if args.command == 'discover':
            from .github import GitHubClient, GitHubError, discover as run_discover
            try:
                result = run_discover(GitHubClient(), ' '.join(args.words), hunt=args.hunt,
                                      min_stars=args.min_stars, inactive_months=args.inactive_months,
                                      license_id=args.license_id, language=args.lang,
                                      has_passing_ci=args.has_passing_ci, limit=args.limit)
            except GitHubError as exc:
                print(f'GitRevival: {exc}', file=sys.stderr)
                return 2
            if args.json:
                json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
                sys.stdout.write('\n')
            else:
                for row in result['results']:
                    json.dump(row, sys.stdout, ensure_ascii=False)
                    sys.stdout.write('\n')
            return 0
        if args.command == 'audit':
            from .audit import audit_report, audit_text, namespace_audit, namespace_text, AuditError
            from .github import GitHubError
            try:
                report = inspect(args.repository)
                result = audit_report(report)
                namespaces = namespace_audit(args.repository)
            except (AuditError, GitHubError) as exc:
                print(f'GitRevival: {exc}', file=sys.stderr)
                return 2
            if args.json:
                json.dump({'audit': result, 'namespaces': namespaces}, sys.stdout, ensure_ascii=False, indent=2)
                sys.stdout.write('\n')
            else:
                print(audit_text(result) + namespace_text(namespaces))
            return 0
        if args.command == 'deps':
            report = inspect(args.repository)
            payload = {'edges': [vars(e) for e in report.edges],
                       'license_detections': [vars(d) for d in report.license_detections]}
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write('\n')
            return 0
        store = open_store(args)
        try:
            if args.command == 'projects':
                projects = []
                for root, name, payload in store.projects():
                    data = json.loads(payload)
                    projects.append({'root': root, 'name': name, 'scanned_at': data.get('scanned_at', ''),
                                     'files': data.get('files', 0), 'findings': len(data.get('findings', []))})
                json.dump(projects, sys.stdout, ensure_ascii=False, indent=2)
                sys.stdout.write('\n')
                return 0
            if args.command == 'export':
                require_new_file(args.output)
                report = inspect(args.repository)
                store.save_report(report)
                export_report(report, store, args.output)
                return 0
            if args.command == 'backup':
                store.backup(args.output)
                return 0
            if args.command == 'scans':
                root, _, _ = find_project(store, args.project)
                rows = [{'seq': seq, 'at': at, 'files': json.loads(payload).get('files', 0),
                         'findings': len(json.loads(payload).get('findings', []))}
                        for seq, at, payload in store.scans(root)]
                json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
                sys.stdout.write('\n')
                return 0
            if args.command == 'diff-scans':
                root, _, _ = find_project(store, args.project)
                records = {seq: json.loads(payload) for seq, _, payload in store.scans(root)}
                if args.older not in records or args.newer not in records:
                    raise ValueError(f'Both snapshot numbers must be listed by the `scans` command for this project (got {args.older} and {args.newer}).')
                data = compare_reports(records[args.older], records[args.newer])
                write_json_new_file(data, args.output)
                return int(any(data[k] for k in ('added', 'removed', 'changed')))
            if args.command == 'shortlist':
                require_new_file(args.output)
                export_shortlist(store, args.output)
                return 0
            if args.command == 'kickstart':
                from .kickstart import generate_kickstart
                report = inspect(args.repository)
                snapshot = None
                try:
                    root, _, _ = find_project(store, args.repository)
                    upstream = store.upstream(root)
                    if upstream:
                        snapshot = store.github_check(root, upstream)
                except ValueError:
                    snapshot = None
                names = generate_kickstart(report, snapshot, args.output)
                print('Wrote drafts: ' + ', '.join(names))
                return 0
        finally:
            store.close()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f'GitRevival: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

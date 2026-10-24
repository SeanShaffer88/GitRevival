"""GUI-independent report comparison and CSV helpers."""
import csv
from pathlib import Path

def compare_reports(before, after):
    """Compare stable IDs and evidence, ignoring retrieval times and task annotations."""
    left = {f['id']: f for f in before['findings']}
    right = {f['id']: f for f in after['findings']}
    fields = ('title', 'severity', 'category', 'file', 'line', 'evidence', 'action', 'confidence')
    return {
        'added': [right[k] for k in sorted(right.keys() - left.keys())],
        'removed': [left[k] for k in sorted(left.keys() - right.keys())],
        'changed': [right[k] for k in sorted(left.keys() & right.keys())
                    if any(left[k].get(f) != right[k].get(f) for f in fields)],
        'unchanged': sum(all(left[k].get(f) == right[k].get(f) for f in fields)
                         for k in left.keys() & right.keys()),
    }


def delta_text(delta):
    lines = ['Finding differences (bounded static scans; removed does not prove repaired).',
             f"Added: {len(delta['added'])} | Removed: {len(delta['removed'])} | Changed: {len(delta['changed'])} | Unchanged: {delta['unchanged']}"]
    for group in ('added', 'removed', 'changed'):
        lines += ['', group.upper()]
        lines += [f"{f['id']} — {f['title']} ({f['file']}:{f['line']})" for f in delta[group]] or ['None']
    return '\n'.join(lines)


def export_csv(data, path):
    columns = ('id', 'title', 'status', 'priority', 'due', 'severity', 'category', 'file', 'line', 'evidence', 'action', 'notes')
    def cell(value):
        value = str(value)
        # Excel/LibreOffice may interpret formula prefixes even in quoted CSV fields.
        return "'" + value if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for finding in data['findings']:
            writer.writerow([cell(finding.get(k, '')) for k in columns])


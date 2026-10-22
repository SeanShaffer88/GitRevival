"""Local SQLite backlog. Scan results remain evidence; task state is separate."""
from pathlib import Path
import json
import sqlite3

STATES = ('Queued', 'In progress', 'Blocked', 'Done', 'Dismissed')

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS projects (root TEXT PRIMARY KEY, name TEXT NOT NULL, report TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (root TEXT, id TEXT, status TEXT NOT NULL, notes TEXT NOT NULL, PRIMARY KEY(root,id))')
        self.db.commit()

    def save_report(self, report):
        self.db.execute('INSERT OR REPLACE INTO projects VALUES (?,?,?)', (report.root, report.name, json.dumps(report.to_dict())))
        self.db.commit()

    def projects(self):
        return self.db.execute('SELECT root,name,report FROM projects ORDER BY name COLLATE NOCASE').fetchall()

    def task(self, root, id):
        return self.db.execute('SELECT status,notes FROM tasks WHERE root=? AND id=?', (root,id)).fetchone() or ('Queued','')

    def save_task(self, root, id, status, notes):
        if status not in STATES:
            raise ValueError('Invalid task status')
        self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)', (root,id,status,notes))
        self.db.commit()

    def close(self):
        self.db.close()

def restore(data):
    from .analyzer import Report, Finding, Dependency
    data = dict(data)
    data['findings'] = [Finding(**x) for x in data['findings']]
    data['dependencies'] = [Dependency(**x) for x in data['dependencies']]
    return Report(**data)

def export_report(report, store, path):
    data = report.to_dict()
    for finding in data['findings']:
        finding['status'], finding['notes'] = store.task(report.root, finding['id'])
    if str(path).lower().endswith('.json'):
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    else:
        lines = [f'# GitRevival — {report.name}', '', f'Scanned (UTC): {report.scanned_at}',
                 f'Repository: {report.root}', '', 'Static inspection only. Build success, security, current upstream maintenance and license compatibility are unverified.', '',
                 f'{report.files} files inventoried · {len(report.dependencies)} declared dependencies · {len(report.findings)} findings', '', '## Scope warnings', '']
        lines += [f'- {x}' for x in report.warnings] or ['None reported. Excluded generated/vendor folders and bounded reads still apply.']
        lines += ['', '## Declared dependencies', '']
        lines += [f'- {d.name} — {d.version} ({d.ecosystem}; {d.file})' for d in report.dependencies] or ['None extracted by supported parsers.']
        lines += ['', '## Repair backlog', '']
        for f in data['findings']:
            lines += [f"### [{f['status']}] {f['title']}", '', f"{f['severity']} · {f['category']} · {f['confidence']}",
                      f"Source: {f['file'] or '(repository scope)'}:{f['line']}", '', 'Evidence:', '', f['evidence'], '', 'Next step: ' + f['action'], '', 'Notes: ' + f['notes'], '']
        Path(path).write_text('\n'.join(lines), encoding='utf-8')

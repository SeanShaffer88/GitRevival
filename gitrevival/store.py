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
        self.db.execute('CREATE TABLE IF NOT EXISTS github_checks (name TEXT PRIMARY KEY, snapshot TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS candidates (name TEXT PRIMARY KEY, status TEXT NOT NULL, notes TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS github_searches (query TEXT, page INTEGER, payload TEXT NOT NULL, PRIMARY KEY(query,page))')
        self.db.execute('CREATE TABLE IF NOT EXISTS upstreams (root TEXT PRIMARY KEY, name TEXT NOT NULL)')
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

    def save_check(self, snapshot, previous=None):
        snapshot = dict(snapshot)
        name = snapshot['full_name'].casefold()
        old_snapshot = self.github_check(previous or name)
        for key in ('discovered_query','discovered_page'):
            if old_snapshot and key in old_snapshot:
                snapshot.setdefault(key,old_snapshot[key])
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO github_checks VALUES (?,?)', (name,json.dumps(snapshot)))
            if previous and previous.casefold() != name:
                old = previous.casefold()
                self.db.execute('INSERT OR IGNORE INTO candidates SELECT ?,status,notes FROM candidates WHERE name=?', (name,old))
                self.db.execute('DELETE FROM candidates WHERE name=?',(old,))
                self.db.execute('UPDATE upstreams SET name=? WHERE name=?',(name,old))

    def github_check(self, name):
        row = self.db.execute('SELECT snapshot FROM github_checks WHERE name=?',(name.casefold(),)).fetchone()
        return json.loads(row[0]) if row else None

    def save_candidate(self, snapshot, status='Research', notes=''):
        if status not in ('Research','Promising','Investigating','Reviving','Passed'):
            raise ValueError('Invalid candidate status')
        existing = self.github_check(snapshot['full_name'])
        if not existing or 'checks' in snapshot:
            self.save_check(snapshot)
        self.db.execute('INSERT OR REPLACE INTO candidates VALUES (?,?,?)', (snapshot['full_name'].casefold(),status,notes))
        self.db.commit()

    def candidate(self, name):
        return self.db.execute('SELECT status,notes FROM candidates WHERE name=?',(name.casefold(),)).fetchone()

    def candidates(self):
        return [(json.loads(data),status,notes) for data,status,notes in self.db.execute(
            'SELECT g.snapshot,c.status,c.notes FROM candidates c JOIN github_checks g ON c.name=g.name ORDER BY c.name')]

    def save_search(self, payload):
        self.db.execute('INSERT OR REPLACE INTO github_searches VALUES (?,?,?)', (payload['query'],payload['page'],json.dumps(payload)))
        self.db.commit()

    def github_search(self, query, page):
        row = self.db.execute('SELECT payload FROM github_searches WHERE query=? AND page=?',(query,page)).fetchone()
        return json.loads(row[0]) if row else None

    def link_upstream(self, root, name):
        self.db.execute('INSERT OR REPLACE INTO upstreams VALUES (?,?)',(str(Path(root).resolve()),name.casefold()))
        self.db.commit()

    def upstream(self, root):
        row = self.db.execute('SELECT name FROM upstreams WHERE root=?',(str(Path(root).resolve()),)).fetchone()
        return row[0] if row else None

def restore(data):
    from .analyzer import Report, Finding, Dependency
    data = dict(data)
    data['findings'] = [Finding(**x) for x in data['findings']]
    data['dependencies'] = [Dependency(**x) for x in data['dependencies']]
    return Report(**data)

def export_report(report, store, path):
    data = report.to_dict()
    upstream = store.upstream(report.root)
    data['github_upstream'] = store.github_check(upstream) if upstream else None
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
        if data['github_upstream']:
            from .github import evidence_text
            lines += ['', '## Saved GitHub evidence (check timestamp for freshness)', '', evidence_text(data['github_upstream'])]
        lines += ['', '## Repair backlog', '']
        for f in data['findings']:
            lines += [f"### [{f['status']}] {f['title']}", '', f"{f['severity']} · {f['category']} · {f['confidence']}",
                      f"Source: {f['file'] or '(repository scope)'}:{f['line']}", '', 'Evidence:', '', f['evidence'], '', 'Next step: ' + f['action'], '', 'Notes: ' + f['notes'], '']
        Path(path).write_text('\n'.join(lines), encoding='utf-8')

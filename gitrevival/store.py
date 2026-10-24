"""Local SQLite backlog. Scan results remain evidence; task state is separate."""
from pathlib import Path
import json
import sqlite3
from datetime import date, datetime, timezone
import uuid
from contextlib import closing

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
        self.db.execute('CREATE TABLE IF NOT EXISTS task_meta (root TEXT, id TEXT, priority TEXT NOT NULL, due TEXT NOT NULL, PRIMARY KEY(root,id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS task_events (seq INTEGER PRIMARY KEY, root TEXT, id TEXT, at TEXT, status TEXT, notes TEXT, priority TEXT, due TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS scan_history (seq INTEGER PRIMARY KEY, root TEXT, at TEXT, report TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS custom_tasks (root TEXT, id TEXT, title TEXT, action TEXT, PRIMARY KEY(root,id))')
        for root,payload in self.db.execute('SELECT root,report FROM projects p WHERE NOT EXISTS (SELECT 1 FROM scan_history h WHERE h.root=p.root)').fetchall():
            self.db.execute('INSERT INTO scan_history(root,at,report) VALUES (?,?,?)', (root,json.loads(payload).get('scanned_at','Unknown (migrated)'),payload))
        self.db.commit()

    def save_report(self, report):
        payload = json.dumps(report.to_dict())
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO projects VALUES (?,?,?)', (report.root, report.name, payload))
            self.db.execute('INSERT INTO scan_history(root,at,report) VALUES (?,?,?)', (report.root,report.scanned_at,payload))
            self.db.execute('DELETE FROM scan_history WHERE root=? AND seq NOT IN (SELECT seq FROM scan_history WHERE root=? ORDER BY seq DESC LIMIT 20)', (report.root,report.root))

    def projects(self):
        return self.db.execute('SELECT root,name,report FROM projects ORDER BY name COLLATE NOCASE').fetchall()

    def task(self, root, id):
        return self.db.execute('SELECT status,notes FROM tasks WHERE root=? AND id=?', (root,id)).fetchone() or ('Queued','')

    def save_task(self, root, id, status, notes, priority=None, due=None):
        if status not in STATES:
            raise ValueError('Invalid task status')
        old_priority, old_due = self.task_meta(root,id)
        priority = old_priority if priority is None else priority
        due = old_due if due is None else due.strip()
        if priority not in ('Low','Normal','High','Urgent'):
            raise ValueError('Invalid priority')
        if due and (date.fromisoformat(due).isoformat() != due):
            raise ValueError('Use a due date in YYYY-MM-DD format')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)', (root,id,status,notes))
            self.db.execute('INSERT OR REPLACE INTO task_meta VALUES (?,?,?,?)', (root,id,priority,due))
            self.db.execute('INSERT INTO task_events(root,id,at,status,notes,priority,due) VALUES (?,?,?,?,?,?,?)',
                (root,id,datetime.now(timezone.utc).isoformat(),status,notes,priority,due))

    def task_meta(self, root, id):
        return self.db.execute('SELECT priority,due FROM task_meta WHERE root=? AND id=?',(root,id)).fetchone() or ('Normal','')

    def task_history(self, root, id):
        return self.db.execute('SELECT at,status,notes,priority,due FROM task_events WHERE root=? AND id=? ORDER BY seq DESC LIMIT 100',(root,id)).fetchall()

    def scans(self, root):
        return self.db.execute('SELECT seq,at,report FROM scan_history WHERE root=? ORDER BY seq DESC',(root,)).fetchall()

    def add_custom_task(self, root, title, action):
        if not title.strip() or len(title) > 200 or len(action) > 20000:
            raise ValueError('Provide a title (1–200 characters) and at most 20,000 action characters')
        id = 'custom-' + uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO custom_tasks VALUES (?,?,?,?)',(root,id,title.strip(),action))
        return id

    def custom_findings(self, root):
        from .analyzer import Finding
        return [Finding(id,'Info','Custom',title,'',0,'Manually created task; not an inspection result.',action,'Manual')
            for id,title,action in self.db.execute('SELECT id,title,action FROM custom_tasks WHERE root=? ORDER BY rowid',(root,))]

    def backup(self, path):
        target = Path(path)
        # Exclusive creation keeps an accidental destination selection from destroying another workspace.
        with target.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(target)) as destination:
                self.db.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup integrity check failed')
        except Exception:
            target.unlink(missing_ok=True)
            raise

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
        finding['priority'], finding['due'] = store.task_meta(report.root, finding['id'])
    if str(path).lower().endswith('.csv'):
        from .planning_data import export_csv
        export_csv(data, path)
    elif str(path).lower().endswith('.json'):
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
            lines += [f"### [{f['status']}] {f['title']}", '', f"{f['severity']} · {f['category']} · {f['confidence']} · Priority: {f['priority']} · Due: {f['due'] or 'none'}",
                      f"Source: {f['file'] or '(repository scope)'}:{f['line']}", '', 'Evidence:', '', f['evidence'], '', 'Next step: ' + f['action'], '', 'Notes: ' + f['notes'], '']
        Path(path).write_text('\n'.join(lines), encoding='utf-8')

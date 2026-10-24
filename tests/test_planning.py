from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from gitrevival.analyzer import inspect
from gitrevival.store import Store, export_report
from gitrevival.planning_data import compare_reports


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root/'repo'; self.repo.mkdir()
        self.report = inspect(self.repo)
        self.store = Store(self.root/'state.sqlite3')

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def test_priorities_due_dates_and_transaction_history(self):
        f = self.report.findings[0]
        self.store.save_task(self.report.root,f.id,'In progress','evidence','Urgent','2026-12-31')
        self.store.save_task(self.report.root,f.id,'Done','tested')
        self.assertEqual(self.store.task_meta(self.report.root,f.id),('Urgent','2026-12-31'))
        self.assertEqual([x[1] for x in self.store.task_history(self.report.root,f.id)],['Done','In progress'])
        for priority,due in [('Invalid',''),('High','2026-02-30'),('Low','20261231')]:
            with self.assertRaises(ValueError):
                self.store.save_task(self.report.root,f.id,'Blocked','bad',priority,due)
        self.assertEqual(self.store.task(self.report.root,f.id),('Done','tested'))
        self.assertEqual(len(self.store.task_history(self.report.root,f.id)),2)

    def test_scan_retention_and_differences(self):
        before = self.report.to_dict()
        (self.repo/'README.md').write_text('Read me')
        after = inspect(self.repo).to_dict()
        delta = compare_reports(before,after)
        self.assertTrue(delta['removed'])
        self.assertFalse(delta['added'])
        changed = json.loads(json.dumps(before)); changed['findings'][0]['evidence']='Changed evidence'
        self.assertEqual(len(compare_reports(before,changed)['changed']),1)
        for _ in range(23): self.store.save_report(self.report)
        self.assertEqual(len(self.store.scans(self.report.root)),20)

    def test_custom_tasks_and_exports(self):
        id = self.store.add_custom_task(self.report.root,'=SUM(A1:A2)','Acceptance criteria')
        self.report.findings += self.store.custom_findings(self.report.root)
        self.store.save_task(self.report.root,id,'Queued','@formula','High','2026-12-01')
        for ext in ('json','csv','md'):
            export_report(self.report,self.store,self.root/f'report.{ext}')
        data = json.loads((self.root/'report.json').read_text())
        self.assertEqual(data['findings'][-1]['priority'],'High')
        with (self.root/'report.csv').open(encoding='utf-8-sig',newline='') as stream:
            row = list(csv.DictReader(stream))[-1]
        self.assertEqual(row['title'],"'=SUM(A1:A2)")
        self.assertEqual(row['notes'],"'@formula")
        self.assertEqual(self.store.custom_findings(self.report.root)[0].id,id)
        with self.assertRaises(ValueError): self.store.add_custom_task(self.report.root,' ','')

    def test_consistent_backup_and_existing_destination_refusal(self):
        self.store.save_report(self.report)
        self.store.save_task(self.report.root,'task','Done','notes','High','')
        path = self.root/'backup.sqlite3'; self.store.backup(path)
        with closing(sqlite3.connect(path)) as backup:
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(backup.execute('SELECT notes FROM tasks').fetchone()[0],'notes')
        digest = path.read_bytes()
        with self.assertRaises(FileExistsError): self.store.backup(path)
        self.assertEqual(path.read_bytes(),digest)

    def test_old_workspace_migration_keeps_notes(self):
        path = self.root/'old.sqlite3'
        with closing(sqlite3.connect(path)) as old:
            old.execute('CREATE TABLE projects (root TEXT PRIMARY KEY,name TEXT,report TEXT)')
            old.execute('CREATE TABLE tasks (root TEXT,id TEXT,status TEXT,notes TEXT,PRIMARY KEY(root,id))')
            old.execute('INSERT INTO projects VALUES (?,?,?)',(self.report.root,self.report.name,json.dumps(self.report.to_dict())))
            old.execute('INSERT INTO tasks VALUES (?,?,?,?)',(self.report.root,'f','Done','old notes'))
            old.commit()
        migrated = Store(path)
        try:
            self.assertEqual(migrated.task(self.report.root,'f'),('Done','old notes'))
            self.assertEqual(len(migrated.scans(self.report.root)),1)
            self.assertEqual(migrated.task_meta(self.report.root,'f'),('Normal',''))
        finally: migrated.close()

    def test_headless_commands_and_no_overwrite(self):
        def run(*args):
            return subprocess.run([sys.executable,'-m','gitrevival.cli',*map(str,args)],capture_output=True,timeout=15)
        first = self.root/'first.json'; second = self.root/'second.json'; diff = self.root/'diff.json'
        self.assertEqual(run('inspect',self.repo,'--output',first).returncode,0)
        self.assertEqual(run('inspect',self.repo,'--output',first).returncode,2)
        (self.repo/'README.md').write_text('New readme')
        self.assertEqual(run('inspect',self.repo,'--output',second).returncode,0)
        self.assertEqual(run('compare',first,second,'--output',diff).returncode,1)
        self.assertTrue(json.loads(diff.read_text())['removed'])
        self.assertEqual(run('compare',second,second,'--output',self.root/'same.json').returncode,0)
        first.write_text('{bad')
        self.assertEqual(run('compare',first,second,'--output',self.root/'bad.json').returncode,2)
        p = subprocess.run([sys.executable,'-c','import sys; import gitrevival.cli; assert "tkinter" not in sys.modules'],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_gui_planning_filters_sort_and_persistence(self):
        from gitrevival.app import App
        from gitrevival.planning import sort_tree
        app = App(self.root/'gui.sqlite3')
        try:
            app.store.save_report(self.report); app.load(self.report); app.update()
            app.filter_severity.set('Review'); app.render_findings()
            for id in app.findings.get_children():
                self.assertEqual(next(f for f in app.report.findings if f.id==id).severity,'Review')
            app.filter_severity.set('All severities'); app.render_findings()
            id = app.findings.get_children()[0]; app.findings.selection_set(id); app.show_finding()
            app.priority_var.set('Urgent'); app.due_var.set('2026-12-31'); app.status_var.set('Done'); app.save_task()
            self.assertEqual(app.store.task_meta(self.report.root,id),('Urgent','2026-12-31'))
            self.assertGreater(float(app.progress['value']),0)
            with patch('gitrevival.planning.simpledialog.askstring',side_effect=['Custom repair','Check result']):
                app.planning.add_task()
            custom = app.selected.id; self.assertTrue(custom.startswith('custom-'))
            app.load(self.report); self.assertIn(custom,[f.id for f in app.report.findings])
            app.findings.selection_set(custom); app.show_finding(); app.notes.insert('1.0','custom evidence'); app.save_task()
            app.planning.task_history(); self.assertIn('custom evidence',app.planning.detail.get('1.0','end'))
            app.store.save_report(self.report); app.planning.refresh()
            app.planning.scans.selection_set(app.planning.scans.get_children()); app.planning.show_scans()
            self.assertIn('Finding differences',app.planning.detail.get('1.0','end'))
            app.dependencies.insert('','end',values=('z','10','Python','requirements.txt'))
            app.dependencies.insert('','end',values=('a','2','Python','requirements.txt'))
            sort_tree(app.dependencies,'version')
            self.assertEqual(app.dependencies.set(app.dependencies.get_children()[0],'version'),'2')
            app.dependency_search.set('no-match'); self.assertEqual(len(app.dependencies.get_children()),0)
            with patch('gitrevival.app.messagebox.showinfo') as help:
                app.shortcut_help(); help.assert_called_once()
            app.focus_search(); app.update(); self.assertEqual(app.tabs.select(),str(app.findings_tab))
            self.assertGreater(app.notes.winfo_height(),25)
        finally:
            app.store.close(); app.destroy()


if __name__=='__main__': unittest.main()

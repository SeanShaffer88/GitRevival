"""0.5.0 CLI parity: workspace operations from the command line.

Everything runs through real CLI subprocesses against a seeded temporary
workspace. The seeding store is closed before the subprocesses start and
before the temporary folder is removed (an open SQLite file cannot be
deleted on Windows).
"""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from gitrevival.analyzer import inspect
from gitrevival.github import summarize
from gitrevival.store import Store


def run_cli(*args):
    return subprocess.run([sys.executable, '-m', 'gitrevival.cli', *map(str, args)],
                          capture_output=True, text=True, timeout=30)


class CliParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'package.json').write_text('{"dependencies":{"old-pkg":"*"}}', encoding='utf-8')
        self.workspace = self.root / 'workspace.sqlite3'
        store = Store(self.workspace)
        self.report = inspect(self.repo)
        store.save_report(self.report)
        first = self.report.findings[0]
        store.save_task(self.report.root, first.id, 'Done', 'cli parity evidence')
        (self.repo / 'README.md').write_text('Now documented', encoding='utf-8')
        second = inspect(self.repo)
        self.latest_findings = len(second.findings)
        store.save_report(second)
        rows = store.scans(self.report.root)
        self.newer_seq, self.older_seq = rows[0][0], rows[-1][0]
        snapshot = summarize({'full_name': 'example/old-tool', 'description': 'A synthetic tool',
                              'language': 'Python', 'license': {'spdx_id': 'MIT'}})
        store.save_candidate(snapshot, 'Promising', 'seeded research note')
        store.close()
        self.finding_id = first.id

    def tearDown(self):
        self.tmp.cleanup()

    def test_projects_lists_seeded_project(self):
        result = run_cli('projects', '--workspace', self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        projects = json.loads(result.stdout)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]['root'], self.report.root)
        self.assertEqual(projects[0]['findings'], self.latest_findings)

    def test_export_merges_saved_task_state_and_refuses_overwrite(self):
        out = self.root / 'report.json'
        result = run_cli('export', self.repo, '--output', out, '--workspace', self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(out.read_text(encoding='utf-8'))
        finding = next(f for f in data['findings'] if f['id'] == self.finding_id)
        self.assertEqual(finding['status'], 'Done')
        self.assertEqual(finding['notes'], 'cli parity evidence')
        markdown = self.root / 'report.md'
        self.assertEqual(run_cli('export', self.repo, '--output', markdown, '--workspace', self.workspace).returncode, 0)
        self.assertIn('cli parity evidence', markdown.read_text(encoding='utf-8'))
        again = run_cli('export', self.repo, '--output', out, '--workspace', self.workspace)
        self.assertEqual(again.returncode, 2)

    def test_backup_is_checked_and_refuses_existing_destination(self):
        backup = self.root / 'backup.sqlite3'
        result = run_cli('backup', '--output', backup, '--workspace', self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(backup)) as copy:
            self.assertEqual(copy.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(copy.execute('SELECT COUNT(*) FROM projects').fetchone()[0], 1)
        self.assertEqual(run_cli('backup', '--output', backup, '--workspace', self.workspace).returncode, 2)

    def test_scans_and_diff_scans(self):
        result = run_cli('scans', self.repo, '--workspace', self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)), 2)
        out = self.root / 'delta.json'
        diff = run_cli('diff-scans', self.repo, self.older_seq, self.newer_seq, '--output', out, '--workspace', self.workspace)
        self.assertEqual(diff.returncode, 1, diff.stderr)
        self.assertTrue(json.loads(out.read_text(encoding='utf-8'))['removed'])
        same = self.root / 'same.json'
        nodiff = run_cli('diff-scans', self.repo, self.older_seq, self.older_seq, '--output', same, '--workspace', self.workspace)
        self.assertEqual(nodiff.returncode, 0, nodiff.stderr)
        missing = run_cli('diff-scans', self.repo, 9999, self.newer_seq, '--output', self.root / 'x.json', '--workspace', self.workspace)
        self.assertEqual(missing.returncode, 2)

    def test_shortlist_export_json_and_markdown(self):
        out = self.root / 'shortlist.json'
        result = run_cli('shortlist', '--output', out, '--workspace', self.workspace)
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(entries[0]['repository']['full_name'], 'example/old-tool')
        self.assertEqual(entries[0]['status'], 'Promising')
        markdown = self.root / 'shortlist.md'
        self.assertEqual(run_cli('shortlist', '--output', markdown, '--workspace', self.workspace).returncode, 0)
        self.assertIn('seeded research note', markdown.read_text(encoding='utf-8'))

    def test_unknown_projects_and_missing_folders_are_errors(self):
        self.assertEqual(run_cli('scans', 'no-such-project', '--workspace', self.workspace).returncode, 2)
        self.assertEqual(run_cli('export', self.root / 'missing', '--output', self.root / 'e.json', '--workspace', self.workspace).returncode, 2)

    def test_cli_still_never_imports_tkinter(self):
        probe = subprocess.run([sys.executable, '-c', 'import gitrevival.cli; import sys; assert "tkinter" not in sys.modules'],
                               capture_output=True, timeout=15)
        self.assertEqual(probe.returncode, 0, probe.stderr)


if __name__ == '__main__':
    unittest.main()

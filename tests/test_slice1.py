"""0.8.0 Slice 1: revival potential evidence, license classes, CI bitrot."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GITREVIVAL_NO_DEMO', '1')

from gitrevival.analyzer import inspect
from gitrevival.github import GitHubClient, evidence_text, summarize
from gitrevival.licenses import license_class
from tests.test_github import Opener, REPO, http_error

class PotentialEvidenceTests(unittest.TestCase):
    def test_check_collects_demand_ci_and_living_fork(self):
        fork = dict(REPO, full_name='helper/old-tool', stargazers_count=40,
                    pushed_at='2026-09-01T00:00:00Z', fork=True)
        opener = Opener([
            REPO, http_error(404),
            [{'sha': 'abc', 'commit': {'committer': {'date': '2020-01-01T00:00:00Z'}}}],
            [],
            {'total_count': 42}, {'total_count': 5},
            {'workflow_runs': [{'name': 'CI', 'conclusion': 'success',
                                'updated_at': '2021-03-04T00:00:00Z',
                                'html_url': 'https://github.com/example/old-tool/actions/runs/1'}]},
            [fork],
            {'ahead_by': 17, 'behind_by': 3},
        ])
        result = GitHubClient(opener=opener).check('example/old-tool')
        self.assertEqual(result['checks']['demand'], 'Checked')
        self.assertEqual(result['demand']['open_issues'], 42)
        self.assertEqual(result['ci']['conclusion'], 'success')
        self.assertEqual(result['living_forks'][0]['ahead_by'], 17)
        text = evidence_text(result)
        self.assertIn('UNMET DEMAND', text)
        self.assertIn('may still be waiting for fixes', text)
        self.assertIn('LAST KNOWN HEALTHY STATE', text)
        self.assertIn('LIVING FORKS', text)
        self.assertIn('possible living fork', text)
        self.assertIn('(permissive)', text)

    def test_quiet_fork_is_not_compared(self):
        fork = dict(REPO, full_name='helper/old-tool', pushed_at='2019-01-01T00:00:00Z', fork=True)
        opener = Opener([REPO, http_error(404), [], [],
                         {'total_count': 0}, {'total_count': 0},
                         {'workflow_runs': []}, [fork]])
        result = GitHubClient(opener=opener).check('example/old-tool')
        self.assertIsNone(result['living_forks'][0]['ahead_by'])
        self.assertEqual(len(opener.requests), 8)

    def test_license_classes(self):
        self.assertEqual(license_class('MIT'), 'Permissive')
        self.assertEqual(license_class('GPL-3.0'), 'Copyleft')
        self.assertEqual(license_class('LGPL-2.1'), 'Weak copyleft')
        self.assertEqual(license_class('NOASSERTION'), 'No licence identified')
        self.assertEqual(summarize(REPO)['license_class'], 'Permissive')
        self.assertEqual(summarize({'full_name': 'a/b'})['license_class'], 'No licence identified')

class CiBitrotTests(unittest.TestCase):
    def build(self, files):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        for rel, text in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        return tmp, inspect(root)

    def test_bitrot_findings(self):
        tmp, report = self.build({
            'README.md': '# x\n',
            '.github/workflows/ci.yml': (
                'jobs:\n  build:\n    runs-on: ubuntu-20.04\n    steps:\n'
                '      - uses: actions/checkout@v2\n'
                '      - uses: actions/cache@v3\n'
                '      - uses: actions/setup-java@v1\n'),
            'appveyor.yml': 'build: off\n',
            'circle.yml': 'machine:\n  node:\n    version: 6\n',
        })
        titles = {(f.category, f.title) for f in report.findings}
        self.assertIn(('Automation', 'Review an older GitHub Actions major version'), titles)
        self.assertIn(('Automation', 'Review legacy hosted runner label'), titles)
        self.assertIn(('Automation', 'Confirm AppVeyor CI still runs'), titles)
        self.assertIn(('Automation', 'Legacy CircleCI 1.0 configuration'), titles)
        tmp.cleanup()

    def test_current_workflow_is_quiet(self):
        tmp, report = self.build({
            'README.md': '# x\n',
            '.github/workflows/ci.yml': (
                'jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n'
                '      - uses: actions/checkout@v4\n'
                '      - uses: actions/setup-python@v5\n'),
        })
        automation = [f for f in report.findings if f.category == 'Automation'
                      and 'Actions major version' in f.title or 'runner label' in f.title]
        self.assertEqual(automation, [])
        tmp.cleanup()

if __name__ == '__main__':
    unittest.main()

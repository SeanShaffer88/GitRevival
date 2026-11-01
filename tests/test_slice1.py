"""0.8.0 Slice 1: revival potential evidence, license classes, CI bitrot."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from contextlib import redirect_stdout
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GITREVIVAL_NO_DEMO', '1')
from gitrevival.cli import main

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
            [{'number': 9, 'title': 'Fix the crash', 'updated_at': '2021-01-01T00:00:00Z',
              'html_url': 'https://github.com/example/old-tool/pull/9'}],
            [{'state': 'APPROVED', 'user': {'login': 'helper'}}],
            [{'login': 'helper', 'contributions': 55}, {'login': 'example', 'contributions': 900}],
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
        self.assertEqual(result['pr_graveyard'][0]['approvals'], 1)
        self.assertIn('PR GRAVEYARD', text)
        self.assertEqual(result['top_contributors'], [{'login': 'helper', 'contributions': 55}])
        self.assertIn('CONTRIBUTOR OUTREACH', text)

    def test_quiet_fork_is_not_compared(self):
        fork = dict(REPO, full_name='helper/old-tool', pushed_at='2019-01-01T00:00:00Z', fork=True)
        opener = Opener([REPO, http_error(404), [], [],
                         {'total_count': 0}, {'total_count': 0},
                         {'workflow_runs': []}, [fork], [], []])
        result = GitHubClient(opener=opener).check('example/old-tool')
        self.assertIsNone(result['living_forks'][0]['ahead_by'])
        self.assertEqual(len(opener.requests), 10)

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

class ProfilerTests(unittest.TestCase):
    def build(self, files):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        for rel, text in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        return tmp, inspect(root)

    def test_god_file_no_tests_thin_docs(self):
        tmp, report = self.build({
            'README.md': '# x\n',
            'big.py': 'x = 1\n' * 1600,
            'small.py': 'y = 2\n',
        })
        titles = {f.title for f in report.findings}
        self.assertTrue(any(t.startswith('God file: big.py') for t in titles))
        self.assertIn('No test files observed', titles)
        self.assertIn('Documentation is thin', titles)
        tmp.cleanup()

    def test_tests_docs_and_funding(self):
        tmp, report = self.build({
            'README.md': '# x\n' + 'line\n' * 60,
            'app.py': 'y = 2\n',
            'tests/test_app.py': 'def test_x():\n    pass\n',
            'docs/guide.md': '# Guide\n',
            '.github/FUNDING.yml': 'github: someone\n',
            'coverage.xml': '<coverage/>\n',
        })
        titles = {f.title for f in report.findings}
        self.assertIn('Test files present', titles)
        self.assertIn('Architecture documentation present', titles)
        self.assertIn('Sponsor or funding signals present', titles)
        self.assertIn('Recorded coverage evidence present', titles)
        self.assertNotIn('No test files observed', titles)
        tmp.cleanup()

class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
    def read(self, limit=-1):
        return json.dumps(self.payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False

def fake_opener(mapping):
    def open_it(request, timeout=12):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        for needle, payload in mapping.items():
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return FakeResponse(payload)
        raise urllib.error.HTTPError(url, 404, 'not found', {}, None)
    return open_it

class AuditTests(unittest.TestCase):
    def test_registry_states(self):
        from gitrevival.audit import registry_state, name_available
        opener = fake_opener({
            'pypi.org': {'info': {'version': '2.0'}, 'releases': {'1.0': [{'upload_time_iso_8601': '2020-01-01T00:00:00'}], '2.0': [{'upload_time_iso_8601': '2021-06-01T00:00:00'}]}},
            'registry.npmjs.org': {'dist-tags': {'latest': '3.1'}, 'time': {'3.1': '2022-02-02T00:00:00Z', 'modified': '2022-02-02T00:00:00Z'}},
            'api.npmjs.org': {'downloads': 12345},
            'reverse_dependencies': {'meta': {'total': 42}},
            'crates.io': {'crate': {'max_stable_version': '1.2', 'updated_at': '2023-03-03T00:00:00Z'}},
        })
        pypi = registry_state('pypi', 'demo', opener)
        self.assertEqual((pypi['latest'], pypi['last_release']), ('2.0', '2021-06-01T00:00:00'))
        npm = registry_state('npm', 'demo', opener)
        self.assertEqual(npm['weekly_downloads'], 12345)
        crates = registry_state('crates', 'demo', opener)
        self.assertEqual(crates['dependents'], 42)
        self.assertTrue(name_available('pypi', 'missing-name', fake_opener({})))

    def test_advisories_and_report(self):
        from gitrevival.audit import audit_report, audit_text
        from gitrevival.analyzer import Dependency
        class FakeClient:
            def get(self, path, params=None):
                assert path == '/advisories'
                return [{'ghsa_id': 'GHSA-xxxx', 'severity': 'high', 'summary': 'Bad thing',
                         'html_url': 'https://github.com/advisories/GHSA-xxxx', 'published_at': '2021-01-01'}]
        class FakeReport:
            name = 'demo'
            root = '/nonexistent'
            dependencies = [Dependency('demo-lib', '1.0.0', 'Python', 'pyproject.toml'),
                            Dependency('ranged', '^2.0', 'Node.js', 'package.json')]
        opener = fake_opener({'pypi.org': {'info': {'version': '9.9'}, 'releases': {}}})
        result = audit_report(FakeReport(), client=FakeClient(), opener=opener)
        first, second = result['entries']
        self.assertEqual(first['advisories']['advisories'][0]['id'], 'GHSA-xxxx')
        self.assertFalse(second['advisories']['checked'])
        text = audit_text(result)
        self.assertIn('ADVISORY GHSA-xxxx', text)
        self.assertIn('not an exact version', text)


class KickstartTests(unittest.TestCase):
    def test_drafts_written_and_never_overwritten(self):
        from gitrevival.kickstart import generate_kickstart
        tmp, report = ProfilerTests().build({
            'README.md': '# x\n' + 'line\n' * 60,
            'app.py': 'y = 2\n',
        })
        snapshot = {'full_name': 'example/old-tool', 'html_url': 'https://github.com/example/old-tool',
                    'pushed_at': '2021-05-01T00:00:00Z',
                    'top_contributors': [{'login': 'helper', 'contributions': 55}],
                    'issues': [{'number': 7, 'title': 'Crash on start', 'html_url': 'https://github.com/example/old-tool/issues/7'}]}
        out = Path(tmp.name) / 'drafts'
        names = generate_kickstart(report, snapshot, out)
        self.assertEqual(names, ['ADOPTERS.md', 'BACKLINK.md', 'MODERNIZATION.md', 'OUTREACH.md'])
        adopters = (out / 'ADOPTERS.md').read_text(encoding='utf-8')
        self.assertIn('example/old-tool', adopters)
        self.assertIn('helper', adopters)
        backlink = (out / 'BACKLINK.md').read_text(encoding='utf-8')
        self.assertIn('#7 (Crash on start)', backlink)
        with self.assertRaises(ValueError):
            generate_kickstart(report, snapshot, out)
        tmp.cleanup()

    def test_kickstart_cli(self):
        repo = Path(__file__).resolve().parent.parent / 'demo' / 'old-orbit'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'drafts'
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(['kickstart', str(repo), '--output', str(out), '--workspace', str(Path(tmp) / 'ws.db')])
            self.assertEqual(code, 0)
            self.assertIn('ADOPTERS.md', stdout.getvalue())
            self.assertTrue((out / 'OUTREACH.md').exists())

class DiscoverTests(unittest.TestCase):
    def repo(self, name='example/old-tool'):
        return {'full_name': name, 'html_url': f'https://github.com/{name}',
                'description': 'A tool', 'stargazers_count': 250, 'watchers_count': 250,
                'forks_count': 30, 'open_issues_count': 12, 'language': 'Python',
                'license': {'spdx_id': 'MIT'}, 'pushed_at': '2020-01-01T00:00:00Z',
                'created_at': '2015-01-01T00:00:00Z', 'updated_at': '2020-01-02T00:00:00Z',
                'fork': False, 'archived': False, 'disabled': False}

    def test_strict_filters_build_query(self):
        from datetime import datetime, timezone
        from gitrevival.github import GitHubClient, discover
        opener = Opener([{'total_count': 1, 'items': [self.repo()]}])
        client = GitHubClient(opener=opener)
        result = discover(client, 'audio editor', hunt='loved', min_stars=100,
                          inactive_months='18-36', license_id='MIT',
                          at=datetime(2026, 10, 31, tzinfo=timezone.utc))
        query = result['query']
        self.assertIn('stars:>=100', query)
        self.assertIn('license:MIT', query)
        self.assertIn('pushed:<2025-05-01', query)
        self.assertIn('pushed:>2023-10-31', query)
        self.assertEqual(result['results'][0]['verdict'], 'Strong candidate')
        import urllib.parse
        sent = urllib.parse.parse_qs(urllib.parse.urlparse(opener.requests[0].full_url).query)
        self.assertEqual(sent['q'][0], query)

    def test_passing_ci_filter(self):
        from gitrevival.github import GitHubClient, discover
        runs_ok = {'workflow_runs': [{'name': 'CI', 'conclusion': 'success', 'updated_at': '2020-01-01T00:00:00Z'}]}
        runs_bad = {'workflow_runs': [{'name': 'CI', 'conclusion': 'failure', 'updated_at': '2020-01-01T00:00:00Z'}]}
        opener = Opener([{'total_count': 2, 'items': [self.repo('a/one'), self.repo('b/two')]}, runs_ok, runs_bad])
        result = discover(GitHubClient(opener=opener), 'tool', has_passing_ci=True)
        self.assertEqual([r['full_name'] for r in result['results']], ['a/one'])

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
from gitrevival.github import (GitHubClient, GitHubError, ApiRedirect, repository_name,
                               local_origin, summarize, lead_signals, evidence_text, MAX_RESPONSE)
from gitrevival.store import Store, export_report
from gitrevival.analyzer import inspect

REPO = {'full_name':'example/old-tool','description':'A synthetic tool','language':'C++',
        'stargazers_count':100,'forks_count':12,'open_issues_count':4,'archived':True,
        'pushed_at':'2020-01-01T00:00:00Z','default_branch':'main','license':{'spdx_id':'MIT'},'topics':['tools']}

class Response(io.BytesIO):
    headers = {'X-RateLimit-Remaining':'58','X-RateLimit-Limit':'60','X-RateLimit-Resource':'core','X-RateLimit-Reset':'1792700000'}

class Opener:
    def __init__(self,results):
        self.results = list(results)
        self.requests = []
    def open(self,request,timeout):
        self.requests.append(request)
        item = self.results.pop(0)
        if isinstance(item,Exception):
            raise item
        return Response(item if isinstance(item,bytes) else json.dumps(item).encode())

def http_error(code,headers=None):
    return urllib.error.HTTPError('https://api.github.com/test',code,'test',headers or {},None)

class GithubTests(unittest.TestCase):
    def test_repository_input_validation(self):
        for value in ('example/old-tool','https://github.com/example/old-tool','https://github.com/example/old-tool.git','git@github.com:example/old-tool.git'):
            self.assertEqual(repository_name(value),'example/old-tool')
        for value in ('https://evil.test/example/repo','https://github.com.evil.test/a/b','https://token@github.com/a/b','https://github.com/a/b?token=x','https://github.com/a/b/tree/main','a/..','../b','https://github.com:443/a/b'):
            with self.assertRaises(ValueError,msg=value):
                repository_name(value)
    def test_request_encoding_bounds_and_auth_is_not_in_results(self):
        opener = Opener([{'items':[REPO],'total_count':120,'incomplete_results':True}])
        client = GitHubClient(token='test-secret',opener=opener)
        result = client.search('language:C++ pushed:<2024-01-01',2)
        self.assertIn('language%3AC%2B%2B',opener.requests[0].full_url)
        self.assertIn('page=2',opener.requests[0].full_url)
        self.assertEqual(opener.requests[0].get_header('Authorization'),'Bearer test-secret')
        self.assertNotIn('test-secret',json.dumps(result))
        self.assertTrue(result['incomplete_results'])
        self.assertEqual(result['rate']['remaining'],'58')
        for page in (0,41):
            with self.assertRaises(ValueError):
                client.search('tools',page)
    def test_oversized_unreadable_and_network_failures(self):
        for response in (b'x'*(MAX_RESPONSE+1),b'not json',urllib.error.URLError('test')):
            with self.assertRaises(GitHubError):
                GitHubClient(opener=Opener([response])).get('/repos/a/b')
    def test_invalid_token_is_not_echoed_in_error(self):
        with self.assertRaises(GitHubError) as caught:
            GitHubClient(token='private-secret\n',opener=Opener([])).get('/repos/a/b')
        self.assertNotIn('private-secret',str(caught.exception))
    def test_rate_limit_has_retry_information_and_no_retry(self):
        opener = Opener([http_error(429,{'Retry-After':'60','X-RateLimit-Remaining':'0','X-RateLimit-Reset':'1792700000'})])
        with self.assertRaisesRegex(GitHubError,'retry after seconds: 60'):
            GitHubClient(opener=opener).search('tools')
        self.assertEqual(len(opener.requests),1)
    def test_http_failures_are_actionable(self):
        for status,phrase in ((401,'Authentication failed'),(404,'not found'),(422,'query')):
            with self.assertRaisesRegex(GitHubError,phrase):
                GitHubClient(opener=Opener([http_error(status)])).check('a/b')
    def test_live_check_filters_prs_and_retains_404_release_semantics(self):
        opener = Opener([REPO,http_error(404),[{'sha':'abc','commit':{'committer':{'date':'2020-01-01T00:00:00Z'}}}],
                         [{'number':1,'title':'Issue','html_url':'https://github.com/example/old-tool/issues/1'},
                          {'number':2,'title':'PR','pull_request':{}}]])
        result = GitHubClient(opener=opener).check('example/old-tool')
        self.assertIsNone(result['release'])
        self.assertIn('non-prerelease',result['checks']['release'])
        self.assertEqual(len(result['issues']),1)
        self.assertEqual(result['commit']['sha'],'abc')
        self.assertEqual(len(opener.requests),4)
    def test_partial_failure_stops_rate_limited_checks(self):
        opener = Opener([REPO,http_error(403,{'X-RateLimit-Remaining':'0'})])
        result = GitHubClient(opener=opener).check('example/old-tool')
        self.assertTrue(result['warnings'])
        self.assertIn('earlier failure',result['checks']['issues'])
        self.assertEqual(len(opener.requests),2)
        self.assertEqual(result['full_name'],'example/old-tool')
    def test_external_redirect_is_refused(self):
        import urllib.request
        with self.assertRaises(GitHubError):
            ApiRedirect().redirect_request(urllib.request.Request('https://api.github.com/test'),None,302,'',{},'https://evil.test/repo')
    def test_score_is_explained_and_archived_not_rejected(self):
        snapshot = summarize(REPO)
        score,reasons = lead_signals(snapshot,datetime(2026,10,22,tzinfo=timezone.utc))
        self.assertEqual(score,5)
        self.assertTrue(any('not automatically excluded' in x for x in reasons))
        self.assertIn('not revival feasibility',evidence_text(snapshot))
        unknown = summarize({'full_name':'a/b','license':{'spdx_id':'NOASSERTION'}})
        self.assertEqual(lead_signals(unknown)[0],0)
    def test_origin_is_read_without_executing_git_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'.git'
            path.mkdir()
            (path/'config').write_text('[remote "origin"]\nurl = git@github.com:example/old-tool.git\n[include]\npath = /never-read-this\n')
            self.assertEqual(local_origin(tmp),'example/old-tool')
    def test_store_migration_shortlist_cache_and_linked_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'workspace.sqlite3')
            snapshot = summarize(REPO)
            snapshot['checks'] = {'release':'Checked'}
            store.save_candidate(snapshot,'Promising','Unique benefit; compare maintained alternatives.')
            store.save_candidate(summarize(REPO),'Investigating','Keep richer live evidence')
            self.assertIn('checks',store.github_check('EXAMPLE/OLD-TOOL'))
            payload = {'query':'tools','page':1,'items':[snapshot]}
            store.save_search(payload)
            self.assertEqual(store.github_search('tools',1),payload)
            store.link_upstream(tmp,'example/old-tool')
            report = inspect(tmp)
            export_report(report,store,Path(tmp)/'export.json')
            self.assertEqual(json.loads((Path(tmp)/'export.json').read_text())['github_upstream']['full_name'],'example/old-tool')
            export_report(report,store,Path(tmp)/'export.md')
            self.assertIn('Saved GitHub evidence',(Path(tmp)/'export.md').read_text(encoding='utf-8'))
            moved = dict(snapshot,full_name='example/new-name')
            store.save_check(moved,previous='example/old-tool')
            self.assertEqual(store.upstream(tmp),'example/new-name')
            self.assertEqual(store.candidate('example/new-name')[0],'Investigating')
            store.close()
            store = Store(Path(tmp)/'workspace.sqlite3')
            self.assertEqual(len(store.candidates()),1)
            self.assertEqual(store.github_search('tools',1),payload)
            store.close()

class DiscoveryGuiTests(unittest.TestCase):
    def test_async_search_check_notes_link_and_export(self):
        from gitrevival.app import App
        with tempfile.TemporaryDirectory() as tmp:
            app = App(Path(tmp)/'workspace.sqlite3')
            panel = app.discovery
            try:
                panel.client = GitHubClient(opener=Opener([{'items':[REPO],'total_count':1,'incomplete_results':False}, REPO,http_error(404),[],[]]))
                app.tabs.select(panel)
                app.update()
                panel.query.set('example')
                panel.search()
                self.drain(app,panel)
                self.assertEqual(len(panel.tree.get_children()),1)
                key = 'example/old-tool'
                panel.tree.selection_set(key)
                panel.select()
                panel.notes.insert('1.0','Preserve useful GUI behavior; compare maintained alternatives.')
                panel.candidate_state.set('Promising')
                self.assertTrue(panel.save())
                panel.check_selected()
                self.drain(app,panel)
                self.assertIn('LIVE CHECK DETAILS',panel.detail.get('1.0','end'))
                self.assertEqual(panel.notes.get('1.0','end-1c'),'Preserve useful GUI behavior; compare maintained alternatives.')
                report = inspect(tmp)
                app.store.save_report(report)
                app.load(report)
                panel.link()
                self.assertEqual(app.store.upstream(tmp),key)
                panel.show_saved()
                self.assertEqual(len(panel.tree.get_children()),1)
                panel.tree.selection_set(key)
                panel.select()
                app.update()
                self.assertGreater(panel.notes.winfo_height(),30)
                path = str(Path(tmp)/'shortlist.json')
                with patch('gitrevival.discovery.filedialog.asksaveasfilename',return_value=path):
                    panel.export()
                entries = json.loads(Path(path).read_text())
                self.assertEqual(entries[0]['status'],'Promising')
                self.assertIn('checks',entries[0]['repository'])
                panel.cached_search()
                self.assertIn('CACHED',panel.info.get())
            finally:
                app.store.close()
                app.destroy()
    def drain(self,app,panel):
        deadline = time.monotonic()+3
        while panel.busy and time.monotonic()<deadline:
            app.update()
            time.sleep(.01)
        self.assertFalse(panel.busy,'Background request did not complete')

if __name__ == '__main__':
    unittest.main()

"""Read-only public GitHub API access. No Git execution or credential discovery."""
from __future__ import annotations
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE = 2_000_000

class GitHubError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

def repository_name(value):
    value = value.strip()
    if value.startswith('git@github.com:'):
        value = value[len('git@github.com:'):]
    elif '://' in value:
        url = urllib.parse.urlsplit(value)
        if url.scheme != 'https' or url.hostname != 'github.com' or url.username or url.password or url.port:
            raise ValueError('Use owner/repository or an HTTPS github.com repository URL.')
        if url.query or url.fragment:
            raise ValueError('Use the repository URL without query parameters or fragments.')
        value = url.path.strip('/')
    value = value.removesuffix('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('Enter a GitHub owner/repository, such as microsoft/terminal.')
    owner, repo = value.split('/')
    if repo in {'.', '..'}:
        raise ValueError('Invalid repository name.')
    return f'{owner}/{repo}'

def local_origin(root):
    """Only read an ordinary .git/config. Do not invoke git or follow includes."""
    path = Path(root) / '.git' / 'config'
    if (Path(root)/'.git').is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError('No ordinary .git/config found. Paste the GitHub upstream URL manually (including for Git worktrees).')
    with path.open('rb') as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise ValueError('Git config is too large; paste the upstream manually.')
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read_string(raw.decode('utf-8-sig'))
        return repository_name(parser.get('remote "origin"', 'url'))
    except (configparser.Error, UnicodeError):
        raise ValueError('Could not read origin; paste the GitHub upstream manually.') from None

class ApiRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or target.netloc != 'api.github.com':
            raise GitHubError('GitHub redirected outside api.github.com; request stopped.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class GitHubClient:
    def __init__(self, token=None, opener=None):
        self.token = token if token is not None else os.environ.get('GITREVIVAL_GITHUB_TOKEN', '')
        self.opener = opener or urllib.request.build_opener(ApiRedirect())
        self.rate = {}

    def get(self, path, params=None):
        if not path.startswith('/') or path.startswith('//') or '://' in path:
            raise ValueError('Expected a relative GitHub API path.')
        url = 'https://api.github.com' + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        headers = {'Accept':'application/vnd.github+json', 'User-Agent':'GitRevival/0.2.0',
                   'X-GitHub-Api-Version':'2022-11-28'}
        if self.token:
            if any(not (33 <= ord(char) <= 126) for char in self.token):
                raise GitHubError('GITREVIVAL_GITHUB_TOKEN contains invalid header characters. Correct or remove the environment variable.')
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(url, headers=headers)
        try:
            with self.opener.open(request, timeout=12) as response:
                self.record_rate(response.headers)
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise GitHubError('GitHub response exceeded the 2 MB limit. Narrow the search.')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            self.record_rate(exc.headers)
            if exc.code in {403,429}:
                reset = self.rate.get('reset', 'unknown')
                retry = exc.headers.get('Retry-After', 'not supplied')
                raise GitHubError(f'GitHub denied this request or limited the rate (HTTP {exc.code}). Remaining: {self.rate.get("remaining", "unknown")}; reset UTC: {reset}; retry after seconds: {retry}. No automatic retry.', exc.code) from None
            messages = {401:'Authentication failed. Check GITREVIVAL_GITHUB_TOKEN or remove it to use public access.',
                        404:'Repository or endpoint not found, or not accessible with this authentication.',
                        422:'GitHub rejected this query. Check search syntax and qualifiers.',
                        409:'Repository has no usable commit history for this request.'}
            raise GitHubError(messages.get(exc.code, f'GitHub returned HTTP {exc.code}. Try again later.'), exc.code) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            raise GitHubError('Could not reach GitHub within the request timeout. Check connectivity and try again; saved evidence remains available.') from None
        except (json.JSONDecodeError, UnicodeError):
            raise GitHubError('GitHub returned an unreadable JSON response.') from None

    def record_rate(self, headers):
        self.rate = {k:headers.get('X-RateLimit-'+k.capitalize(), 'unknown') for k in ('remaining','limit','resource')}
        try:
            self.rate['reset'] = datetime.fromtimestamp(int(headers.get('X-RateLimit-Reset')), timezone.utc).isoformat()
        except (ValueError,TypeError,OverflowError,OSError):
            self.rate['reset'] = 'unknown'

    def search(self, query, page=1):
        query = query.strip()
        if not query or len(query) > 256:
            raise ValueError('Enter a search query of 1–256 characters.')
        if not 1 <= page <= 40:
            raise ValueError('Search pages must be between 1 and 40 (GitHub limits search to 1,000 results).')
        data = self.get('/search/repositories', {'q': query, 'per_page':25, 'page':page, 'sort':'stars','order':'desc'})
        if not isinstance(data,dict) or not isinstance(data.get('items'),list):
            raise GitHubError('Unexpected repository search response.')
        items = [dict(summarize(x),discovered_query=query,discovered_page=page) for x in data['items']]
        return {'query':query, 'page':page, 'checked_at':now(), 'total_count':data.get('total_count',0),
                'incomplete_results':bool(data.get('incomplete_results')), 'items':items, 'rate':dict(self.rate)}

    def check(self, name):
        name = repository_name(name)
        data = self.get('/repos/'+name)
        snapshot = summarize(data)
        # Repository transfers/renames return the canonical current name.
        name = repository_name(snapshot['full_name'])
        snapshot.update({'warnings':[], 'release':None, 'commit':None, 'issues':[], 'checked_at':now(), 'checks':{}})
        paths = [('release', '/releases/latest', None), ('commit', '/commits', {'per_page':1}),
                 ('issues', '/issues', {'state':'open','per_page':5,'sort':'updated','direction':'desc'})]
        for key,path,params in paths:
            try:
                result = self.get('/repos/'+name+path,params)
                snapshot['checks'][key] = 'Checked'
                if key == 'release':
                    snapshot[key] = {k:result.get(k) for k in ('tag_name','published_at','html_url')}
                elif key == 'commit' and result:
                    first = result[0]
                    snapshot[key] = {'sha':first.get('sha'), 'date':first.get('commit',{}).get('committer',{}).get('date'), 'html_url':first.get('html_url')}
                elif key == 'issues':
                    snapshot[key] = [{k:x.get(k) for k in ('number','title','updated_at','html_url')} for x in result if 'pull_request' not in x]
            except GitHubError as exc:
                if exc.status == 404 and key == 'release':
                    snapshot['checks'][key] = 'No latest published non-prerelease release found (HTTP 404)'
                else:
                    snapshot['checks'][key] = 'Unavailable'
                    snapshot['warnings'].append(f'{key}: {exc}')
                if exc.status in {401,403,429} or exc.status is None:
                    break
        for key,_,_ in paths:
            snapshot['checks'].setdefault(key,'Not requested after an earlier failure')
        snapshot['rate'] = dict(self.rate)
        return snapshot

def now():
    return datetime.now(timezone.utc).isoformat()

def summarize(data):
    name = repository_name(data.get('full_name',''))
    license = data.get('license') or {}
    parent = data.get('parent') or {}
    return {'full_name':name, 'html_url':'https://github.com/'+name,
            'description':data.get('description') or '', 'language':data.get('language') or 'Unknown',
            'stars':data.get('stargazers_count',0), 'forks':data.get('forks_count',0),
            'open_issues_and_prs':data.get('open_issues_count',0), 'archived':bool(data.get('archived')),
            'disabled':bool(data.get('disabled')), 'fork':bool(data.get('fork')),
            'parent':parent.get('full_name'), 'pushed_at':data.get('pushed_at'),
            'default_branch':data.get('default_branch'), 'license':license.get('spdx_id') or 'Unknown',
            'topics':data.get('topics') or [], 'checked_at':now()}

def lead_signals(repo, at=None):
    """Explainable research priority, never a repair feasibility or license verdict."""
    reasons = []
    score = 0
    if repo.get('license') not in {None,'Unknown','NOASSERTION'}:
        score += 2
        reasons.append('+2 GitHub identifies a license; verify its text and scope')
    else:
        reasons.append('+0 License permission needs investigation')
    if repo.get('stars',0) >= 25:
        score += 1
        reasons.append('+1 At least 25 stars: a weak historical-interest signal')
    try:
        pushed = datetime.fromisoformat(repo['pushed_at'].replace('Z','+00:00'))
        days = ((at or datetime.now(timezone.utc)) - pushed).days
        if days >= 730:
            score += 1
            reasons.append(f'+1 Last push {days} days ago: maintenance review lead')
    except (KeyError,TypeError,ValueError,AttributeError):
        reasons.append('Last-push age unavailable')
    if repo.get('topics'):
        score += 1
        reasons.append('+1 Topics provide clues about project purpose')
    if repo.get('archived'):
        reasons.append('Archived: consider a fork and ownership needs; not automatically excluded')
    if repo.get('fork'):
        reasons.append('Fork: compare with the parent project before choosing revival work')
    if repo.get('disabled'):
        reasons.append('Disabled on GitHub: availability requires separate investigation')
    return score,reasons

def evidence_text(repo):
    score,reasons = lead_signals(repo)
    lines = [repo['full_name'], repo.get('description',''), repo['html_url'], '',
             f"Evidence retrieved (UTC): {repo.get('checked_at','Unknown')}",
             f"Language: {repo.get('language')} | Stars: {repo.get('stars')} | Forks: {repo.get('forks')}",
             f"Archived: {repo.get('archived')} | Disabled: {repo.get('disabled')} | Fork: {repo.get('fork')}",
             f"Parent: {repo.get('parent') or 'Not provided'} | Default branch: {repo.get('default_branch')}",
             f"Last push: {repo.get('pushed_at') or 'Unknown'} (any ref; not necessarily a code change)",
             f"GitHub license detection: {repo.get('license')} — compatibility and fork rights unverified",
             f"Open issues + pull requests: {repo.get('open_issues_and_prs')}", '',
             f'RESEARCH PRIORITY: {score}/5 (heuristic, not revival feasibility)', *reasons, '']
    if 'checks' in repo:
        lines += ['LIVE CHECK DETAILS', json.dumps(repo['checks'],indent=2),
                  'Latest published non-prerelease release: '+json.dumps(repo.get('release'),ensure_ascii=False),
                  'Default-branch commit sample: '+json.dumps(repo.get('commit'),ensure_ascii=False),
                  'Open issue sample (PRs filtered from first 5 most recently updated open issue/PR entries):']
        lines += [f"#{i['number']} {i['title']} — {i['html_url']}" for i in repo.get('issues',[])]
        lines += ['Warnings: '+('; '.join(repo.get('warnings',[])) or 'None reported.')]
    else:
        lines += ['Search metadata only. Use Check selected for release, commit and issue samples.']
    lines += ['', 'ASSESS BEFORE ADOPTION',
              'What unique benefit would revival provide? Which maintained alternatives exist? What permissions, repair effort, security work, platform tests and long-term ownership would it require?',
              'No code was cloned or run. No vulnerability or dependency-license scan was performed.']
    if repo.get('discovered_query'):
        lines += ['',f'Discovery query: {repo["discovered_query"]} (page {repo.get("discovered_page")})']
    return '\n'.join(lines)

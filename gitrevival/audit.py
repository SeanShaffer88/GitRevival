"""Online dependency audit: registry state and known vulnerabilities.

Explicit, user-triggered network work — the local scan never calls this.
Every request is a plain GET to a pinned host: the package registries
(PyPI, npm, crates.io, NuGet, RubyGems) for package state, and GitHub's
advisory database for published vulnerability records matched against
the exact declared versions found by the local scan. Results are leads
with dates, never a safety verdict: a quiet registry entry can still be
maintained elsewhere, and no advisory match is not proof of safety.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .github import GitHubClient, GitHubError

MAX_RESPONSE = 2_000_000
MAX_DEPENDENCIES = 25
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
VERSION_RE = re.compile(r'^[0-9][0-9A-Za-z.+-]*$')

ECOSYSTEM_MAP = {
    'Node.js': ('npm', 'npm'),
    'Python': ('pip', 'pypi'),
    'Rust': ('rust', 'crates'),
    'Ruby': ('rubygems', 'rubygems'),
    'PHP': ('composer', None),
    'Go': ('go', None),
    '.NET': ('nuget', 'nuget'),
    'NuGet': ('nuget', 'nuget'),
}


class AuditError(Exception):
    pass


def _get_json(url, opener=None):
    request = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'GitRevival-Audit/0.9 (+https://github.com/SeanShaffer88/GitRevival)',
    })
    open_fn = (opener or urllib.request.urlopen)
    try:
        with open_fn(request, timeout=12) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise AuditError(f'{url.split("/")[2]} answered HTTP {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AuditError(f'Could not reach {url.split("/")[2]}: {exc.__class__.__name__}') from exc
    if len(raw) > MAX_RESPONSE:
        raise AuditError('Registry response was too large.')
    try:
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditError('Registry response was not JSON.') from exc


def registry_state(registry, name, opener=None):
    """Latest release facts for one package, or None when not found."""
    if not NAME_RE.match(name or ''):
        raise AuditError(f'Unsafe package name: {name!r}')
    quoted = urllib.parse.quote(name, safe='')
    if registry == 'pypi':
        data = _get_json(f'https://pypi.org/pypi/{quoted}/json', opener)
        if not data:
            return None
        info = data.get('info') or {}
        uploads = [f.get('upload_time_iso_8601') for rel in (data.get('releases') or {}).values()
                   for f in rel if f.get('upload_time_iso_8601')]
        return {'registry': 'PyPI', 'name': name, 'latest': info.get('version'),
                'last_release': max(uploads) if uploads else None}
    if registry == 'npm':
        data = _get_json(f'https://registry.npmjs.org/{quoted}', opener)
        if not data:
            return None
        times = data.get('time') or {}
        latest = (data.get('dist-tags') or {}).get('latest')
        state = {'registry': 'npm', 'name': name, 'latest': latest,
                 'last_release': times.get(latest) or times.get('modified')}
        try:
            downloads = _get_json(f'https://api.npmjs.org/downloads/point/last-week/{quoted}', opener)
            if downloads:
                state['weekly_downloads'] = downloads.get('downloads')
        except AuditError:
            pass
        return state
    if registry == 'crates':
        data = _get_json(f'https://crates.io/api/v1/crates/{quoted}', opener)
        if not data:
            return None
        crate = data.get('crate') or {}
        state = {'registry': 'crates.io', 'name': name, 'latest': crate.get('max_stable_version') or crate.get('max_version'),
                 'last_release': crate.get('updated_at')}
        try:
            reverse = _get_json(f'https://crates.io/api/v1/crates/{quoted}/reverse_dependencies', opener)
            if reverse:
                state['dependents'] = (reverse.get('meta') or {}).get('total')
        except AuditError:
            pass
        return state
    if registry == 'nuget':
        data = _get_json(f'https://api.nuget.org/v3-flatcontainer/{quoted.lower()}/index.json', opener)
        if not data:
            return None
        versions = data.get('versions') or []
        return {'registry': 'NuGet', 'name': name, 'latest': versions[-1] if versions else None,
                'last_release': None, 'versions_published': len(versions)}
    if registry == 'rubygems':
        data = _get_json(f'https://rubygems.org/api/v1/gems/{quoted}.json', opener)
        if not data:
            return None
        return {'registry': 'RubyGems', 'name': name, 'latest': data.get('version'),
                'last_release': data.get('version_created_at'),
                'downloads': data.get('downloads')}
    raise AuditError(f'Unknown registry: {registry}')


def name_available(registry, name, opener=None):
    """True when the registry has no package under this exact name."""
    return registry_state(registry, name, opener) is None


def advisories_for(client, ecosystem, name, version):
    """Published advisories affecting one exact declared version."""
    if not VERSION_RE.match(version or ''):
        return {'checked': False, 'reason': f'version {version!r} is a range or label, not an exact version', 'advisories': []}
    data = client.get('/advisories', {'ecosystem': ecosystem, 'affects': f'{name}@{version}', 'per_page': 30})
    found = [{'id': item.get('ghsa_id'), 'severity': item.get('severity'),
              'summary': item.get('summary'), 'url': item.get('html_url'),
              'published': item.get('published_at')} for item in data]
    return {'checked': True, 'reason': '', 'advisories': found}


def audit_report(report, client=None, opener=None, at=None):
    """Registry state + advisories for a local scan's declared dependencies."""
    client = client or GitHubClient()
    at = at or datetime.now(timezone.utc)
    seen = set()
    entries = []
    warnings = []
    for dep in report.dependencies:
        mapping = ECOSYSTEM_MAP.get(dep.ecosystem)
        if not mapping:
            continue
        key = (dep.ecosystem, dep.name.casefold())
        if key in seen:
            continue
        seen.add(key)
        if len(entries) >= MAX_DEPENDENCIES:
            warnings.append(f'Stopped at {MAX_DEPENDENCIES} dependencies; the rest were not audited.')
            break
        advisory_ecosystem, registry = mapping
        entry = {'name': dep.name, 'declared': dep.version, 'ecosystem': dep.ecosystem,
                 'registry_state': None, 'advisories': {'checked': False, 'reason': 'not checked', 'advisories': []}}
        if registry:
            try:
                entry['registry_state'] = registry_state(registry, dep.name, opener)
            except AuditError as exc:
                warnings.append(f'{dep.name}: {exc}')
        try:
            entry['advisories'] = advisories_for(client, advisory_ecosystem, dep.name, dep.version)
        except GitHubError as exc:
            warnings.append(f'{dep.name}: advisory check failed: {exc}')
        entries.append(entry)
    return {'project': report.name, 'checked_at': at.isoformat(), 'entries': entries, 'warnings': warnings}


def audit_text(result):
    lines = [f"ONLINE DEPENDENCY AUDIT — {result['project']}",
             f"Checked (UTC): {result['checked_at']}",
             'Registry state and published advisories are leads with dates, not a safety verdict.', '']
    if not result['entries']:
        lines += ['No declared dependencies in a supported ecosystem were found.']
    for entry in result['entries']:
        state = entry['registry_state']
        if state is None:
            state_text = 'not found on its registry (name may differ or the package may be unpublished)'
        else:
            state_text = f"{state['registry']}: latest {state.get('latest') or 'unknown'}"
            if state.get('last_release'):
                state_text += f", last release {str(state['last_release'])[:10]}"
            if state.get('dependents') is not None:
                state_text += f", {state['dependents']} dependent crates"
            if state.get('weekly_downloads') is not None:
                state_text += f", {state['weekly_downloads']:,} downloads last week"
            if state.get('versions_published'):
                state_text += f", {state['versions_published']} versions published"
        lines.append(f"- {entry['name']} {entry['declared']} ({entry['ecosystem']}): {state_text}")
        advisories = entry['advisories']
        if not advisories['checked']:
            lines.append(f"  Advisories not checked: {advisories['reason']}.")
        elif advisories['advisories']:
            for item in advisories['advisories']:
                lines.append(f"  ADVISORY {item['id']} ({item['severity']}): {item['summary']} — {item['url']}")
        else:
            lines.append('  No published advisories match this exact version.')
    if result['warnings']:
        lines += ['', 'Warnings: ' + '; '.join(result['warnings'])]
    return '\n'.join(lines)


def project_package_names(root):
    """The project's own package names, read from its manifests."""
    from pathlib import Path
    base = Path(root)
    names = {}
    try:
        package = json.loads((base / 'package.json').read_text(encoding='utf-8-sig'))
        if isinstance(package.get('name'), str) and package['name']:
            names['npm'] = package['name'].split('/')[-1]
    except (OSError, ValueError):
        pass
    for manifest, registry, pattern in (
            ('pyproject.toml', 'pypi', r'(?ms)^\[project\]\s.*?^name\s*=\s*"([^"]+)"'),
            ('Cargo.toml', 'crates', r'(?ms)^\[package\]\s.*?^name\s*=\s*"([^"]+)"')):
        try:
            text = (base / manifest).read_text(encoding='utf-8-sig', errors='replace')
            match = re.search(pattern, text)
            if match:
                names[registry] = match.group(1)
        except OSError:
            pass
    return names


def namespace_audit(root, opener=None):
    """Own-name registry state plus availability of revival variants."""
    results = []
    for registry, name in sorted(project_package_names(root).items()):
        entry = {'registry': registry, 'name': name, 'state': None, 'variants': {}}
        try:
            entry['state'] = registry_state(registry, name, opener)
            variants = [f'{name}-ng', f'{name}2']
            if registry == 'crates':
                variants.append(f'{name}-rs')
            for variant in variants:
                entry['variants'][variant] = name_available(registry, variant, opener)
        except AuditError as exc:
            entry['error'] = str(exc)
        results.append(entry)
    return results


def namespace_text(results):
    if not results:
        return ''
    lines = ['', 'NAMESPACE AUDIT (the project’s own package names)']
    for entry in results:
        state = entry.get('state')
        if entry.get('error'):
            lines.append(f"- {entry['name']} ({entry['registry']}): check failed — {entry['error']}")
        elif state is None:
            lines.append(f"- {entry['name']} ({entry['registry']}): not published under this name.")
        else:
            last = f", last release {str(state['last_release'])[:10]}" if state.get('last_release') else ''
            lines.append(f"- {entry['name']} ({entry['registry']}): latest {state.get('latest') or 'unknown'}{last}. "
                         'If that release is old, the registry name may be dormant; transfer policies differ per registry and are the maintainer’s to grant.')
        for variant, free in entry.get('variants', {}).items():
            lines.append(f"  Variant {variant}: {'available' if free else 'taken'}")
    return '\n'.join(lines)

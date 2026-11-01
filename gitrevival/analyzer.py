"""Bounded, read-only static inspection. Never imports or executes project code."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
import hashlib
import json
import os
import re
import tomllib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from .licenses import COPYLEFT, declared_matches, detect_license

SKIP = {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__',
        'vendor', 'dist', 'build', 'bin', 'obj', '.idea', '.vs', '.local'}
MANIFESTS = {'package.json', 'pyproject.toml', 'requirements.txt', 'setup.py',
             'Cargo.toml', 'go.mod', 'CMakeLists.txt', 'packages.config',
             'global.json', '.gitmodules', '.travis.yml', 'appveyor.yml', '.appveyor.yml', 'circle.yml',
             'Dockerfile', 'Makefile', 'azure-pipelines.yml', 'vcpkg.json'}
MAX_FILES = 15000
MAX_BYTES = 512_000
MAX_TOTAL = 12_000_000

@dataclass
class Finding:
    id: str
    severity: str
    category: str
    title: str
    file: str
    line: int
    evidence: str
    action: str
    confidence: str = 'Observed'

@dataclass
class Dependency:
    name: str
    version: str
    ecosystem: str
    file: str

@dataclass
class Edge:
    """One internal import: `source` file imports `target` file at `line`."""
    source: str
    target: str
    kind: str
    line: int

@dataclass
class LicenseDetection:
    file: str
    spdx: str
    phrase: str

@dataclass
class Report:
    root: str
    name: str
    scanned_at: str
    files: int
    ecosystems: list[str]
    dependencies: list[Dependency]
    findings: list[Finding]
    licenses: list[str]
    warnings: list[str]
    manifests: list[str]
    edges: list[Edge] = field(default_factory=list)
    license_detections: list[LicenseDetection] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

def inspect(root: str | Path) -> Report:
    base = Path(root).resolve(strict=True)
    if not base.is_dir():
        raise ValueError('Select a repository folder.')
    report = Report(str(base), base.name, datetime.now(timezone.utc).isoformat(),
                    0, [], [], [], [], [], [])
    paths: set[str] = set()
    texts: dict[str, str] = {}
    total = 0
    limited = False
    def walk_error(error):
        report.warnings.append(f'Folder could not be read: {error.filename}')
    def traversable(path):
        try:
            return not path.is_symlink() and not (getattr(path.stat(), 'st_file_attributes', 0) & 0x400)
        except OSError:
            report.warnings.append(f'Folder could not be inspected: {path.relative_to(base).as_posix()}')
            return False
    for folder, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and traversable(Path(folder) / d))
        for name in sorted(files):
            path = Path(folder) / name
            if path.is_symlink():
                continue
            if report.files >= MAX_FILES:
                limited = True
                break
            rel = path.relative_to(base).as_posix()
            paths.add(rel)
            report.files += 1
            low = name.lower()
            wanted = (name in MANIFESTS or path.suffix.lower() in {'.csproj', '.vcxproj', '.sln', '.py', '.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs'}
                      or low.startswith(('license', 'copying', 'readme'))
                      or (rel.startswith('.github/workflows/') and path.suffix in {'.yml', '.yaml'}))
            if not wanted:
                continue
            try:
                # Bound the actual read, not just a stat that could race a writer.
                if path.stat().st_size > MAX_BYTES or total >= MAX_TOTAL:
                    report.warnings.append(f'Skipped large file or scan byte budget: {rel}')
                    continue
                raw = path.open('rb')
                with raw:
                    data = raw.read(min(MAX_BYTES, MAX_TOTAL - total) + 1)
                if len(data) > min(MAX_BYTES, MAX_TOTAL - total):
                    report.warnings.append(f'Skipped file exceeding read budget: {rel}')
                    continue
                total += len(data)
                texts[rel] = data.decode('utf-8-sig', errors='replace')
            except OSError as exc:
                report.warnings.append(f'Cannot read {rel}: {exc.__class__.__name__}')
        if limited:
            break
    if limited:
        report.warnings.append(f'Scan stopped at {MAX_FILES:,} files; results are incomplete.')

    def add(category, title, file='', evidence='', action='', severity='Review', confidence='Observed', needle=''):
        source = texts.get(file, '')
        line = next((i for i, t in enumerate(source.splitlines(), 1) if (needle or evidence) and (needle or evidence) in t), 1)
        key = hashlib.sha256(f'{category}|{title}|{file}|{evidence}'.encode()).hexdigest()[:20]
        report.findings.append(Finding(key, severity, category, title, file, line, evidence[:900], action, confidence))

    def dep(name, version, ecosystem, file):
        report.dependencies.append(Dependency(str(name), str(version), ecosystem, file))
        if ecosystem not in report.ecosystems:
            report.ecosystems.append(ecosystem)

    declared: list[tuple[str, str]] = []
    for rel, text in texts.items():
        name = Path(rel).name
        low = name.lower()
        if low.startswith(('license', 'copying')):
            report.licenses.append(rel)
            spdx, phrase = detect_license(text)
            report.license_detections.append(LicenseDetection(rel, spdx, phrase))
            add('License', 'Review license scope and third-party notices', rel,
                '\n'.join(text.splitlines()[:8]),
                'Identify the exact license and copyright holders. Check dependency and asset licenses separately; a license file alone does not establish redistribution rights.', 'Info')
        if name in MANIFESTS or Path(rel).suffix in {'.csproj', '.vcxproj', '.sln'}:
            report.manifests.append(rel)
        try:
            if name == 'package.json':
                obj = json.loads(text)
                license_value = obj.get('license')
                if isinstance(license_value, str) and license_value.strip():
                    declared.append((license_value, rel))
                elif isinstance(license_value, dict) and license_value.get('type'):
                    declared.append((str(license_value['type']), rel))
                for group in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
                    for n, v in obj.get(group, {}).items():
                        dep(n, v, 'Node.js', rel)
                        if str(v) in {'*', 'latest'} or str(v).startswith(('git+', 'http:', 'https:', 'github:')):
                            add('Dependencies', f'Review reproducibility: {n}', rel, f'"{n}": "{v}"',
                                'Resolve and review the upstream source, choose a deliberate version and commit a lockfile.', needle=n)
                if not any((Path(rel).parent / x).as_posix() in paths for x in ('package-lock.json','yarn.lock','pnpm-lock.yaml','npm-shrinkwrap.json','bun.lock','bun.lockb')):
                    add('Dependencies', 'No Node lockfile found beside manifest', rel, 'package.json has no recognized adjacent lockfile.',
                        'Confirm the intended package manager and create a lockfile in a reviewed environment.')
                if obj.get('engines'):
                    add('Build', 'Verify requested Node runtime', rel, json.dumps(obj['engines']),
                        'Compare this constraint with a supported runtime and record a tested version. Static inspection does not prove compatibility.', 'Info', needle='engines')
                if obj.get('scripts'):
                    add('Build', 'Review project scripts before running', rel, json.dumps(obj['scripts'], indent=2),
                        'Read scripts and install hooks, then reproduce the build in an isolated environment.', 'Info', needle='scripts')
            elif name in {'pyproject.toml', 'Cargo.toml'}:
                obj = tomllib.loads(text)
                if name == 'pyproject.toml':
                    project = obj.get('project', {})
                    license_value = project.get('license')
                    if isinstance(license_value, str) and license_value.strip():
                        declared.append((license_value, rel))
                    elif isinstance(license_value, dict) and license_value.get('text'):
                        declared.append((str(license_value['text']), rel))
                    for entry in project.get('dependencies', []):
                        dep(entry, 'declared requirement', 'Python', rel)
                    for n, v in obj.get('tool', {}).get('poetry', {}).get('dependencies', {}).items():
                        dep(n, v, 'Python / Poetry', rel)
                    if project.get('requires-python'):
                        add('Build', 'Verify Python runtime constraint', rel, project['requires-python'],
                            'Select a supported interpreter that satisfies the constraint and validate the build.', 'Info', needle='requires-python')
                else:
                    license_value = obj.get('package', {}).get('license')
                    if isinstance(license_value, str) and license_value.strip():
                        declared.append((license_value, rel))
                    for group in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                        for n, v in obj.get(group, {}).items():
                            dep(n, json.dumps(v) if isinstance(v, dict) else v, 'Rust', rel)
            elif name == 'requirements.txt':
                for line in text.splitlines():
                    s = line.strip()
                    if s and not s.startswith(('#', '-')):
                        dep(s, 'declared requirement', 'Python', rel)
                add('Dependencies', 'Verify Python requirements and transitive versions', rel, 'requirements.txt',
                    'Resolve in an isolated environment; check supported Python versions and pin the tested dependency set.', 'Info')
            elif name == 'go.mod':
                for n, v in re.findall(r'^\s*([\w.\-/]+)\s+(v[^\s]+)', text, re.M):
                    dep(n, v, 'Go', rel)
            elif name == 'vcpkg.json':
                obj = json.loads(text)
                for item in obj.get('dependencies', []):
                    dep(item if isinstance(item, str) else item.get('name', '?'), 'manifest dependency', 'vcpkg', rel)
            elif name == 'packages.config' or Path(rel).suffix in {'.csproj', '.vcxproj'}:
                if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                    raise ValueError('XML entities and document types are unsupported')
                tree = ET.fromstring(text)
                for element in tree.iter():
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag in {'package', 'PackageReference'}:
                        version = element.get('version') or element.get('Version') or next((c.text for c in element if c.tag.rsplit('}',1)[-1] == 'Version'), 'unspecified')
                        dep(element.get('id') or element.get('Include') or '?', version, 'NuGet', rel)
                    if tag == 'PlatformToolset' and element.text:
                        add('Build', 'Verify Visual C++ toolset availability', rel, element.text,
                            'Install the required build tools or retarget deliberately; verify architecture, CRT linkage and SDK compatibility.', needle=element.text)
                    if tag in {'TargetFrameworkVersion', 'TargetFramework', 'TargetFrameworks'} and element.text:
                        add('Build', 'Verify .NET target support', rel, element.text,
                            'Check the target framework support policy and reproduce the build before planning a migration.', 'Review', needle=element.text)
            elif name == 'CMakeLists.txt':
                for n in re.findall(r'find_package\s*\(\s*([\w+.-]+)', text, re.I):
                    dep(n, 'find_package', 'CMake / C++', rel)
                minimum = re.search(r'cmake_minimum_required\s*\(\s*VERSION\s+([\d.]+)', text, re.I)
                if minimum:
                    add('Build', 'Check CMake policy compatibility', rel, minimum.group(0),
                        'Test with the intended CMake version; inspect policy changes and compiler requirements. A low minimum alone does not prove a broken build.', 'Review', needle=minimum.group(0))
            if name == '.gitmodules':
                for sub in re.findall(r'^\s*path\s*=\s*(.+)$', text, re.M):
                    target = (Path(rel).parent / sub.strip()).as_posix().rstrip('/')
                    if not any(p.startswith(target + '/') for p in paths):
                        add('Dependencies', 'Submodule content was not observed', rel, sub.strip(),
                            'Review the submodule URL, pinned commit and license before retrieving it. Empty, excluded or limited scan content may explain this finding.')
        except (ValueError, TypeError, AttributeError, ET.ParseError) as exc:
            add('Inspection', 'Manifest could not be interpreted', rel, f'{type(exc).__name__}: {exc}',
                'Inspect this manifest manually; dependency results for it are incomplete.', 'Review')

        if rel.startswith('.github/workflows/'):
            for match in re.finditer(r'uses:\s*(actions/(?:checkout|setup-node|setup-python|setup-go|setup-java|setup-dotnet|setup-ruby|cache|upload-artifact|download-artifact))@(v[123])\b', text):
                add('Automation', 'Review an older GitHub Actions major version', rel, match.group(0),
                    'Read the action upstream migration notes, runtime requirements and runner support. Verify current versions before updating.', confidence='Heuristic', needle=match.group(0))
            for match in re.finditer(r'uses:\s*(actions/(?!checkout|setup-node|setup-python|setup-go|setup-java|setup-dotnet|setup-ruby|cache|upload-artifact|download-artifact)[a-z0-9-]+)@(v1)\b', text):
                add('Automation', 'Review a first-generation GitHub Action version', rel, match.group(0),
                    'v1 actions run on retired runtimes. Check the action upstream for a current release before relying on this workflow.', confidence='Heuristic', needle=match.group(0))
            for match in re.finditer(r'\b(?:ubuntu-18\.04|ubuntu-16\.04|ubuntu-20\.04|windows-2016|windows-2019|macos-10\.15|macos-11|macos-12)\b', text):
                add('Automation', 'Review legacy hosted runner label', rel, match.group(0),
                    'Check the provider runner availability and select a currently supported image. Reproduce platform-specific behavior.', confidence='Heuristic', needle=match.group(0))
        if name == '.travis.yml':
            add('Automation', 'Confirm legacy CI still runs', rel, '.travis.yml is present.',
                'Check upstream CI status, required secrets and service availability; retain useful test coverage when migrating.', confidence='Heuristic')
        if name in {'appveyor.yml', '.appveyor.yml'}:
            add('Automation', 'Confirm AppVeyor CI still runs', rel, f'{name} is present.',
                'Check whether the AppVeyor project is still active and its builds still pass; retain useful Windows test coverage when migrating.', confidence='Heuristic')
        if name == 'circle.yml':
            add('Automation', 'Legacy CircleCI 1.0 configuration', rel, 'circle.yml is present.',
                'CircleCI 1.0 shut down years ago; this configuration cannot run today. Treat the test commands in it as the record of how the project was verified.', confidence='Heuristic')
        if name == 'setup.py':
            add('Build', 'Review executable Python packaging', rel, 'setup.py is present.',
                'Inspect setup.py without executing it. Consider declarative packaging after reproducing the original behavior.', 'Info')
    # Internal dependency edges: static imports between files inside this
    # project only. Text-level matching; nothing is imported or executed.
    def resolve_python(module, package_parts):
        parts = [p for p in module.split('.') if p]
        for cut in range(len(parts), 0, -1):
            stem = '/'.join(package_parts + parts[:cut])
            for candidate in (stem + '.py', stem + '/__init__.py'):
                if candidate in paths:
                    return candidate
        return None

    def resolve_relative(source, reference):
        folder = source.rsplit('/', 1)[0] if '/' in source else ''
        joined = '/'.join(part for part in (folder + '/' + reference).split('/') if part not in ('', '.'))
        segments = []
        for part in joined.split('/'):
            if part == '..':
                if segments:
                    segments.pop()
            else:
                segments.append(part)
        stem = '/'.join(segments)
        for candidate in [stem] + [stem + ext for ext in ('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs')] + [stem + '/index.js', stem + '/index.ts']:
            if candidate in paths:
                return candidate
        return None

    seen_edges: dict[tuple[str, str], Edge] = {}
    for rel, text in texts.items():
        suffix = Path(rel).suffix.lower()
        if suffix == '.py':
            own_package = rel.rsplit('/', 1)[0].split('/') if '/' in rel else []
            for number, line in enumerate(text.splitlines(), 1):
                targets = []
                plain = re.match(r'\s*import\s+(.+)$', line)
                from_match = re.match(r'\s*from\s+(\.*)([A-Za-z_][\w.]*)?\s+import\s+(.+)$', line)
                if from_match:
                    level = len(from_match.group(1))
                    module = from_match.group(2) or ''
                    if level:
                        base = own_package[:len(own_package) - (level - 1)] if level - 1 <= len(own_package) else []
                        resolved = resolve_python(module, base) if module else None
                        if resolved:
                            targets.append(resolved)
                        for imported in re.findall(r'[A-Za-z_]\w*', from_match.group(3)):
                            candidate = resolve_python(f'{module}.{imported}' if module else imported, base)
                            if candidate:
                                targets.append(candidate)
                    else:
                        resolved = resolve_python(module, [])
                        if resolved:
                            targets.append(resolved)
                        for imported in re.findall(r'[A-Za-z_]\w*', from_match.group(3)):
                            candidate = resolve_python(f'{module}.{imported}', [])
                            if candidate:
                                targets.append(candidate)
                elif plain:
                    for token in plain.group(1).split(','):
                        module = token.strip().split(' ')[0]
                        if module:
                            resolved = resolve_python(module, [])
                            if resolved:
                                targets.append(resolved)
                for target in targets:
                    if target != rel and (rel, target) not in seen_edges:
                        seen_edges[(rel, target)] = Edge(rel, target, 'python-import', number)
        elif suffix in {'.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs'}:
            for number, line in enumerate(text.splitlines(), 1):
                for reference in re.findall(r"(?:from\s+|require\(\s*|import\(\s*)['\"](\.[^'\"]+)['\"]", line):
                    target = resolve_relative(rel, reference)
                    if target and target != rel and (rel, target) not in seen_edges:
                        seen_edges[(rel, target)] = Edge(rel, target, 'script-import', number)
        if len(seen_edges) >= 2000:
            break
    report.edges = sorted(seen_edges.values(), key=lambda e: (e.source, e.target))[:2000]
    if len(seen_edges) >= 2000:
        report.warnings.append('Internal dependency edge list stopped at 2,000 edges; the graph is incomplete.')

    # License-text checks: advisories from the fingerprint matches above.
    for detection in report.license_detections:
        if detection.spdx == 'Unknown':
            add('License', 'License text was not recognized', detection.file,
                '\n'.join(texts.get(detection.file, '').splitlines()[:8]),
                'Read the full license text and identify it manually. Do not assume terms from the file name; an unrecognized text can be anything, including all-rights-reserved.', 'Review', 'Heuristic')
        elif detection.spdx in COPYLEFT:
            add('License', f'Copyleft license terms detected: {detection.spdx}', detection.file,
                f'License text matches the fingerprint phrase "{detection.phrase}".',
                'Review the copyleft obligations (source disclosure, same-license distribution) against the intended use before adopting or redistributing. This is a text match, not a legal determination.', 'Info', 'Heuristic')
    known = [d for d in report.license_detections if d.spdx != 'Unknown']
    for value, manifest in declared:
        if known and not any(declared_matches(value, d.spdx) for d in known):
            add('License', 'Declared license does not match the license text', manifest,
                f'Declared: {value} ({manifest}); license text detected: {known[0].spdx} ({known[0].file})',
                'Decide which is authoritative, then correct the manifest or replace the license text deliberately. A mismatch means one of the two is misleading users and tooling.', 'Review', 'Heuristic', needle='license')

    if not report.licenses:
        add('License', 'No license file observed', evidence='No LICENSE* or COPYING* file was read within scan scope.',
            action='Check README, source headers and upstream history. Establish permission before redistributing; absence of a file is not a license determination.', severity='Review')
    if not any(Path(p).name.lower().startswith('readme') for p in paths):
        add('Documentation', 'No README observed', evidence='No README* file found within scan scope.',
            action='Record purpose, build prerequisites, platform support and a minimal working example.')
    if not any(p.startswith('.github/workflows/') for p in paths):
        add('Automation', 'No GitHub Actions workflow observed', evidence='No .github/workflows files found within scan scope.',
            action='Inspect other CI providers. Capture a baseline build and test command before adding automation.', severity='Info')
    add('Validation', 'Establish a reproducible build baseline', evidence='Static scan only; no build or test was executed.',
        action='Review code and build scripts, choose an isolated environment, then record exact tool versions, commands, exit codes and test evidence.')
    report.ecosystems = sorted(set(report.ecosystems + [
        ('C++ / MSBuild' if m.endswith('.vcxproj') else '.NET' if m.endswith('.csproj') else 'Python' if Path(m).name in {'pyproject.toml','setup.py','requirements.txt'} else 'Node.js' if Path(m).name == 'package.json' else 'Rust' if Path(m).name == 'Cargo.toml' else 'Go' if Path(m).name == 'go.mod' else 'CMake / C++')
        for m in report.manifests if Path(m).name in {'pyproject.toml','setup.py','requirements.txt','package.json','Cargo.toml','go.mod','CMakeLists.txt'} or m.endswith(('.csproj','.vcxproj'))]))
    report.findings.sort(key=lambda f: ({'Review':0,'Info':1}.get(f.severity,2), f.category, f.file, f.title))
    return report

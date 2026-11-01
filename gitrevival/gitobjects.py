"""Git object forensics: read-only parsing of a repository's .git folder.

Finds work Git considers lost — dangling commits, blobs and trees that no
ref, reflog or index entry reaches — plus reflog history and staged index
entries (including partial recovery from a damaged index). Everything is
parsed directly (loose objects and packfiles); no git program is run and
nothing in the repository is modified. Recovery writes go to a separate
output folder, file by file, via a temporary file renamed into place, and
existing files are never overwritten.

Bounds: at most MAX_OBJECTS objects are catalogued, one decompressed
object is at most MAX_OBJECT_BYTES, delta chains are at most MAX_DELTA_DEPTH
deep, and one recovery writes at most MAX_RECOVER_FILES files /
MAX_RECOVER_BYTES in total. Anything past a bound is reported as a warning,
never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import os
import re
import struct
import zlib

MAX_OBJECTS = 50_000
MAX_OBJECT_BYTES = 33_554_432
MAX_DELTA_DEPTH = 64
MAX_RECOVER_FILES = 10_000
MAX_RECOVER_BYTES = 268_435_456
TYPES = {1: 'commit', 2: 'tree', 3: 'blob', 4: 'tag'}


class GitError(ValueError):
    pass


def find_git_dir(root):
    """Return the .git directory for a worktree root, or None."""
    dot = Path(root) / '.git'
    if dot.is_dir():
        return dot
    if dot.is_file():
        text = dot.read_text(encoding='utf-8', errors='replace').strip()
        if text.startswith('gitdir:'):
            target = Path(text[7:].strip())
            return target if target.is_absolute() else (Path(root) / target).resolve()
    return None


def _inflate(data, limit=MAX_OBJECT_BYTES):
    obj = zlib.decompressobj()
    out = obj.decompress(data, limit + 1)
    if len(out) > limit:
        raise GitError(f'Object exceeds {limit} bytes when decompressed')
    return out


class ObjectStore:
    """Loose + packed objects of one .git directory, read-only."""

    def __init__(self, git_dir):
        self.git_dir = Path(git_dir)
        self.objects_dir = self.git_dir / 'objects'
        self.warnings = []
        self._loose = {}
        self._packs = []  # (idx_bytes, pack_path, [sha,...], [offset,...])
        self._cache = {}
        self._catalogue()

    def _catalogue(self):
        if self.objects_dir.is_dir():
            for fanout in sorted(self.objects_dir.iterdir()):
                if len(fanout.name) == 2 and all(c in '0123456789abcdef' for c in fanout.name) and fanout.is_dir():
                    for entry in sorted(fanout.iterdir()):
                        if len(entry.name) == 38 and all(c in '0123456789abcdef' for c in entry.name):
                            self._loose[fanout.name + entry.name] = entry
                if len(self._loose) >= MAX_OBJECTS:
                    self.warnings.append(f'Loose object catalogue stopped at {MAX_OBJECTS:,} objects.')
                    break
        pack_dir = self.objects_dir / 'pack'
        if pack_dir.is_dir():
            for idx_path in sorted(pack_dir.glob('*.idx')):
                try:
                    self._packs.append(self._read_idx(idx_path))
                except (OSError, GitError, struct.error) as exc:
                    self.warnings.append(f'Pack index unreadable: {idx_path.name} ({exc.__class__.__name__})')
        total = len(self._loose) + sum(len(p[2]) for p in self._packs)
        if total > MAX_OBJECTS:
            self.warnings.append(f'Repository holds more than {MAX_OBJECTS:,} objects; results are partial.')

    def _read_idx(self, idx_path):
        data = idx_path.read_bytes()
        if len(data) < 8 + 256 * 4 or data[:4] != b'\xfftOc':
            raise GitError('not a version-2 pack index')
        version = struct.unpack('>I', data[4:8])[0]
        if version != 2:
            raise GitError(f'unsupported pack index version {version}')
        fanout = struct.unpack('>256I', data[8:8 + 256 * 4])
        count = fanout[255]
        base = 8 + 256 * 4
        shas = [data[base + i * 20: base + (i + 1) * 20].hex() for i in range(count)]
        off_base = base + count * 20 + count * 4
        offsets = []
        large_base = off_base + count * 4
        for i in range(count):
            raw = struct.unpack('>I', data[off_base + i * 4: off_base + i * 4 + 4])[0]
            if raw & 0x80000000:
                large_at = large_base + (raw & 0x7FFFFFFF) * 8
                raw = struct.unpack('>Q', data[large_at: large_at + 8])[0]
            offsets.append(raw)
        return (data, idx_path.with_suffix('.pack'), shas, offsets)

    def __contains__(self, sha):
        return sha in self._loose or any(sha in pack[2] for pack in self._packs)

    def shas(self):
        out = list(self._loose)
        for _, _, shas, _ in self._packs:
            out.extend(shas)
        return out

    def read(self, sha, _depth=0):
        """Return (type, bytes) for an object, resolving pack deltas."""
        if sha in self._cache:
            return self._cache[sha]
        if _depth > MAX_DELTA_DEPTH:
            raise GitError('Delta chain too deep')
        if sha in self._loose:
            raw = _inflate(self._loose[sha].read_bytes())
            header, _, payload = raw.partition(b'\0')
            kind = header.split(b' ')[0].decode('ascii', 'replace')
            result = (kind, payload)
        else:
            result = None
            for _, pack_path, shas, offsets in self._packs:
                if sha in shas:
                    result = self._read_packed(pack_path, offsets[shas.index(sha)], _depth)
                    break
            if result is None:
                raise GitError(f'Object not found: {sha}')
        if len(self._cache) < 4096:
            self._cache[sha] = result
        return result

    def _read_packed(self, pack_path, offset, depth):
        with pack_path.open('rb') as stream:
            stream.seek(offset)
            head = stream.read(1)[0]
            kind_num = (head >> 4) & 0x7
            size = head & 0x0F
            shift = 4
            while head & 0x80:
                head = stream.read(1)[0]
                size |= (head & 0x7F) << shift
                shift += 7
            if size > MAX_OBJECT_BYTES:
                raise GitError(f'Packed object exceeds {MAX_OBJECT_BYTES} bytes')
            if kind_num == 6:  # OFS_DELTA
                byte = stream.read(1)[0]
                base_offset = byte & 0x7F
                while byte & 0x80:
                    byte = stream.read(1)[0]
                    base_offset = ((base_offset + 1) << 7) | (byte & 0x7F)
                base = self._read_packed_at(stream, pack_path, offset - base_offset, depth + 1)
                return (base[0], _apply_delta(base[1], _inflate(stream.read(MAX_OBJECT_BYTES + 1_048_576), MAX_OBJECT_BYTES)))
            if kind_num == 7:  # REF_DELTA
                base_sha = stream.read(20).hex()
                base = self.read(base_sha, depth + 1)
                return (base[0], _apply_delta(base[1], _inflate(stream.read(MAX_OBJECT_BYTES + 1_048_576), MAX_OBJECT_BYTES)))
            payload = _inflate(stream.read(MAX_OBJECT_BYTES + 1_048_576), MAX_OBJECT_BYTES)
            return (TYPES[kind_num], payload)

    def _read_packed_at(self, stream, pack_path, offset, depth):
        return self._read_packed(pack_path, offset, depth)


def _apply_delta(base, delta):
    def varint(buf, pos):
        value = 0
        shift = 0
        while True:
            byte = buf[pos]
            pos += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value, pos
    source_size, pos = varint(delta, 0)
    if source_size != len(base):
        raise GitError('Delta base size mismatch')
    target_size, pos = varint(delta, pos)
    if target_size > MAX_OBJECT_BYTES:
        raise GitError('Delta result exceeds size bound')
    out = bytearray()
    while pos < len(delta):
        op = delta[pos]
        pos += 1
        if op & 0x80:
            copy_offset = 0
            copy_size = 0
            for i in range(4):
                if op & (1 << i):
                    copy_offset |= delta[pos] << (8 * i)
                    pos += 1
            for i in range(3):
                if op & (0x10 << i):
                    copy_size |= delta[pos] << (8 * i)
                    pos += 1
            if copy_size == 0:
                copy_size = 0x10000
            out += base[copy_offset: copy_offset + copy_size]
        elif op:
            out += delta[pos: pos + op]
            pos += op
        else:
            raise GitError('Delta opcode 0 is invalid')
    if len(out) != target_size:
        raise GitError('Delta result size mismatch')
    return bytes(out)


def parse_commit(payload):
    headers, _, message = payload.partition(b'\n\n')
    result = {'tree': '', 'parents': [], 'author': '', 'committer_date': '', 'summary': ''}
    for line in headers.split(b'\n'):
        if line.startswith(b'tree '):
            result['tree'] = line[5:].decode('ascii', 'replace').strip()
        elif line.startswith(b'parent '):
            result['parents'].append(line[7:].decode('ascii', 'replace').strip())
        elif line.startswith(b'author '):
            result['author'] = line[7:].decode('utf-8', 'replace').strip()
        elif line.startswith(b'committer '):
            stamp = re.search(rb' (\d+) [+-]\d{4}$', line)
            if stamp:
                from datetime import datetime, timezone
                result['committer_date'] = datetime.fromtimestamp(int(stamp.group(1)), timezone.utc).isoformat()
    result['summary'] = message.decode('utf-8', 'replace').strip().splitlines()[0] if message.strip() else ''
    return result


def parse_tree(payload):
    entries = []
    pos = 0
    while pos < len(payload):
        space = payload.index(b' ', pos)
        mode = payload[pos:space].decode('ascii')
        nul = payload.index(b'\0', space)
        name = payload[space + 1: nul].decode('utf-8', 'replace')
        sha = payload[nul + 1: nul + 21].hex()
        entries.append((mode, name, sha))
        pos = nul + 21
    return entries


def read_refs(git_dir):
    """All ref tips: HEAD, loose refs and packed refs."""
    git_dir = Path(git_dir)
    refs = {}
    head = git_dir / 'HEAD'
    if head.is_file():
        text = head.read_text(encoding='utf-8', errors='replace').strip()
        if text.startswith('ref:'):
            refs['HEAD'] = text[4:].strip()
        elif re.fullmatch(r'[0-9a-f]{40}', text):
            refs['HEAD'] = text
    refs_dir = git_dir / 'refs'
    if refs_dir.is_dir():
        for path in refs_dir.rglob('*'):
            if path.is_file():
                value = path.read_text(encoding='utf-8', errors='replace').strip()
                if re.fullmatch(r'[0-9a-f]{40}', value):
                    refs[path.relative_to(git_dir).as_posix()] = value
    packed = git_dir / 'packed-refs'
    if packed.is_file():
        for line in packed.read_text(encoding='utf-8', errors='replace').splitlines():
            if line and not line.startswith(('#', '^')):
                sha, _, name = line.partition(' ')
                if re.fullmatch(r'[0-9a-f]{40}', sha.strip()):
                    refs.setdefault(name.strip(), sha.strip())
    return refs


def read_reflogs(git_dir):
    """Reflog entries across HEAD and all refs, oldest file order kept."""
    git_dir = Path(git_dir)
    entries = []
    logs_dir = git_dir / 'logs'
    files = []
    if (logs_dir / 'HEAD').is_file():
        files.append(logs_dir / 'HEAD')
    refs_logs = logs_dir / 'refs'
    if refs_logs.is_dir():
        files += sorted(p for p in refs_logs.rglob('*') if p.is_file())
    pattern = re.compile(r'^([0-9a-f]{40}) ([0-9a-f]{40}) (.*?) (\d+) [+-]\d{4}\t?(.*)$')
    for path in files:
        ref = path.relative_to(git_dir / 'logs').as_posix()
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            match = pattern.match(line)
            if match:
                from datetime import datetime, timezone
                entries.append({'ref': ref, 'old': match.group(1), 'new': match.group(2),
                                'who': match.group(3), 'at': datetime.fromtimestamp(int(match.group(4)), timezone.utc).isoformat(),
                                'message': match.group(5)})
    return entries


def read_index(git_dir):
    """Parse .git/index (versions 2, 3 and 4).

    A damaged or truncated index yields the entries recovered before the
    damage, with `damaged` set — a partial answer, never a silent one.
    """
    path = Path(git_dir) / 'index'
    result = {'exists': path.is_file(), 'version': 0, 'entries': [], 'damaged': False, 'error': ''}
    if not path.is_file():
        return result
    data = path.read_bytes()
    try:
        if len(data) < 12 or data[:4] != b'DIRC':
            raise GitError('index header missing or not DIRC')
        version, count = struct.unpack('>II', data[4:12])
        result['version'] = version
        if version not in (2, 3, 4):
            raise GitError(f'unsupported index version {version}')
        pos = 12
        previous = ''
        for _ in range(count):
            start = pos
            if version == 4:
                # Fixed fields come first (sha at +40, flags at +60), then a
                # prefix-compression varint and a NUL-terminated name suffix.
                if pos + 62 > len(data):
                    raise GitError('index entry truncated')
                sha = data[start + 40: start + 60].hex()
                flags = struct.unpack('>H', data[start + 60: start + 62])[0]
                strip, after_varint = _index_varint(data, start + 62)
                suffix, end = _read_cstring(data, after_varint)
                name = previous[:len(previous) - strip] + suffix
                previous = name
                pos = end
                result['entries'].append({'path': name, 'sha': sha, 'stage': (flags >> 12) & 0x3})
            else:
                if pos + 62 > len(data):
                    raise GitError('index entry truncated')
                sha = data[pos + 40: pos + 60].hex()
                flags = struct.unpack('>H', data[pos + 60: pos + 62])[0]
                size = 62
                if version == 3 and flags & 0x4000:
                    size = 64
                name_length = flags & 0x0FFF
                name_start = pos + size
                if name_length < 0x0FFF:
                    name = data[name_start: name_start + name_length].decode('utf-8', 'replace')
                    entry_length = (size + name_length + 8) // 8 * 8
                else:
                    end = data.index(b'\0', name_start)
                    name = data[name_start: end].decode('utf-8', 'replace')
                    entry_length = (size + (end - name_start) + 8) // 8 * 8
                result['entries'].append({'path': name, 'sha': sha, 'stage': (flags >> 12) & 0x3})
                pos = start + entry_length
    except (GitError, struct.error, IndexError, ValueError) as exc:
        result['damaged'] = True
        result['error'] = f'{exc.__class__.__name__}: {exc}'
    return result


def _index_varint(data, pos):
    byte = data[pos]
    pos += 1
    value = byte & 0x7F
    while byte & 0x80:
        byte = data[pos]
        pos += 1
        value = ((value + 1) << 7) | (byte & 0x7F)
    return value, pos


def _read_cstring(data, pos):
    end = data.index(b'\0', pos)
    return data[pos:end].decode('utf-8', 'replace'), end + 1


@dataclass
class GitForensics:
    present: bool = False
    git_dir: str = ''
    objects_total: int = 0
    objects_by_type: dict = field(default_factory=dict)
    reachable: int = 0
    dangling_commits: list = field(default_factory=list)
    dangling_trees: int = 0
    dangling_blobs: int = 0
    reflog_entries: int = 0
    reflog_recent: list = field(default_factory=list)
    index: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def scan_git(root):
    """Full forensic pass over one repository root. Read-only."""
    report = GitForensics()
    git_dir = find_git_dir(root)
    if git_dir is None or not (git_dir / 'objects').is_dir():
        return report
    report.present = True
    report.git_dir = str(git_dir)
    store = ObjectStore(git_dir)
    report.warnings.extend(store.warnings)
    refs = read_refs(git_dir)
    reflogs = read_reflogs(git_dir)
    report.reflog_entries = len(reflogs)
    report.reflog_recent = reflogs[-10:][::-1]
    index = read_index(git_dir)
    report.index = {'exists': index['exists'], 'version': index['version'],
                    'entries': len(index['entries']), 'damaged': index['damaged'], 'error': index['error']}
    if index['damaged']:
        report.warnings.append(f"Index is damaged; recovered {len(index['entries'])} entries before the damage ({index['error']}).")

    roots = set()
    for value in refs.values():
        if re.fullmatch(r'[0-9a-f]{40}', value or ''):
            roots.add(value)
        elif value in refs:
            roots.add(refs[value])
    head_target = refs.get('HEAD')
    if head_target and re.fullmatch(r'[0-9a-f]{40}', head_target):
        roots.add(head_target)
    for entry in reflogs:
        roots.add(entry['old'])
        roots.add(entry['new'])
    for entry in index['entries']:
        roots.add(entry['sha'])
    roots.discard('0' * 40)

    reachable = set()
    stack = [sha for sha in roots if sha in store]
    while stack:
        sha = stack.pop()
        if sha in reachable:
            continue
        reachable.add(sha)
        try:
            kind, payload = store.read(sha)
        except (GitError, OSError, zlib.error):
            continue
        if kind == 'commit':
            parsed = parse_commit(payload)
            if parsed['tree']:
                stack.append(parsed['tree'])
            stack.extend(parsed['parents'])
        elif kind == 'tree':
            try:
                stack.extend(entry_sha for _, _, entry_sha in parse_tree(payload))
            except (IndexError, ValueError):
                report.warnings.append(f'Tree object {sha[:10]} could not be parsed.')
        elif kind == 'tag':
            match = re.search(rb'object ([0-9a-f]{40})', payload)
            if match:
                stack.append(match.group(1).decode())
    report.reachable = len(reachable)

    all_shas = store.shas()
    report.objects_total = len(all_shas)
    dangling = []
    for sha in all_shas:
        try:
            kind, payload = store.read(sha)
        except (GitError, OSError, zlib.error):
            report.warnings.append(f'Object {sha[:10]} could not be read (corrupt or unsupported).')
            continue
        report.objects_by_type[kind] = report.objects_by_type.get(kind, 0) + 1
        if sha not in reachable:
            dangling.append((sha, kind, payload))
    for sha, kind, payload in dangling:
        if kind == 'commit':
            parsed = parse_commit(payload)
            report.dangling_commits.append({'sha': sha, 'summary': parsed['summary'], 'author': parsed['author'],
                                            'date': parsed['committer_date'], 'tree': parsed['tree'],
                                            'parents': parsed['parents']})
        elif kind == 'tree':
            report.dangling_trees += 1
        elif kind == 'blob':
            report.dangling_blobs += 1
    report.dangling_commits.sort(key=lambda c: c['date'] or '', reverse=True)
    return report


def recover_commit(root, commit_sha, output):
    """Rebuild a commit's tree into `output`. Never overwrites a file.

    Every file is written to a temporary name in its destination folder and
    renamed into place only when the destination does not exist, so a
    recovery can never clobber work already on disk. Returns a summary dict.
    """
    git_dir = find_git_dir(root)
    if git_dir is None:
        raise GitError('No .git directory found.')
    store = ObjectStore(git_dir)
    kind, payload = store.read(commit_sha)
    if kind != 'commit':
        raise GitError(f'Object {commit_sha[:10]} is a {kind}, not a commit.')
    tree_sha = parse_commit(payload)['tree']
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {'commit': commit_sha, 'written': [], 'skipped_existing': [], 'skipped_other': [], 'bytes': 0}

    def write_file(relative, data, executable):
        if len(summary['written']) >= MAX_RECOVER_FILES:
            summary['skipped_other'].append(f'{relative} (file bound reached)')
            return
        if summary['bytes'] + len(data) > MAX_RECOVER_BYTES:
            summary['skipped_other'].append(f'{relative} (byte bound reached)')
            return
        target = output / relative
        if target.exists() or target.is_symlink():
            summary['skipped_existing'].append(relative)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f'.gitrevival-tmp-{os.getpid()}')
        try:
            with temporary.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists():
                temporary.unlink()
                summary['skipped_existing'].append(relative)
                return
            os.replace(temporary, target)
        except OSError:
            if temporary.exists():
                temporary.unlink()
            raise
        if executable:
            try:
                os.chmod(target, 0o755)
            except OSError:
                pass
        summary['written'].append(relative)
        summary['bytes'] += len(data)

    def walk(tree, prefix):
        kind, payload = store.read(tree)
        if kind != 'tree':
            raise GitError('Commit tree reference is not a tree.')
        for mode, name, sha in parse_tree(payload):
            relative = f'{prefix}{name}'
            if mode == '40000':
                walk(sha, relative + '/')
            elif mode in ('100644', '100755'):
                _, blob = store.read(sha)
                write_file(relative, blob, mode == '100755')
            elif mode == '120000':
                _, blob = store.read(sha)
                write_file(relative + '.symlink-target.txt', blob, False)
                summary['skipped_other'].append(f'{relative} (symlink recorded as .symlink-target.txt)')
            else:
                summary['skipped_other'].append(f'{relative} (mode {mode} not recovered)')

    walk(tree_sha, '')
    return summary


def object_id(kind, payload):
    """The git object id for content — used by tests and fixtures."""
    return hashlib.sha1(f'{kind} {len(payload)}\0'.encode() + payload).hexdigest()

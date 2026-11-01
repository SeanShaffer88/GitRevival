"""0.7.0 Git forensics: hand-built .git fixtures (no git program needed).

Objects, packfiles, reflogs and index files are constructed byte by byte
so the parsers are tested against the formats themselves.
"""
import json
import struct
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitrevival.gitobjects import (ObjectStore, _apply_delta, object_id,
                                   read_index, recover_commit, scan_git)


def loose(git_dir, kind, payload):
    sha = object_id(kind, payload)
    path = Path(git_dir) / 'objects' / sha[:2] / sha[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(f'{kind} {len(payload)}\0'.encode() + payload))
    return sha


def tree_payload(entries):
    out = b''
    for mode, name, sha in entries:
        out += f'{mode} {name}\0'.encode() + bytes.fromhex(sha)
    return out


def commit_payload(tree, parents=(), message=b'Work', stamp=1700000000):
    lines = [f'tree {tree}']
    lines += [f'parent {p}' for p in parents]
    lines += [f'author A U Thor <a@example.com> {stamp} +0000',
              f'committer A U Thor <a@example.com> {stamp} +0000']
    return ('\n'.join(lines) + '\n\n').encode() + message + b'\n'


def varint_type_size(kind_num, size):
    out = bytearray()
    first = (kind_num << 4) | (size & 0x0F)
    size >>= 4
    if size:
        first |= 0x80
    out.append(first)
    while size:
        byte = size & 0x7F
        size >>= 7
        if size:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def build_pack(git_dir, objects):
    """objects: list of (sha, kind_num, raw_entry_bytes_after_header, payload).

    Returns nothing; writes .idx v2 + .pack with correct fanout/offsets.
    """
    pack = bytearray(b'PACK' + struct.pack('>II', 2, len(objects)))
    offsets = {}
    for sha, kind_num, entry, payload in objects:
        offsets[sha] = len(pack)
        pack += entry
    pack += bytes.fromhex(object_id('blob', b''))[:0]  # no-op clarity
    import hashlib
    pack_checksum = hashlib.sha1(bytes(pack)).digest()
    pack += pack_checksum
    ordered = sorted(offsets)
    fanout = []
    running = 0
    by_first = {}
    for sha in ordered:
        by_first[sha[:2]] = by_first.get(sha[:2], 0) + 1
    for i in range(256):
        running += by_first.get(f'{i:02x}', 0)
        fanout.append(running)
    idx = bytearray(b'\xfftOc' + struct.pack('>I', 2))
    idx += struct.pack('>256I', *fanout)
    for sha in ordered:
        idx += bytes.fromhex(sha)
    for sha in ordered:
        idx += struct.pack('>I', 0)  # crc32 (parser does not verify)
    for sha in ordered:
        idx += struct.pack('>I', offsets[sha])
    idx += pack_checksum
    idx += hashlib.sha1(bytes(idx)).digest()
    pack_dir = Path(git_dir) / 'objects' / 'pack'
    pack_dir.mkdir(parents=True, exist_ok=True)
    name = 'pack-' + ordered[0][:16]
    (pack_dir / f'{name}.pack').write_bytes(bytes(pack))
    (pack_dir / f'{name}.idx').write_bytes(bytes(idx))


def index_entry(name, sha, stage=0):
    fixed = struct.pack('>II', 1700000000, 0) * 2  # ctime, mtime
    fixed += struct.pack('>IIIIII', 1, 1, 0o100644, 0, 0, 5)
    fixed += bytes.fromhex(sha)
    flags = (stage << 12) | len(name)
    fixed += struct.pack('>H', flags)
    entry = fixed + name.encode()
    padding = (8 - len(entry) % 8) % 8
    return entry + b'\0' * padding


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git = self.root / '.git'
        (self.git / 'refs' / 'heads').mkdir(parents=True)
        (self.git / 'logs' / 'refs' / 'heads').mkdir(parents=True)
        (self.git / 'objects').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def basic_history(self):
        blob = loose(self.git, 'blob', b'hello world')
        tree = loose(self.git, 'tree', tree_payload([('100644', 'file.txt', blob)]))
        commit = loose(self.git, 'commit', commit_payload(tree, message=b'First commit'))
        (self.git / 'refs' / 'heads' / 'main').write_text(commit + '\n')
        (self.git / 'HEAD').write_text('ref: refs/heads/main\n')
        return blob, tree, commit


class ObjectStoreTests(GitFixture):
    def test_loose_objects_and_dangling_detection(self):
        blob, tree, commit = self.basic_history()
        lost_blob = loose(self.git, 'blob', b'lost work')
        lost_tree = loose(self.git, 'tree', tree_payload([('100644', 'lost.txt', lost_blob)]))
        lost_commit = loose(self.git, 'commit', commit_payload(lost_tree, parents=[commit], message=b'Lost commit', stamp=1700003600))
        report = scan_git(self.root)
        self.assertTrue(report.present)
        self.assertEqual([c['sha'] for c in report.dangling_commits], [lost_commit])
        self.assertEqual(report.dangling_commits[0]['summary'], 'Lost commit')
        self.assertEqual(report.dangling_blobs, 1)
        self.assertEqual(report.dangling_trees, 1)
        self.assertGreaterEqual(report.reachable, 3)

    def test_reflog_rescues_a_commit(self):
        blob, tree, commit = self.basic_history()
        rescued_tree = loose(self.git, 'tree', tree_payload([('100644', 'rescued.txt', blob)]))
        rescued = loose(self.git, 'commit', commit_payload(rescued_tree, parents=[commit], message=b'Rescued by reflog'))
        line = f"{commit} {rescued} A U Thor <a@example.com> 1700007200 +0000\tcommit: Rescued by reflog\n"
        (self.git / 'logs' / 'HEAD').write_text(line)
        (self.git / 'logs' / 'refs' / 'heads' / 'main').write_text(line)
        report = scan_git(self.root)
        self.assertEqual(report.dangling_commits, [])
        self.assertEqual(report.reflog_entries, 2)
        self.assertEqual(report.reflog_recent[0]['new'], rescued)

    def test_packfile_objects_and_ofs_delta(self):
        base_payload = b'hello world, packed'
        base_sha = object_id('blob', base_payload)
        delta = bytearray()
        delta += bytes([len(base_payload)])          # source size (single-byte varint)
        delta += bytes([5])                            # target size
        delta += bytes([5]) + b'hello'                 # insert op
        delta = bytes(delta)
        entries = []
        base_entry = varint_type_size(3, len(base_payload)) + zlib.compress(base_payload)
        entries.append((base_sha, 3, base_entry, base_payload))
        pack_header = 12
        base_offset = pack_header
        delta_offset = pack_header + len(base_entry)
        ofs = delta_offset - base_offset
        encoded = bytearray([ofs & 0x7F])
        rest = ofs >> 7
        while rest:
            rest -= 1
            encoded.insert(0, 0x80 | (rest & 0x7F))
            rest >>= 7
        delta_sha = object_id('blob', b'hello')
        delta_entry = varint_type_size(6, len(delta)) + bytes(encoded) + zlib.compress(delta)
        entries.append((delta_sha, 6, delta_entry, b'hello'))
        build_pack(self.git, entries)
        store = ObjectStore(self.git)
        self.assertEqual(store.read(base_sha), ('blob', base_payload))
        self.assertEqual(store.read(delta_sha), ('blob', b'hello'))

    def test_apply_delta_copy_op(self):
        base = b'hello world'
        delta = bytes([11, 5, 0x90, 5])  # base 11 bytes, target 5, copy op (size byte follows): copy 5 from offset 0
        self.assertEqual(_apply_delta(base, delta), b'hello')


class IndexTests(GitFixture):
    def test_index_v2_entries(self):
        blob, _, _ = self.basic_history()
        data = b'DIRC' + struct.pack('>II', 2, 2)
        data += index_entry('file.txt', blob)
        data += index_entry('sub/other.txt', blob)
        (self.git / 'index').write_bytes(data)
        result = read_index(self.git)
        self.assertFalse(result['damaged'])
        self.assertEqual([e['path'] for e in result['entries']], ['file.txt', 'sub/other.txt'])
        self.assertEqual(result['entries'][0]['sha'], blob)

    def test_damaged_index_recovers_partial_entries(self):
        blob, _, _ = self.basic_history()
        data = b'DIRC' + struct.pack('>II', 2, 2)
        data += index_entry('kept.txt', blob)
        data += index_entry('gone.txt', blob)[:20]  # truncated mid-entry
        (self.git / 'index').write_bytes(data)
        result = read_index(self.git)
        self.assertTrue(result['damaged'])
        self.assertEqual([e['path'] for e in result['entries']], ['kept.txt'])
        report = scan_git(self.root)
        self.assertTrue(report.index['damaged'])
        self.assertTrue(any('Index is damaged' in w for w in report.warnings))


class RecoveryTests(GitFixture):
    def test_recover_commit_never_overwrites(self):
        blob, tree, commit = self.basic_history()
        deep_blob = loose(self.git, 'blob', b'deep content')
        sub_tree = loose(self.git, 'tree', tree_payload([('100644', 'deep.txt', deep_blob)]))
        full_tree = loose(self.git, 'tree', tree_payload([('100644', 'file.txt', blob), ('40000', 'sub', sub_tree)]))
        full_commit = loose(self.git, 'commit', commit_payload(full_tree, message=b'Full'))
        out = self.root / 'recovered'
        out.mkdir()
        (out / 'file.txt').write_text('MY EXISTING WORK', encoding='utf-8')
        summary = recover_commit(self.root, full_commit, out)
        self.assertEqual((out / 'file.txt').read_text(encoding='utf-8'), 'MY EXISTING WORK')
        self.assertIn('file.txt', summary['skipped_existing'])
        self.assertEqual((out / 'sub' / 'deep.txt').read_bytes(), b'deep content')
        self.assertIn('sub/deep.txt', summary['written'])
        self.assertFalse(list(out.rglob('*.gitrevival-tmp-*')))

    def test_cli_git_scan_and_recover(self):
        blob, tree, commit = self.basic_history()
        lost_blob = loose(self.git, 'blob', b'salvage me')
        lost_tree = loose(self.git, 'tree', tree_payload([('100644', 'lost.txt', lost_blob)]))
        lost_commit = loose(self.git, 'commit', commit_payload(lost_tree, parents=[commit], message=b'Salvage'))
        scan = subprocess.run([sys.executable, '-m', 'gitrevival.cli', 'git-scan', str(self.root)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        payload = json.loads(scan.stdout)
        self.assertEqual(payload['dangling_commits'][0]['sha'], lost_commit)
        out = self.root / 'out'
        rec = subprocess.run([sys.executable, '-m', 'gitrevival.cli', 'git-recover', str(self.root), lost_commit, '--output', str(out)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(rec.returncode, 0, rec.stderr)
        self.assertEqual((out / 'lost.txt').read_bytes(), b'salvage me')
        missing = subprocess.run([sys.executable, '-m', 'gitrevival.cli', 'git-scan', str(self.root / 'nope')],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(missing.returncode, 2)


if __name__ == '__main__':
    unittest.main()


class RecoveryTabTests(GitFixture):
    def test_tab_scans_and_lists_dangling_commit(self):
        from gitrevival.app import App
        blob, tree, commit = self.basic_history()
        lost_blob = loose(self.git, 'blob', b'salvage me')
        lost_tree = loose(self.git, 'tree', tree_payload([('100644', 'lost.txt', lost_blob)]))
        lost_commit = loose(self.git, 'commit', commit_payload(lost_tree, parents=[commit], message=b'Salvage'))
        app = App(self.root.parent / 'ws.sqlite3')
        app.withdraw()
        root = app
        try:
            from gitrevival.analyzer import inspect
            app.report = inspect(self.root)
            tab_titles = [app.tabs.tab(i, 'text') for i in range(len(app.tabs.tabs()))]
            self.assertIn('Git recovery (advanced)', tab_titles)
            app.recovery.scan()
            deadline = time.time() + 10
            while time.time() < deadline and not app.recovery.tree.get_children():
                root.update(); time.sleep(0.05)
            rows = app.recovery.tree.get_children()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], lost_commit)
        finally:
            app.store.close(); app.destroy()

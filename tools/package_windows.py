"""Package tracked sources with a local CPython 3.15.1 x64 runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = 'GitRevival-0.3.0-win-x64'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    runtime = args.python_root.resolve()
    version = subprocess.check_output([str(runtime/'python.exe'), '-I', '-c',
        'import sys,struct; assert sys.version_info[:3]==(3,15,1) and struct.calcsize("P")==8; print(sys.version)'], text=True).strip()
    package = args.output.resolve()/NAME
    package.mkdir(parents=True, exist_ok=False)
    tracked = subprocess.check_output(['git','ls-files','-z'], cwd=ROOT).decode().split('\0')
    for relative in filter(None, tracked):
        path = Path(relative)
        if '.local' in path.parts or '__pycache__' in path.parts or '.git' in path.parts or path.suffix in ('.pyc','.zip'):
            raise RuntimeError('Unexpected tracked private/generated file')
        target = package/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/path,target)
    destination = package/'runtime'
    destination.mkdir()
    for name in ('python.exe','pythonw.exe','python315.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(runtime/name,destination/name)
    for name in ('Lib','DLLs','tcl'):
        shutil.copytree(runtime/name,destination/name,
            ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','*.pdb','test','tests','idlelib','ensurepip','_test*','_ctypes_test*','demos','*.lib','*.cat'))
    # Isolate imports from the registry, environment and user site packages.
    (destination/'python315._pth').write_text('.\nLib\nDLLs\n..\n',encoding='ascii')
    (package/'Start GitRevival.bat').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0runtime\\pythonw.exe" -B "%~dp0launch.pyw" %*\r\n')
    (package/'GitRevival CLI.bat').write_bytes(b'@echo off\r\n"%~dp0runtime\\python.exe" -B -m gitrevival.cli %*\r\n')
    (package/'PORTABLE.txt').write_text('GitRevival 0.3.0 Windows x64 portable\n\nExtract the entire ZIP into a writable folder. Run Start GitRevival.bat.\nNo installed Python is required. Data is saved beside the app in .local/workspace.sqlite3.\nTo upgrade, close the app, back up .local, then copy that folder into this new app folder.\nKeep notes, tokens and backups private. Never replace a live database.\n\nRuntime: CPython 3.15.1 x64 with Tcl/Tk 9.0.4. Interpreter binaries are unmodified.\nThis redistribution omits pip/site-packages, tests, IDLE, developer/import libraries and caches; a ._pth file isolates imports.\nApp source and third-party notices are included. See runtime/LICENSE.txt and licenses/runtime.\nNo GitRevival public Windows publisher trust is claimed. Upstream runtime signatures are retained.\n\nSource: https://github.com/SeanShaffer88/GitRevival\nPython: https://www.python.org/downloads/release/python-3151/\n',encoding='utf-8')
    identity = {'application':'GitRevival','version':'0.3.0','python':version,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'runtime_origin':'Existing unmodified CPython 3.15.1 Windows x64 distribution; hashes in SHA256.json',
        'checked_on':'2026-10-23'}
    (package/'package.json').write_text(json.dumps(identity,indent=2)+'\n')
    manifest = {p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(package.rglob('*')) if p.is_file()}
    (package/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Prepared:',package)


if __name__=='__main__': main()

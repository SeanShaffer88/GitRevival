"""Verify a relocated package without an installed Python on PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def verify(package):
    manifest = json.loads((package/'SHA256.json').read_text())
    for name,digest in manifest.items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest()==digest,name
    assert not (package/'.local').exists(), 'User workspace must not be packaged'
    results = []
    with tempfile.TemporaryDirectory(prefix='GitRevival release ') as tmp:
        for name in ('Space Path','Unicode Ω Path'):
            folder = Path(tmp)/name
            shutil.copytree(package,folder)
            env = {k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','TCL','TK','GITREVIVAL'))}
            env['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
            python = folder/'runtime/python.exe'
            subprocess.run([str(python),'-B','-c','import sys,sqlite3,ssl,tkinter; from pathlib import Path; assert sys.flags.isolated and sys.flags.no_user_site; assert all(not p or Path(p).resolve().is_relative_to(Path(sys.executable).resolve().parent.parent) for p in sys.path); t=tkinter.Tk(); t.update(); t.destroy()'],cwd=folder,env=env,check=True,timeout=20)
            subprocess.run([str(python),'-B','-m','unittest','discover','-s','tests','-v'],cwd=folder,env=env,check=True,timeout=90)
            scan=Path(tmp)/(name+'.json')
            subprocess.run([str(python),'-B','-m','gitrevival.cli','inspect',str(folder/'demo/old-orbit'),'--output',str(scan)],cwd=folder,env=env,check=True,timeout=20)
            assert json.loads(scan.read_text())['findings']
            process = subprocess.Popen([str(folder/'runtime/pythonw.exe'),'-B',str(folder/'launch.pyw')],cwd=folder,env=env)
            try:
                time.sleep(2)
                assert process.poll() is None,'GUI launcher exited'
                assert (folder/'.local/workspace.sqlite3').is_file()
            finally:
                if process.poll() is None: process.terminate()
                process.wait(timeout=10)
            results.append({'path':name,'isolated_runtime':True,'native_tk':True,'suite':'passed','headless_inspection':True,'launcher_alive':True})
    return {'manifest_files':len(manifest),'checks':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args()
    data=verify(args.package.resolve())
    args.results.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data))


if __name__=='__main__': main()

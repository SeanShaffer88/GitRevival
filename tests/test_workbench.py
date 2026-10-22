import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from gitrevival.analyzer import inspect, MAX_BYTES
from gitrevival.store import Store, restore, export_report

class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')
    def test_node_evidence_and_lockfile(self):
        self.put('package.json', '{\n"dependencies":{"old-pkg":"*"}\n}')
        first = inspect(self.root)
        finding = next(f for f in first.findings if 'reproducibility' in f.title)
        self.assertEqual(finding.line,2)
        self.assertEqual(first.dependencies[0].name,'old-pkg')
        self.assertTrue(any('lockfile' in f.title for f in first.findings))
        self.put('package-lock.json','{}')
        second = inspect(self.root)
        self.assertFalse(any('lockfile' in f.title for f in second.findings))
        self.assertIn(finding.id,[f.id for f in second.findings])
    def test_malformed_manifests_do_not_abort_scan(self):
        self.put('package.json','{"dependencies": [] invalid')
        self.put('pyproject.toml','[[invalid')
        self.put('broken.csproj','<Project>')
        report = inspect(self.root)
        self.assertEqual(sum(f.category=='Inspection' for f in report.findings),3)
        self.assertTrue(any(f.category=='Validation' for f in report.findings))
    def test_nested_manifests_and_xml_namespaces(self):
        self.put('src/app.csproj','<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><ItemGroup><PackageReference Include="Example" Version="2.0"/></ItemGroup><PropertyGroup><TargetFrameworkVersion>v4.0</TargetFrameworkVersion></PropertyGroup></Project>')
        self.put('native/CMakeLists.txt','cmake_minimum_required(VERSION 2.8)\nfind_package(Boost REQUIRED)')
        report = inspect(self.root)
        self.assertEqual({d.name for d in report.dependencies},{'Example','Boost'})
        self.assertTrue(any(f.file=='src/app.csproj' and 'target support' in f.title for f in report.findings))
    def test_python_rust_go(self):
        self.put('pyproject.toml','[project]\nrequires-python=">=3.11"\ndependencies=["example>=1"]')
        self.put('rust/Cargo.toml','[dependencies]\nexample-rs="1"')
        self.put('go/go.mod','module example.org/app\nrequire (\n example.org/pkg v1.2.0\n)')
        report = inspect(self.root)
        self.assertEqual(len(report.dependencies),3)
        self.assertTrue({'Python','Rust','Go'}.issubset(report.ecosystems))
    def test_exclusions_and_oversized_file(self):
        self.put('node_modules/bad/package.json','{}')
        self.put('.git/config','secret')
        self.put('LICENSE','x'*(MAX_BYTES+1))
        report = inspect(self.root)
        self.assertEqual(report.files,1)
        self.assertFalse(report.licenses)
        self.assertTrue(report.warnings)
    def test_file_budget_is_explicit(self):
        self.put('a.txt','a')
        self.put('b.txt','b')
        with patch('gitrevival.analyzer.MAX_FILES',1):
            report = inspect(self.root)
        self.assertEqual(report.files,1)
        self.assertTrue(any('incomplete' in w for w in report.warnings))
    def test_read_only_and_does_not_execute_setup(self):
        self.put('setup.py', "raise RuntimeError('MUST NEVER RUN')")
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        inspect(self.root)
        after = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as external:
            Path(external,'package.json').write_text('{}')
            try:
                (self.root/'linked').symlink_to(external,target_is_directory=True)
            except OSError:
                self.skipTest('Symlink creation unavailable')
            self.assertEqual(inspect(self.root).files,0)
    def test_license_presence_is_not_clearance(self):
        self.put('LICENSE','Example license text')
        report = inspect(self.root)
        self.assertEqual(report.licenses,['LICENSE'])
        self.assertTrue(any('third-party' in f.title for f in report.findings))
        self.assertFalse(any(f.title=='No license file observed' for f in report.findings))
    def test_store_roundtrip_export_and_rescan(self):
        report = inspect(self.root)
        dbpath = self.root/'state.sqlite3'
        store = Store(dbpath)
        store.save_report(report)
        finding = report.findings[0]
        store.save_task(report.root,finding.id,'In progress','Test evidence\nSecond line')
        store.close()
        store = Store(dbpath)
        loaded = restore(json.loads(store.projects()[0][2]))
        self.assertEqual(loaded.to_dict(),report.to_dict())
        self.assertEqual(store.task(report.root,finding.id)[0],'In progress')
        rescanned = inspect(self.root)
        store.save_report(rescanned)
        self.assertEqual(store.task(report.root,finding.id)[1],'Test evidence\nSecond line')
        export_report(report,store,self.root/'report.json')
        data = json.loads((self.root/'report.json').read_text())
        self.assertEqual(data['findings'][0]['status'],'In progress')
        export_report(report,store,self.root/'report.md')
        self.assertIn('Second line',(self.root/'report.md').read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            store.save_task(report.root,finding.id,'Invented','')
        store.close()
    def test_invalid_folder(self):
        with self.assertRaises(FileNotFoundError):
            inspect(self.root/'missing')

class GuiTests(unittest.TestCase):
    def test_gui_load_filter_save_map_export(self):
        from gitrevival.app import App
        with tempfile.TemporaryDirectory() as tmp:
            app = App(Path(tmp)/'state.sqlite3')
            try:
                app.update()
                demo = Path(__file__).resolve().parent.parent/'demo'/'old-orbit'
                report = inspect(demo)
                app.store.save_report(report)
                app.load(report)
                app.update()
                self.assertEqual(len(app.dependencies.get_children()),3)
                finding = report.findings[0]
                app.findings.selection_set(finding.id)
                app.show_finding()
                app.status_var.set('Done')
                app.notes.insert('1.0','GUI persistence evidence')
                app.save_task()
                self.assertEqual(app.store.task(report.root,finding.id),('Done','GUI persistence evidence'))
                app.search.set('lockfile')
                app.update()
                self.assertEqual(len(app.findings.get_children()),1)
                app.search.set('')
                app.map_filter('License')
                self.assertTrue(all(app.findings.item(i,'values')[1]=='License' for i in app.findings.get_children()))
                self.assertTrue(app.canvas.find_all())
                self.assertGreater(app.notes.winfo_height(),30)
                self.assertGreater(app.findings.winfo_height(),80)
                export_report(report,app.store,Path(tmp)/'gui-report.json')
                self.assertTrue((Path(tmp)/'gui-report.json').exists())
            finally:
                app.store.close()
                app.destroy()

if __name__ == '__main__':
    unittest.main()

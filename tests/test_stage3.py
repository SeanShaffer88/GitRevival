"""0.6.0 Stage 3: internal dependency edges, source navigation data and
license-text checks (fingerprints, declared-vs-detected, advisories)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from gitrevival.analyzer import inspect
from gitrevival.licenses import detect_license, declared_matches
from gitrevival.store import Store, restore

MIT_TEXT = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""

GPL_TEXT = """GNU GENERAL PUBLIC LICENSE
Version 3, 29 June 2007

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3 of the License.
"""


class Stage3Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


class DependencyEdgeTests(Stage3Fixture):
    def test_python_absolute_relative_and_from_imports(self):
        self.put('pkg/__init__.py', '')
        self.put('pkg/core.py', 'VALUE = 1\n')
        self.put('pkg/util.py', 'import pkg.core\nfrom . import core\nfrom pkg import core as c\n')
        self.put('main.py', 'from pkg.util import helper\nimport os\n')
        report = inspect(self.root)
        pairs = {(e.source, e.target) for e in report.edges}
        self.assertIn(('pkg/util.py', 'pkg/core.py'), pairs)
        self.assertIn(('main.py', 'pkg/util.py'), pairs)
        self.assertTrue(all(e.kind == 'python-import' for e in report.edges))
        edge = next(e for e in report.edges if e.source == 'pkg/util.py' and e.target == 'pkg/core.py')
        self.assertEqual(edge.line, 1)

    def test_script_relative_imports_and_external_ignored(self):
        self.put('src/index.js', "import { x } from './lib/helper.js';\nimport react from 'react';\nconst y = require('./lib/other');\n")
        self.put('src/lib/helper.js', 'export const x = 1;\n')
        self.put('src/lib/other.ts', 'export const y = 2;\n')
        report = inspect(self.root)
        pairs = {(e.source, e.target) for e in report.edges}
        self.assertEqual(pairs, {('src/index.js', 'src/lib/helper.js'), ('src/index.js', 'src/lib/other.ts')})

    def test_edges_survive_store_roundtrip_and_old_payloads_restore(self):
        self.put('a.py', 'import b\n')
        self.put('b.py', '')
        report = inspect(self.root)
        db = self.root / 'ws.sqlite3'
        store = Store(db)
        store.save_report(report)
        payload = json.loads(store.projects()[0][2])
        store.close()
        self.assertEqual(restore(payload).to_dict(), report.to_dict())
        old = dict(payload)
        old.pop('edges'); old.pop('license_detections')
        self.assertEqual(restore(old).edges, [])


class LicenseCheckTests(Stage3Fixture):
    def test_fingerprints(self):
        self.assertEqual(detect_license(MIT_TEXT)[0], 'MIT')
        self.assertEqual(detect_license(GPL_TEXT)[0], 'GPL-3.0')
        self.assertEqual(detect_license('Some custom terms nobody recognizes.')[0], 'Unknown')
        self.assertEqual(detect_license('Redistribution and use in source and binary forms, with or without modification, are permitted. Neither the name of the author may be used.')[0], 'BSD-3-Clause')
        self.assertEqual(detect_license('Redistribution and use in source and binary forms, with or without modification, are permitted.')[0], 'BSD-2-Clause')

    def test_declared_matching(self):
        self.assertTrue(declared_matches('MIT', 'MIT'))
        self.assertTrue(declared_matches('MIT OR Apache-2.0', 'Apache-2.0'))
        self.assertTrue(declared_matches('Apache 2.0', 'Apache-2.0'))
        self.assertTrue(declared_matches('GPLv3', 'GPL-3.0'))
        self.assertFalse(declared_matches('MIT', 'GPL-3.0'))

    def test_detection_findings_and_copyleft_advisory(self):
        self.put('LICENSE', MIT_TEXT)
        report = inspect(self.root)
        self.assertEqual(report.license_detections[0].spdx, 'MIT')
        self.put('LICENSE', GPL_TEXT)
        report = inspect(self.root)
        self.assertTrue(any('Copyleft license terms detected: GPL-3.0' in f.title for f in report.findings))

    def test_unrecognized_text_and_mismatch_findings(self):
        self.put('LICENSE', 'All rights reserved by the author, custom terms.')
        report = inspect(self.root)
        self.assertTrue(any(f.title == 'License text was not recognized' for f in report.findings))
        self.put('LICENSE', MIT_TEXT)
        self.put('package.json', '{"license": "GPL-3.0"}')
        report = inspect(self.root)
        mismatch = [f for f in report.findings if f.title == 'Declared license does not match the license text']
        self.assertEqual(len(mismatch), 1)
        self.assertIn('GPL-3.0', mismatch[0].evidence)
        self.assertIn('MIT', mismatch[0].evidence)
        self.put('package.json', '{"license": "MIT"}')
        report = inspect(self.root)
        self.assertFalse(any(f.title == 'Declared license does not match the license text' for f in report.findings))

    def test_cli_deps_outputs_edges_and_detections(self):
        self.put('a.py', 'import b\n')
        self.put('b.py', '')
        self.put('LICENSE', MIT_TEXT)
        result = subprocess.run([sys.executable, '-m', 'gitrevival.cli', 'deps', str(self.root)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['edges'][0]['target'], 'b.py')
        self.assertEqual(payload['license_detections'][0]['spdx'], 'MIT')


if __name__ == '__main__':
    unittest.main()

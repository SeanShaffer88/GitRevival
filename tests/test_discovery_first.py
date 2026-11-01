"""Discovery-first checks: plain words become searches; verdicts stay plain."""
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GITREVIVAL_NO_DEMO', '1')

from gitrevival.github import build_query, verdict

TODAY = date(2026, 10, 31)
CUTOFF = 'pushed:<2024-10-31'

class BuildQueryTests(unittest.TestCase):
    def test_plain_words_and_language(self):
        query = build_query('photo editor python', 'explore', today=TODAY)
        self.assertEqual(query, 'photo editor language:Python fork:false archived:false')

    def test_language_only(self):
        self.assertEqual(build_query('rust', 'explore', today=TODAY), 'language:Rust fork:false archived:false')

    def test_loved_hunt_adds_age_and_stars(self):
        query = build_query('music player', 'loved', today=TODAY)
        self.assertIn(CUTOFF, query)
        self.assertIn('stars:>=50', query)

    def test_small_hunt_adds_age_and_size(self):
        query = build_query('', 'small', today=TODAY)
        self.assertIn(CUTOFF, query)
        self.assertIn('size:<5000', query)

    def test_licensed_hunt_has_no_license_qualifier(self):
        query = build_query('notes app', 'licensed', today=TODAY)
        self.assertNotIn('license:', query)
        self.assertIn(CUTOFF, query)

    def test_unknown_hunt_rejected(self):
        with self.assertRaises(ValueError):
            build_query('x', 'everything', today=TODAY)

class VerdictTests(unittest.TestCase):
    def repo(self, **overrides):
        base = {'license': 'MIT', 'stars': 120, 'pushed_at': '2020-06-01T00:00:00Z',
                'topics': ['gui'], 'archived': False, 'fork': False}
        base.update(overrides)
        return base

    def test_strong_candidate(self):
        label, score, reasons = verdict(self.repo(), at=datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual(label, 'Strong candidate')
        self.assertEqual(score, 5)
        self.assertFalse(any(reason.startswith('+') for reason in reasons))
        self.assertTrue(any('may need a new maintainer' in reason for reason in reasons))

    def test_worth_a_look(self):
        label, score, _ = verdict(self.repo(stars=10, topics=[], pushed_at='2026-10-01T00:00:00Z'),
                                  at=datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual((label, score), ('Worth a look', 2))

    def test_long_shot(self):
        label, score, reasons = verdict(self.repo(license='Unknown', stars=2, topics=[],
                                                  pushed_at='2026-10-30T00:00:00Z'),
                                        at=datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual((label, score), ('Long shot', 0))
        self.assertIn('License permission needs investigation', reasons)

class DiscoveryFirstGuiTests(unittest.TestCase):
    def test_find_builds_query_and_verdict_column(self):
        try:
            import tkinter
            tkinter.Tk().destroy()
        except Exception:
            self.skipTest('Tk display unavailable')
        from gitrevival.app import App
        with tempfile.TemporaryDirectory() as tmp:
            app = App(Path(tmp) / 'workspace.sqlite3')
            try:
                panel = app.discovery
                panel.find_words.set('photo editor python')
                panel.find('loved')
                self.assertIn('language:Python', panel.query.get())
                self.assertIn('stars:>=50', panel.query.get())
                item = {'full_name': 'example/old-tool', 'language': 'Python', 'stars': 90,
                        'pushed_at': '2020-01-01T00:00:00Z', 'license': 'MIT', 'topics': ['gui'],
                        'archived': False, 'fork': False, 'description': 'x', 'html_url': '',
                        'checked_at': 'now', 'warnings': []}
                panel.show_items([item])
                values = panel.tree.item('example/old-tool', 'values')
                self.assertEqual(values[0], 'Strong candidate')
                panel.tree.selection_set('example/old-tool')
                panel.select()
                self.assertIn('VERDICT: Strong candidate', panel.detail.get('1.0', 'end'))
                app.show_discovery()
                app.update()
                self.assertGreater(panel.find_entry.winfo_width(), 100)
            finally:
                app.destroy()

if __name__ == '__main__':
    unittest.main()

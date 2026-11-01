"""0.4.0 catch-up: tooltips, WAL + settings, autosave, session restore, help."""
from contextlib import closing
import sqlite3
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from gitrevival.analyzer import inspect
from gitrevival.store import Store


class StoreCatchupTests(unittest.TestCase):
    def test_wal_mode_and_settings_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.sqlite3'
            store = Store(path)
            mode = store.db.execute('PRAGMA journal_mode').fetchone()[0]
            self.assertEqual(mode, 'wal')
            self.assertEqual(store.get_setting('missing', 'fallback'), 'fallback')
            store.set_setting('geometry', '1200x800+10+10')
            store.close()
            # closing() matters on Windows: a sqlite3 connection used as a
            # plain context manager is not closed, and an open database
            # file cannot be deleted by the temporary-folder cleanup.
            with closing(sqlite3.connect(path)) as raw:
                self.assertEqual(raw.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            store = Store(path)
            self.assertEqual(store.get_setting('geometry'), '1200x800+10+10')
            store.close()


class GuiCatchupTests(unittest.TestCase):
    def make_app(self, tmp):
        from gitrevival.app import App
        return App(Path(tmp) / 'state.sqlite3')

    def test_every_button_and_key_control_has_a_tooltip(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(tmp)
            try:
                app.update()
                buttons = []
                stack = [app]
                while stack:
                    widget = stack.pop()
                    stack.extend(widget.winfo_children())
                    if 'Button' in widget.winfo_class():
                        buttons.append(widget)
                self.assertGreaterEqual(len(buttons), 20)
                missing = [b.cget('text') for b in buttons if not getattr(b, '_tooltip_text', '')]
                self.assertEqual(missing, [])
                for widget in (app.search_entry, app.projects, app.recents, app.findings,
                               app.dependencies, app.notes, app.discovery.tree,
                               app.discovery.query_entry, app.planning.scans):
                    self.assertTrue(getattr(widget, '_tooltip_text', ''), widget)
            finally:
                app.store.close()
                app.destroy()

    def test_autosave_writes_notes_without_manual_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(tmp)
            try:
                demo = Path(__file__).resolve().parent.parent / 'demo' / 'old-orbit'
                report = inspect(demo)
                app.store.save_report(report)
                app.load(report)
                finding = report.findings[0]
                app.findings.selection_set(finding.id)
                app.show_finding()
                app.notes.insert('1.0', 'autosaved evidence')
                app.notes.edit_modified(True)
                app._autosave_notes()
                self.assertFalse(app.notes.edit_modified())
                self.assertEqual(app.store.task(report.root, finding.id)[1], 'autosaved evidence')
            finally:
                app.store.close()
                app.destroy()

    def test_session_restore_recents_and_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            demo = Path(__file__).resolve().parent.parent / 'demo' / 'old-orbit'
            report = inspect(demo)
            app = self.make_app(tmp)
            try:
                app.store.save_report(report)
                app.load(report)
                app.tabs.select(app.map_tab)
                app._save_session()
                self.assertEqual(app.store.get_setting('last_project'), report.root)
                self.assertIn(report.root, app.recent_roots)
                saved_geometry = app.store.get_setting('geometry')
                self.assertTrue(saved_geometry)
            finally:
                app.store.close()
                app.destroy()
            app = self.make_app(tmp)
            try:
                self.assertTrue(app.restore_session())
                self.assertEqual(app.report.root, report.root)
                self.assertEqual(app.tabs.select(), str(app.map_tab))
            finally:
                app.store.close()
                app.destroy()

    def test_help_dialog_shows_plain_words_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.make_app(tmp)
            try:
                app.show_help()
                app.update()
                window = app.help_window
                self.assertIsNotNone(window)
                texts = []
                stack = [window]
                while stack:
                    widget = stack.pop()
                    stack.extend(widget.winfo_children())
                    if isinstance(widget, tk.Text):
                        texts.append(widget.get('1.0', 'end'))
                joined = '\n'.join(texts)
                self.assertIn('THE BASIC WORKFLOW', joined)
                self.assertIn('never runs the', joined)
                window.destroy()
            finally:
                app.store.close()
                app.destroy()


if __name__ == '__main__':
    unittest.main()

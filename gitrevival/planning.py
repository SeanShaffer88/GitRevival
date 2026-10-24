"""Local planning helpers and UI. No repository code or commands are executed."""
import json
import sqlite3
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog


from .planning_data import compare_reports, delta_text


def sort_tree(tree, column, reverse=False):
    def key(item):
        text = tree.set(item, column)
        try:
            return (0, float(text))
        except ValueError:
            return (1, text.casefold())
    for index, item in enumerate(sorted(tree.get_children(''), key=key, reverse=reverse)):
        tree.move(item, '', index)
    tree.heading(column, command=lambda: sort_tree(tree, column, not reverse))


class Planning(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        row = ttk.Frame(self); row.pack(fill='x')
        for text, command in (('Add custom task', self.add_task), ('Task history', self.task_history),
                              ('Refresh snapshots', self.refresh), ('Back up workspace', self.backup)):
            ttk.Button(row, text=text, command=command).pack(side='left', padx=(0, 6))
        ttk.Label(self, text='Latest 20 scans per project. Select one for its summary, or two to compare. Task history retains the latest 100 displayed changes.',
                  wraplength=820, style='Muted.TLabel').pack(anchor='w', pady=8)
        self.scans = app.make_tree(self, ('at', 'files', 'findings'), ('Scan time (UTC)', 'Files', 'Findings'), (400, 110, 110))
        self.scans.configure(selectmode='extended')
        self.scans.bind('<<TreeviewSelect>>', self.show_scans)
        self.detail = app.textbox(self, height=10)
        self.records = {}

    def refresh(self):
        self.scans.delete(*self.scans.get_children())
        self.records = {}
        if self.app.report:
            for seq, at, payload in self.app.store.scans(self.app.report.root):
                data = json.loads(payload); self.records[str(seq)] = data
                self.scans.insert('', 'end', iid=str(seq), values=(at, data['files'], len(data['findings'])))
        self.app.set_text(self.detail, 'Select snapshots above. Workspace backups include local paths, notes and saved GitHub metadata.')

    def show_scans(self, event=None):
        ids = self.scans.selection()
        if len(ids) == 2:
            older, newer = sorted(ids, key=int)
            text = delta_text(compare_reports(self.records[older], self.records[newer]))
        elif len(ids) == 1:
            data = self.records[ids[0]]
            text = f"{data['name']} — {data['scanned_at']}\n{data['files']} inventoried files; {len(data['dependencies'])} declared dependencies\n\nScope warnings:\n" + ('\n'.join(data['warnings']) or 'None recorded')
        else:
            text = 'Select one snapshot to inspect, or exactly two to compare.'
        self.app.set_text(self.detail, text)

    def add_task(self):
        app = self.app
        if not app.report or app.busy or not app.discard_guard():
            return
        title = simpledialog.askstring('Custom repair task', 'Task title (up to 200 characters)', parent=app)
        if title is None: return
        action = simpledialog.askstring('Custom repair task', 'Next step / acceptance criteria', parent=app)
        if action is None: return
        try:
            id = app.store.add_custom_task(app.report.root, title, action)
            app.report.findings = [f for f in app.report.findings if not f.id.startswith('custom-')] + app.store.custom_findings(app.report.root)
            app.category_box.configure(values=('All categories',) + tuple(sorted({f.category for f in app.report.findings})))
            app.search.set(''); app.filter_state.set('All states'); app.filter_category.set('All categories'); app.filter_severity.set('All severities')
            app.render_findings(); app.draw_map(); app.tabs.select(app.findings_tab)
            app.findings.selection_set(id); app.show_finding()
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror('Custom task', str(exc), parent=app)

    def task_history(self):
        app = self.app
        if not app.report or not app.selected: return
        events = app.store.task_history(app.report.root, app.selected.id)
        text = '\n\n'.join(f'{at} | {state} | {priority} | Due: {due or "none"}\n{notes}' for at,state,notes,priority,due in events)
        app.set_text(self.detail, text or 'No recorded task edits. History begins with this version.')
        app.tabs.select(self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self.app, title='Create a new workspace backup',
                                           defaultextension='.sqlite3', filetypes=[('SQLite workspace', '*.sqlite3')])
        if not path: return
        try:
            if not self.app.discard_guard() or not self.app.discovery.guard(): return
            self.app.store.backup(path)
            self.app.footer_var.set('Workspace backup created and SQLite integrity checked. Keep backups private; they contain paths and notes.')
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Backup failed', str(exc), parent=self.app)

"""Advanced tab: Git recovery — forensic scan of the open project's .git.

Clearly separated from the everyday workflow by design. Everything here
is read-only except the one explicit action: rebuilding a chosen
dangling commit's files into a folder the user picks. Recovery never
writes into the repository and never overwrites an existing file.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .gitobjects import GitError, recover_commit, scan_git

INTRO = ('Advanced — for lost work, not everyday use. This looks inside the open '
         'project’s .git folder for commits Git no longer points at: amended, '
         'rebased or reset-away work often survives as “dangling” objects until '
         'Git cleans them up. Scanning never changes anything.')


class Recovery(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.result = None
        self.events = queue.Queue()
        self.after(100, self.poll)
        ttk.Label(self, text=INTRO, style='Muted.TLabel', wraplength=900).pack(anchor='w', pady=(0, 10))
        controls = ttk.Frame(self)
        controls.pack(fill='x', pady=(0, 10))
        self.scan_button = ttk.Button(controls, text='Scan .git data', command=self.scan)
        self.scan_button.pack(side='left')
        self.recover_button = ttk.Button(controls, text='Recover selected commit…',
                                         command=self.recover, state='disabled')
        self.recover_button.pack(side='left', padx=8)
        self.status = ttk.Label(controls, text='Open a local repository, then scan its .git data.', style='Muted.TLabel')
        self.status.pack(side='left', padx=8)
        columns = ('sha', 'summary', 'author', 'date')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=8)
        for key, title, width in (('sha', 'Commit', 110), ('summary', 'Message', 420),
                                  ('author', 'Author', 200), ('date', 'Date', 170)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=key == 'summary')
        self.tree.pack(fill='x')
        self.tree.bind('<<TreeviewSelect>>', lambda *_: self._sync_recover())
        self.details = app.textbox(self)
        self.details.pack(fill='both', expand=True, pady=(10, 0))

    def _report(self):
        return getattr(self.app, 'report', None)

    def _sync_recover(self):
        self.recover_button.configure(state='normal' if self.tree.selection() else 'disabled')

    def scan(self):
        report = self._report()
        if not report:
            self.status.configure(text='Open a local repository first.')
            return
        self.scan_button.configure(state='disabled')
        self.status.configure(text='Reading .git data… (read-only)')
        def work():
            try:
                result = scan_git(report.root)
                self.events.put(('scanned', result, None))
            except Exception as exc:
                self.events.put(('scanned', None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _scanned(self, result, error=None):
        self.scan_button.configure(state='normal')
        self.result = result
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._sync_recover()
        if error:
            self.status.configure(text=f'Scan failed: {error}')
            return
        if not result or not result.present:
            self.status.configure(text='No .git data found in this project.')
            self.app.set_text(self.details, 'This folder has no .git data to inspect.')
            return
        for commit in result.dangling_commits:
            self.tree.insert('', 'end', iid=commit['sha'], values=(
                commit['sha'][:10], commit['summary'], commit['author'],
                (commit['date'] or '')[:19].replace('T', ' ')))
        by_type = ', '.join(f'{kind}: {count}' for kind, count in sorted(result.objects_by_type.items()))
        lines = [f'Git data: {result.git_dir}',
                 f'Objects: {result.objects_total} ({by_type}); reachable from refs/reflogs/index: {result.reachable}.',
                 f'Dangling: {len(result.dangling_commits)} commit(s), {result.dangling_trees} tree(s), {result.dangling_blobs} blob(s). '
                 'Dangling commits are listed above, newest first.',
                 f'Reflog entries read: {result.reflog_entries}. Index: '
                 + ('not present.' if not result.index.get('exists') else
                    f"version {result.index.get('version')}, {result.index.get('entries')} entries"
                    + (' — DAMAGED, partial entries recovered.' if result.index.get('damaged') else '.'))]
        if result.reflog_recent:
            lines += ['', 'Most recent reflog entries:']
            for entry in result.reflog_recent[:5]:
                lines.append(f"  {entry.get('ref', '')}: {entry.get('message', '')} ({(entry.get('new') or '')[:10]})")
        if result.warnings:
            lines += ['', 'Warnings: ' + '; '.join(result.warnings)]
        self.app.set_text(self.details, '\n'.join(lines))
        self.status.configure(text=f'Scan complete: {len(result.dangling_commits)} dangling commit(s) found.')

    def recover(self):
        selection = self.tree.selection()
        report = self._report()
        if not selection or not report:
            return
        sha = selection[0]
        folder = filedialog.askdirectory(title='Recover this commit’s files into which folder?')
        if not folder:
            return
        self.recover_button.configure(state='disabled')
        def work():
            try:
                summary = recover_commit(report.root, sha, folder)
                text = (f"Recovered commit {sha[:10]} into {folder}\n"
                        f"Written: {len(summary['written'])} file(s)"
                        + (f" — {', '.join(summary['written'][:8])}" if summary['written'] else '')
                        + (f"\nSkipped (already existed, never overwritten): {', '.join(summary['skipped_existing'])}"
                           if summary['skipped_existing'] else '')
                        + (f"\nNot recovered: {'; '.join(summary['skipped_other'])}"
                           if summary['skipped_other'] else ''))
                self.events.put(('recovered', text))
            except (GitError, OSError) as exc:
                self.events.put(('recovered', f'Recovery failed: {exc}'))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'scanned':
                    self._scanned(event[1], event[2])
                elif event[0] == 'recovered':
                    self._recovered(event[1])
        except queue.Empty:
            pass
        finally:
            self.after(100, self.poll)

    def _recovered(self, text):
        self._sync_recover()
        current = self.details.get('1.0', 'end-1c')
        self.app.set_text(self.details, current + '\n\n' + text)
        self.status.configure(text=text.split('\n')[0])

from __future__ import annotations
import argparse
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from .analyzer import inspect
from .planning import Planning, sort_tree
from .store import Store, STATES, restore, export_report
from .tooltips import add_tooltip, install_tooltips

BG = '#101820'
PANEL = '#18232e'
INK = '#e6edf3'
MUTED = '#9aaebc'
ACCENT = '#68dac2'

HELP_TEXT = """GitRevival — a plain-words guide

WHAT IT DOES
GitRevival looks at an old software project on your computer and helps you
plan how to bring it back to life. It only reads files. It never runs the
project's code, never changes the project, and works offline except for the
optional GitHub checks in Discover & GitHub.

THE BASIC WORKFLOW
1. Click "+ Open repository" and choose a project folder — or click
   "Load demo" to try the included sample project first.
2. Wait for the inspection. The Repair backlog tab lists what was found.
   Every finding shows the evidence for it and a suggested next step.
3. Click a finding to read it. Set its task state (Queued, In progress,
   Blocked, Done or Dismissed), priority and due date, and write notes —
   build commands you tried, what happened, decisions you made.
   Notes save on their own as you type; Ctrl+S saves right away.
4. Use the Revival map tab to see findings grouped by area, the
   Dependencies tab to search everything the project declares, and
   Scan scope to see exactly what was and was not read, and why.
5. After you change the project, click Rescan (F5). Your task states and
   notes are kept; unchanged findings keep their identity.
6. Click "Export report" to save a Markdown, JSON or CSV report you can
   share or hand to a coding assistant. Reports include local paths,
   evidence snippets and your notes — read one before sharing it.

PLANNING & HISTORY
That tab adds your own repair tasks, shows the history of changes to the
selected task, keeps the latest 20 scans of each project (pick two to see
what changed between them), and makes a checked backup of the whole
workspace. To restore a backup: close GitRevival, keep your current
.local folder somewhere safe, then copy the backup file to
.local/workspace.sqlite3 in the app folder.

DISCOVER & GITHUB
Search GitHub for projects that may be worth reviving, check one for live
evidence (last activity, latest release, open issues), and save the
promising ones to your shortlist with research notes. The 0–5 score is a
research lead only — it does not say a project is valuable, safe, or
allowed to reuse. These are the only features that use the network, they
only ever read, and nothing happens until you click.

YOUR DATA
Projects, tasks, notes and saved GitHub evidence live in one file:
.local/workspace.sqlite3 beside the app. It is plain local data, not
encrypted — keep the app folder and any backups private. A token is only
ever read from the GITREVIVAL_GITHUB_TOKEN environment variable and is
never saved.

KEYBOARD
Ctrl+O open repository · Ctrl+S save task & notes · Ctrl+F search the
backlog · F5 rescan · F1 this guide.
Click a table heading to sort it; click again to reverse.

LIMITS TO KNOW
An inspection is a bounded reading of selected files (at most 15,000
files, 512 KB per file, 12 MB in total). It is not a build, a security
scan, or a legal opinion: a finding is a lead to check, "Done" is your
own record, and build success is always unverified until you build it.
"""

SHORTCUTS_TEXT = ('Ctrl+O: open repository\nCtrl+S: save selected task\nCtrl+F: search repair backlog\n'
                  'F5: rescan current project\nF1: the built-in guide\n\n'
                  'Click a table heading to sort; click again to reverse.')

class App(tk.Tk):
    def __init__(self, state_path=None):
        super().__init__()
        self.title('GitRevival · Project resurrection workbench')
        self.geometry('1380x880')
        self.minsize(1120, 820)
        self.configure(bg=BG)
        self.store = Store(state_path or Path(__file__).resolve().parent.parent / '.local' / 'workspace.sqlite3')
        saved_geometry = self.store.get_setting('geometry')
        if self._valid_geometry(saved_geometry):
            self.geometry(saved_geometry)
        self.report = None
        self._autosave_id = None
        self.selected = None
        self.events = queue.Queue()
        self.busy = False
        self.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=PANEL, foreground=INK, font=('Segoe UI', 10))
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=INK)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'))
        style.configure('TButton', padding=(12, 8), background='#263b48', foreground=INK)
        style.map('TButton', background=[('active','#365666')])
        style.configure('Accent.TButton', background=ACCENT, foreground=BG)
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=34, borderwidth=0)
        style.configure('Treeview.Heading', background='#263746', foreground=MUTED, padding=8)
        style.map('Treeview', background=[('selected','#27574f')], foreground=[('selected','white')])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', padding=(18,10), background=PANEL)
        style.map('TNotebook.Tab', background=[('selected','#2b4c50')])

        header = ttk.Frame(self, padding=(24,20,24,12))
        header.pack(fill='x')
        ttk.Label(header, text='GitRevival', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text='  /  Project resurrection workbench', style='Muted.TLabel').pack(side='left', padx=12)
        self.open_button = ttk.Button(header, text='+ Open repository', style='Accent.TButton', command=self.open_repo)
        self.open_button.pack(side='right')
        ttk.Button(header, text='Load demo', command=self.demo).pack(side='right', padx=8)
        ttk.Button(header, text='Help', command=self.show_help).pack(side='right')

        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=24)
        sidebar = ttk.Frame(body, width=235)
        body.add(sidebar, weight=0)
        ttk.Label(sidebar, text='WORKSPACE', style='Muted.TLabel').pack(anchor='w', pady=(12,10))
        self.projects = tk.Listbox(sidebar, bg=PANEL, fg=INK, selectbackground='#27574f',
                                   font=('Segoe UI',11), relief='flat', borderwidth=0, exportselection=False, width=25)
        self.projects.pack(fill='both', expand=True, padx=(0,14))
        self.projects.bind('<<ListboxSelect>>', self.choose_project)
        self.progress = ttk.Progressbar(sidebar, maximum=100)
        self.progress.pack(fill='x', padx=(0,14), pady=6)
        self.progress_text = ttk.Label(sidebar, text='No project loaded', style='Muted.TLabel', wraplength=220)
        self.progress_text.pack(anchor='w')
        ttk.Label(sidebar, text='RECENT', style='Muted.TLabel').pack(anchor='w', pady=(14,6))
        self.recents = tk.Listbox(sidebar, bg=PANEL, fg=INK, selectbackground='#27574f',
                                  font=('Segoe UI',10), relief='flat', borderwidth=0, exportselection=False, width=25, height=4)
        self.recents.pack(fill='x', padx=(0,14))
        self.recents.bind('<<ListboxSelect>>', self.choose_recent)
        self.recent_roots = []
        ttk.Label(sidebar, text='Local inspection\nNo repository code is executed.\n\nNotes and task states are saved\nin this app’s .local folder.',
                  style='Muted.TLabel', justify='left').pack(anchor='w', pady=18)
        main = ttk.Frame(body)
        body.add(main, weight=1)
        top = ttk.Frame(main)
        top.pack(fill='x', pady=(8,12))
        self.name = ttk.Label(top, text='A second life starts with evidence.', font=('Segoe UI',18,'bold'))
        self.name.pack(anchor='w')
        self.path = ttk.Label(top, text='Open a local repository or explore the included demo.', style='Muted.TLabel')
        self.path.pack(anchor='w', pady=(5,0))
        controls = ttk.Frame(main)
        controls.pack(fill='x', pady=(0,12))
        self.stats = ttk.Label(controls, text='Ready to inspect', foreground=ACCENT)
        self.stats.pack(side='left')
        self.export_button = ttk.Button(controls, text='Export report', command=self.export)
        self.export_button.pack(side='right')
        self.rescan_button = ttk.Button(controls, text='Rescan', command=self.rescan)
        self.rescan_button.pack(side='right', padx=8)
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both', expand=True)
        self.findings_tab = ttk.Frame(self.tabs, padding=12)
        self.map_tab = ttk.Frame(self.tabs, padding=12)
        self.deps_tab = ttk.Frame(self.tabs, padding=12)
        self.scope_tab = ttk.Frame(self.tabs, padding=12)
        for frame, name in ((self.findings_tab,'Repair backlog'),(self.map_tab,'Revival map'),(self.deps_tab,'Dependencies'),(self.scope_tab,'Scan scope')):
            self.tabs.add(frame, text=name)
        filters = ttk.Frame(self.findings_tab)
        filters.pack(fill='x', pady=(0,10))
        ttk.Label(filters, text='Search').pack(side='left')
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(filters, textvariable=self.search, width=22)
        self.search_entry.pack(side='left', padx=8)
        self.search.trace_add('write', lambda *_: self.render_findings())
        self.filter_state = tk.StringVar(value='All states')
        box = ttk.Combobox(filters, textvariable=self.filter_state, values=('All states',)+STATES, state='readonly', width=15)
        box.pack(side='left', padx=8)
        box.bind('<<ComboboxSelected>>', lambda e: self.render_findings())
        self.state_box = box
        self.filter_category = tk.StringVar(value='All categories')
        self.category_box = ttk.Combobox(filters, textvariable=self.filter_category, values=('All categories',), state='readonly', width=16)
        self.category_box.pack(side='left')
        self.category_box.bind('<<ComboboxSelected>>', lambda e: self.render_findings())
        self.filter_severity = tk.StringVar(value='All severities')
        severity = ttk.Combobox(filters, textvariable=self.filter_severity, values=('All severities','Review','Info'), state='readonly', width=14)
        severity.pack(side='left', padx=6)
        severity.bind('<<ComboboxSelected>>', lambda e:self.render_findings())
        self.severity_box = severity
        split = ttk.Panedwindow(self.findings_tab, orient='vertical')
        split.pack(fill='both', expand=True)
        listframe = ttk.Frame(split)
        split.add(listframe, weight=3)
        self.findings = self.make_tree(listframe, ('status','category','title','priority','due'), ('Task state','Area','Finding','Priority','Due'), (115,120,400,85,100))
        self.findings.bind('<<TreeviewSelect>>', self.show_finding)
        detail = ttk.Frame(split, padding=(0,12,0,0))
        split.add(detail, weight=2)
        self.detail = self.textbox(detail, height=6)
        self.set_text(self.detail, 'Select a finding to inspect its evidence and next step.\n\nTask completion is a manual record. It does not prove build success.')
        editrow = ttk.Frame(detail)
        editrow.pack(fill='x', pady=8)
        ttk.Label(editrow, text='Task state').pack(side='left')
        self.status_var = tk.StringVar(value='Queued')
        state_box = ttk.Combobox(editrow, textvariable=self.status_var, values=STATES, state='readonly', width=15)
        state_box.pack(side='left', padx=8)
        state_box.bind('<<ComboboxSelected>>', lambda e: self.notes.edit_modified(True))
        self.task_state_box = state_box
        metadata_row = ttk.Frame(detail)
        metadata_row.pack(fill='x', pady=4)
        ttk.Label(metadata_row, text='Priority').pack(side='left')
        self.priority_var = tk.StringVar(value='Normal')
        priority = ttk.Combobox(metadata_row, textvariable=self.priority_var, values=('Low','Normal','High','Urgent'), state='readonly', width=8)
        priority.pack(side='left', padx=4)
        priority.bind('<<ComboboxSelected>>', lambda e:self.notes.edit_modified(True))
        self.priority_box = priority
        ttk.Label(metadata_row, text='Due YYYY-MM-DD').pack(side='left')
        self.due_var = tk.StringVar()
        self.due_entry = ttk.Entry(metadata_row, textvariable=self.due_var, width=12)
        self.due_entry.pack(side='left', padx=4)
        self.due_var.trace_add('write', lambda *_:self.notes.edit_modified(True))
        self.save_button = ttk.Button(editrow, text='Save task & notes', command=self.save_task)
        self.save_button.pack(side='right')
        self.source_button = ttk.Button(editrow, text='View source', command=self.view_selected_source)
        self.source_button.pack(side='right', padx=(0, 8))
        ttk.Label(detail, text='Notes / build commands / validation evidence', style='Muted.TLabel').pack(anchor='w')
        self.notes = self.textbox(detail, height=3, editable=True)
        self.notes.edit_modified(False)
        self.notes.bind('<<Modified>>', self._notes_modified)
        def initial_split(event):
            if event.height > 300:
                split.sashpos(0, int(event.height * 0.36))
                split.unbind('<Configure>')
        split.bind('<Configure>', initial_split)

        ttk.Label(self.map_tab, text='Repository → inspection areas → findings. Click an area to filter the backlog.', style='Muted.TLabel').pack(anchor='w', pady=(0,8))
        self.canvas = tk.Canvas(self.map_tab, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw_map())
        dependency_bar = ttk.Frame(self.deps_tab); dependency_bar.pack(fill='x')
        ttk.Label(dependency_bar, text='Search dependencies').pack(side='left')
        self.dependency_search = tk.StringVar()
        self.dependency_entry = ttk.Entry(dependency_bar, textvariable=self.dependency_search)
        self.dependency_entry.pack(side='left', fill='x', expand=True, padx=8)
        self.dependency_search.trace_add('write', lambda *_:self.render_dependencies())
        self.dependencies = self.make_tree(self.deps_tab, ('name','version','eco','file'), ('Dependency','Declared version / constraint','Ecosystem','Manifest'), (220,230,130,300))
        ttk.Label(self.deps_tab, text='Internal dependency edges — files in this project importing each other (double-click a row to view the source line)', style='Muted.TLabel').pack(anchor='w', pady=(10, 4))
        self.edges = self.make_tree(self.deps_tab, ('source','target','kind'), ('Imports from','Imports','Kind'), (340,340,140))
        self.edges.bind('<Double-1>', self.view_edge_source)
        self.scope = self.textbox(self.scope_tab)
        from .discovery import Discovery
        self.discovery = Discovery(self.tabs,self)
        self.tabs.add(self.discovery,text='Discover & GitHub')
        self.planning = Planning(self.tabs,self)
        self.tabs.add(self.planning,text='Planning & history')
        self.footer_var = tk.StringVar(value='Local inspection • Optional GitHub checks in Discover & GitHub • Build status unverified')
        ttk.Label(self, textvariable=self.footer_var, style='Muted.TLabel', padding=(24,12)).pack(fill='x')
        self.refresh_projects()
        self.refresh_recents()
        self._install_tooltips()
        self.after(100, self.poll)
        self.bind('<Control-o>', lambda e: self.open_repo())
        self.bind('<Control-s>', lambda e: self.save_task())
        self.bind('<Control-f>', self.focus_search)
        self.bind('<F5>', lambda e:self.rescan())
        self.bind('<F1>', self.show_help)

    def focus_search(self, event=None):
        if self.discard_guard():
            self.tabs.select(self.findings_tab)
            self.search_entry.focus_set()
            self.search_entry.selection_range(0,'end')
        return 'break'

    def shortcut_help(self, event=None):
        messagebox.showinfo('Keyboard shortcuts', SHORTCUTS_TEXT, parent=self)
        return 'break'

    def show_help(self, event=None):
        """Open the built-in plain-words guide (also on F1). Works offline."""
        existing = getattr(self, 'help_window', None)
        if existing is not None:
            try:
                existing.lift()
                return 'break'
            except tk.TclError:
                self.help_window = None
        window = tk.Toplevel(self)
        window.title('GitRevival guide')
        window.configure(bg=BG)
        window.geometry('720x620')
        window.minsize(520, 420)
        text = ScrolledText(window, bg=PANEL, fg=INK, insertbackground=INK, font=('Segoe UI', 10),
                            wrap='word', relief='flat', padx=14, pady=12)
        text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('1.0', HELP_TEXT)
        text.configure(state='disabled')
        close = ttk.Button(window, text='Close help', command=window.destroy)
        close.pack(pady=(0, 12))
        add_tooltip(close, 'Close this guide.')
        self.help_window = window
        window.bind('<Destroy>', lambda e: setattr(self, 'help_window', None) if e.widget is window else None)
        return 'break'

    @staticmethod
    def _valid_geometry(value):
        if not value:
            return False
        try:
            size = value.split('+')[0]
            width, height = (int(part) for part in size.split('x'))
            return width >= 1120 and height >= 700
        except (ValueError, IndexError):
            return False

    def _install_tooltips(self):
        add_tooltip(self.open_button, 'Open a local repository folder and inspect it. Nothing in the folder is run or changed.')
        add_tooltip(self.projects, 'Projects you have inspected. Click one to reopen its saved inspection.')
        add_tooltip(self.recents, 'Projects you opened most recently. Click one to reopen it.')
        add_tooltip(self.progress, 'Share of tasks you have marked Done. This is your own record, not a build result.')
        add_tooltip(self.search_entry, 'Type to filter the repair backlog by title, file, evidence or area (Ctrl+F).')
        add_tooltip(self.state_box, 'Show only findings with this task state.')
        add_tooltip(self.category_box, 'Show only findings in this inspection area.')
        add_tooltip(self.severity_box, 'Show only findings with this severity.')
        add_tooltip(self.findings, 'The repair backlog: one row per finding. Click a row to see its evidence and next step; click a heading to sort.')
        add_tooltip(self.task_state_box, 'Your record of where this task stands. Done is a manual record — it does not prove a build works.')
        add_tooltip(self.priority_box, 'How urgent this task is: Low, Normal, High or Urgent.')
        add_tooltip(self.due_entry, 'Optional due date for this task, as YYYY-MM-DD. No reminders are sent.')
        add_tooltip(self.notes, 'Your notes for the selected task: build commands, results, decisions. Saved on this computer as you type.')
        add_tooltip(self.detail, 'Evidence for the selected finding and the suggested next step.')
        add_tooltip(self.dependencies, 'Dependencies the project declares in files GitRevival can read. Declarations only — nothing was downloaded or checked online.')
        add_tooltip(self.edges, 'Imports between files inside this project, found by reading import lines. Double-click a row to see the source line. External packages are not shown here.')
        add_tooltip(self.source_button, 'Open a read-only view of the file behind the selected finding, with the finding line marked. Nothing is edited or run.')
        add_tooltip(self.dependency_entry, 'Type to filter the dependency list by name, version, kind or file.')
        add_tooltip(self.canvas, 'Findings grouped by inspection area. Click an area to filter the repair backlog.')
        add_tooltip(self.scope, 'What the inspection read, what it left out, and the warnings recorded for this scan.')
        add_tooltip(self.tabs, 'Switch between the repair backlog, revival map, dependencies, scan scope, discovery and planning.')
        install_tooltips(self)

    def refresh_recents(self):
        try:
            roots = json.loads(self.store.get_setting('recents', '[]'))
        except ValueError:
            roots = []
        known = {root: name for root, name, _ in self.store.projects()}
        self.recent_roots = [root for root in roots if root in known][:8]
        self.recents.delete(0, 'end')
        for root in self.recent_roots:
            self.recents.insert('end', known[root])

    def _record_recent(self, root):
        try:
            roots = json.loads(self.store.get_setting('recents', '[]'))
        except ValueError:
            roots = []
        roots = [root] + [item for item in roots if item != root]
        self.store.set_setting('recents', json.dumps(roots[:8]))
        self.store.set_setting('last_project', root)
        self.refresh_recents()

    def choose_recent(self, event=None):
        selection = self.recents.curselection()
        if selection and not self.busy and self.discard_guard():
            root = self.recent_roots[selection[0]]
            row = next((item for item in self.project_rows if item[0] == root), None)
            if row:
                self.load(restore(json.loads(row[2])))

    def restore_session(self):
        """Reopen the last project and tab from the previous run, if saved."""
        root = self.store.get_setting('last_project')
        if not root:
            return False
        row = next((item for item in self.project_rows if item[0] == root), None)
        if not row:
            return False
        self.load(restore(json.loads(row[2])))
        tab = self.store.get_setting('last_tab')
        for frame in self.tabs.winfo_children():
            try:
                if self.tabs.tab(frame, 'text') == tab:
                    self.tabs.select(frame)
            except tk.TclError:
                continue
        return True

    def _save_session(self):
        try:
            self.store.set_setting('geometry', self.geometry())
            selected = self.tabs.select()
            if selected:
                self.store.set_setting('last_tab', self.tabs.tab(selected, 'text'))
        except Exception:
            pass

    def _notes_modified(self, event=None):
        if not self.notes.edit_modified():
            return
        if self._autosave_id is not None:
            self.after_cancel(self._autosave_id)
        self._autosave_id = self.after(800, self._autosave_notes)

    def _autosave_notes(self):
        self._autosave_id = None
        if self.selected and self.report and self.notes.edit_modified():
            self.save_task(quiet=True)

    def make_tree(self, parent, columns, labels, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for col,label,width in zip(columns,labels,widths):
            tree.heading(col, text=label, command=lambda column=col:sort_tree(tree,column))
            tree.column(col, width=width, minwidth=70)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        scroll.pack(side='right', fill='y')
        horizontal.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True)
        return tree

    def textbox(self, parent, height=12, editable=False):
        widget = ScrolledText(parent, height=height, bg=PANEL, fg=INK, insertbackground=INK,
                              font=('Consolas',10), wrap='word', relief='flat', padx=12, pady=10, undo=editable)
        widget.pack(fill='both', expand=True, pady=4)
        if not editable:
            widget.configure(state='disabled')
        return widget

    def set_text(self, widget, text):
        widget.configure(state='normal')
        widget.delete('1.0','end')
        widget.insert('1.0', text)
        widget.configure(state='disabled')

    def refresh_projects(self):
        self.project_rows = self.store.projects()
        self.projects.delete(0,'end')
        for root,name,report in self.project_rows:
            self.projects.insert('end', name)

    def discard_guard(self):
        if self.selected and self.notes.edit_modified():
            answer = messagebox.askyesnocancel('Unsaved notes', 'Save changes to this task before continuing?')
            if answer is None:
                return False
            if answer:
                return self.save_task()
            else:
                self.notes.edit_modified(False)
        return True

    def open_repo(self):
        if self.busy or not self.discard_guard():
            return
        path = filedialog.askdirectory(title='Select repository folder')
        if path:
            self.scan(path)

    def demo(self):
        if not self.busy and self.discard_guard():
            self.scan(Path(__file__).resolve().parent.parent / 'demo' / 'old-orbit')

    def rescan(self):
        if self.report and not self.busy and self.discard_guard():
            self.scan(self.report.root)

    def scan(self, path):
        self.busy = True
        self.open_button.configure(state='disabled')
        self.rescan_button.configure(state='disabled')
        self.footer_var.set('Inspecting repository… bounded file reads; no project code execution.')
        def work():
            try:
                self.events.put(('report', inspect(path)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            kind,value = self.events.get_nowait()
            self.busy = False
            self.open_button.configure(state='normal')
            self.rescan_button.configure(state='normal')
            if kind == 'report':
                if not self.discard_guard():
                    self.footer_var.set('Scan result not opened; unsaved task edits retained.')
                else:
                    try:
                        self.store.save_report(value)
                        self.refresh_projects()
                        self.load(value)
                    except Exception as exc:
                        messagebox.showerror('Could not save inspection', str(exc))
            else:
                self.footer_var.set('Inspection failed. Choose a readable local repository.')
                messagebox.showerror('Inspection failed', value)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def choose_project(self, event=None):
        selection = self.projects.curselection()
        if selection and not self.busy and self.discard_guard():
            self.load(restore(json.loads(self.project_rows[selection[0]][2])))

    def load(self, report):
        report = restore(report.to_dict())
        report.findings = [f for f in report.findings if not f.id.startswith('custom-')] + self.store.custom_findings(report.root)
        self.report = report
        self.selected = None
        self.notes.delete('1.0','end')
        self.notes.edit_modified(False)
        self.set_text(self.detail, 'Select a finding to inspect evidence and a suggested next step.')
        self.name.configure(text=report.name)
        self.path.configure(text=report.root)
        self.filter_category.set('All categories')
        self.category_box.configure(values=('All categories',)+tuple(sorted({f.category for f in report.findings})))
        self.render_findings()
        self.render_dependencies()
        self.planning.refresh()
        scope = (f'SCAN SUMMARY\n\nRepository: {report.root}\nScanned (UTC): {report.scanned_at}\nFiles inventoried: {report.files}\n'
                 f'Ecosystems: {", ".join(report.ecosystems) or "Not identified"}\n\n'
                 'This is a bounded static inspection, not a verified build, vulnerability scan, dependency resolution or legal opinion. '
                 'Version constraints are declarations, not proof that packages can be downloaded or used. '
                 'This local scan did not query remote maintenance, releases or advisories. Optional GitHub evidence is available in Discover & GitHub and may be linked to this project.\n\n'
                 'Excluded: Git internals, generated builds, vendor/node_modules, virtual environments, symlinks and reparse directories. '
                 'Limits: 15,000 files; 512 KB per inspected file; 12 MB total inspected text. '
                 'Only selected manifests, README/license files and GitHub workflows are read. '
                 'Rust target/workspace dependencies, Python optional groups and full YAML/CMake evaluation are not supported.\n\n'
                 'WARNINGS\n' + ('\n'.join(report.warnings) or 'None reported.') + '\n\nMANIFESTS\n' + '\n'.join(report.manifests) +
                 '\n\nLICENSE FILES\n' + ('\n'.join(report.licenses) or 'None observed.'))
        self.set_text(self.scope, scope)
        self.draw_map()
        self.discovery.project_changed()
        self._record_recent(report.root)
        self.footer_var.set(f'{len(report.warnings)} scope warnings • Saved locally • Build status unverified')

    def render_dependencies(self):
        if not self.report: return
        self.dependencies.delete(*self.dependencies.get_children())
        query = self.dependency_search.get().casefold()
        for d in self.report.dependencies:
            values = (d.name,d.version,d.ecosystem,d.file)
            if query in ' '.join(values).casefold():
                self.dependencies.insert('', 'end', values=values)
        self.edges.delete(*self.edges.get_children())
        self._edge_rows = {}
        for e in self.report.edges:
            if query and query not in f'{e.source} {e.target}'.casefold():
                continue
            iid = self.edges.insert('', 'end', values=(f'{e.source}:{e.line}', e.target, e.kind))
            self._edge_rows[iid] = (e.source, e.line)

    def view_edge_source(self, event=None):
        selection = self.edges.selection()
        if selection and selection[0] in getattr(self, '_edge_rows', {}):
            source, line = self._edge_rows[selection[0]]
            self.open_source(source, line)

    def view_selected_source(self):
        if self.selected and self.selected.file:
            self.open_source(self.selected.file, self.selected.line)
        elif self.selected:
            self.footer_var.set('This finding covers the whole repository; it has no single source file.')

    def open_source(self, relative, line):
        """Read-only source viewer: shows the file with the target line marked."""
        if not self.report:
            return
        path = Path(self.report.root) / relative
        try:
            raw = path.open('rb')
            with raw:
                data = raw.read(512_001)
            if len(data) > 512_000:
                self.footer_var.set(f'Source view skipped: {relative} is larger than 512 KB.')
                return
            text = data.decode('utf-8-sig', errors='replace')
        except OSError as exc:
            self.footer_var.set(f'Could not read {relative}: {exc.__class__.__name__}')
            return
        window = tk.Toplevel(self)
        window.title(f'{relative}:{line} — GitRevival source view (read-only)')
        window.geometry('900x640')
        viewer = tk.Text(window, wrap='none', font=('Consolas', 10), bg='#101418', fg='#D7DEE8',
                         insertbackground='#D7DEE8', padx=10, pady=8)
        viewer.pack(fill='both', expand=True)
        numbered = '\n'.join(f'{number:>5}  {content}' for number, content in enumerate(text.splitlines(), 1))
        viewer.insert('1.0', numbered)
        viewer.tag_config('target', background='#5A1F1F', foreground='#FFFFFF')
        target = max(1, min(int(line or 1), max(1, len(text.splitlines()))))
        viewer.tag_add('target', f'{target}.0', f'{target}.end')
        viewer.see(f'{max(1, target - 6)}.0')
        viewer.configure(state='disabled')
        add_tooltip(viewer, 'Read-only view of the file inside the inspected repository. Nothing here can be edited or run.')

    def render_findings(self):
        if not self.report:
            return
        previous = self.findings.selection()
        for item in self.findings.get_children():
            self.findings.delete(item)
        query = self.search.get().casefold()
        completed = 0
        for f in self.report.findings:
            state,_ = self.store.task(self.report.root, f.id)
            completed += state == 'Done'
            if self.filter_state.get() != 'All states' and state != self.filter_state.get():
                continue
            if self.filter_category.get() != 'All categories' and f.category != self.filter_category.get():
                continue
            if self.filter_severity.get() != 'All severities' and f.severity != self.filter_severity.get():
                continue
            if query not in f'{f.title} {f.file} {f.evidence} {f.category}'.casefold():
                continue
            priority,due = self.store.task_meta(self.report.root,f.id)
            self.findings.insert('', 'end', iid=f.id, values=(state,f.category,f.title,priority,due))
        if previous and self.findings.exists(previous[0]):
            self.findings.selection_set(previous[0])
        r = self.report
        total = len(r.findings)
        self.progress['value'] = 100 * completed / total if total else 0
        self.progress_text.configure(text=f'{completed}/{total} tasks done ({100*completed/total if total else 0:.0f}%)\nManual progress; build unverified')
        self.stats.configure(text=f'{r.files:,} files  ·  {len(r.dependencies)} dependencies  ·  {len(r.findings)} findings  ·  {completed} tasks done')

    def show_finding(self, event=None):
        selection = self.findings.selection()
        if not selection or (self.selected and selection[0] == self.selected.id):
            return
        if not self.discard_guard():
            if self.selected and self.findings.exists(self.selected.id):
                self.findings.selection_set(self.selected.id)
            return
        self.selected = next(f for f in self.report.findings if f.id == selection[0])
        f = self.selected
        self.set_text(self.detail, f'{f.title}\n{f.severity} · {f.category} · {f.confidence}\n'
                      f'Source: {f.file or "Repository scope"}:{f.line}\n\nEVIDENCE\n{f.evidence}\n\nNEXT STEP\n{f.action}')
        status,notes = self.store.task(self.report.root,f.id)
        self.status_var.set(status)
        priority,due = self.store.task_meta(self.report.root,f.id)
        self.priority_var.set(priority); self.due_var.set(due)
        self.notes.delete('1.0','end')
        self.notes.insert('1.0', notes)
        self.notes.edit_modified(False)

    def save_task(self, quiet=False):
        if self.selected and self.report:
            try:
                self.store.save_task(self.report.root,self.selected.id,self.status_var.get(),self.notes.get('1.0','end-1c'),self.priority_var.get(),self.due_var.get())
                self.notes.edit_modified(False)
                self.render_findings()
                self.draw_map()
                if quiet:
                    self.footer_var.set('Task and notes saved automatically. Completion is manually recorded; build status remains unverified.')
                else:
                    self.footer_var.set('Task and notes saved. Completion is manually recorded; build status remains unverified.')
                return True
            except Exception as exc:
                if not quiet:
                    messagebox.showerror('Could not save task',str(exc))
                else:
                    self.footer_var.set(f'Automatic save failed: {exc} Press Ctrl+S to save manually.')
                return False
        return True

    def draw_map(self):
        c = self.canvas
        c.delete('all')
        if not self.report:
            c.create_text(30,40, anchor='nw', text='Open a repository to map its revival work.', fill=MUTED, font=('Segoe UI',14))
            return
        groups = sorted({f.category for f in self.report.findings})
        width = max(c.winfo_width(),650)
        height = max(c.winfo_height(),480)
        root_x = 150
        root_y = height / 2
        c.create_rectangle(20,root_y-38,280,root_y+38, fill='#244c47', outline=ACCENT)
        c.create_text(root_x, root_y-8, text=self.report.name[:27], fill=INK, font=('Segoe UI',13,'bold'))
        c.create_text(root_x, root_y+16, text=f'{len(self.report.manifests)} manifests · build unverified', fill=ACCENT, font=('Segoe UI',9))
        for i,group in enumerate(groups):
            y = 45 + i * (height-90) / max(len(groups)-1,1)
            x = width - 260
            c.create_line(280,root_y,x,y, fill='#3b5764', width=2)
            findings = [f for f in self.report.findings if f.category == group]
            done = sum(self.store.task(self.report.root,f.id)[0] == 'Done' for f in findings)
            tag = f'category{i}'
            c.create_rectangle(x,y-27,width-20,y+27,fill=PANEL,outline='#405562',tags=tag)
            c.create_text(x+14,y-7,anchor='w',text=group,fill=INK,font=('Segoe UI',11,'bold'),tags=tag)
            c.create_text(x+14,y+13,anchor='w',text=f'{len(findings)} findings · {done} tasks done',fill=MUTED,font=('Segoe UI',9),tags=tag)
            c.tag_bind(tag,'<Button-1>',lambda e,g=group:self.map_filter(g))
        c.create_text(20,height-12,anchor='sw',text='Planning map • Connections group static findings, not verified build dependencies.',fill=MUTED,font=('Segoe UI',9))

    def map_filter(self, group):
        self.filter_category.set(group)
        self.render_findings()
        self.tabs.select(self.findings_tab)

    def export(self):
        if not self.report or not self.discard_guard():
            return
        path = filedialog.asksaveasfilename(title='Export GitRevival report', defaultextension='.md',
                initialfile=f'{self.report.name}-revival.md', filetypes=[('Markdown report','*.md'),('JSON report','*.json'),('CSV backlog','*.csv')])
        if path:
            try:
                export_report(self.report,self.store,path)
                self.footer_var.set('Report exported. It includes repository paths, evidence snippets and your notes; review before sharing.')
            except OSError as exc:
                messagebox.showerror('Export failed',str(exc))

    def close(self):
        if self.discard_guard() and self.discovery.guard():
            self._save_session()
            self.store.close()
            self.destroy()

    def destroy(self):
        for callback in self.tk.call('after','info'):
            self.tk.call('after','cancel',callback)
        super().destroy()

def main():
    parser = argparse.ArgumentParser(description='GitRevival desktop workbench')
    parser.add_argument('repository', nargs='?')
    parser.add_argument('--discover',action='store_true',help='Open the saved revival shortlist')
    args = parser.parse_args()
    app = App()
    if args.repository:
        app.after(200, lambda: app.scan(args.repository))
    elif not args.discover:
        app.after(200, app.restore_session)
    if args.discover:
        app.tabs.select(app.discovery)
        if app.store.candidates():
            app.discovery.show_saved()
        else:
            app.discovery.cached_search()
    app.mainloop()

if __name__ == '__main__':
    main()

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
from .store import Store, STATES, restore, export_report

BG = '#101820'
PANEL = '#18232e'
INK = '#e6edf3'
MUTED = '#9aaebc'
ACCENT = '#68dac2'

class App(tk.Tk):
    def __init__(self, state_path=None):
        super().__init__()
        self.title('GitRevival · Project resurrection workbench')
        self.geometry('1380x880')
        self.minsize(1120, 820)
        self.configure(bg=BG)
        self.store = Store(state_path or Path(__file__).resolve().parent.parent / '.local' / 'workspace.sqlite3')
        self.report = None
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

        body = ttk.Panedwindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=24)
        sidebar = ttk.Frame(body, width=235)
        body.add(sidebar, weight=0)
        ttk.Label(sidebar, text='WORKSPACE', style='Muted.TLabel').pack(anchor='w', pady=(12,10))
        self.projects = tk.Listbox(sidebar, bg=PANEL, fg=INK, selectbackground='#27574f',
                                   font=('Segoe UI',11), relief='flat', borderwidth=0, exportselection=False, width=25)
        self.projects.pack(fill='both', expand=True, padx=(0,14))
        self.projects.bind('<<ListboxSelect>>', self.choose_project)
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
        ttk.Button(controls, text='Export report', command=self.export).pack(side='right')
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
        ttk.Entry(filters, textvariable=self.search, width=29).pack(side='left', padx=8)
        self.search.trace_add('write', lambda *_: self.render_findings())
        self.filter_state = tk.StringVar(value='All states')
        box = ttk.Combobox(filters, textvariable=self.filter_state, values=('All states',)+STATES, state='readonly', width=15)
        box.pack(side='left', padx=8)
        box.bind('<<ComboboxSelected>>', lambda e: self.render_findings())
        self.filter_category = tk.StringVar(value='All categories')
        self.category_box = ttk.Combobox(filters, textvariable=self.filter_category, values=('All categories',), state='readonly', width=16)
        self.category_box.pack(side='left')
        self.category_box.bind('<<ComboboxSelected>>', lambda e: self.render_findings())
        split = ttk.Panedwindow(self.findings_tab, orient='vertical')
        split.pack(fill='both', expand=True)
        listframe = ttk.Frame(split)
        split.add(listframe, weight=3)
        self.findings = self.make_tree(listframe, ('status','category','title'), ('Task state','Area','Finding'), (115,120,540))
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
        ttk.Button(editrow, text='Save task & notes', command=self.save_task).pack(side='right')
        ttk.Label(detail, text='Notes / build commands / validation evidence', style='Muted.TLabel').pack(anchor='w')
        self.notes = self.textbox(detail, height=3, editable=True)
        self.notes.edit_modified(False)
        def initial_split(event):
            if event.height > 300:
                split.sashpos(0, int(event.height * 0.36))
                split.unbind('<Configure>')
        split.bind('<Configure>', initial_split)

        ttk.Label(self.map_tab, text='Repository → inspection areas → findings. Click an area to filter the backlog.', style='Muted.TLabel').pack(anchor='w', pady=(0,8))
        self.canvas = tk.Canvas(self.map_tab, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw_map())
        self.dependencies = self.make_tree(self.deps_tab, ('name','version','eco','file'), ('Dependency','Declared version / constraint','Ecosystem','Manifest'), (220,230,130,300))
        self.scope = self.textbox(self.scope_tab)
        from .discovery import Discovery
        self.discovery = Discovery(self.tabs,self)
        self.tabs.add(self.discovery,text='Discover & GitHub')
        self.footer_var = tk.StringVar(value='Local inspection • Optional GitHub checks in Discover & GitHub • Build status unverified')
        ttk.Label(self, textvariable=self.footer_var, style='Muted.TLabel', padding=(24,12)).pack(fill='x')
        self.refresh_projects()
        self.after(100, self.poll)
        self.bind('<Control-o>', lambda e: self.open_repo())
        self.bind('<Control-s>', lambda e: self.save_task())

    def make_tree(self, parent, columns, labels, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for col,label,width in zip(columns,labels,widths):
            tree.heading(col, text=label)
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
        for item in self.dependencies.get_children():
            self.dependencies.delete(item)
        for d in report.dependencies:
            self.dependencies.insert('', 'end', values=(d.name,d.version,d.ecosystem,d.file))
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
        self.footer_var.set(f'{len(report.warnings)} scope warnings • Saved locally • Build status unverified')

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
            if query not in f'{f.title} {f.file} {f.evidence} {f.category}'.casefold():
                continue
            self.findings.insert('', 'end', iid=f.id, values=(state,f.category,f.title))
        if previous and self.findings.exists(previous[0]):
            self.findings.selection_set(previous[0])
        r = self.report
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
        self.notes.delete('1.0','end')
        self.notes.insert('1.0', notes)
        self.notes.edit_modified(False)

    def save_task(self):
        if self.selected and self.report:
            try:
                self.store.save_task(self.report.root,self.selected.id,self.status_var.get(),self.notes.get('1.0','end-1c'))
                self.notes.edit_modified(False)
                self.render_findings()
                self.draw_map()
                self.footer_var.set('Task and notes saved. Completion is manually recorded; build status remains unverified.')
                return True
            except Exception as exc:
                messagebox.showerror('Could not save task',str(exc))
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
                initialfile=f'{self.report.name}-revival.md', filetypes=[('Markdown report','*.md'),('JSON report','*.json')])
        if path:
            try:
                export_report(self.report,self.store,path)
                self.footer_var.set('Report exported. It includes repository paths, evidence snippets and your notes; review before sharing.')
            except OSError as exc:
                messagebox.showerror('Export failed',str(exc))

    def close(self):
        if self.discard_guard() and self.discovery.guard():
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
    if args.discover:
        app.tabs.select(app.discovery)
        if app.store.candidates():
            app.discovery.show_saved()
        else:
            app.discovery.cached_search()
    app.mainloop()

if __name__ == '__main__':
    main()

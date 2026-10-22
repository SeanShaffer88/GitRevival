"""Discovery UI, local shortlist and asynchronous GitHub checks."""
from datetime import datetime, timedelta, timezone
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
from .github import GitHubClient, repository_name, local_origin, lead_signals, evidence_text

class Discovery(ttk.Frame):
    def __init__(self, parent, app, client=None):
        super().__init__(parent,padding=12)
        self.app = app
        self.store = app.store
        self.client = client or GitHubClient()
        self.events = queue.Queue()
        self.busy = False
        self.selected = None
        self.items = {}
        self.payload = None
        self.current_query = None
        self.current_page = 1
        self.network_buttons = []
        cutoff = (datetime.now(timezone.utc)-timedelta(days=730)).date().isoformat()
        self.presets = {
            'Niche desktop GUIs':f'gui in:description stars:10..5000 pushed:<{cutoff} fork:false',
            'Windows tools':f'windows in:description,topics stars:25..5000 pushed:<{cutoff} fork:false',
            'C++ libraries':f'language:C++ stars:>=25 pushed:<{cutoff} fork:false',
            'Python tools':f'language:Python stars:>=25 pushed:<{cutoff} fork:false',
            'Archived projects':'archived:true stars:>=25 fork:false',
        }
        row = ttk.Frame(self)
        row.pack(fill='x')
        self.preset = tk.StringVar(value='Niche desktop GUIs')
        presets = ttk.Combobox(row,textvariable=self.preset,values=tuple(self.presets),state='readonly',width=18)
        presets.pack(side='left')
        presets.bind('<<ComboboxSelected>>',lambda e:self.query.set(self.presets[self.preset.get()]))
        self.query = tk.StringVar(value=self.presets[self.preset.get()])
        query_entry = ttk.Entry(row,textvariable=self.query)
        query_entry.pack(side='left',fill='x',expand=True,padx=8)
        query_entry.bind('<Return>',lambda e:self.search(1))
        self.button(row,'Search GitHub',lambda:self.search(1),network=True)
        self.button(row,'Saved shortlist',self.show_saved)
        row = ttk.Frame(self)
        row.pack(fill='x',pady=8)
        ttk.Label(row,text='Repository').pack(side='left')
        self.repo_var = tk.StringVar()
        repo_entry = ttk.Entry(row,textvariable=self.repo_var,width=33)
        repo_entry.pack(side='left',fill='x',expand=True,padx=8)
        repo_entry.bind('<Return>',lambda e:self.check())
        self.button(row,'Check repository',self.check,network=True)
        self.button(row,'Use local origin',self.use_origin)
        self.button(row,'Link to local project',self.link)
        row = ttk.Frame(self)
        row.pack(fill='x')
        self.link_var = tk.StringVar(value='No local project selected. Paste owner/repository or a GitHub URL to check.')
        ttk.Label(row,textvariable=self.link_var,style='Muted.TLabel',wraplength=850).pack(anchor='w')
        row = ttk.Frame(self)
        row.pack(fill='x',pady=6)
        self.button(row,'Previous page',lambda:self.search(self.current_page-1),network=True)
        self.button(row,'Next page',lambda:self.search(self.current_page+1),network=True)
        self.button(row,'Load cached search',self.cached_search)
        self.button(row,'Show linked evidence',self.show_linked)
        self.button(row,'Export shortlist',self.export)
        self.info = tk.StringVar(value='No network requests on startup. Search sends only your query to GitHub. Saved evidence may be stale.')
        ttk.Label(self,textvariable=self.info,style='Muted.TLabel',wraplength=870).pack(anchor='w',pady=(0,8))
        split = ttk.Panedwindow(self,orient='vertical')
        split.pack(fill='both',expand=True)
        listing = ttk.Frame(split)
        split.add(listing,weight=2)
        self.tree = app.make_tree(listing,('score','repo','language','stars','push','license','state'),
                ('Lead /5','Repository','Language','Stars','Last push (UTC)','License ID','State'),(70,240,90,65,120,105,105))
        self.tree.bind('<<TreeviewSelect>>',self.select)
        bottom = ttk.Frame(split,padding=(0,8,0,0))
        split.add(bottom,weight=3)
        self.detail = app.textbox(bottom,height=5)
        app.set_text(self.detail,'Find a candidate, inspect its live evidence, then save it to the shortlist.\nScores prioritize research only; they do not establish value, permissions or repair feasibility.')
        row = ttk.Frame(bottom)
        row.pack(fill='x',pady=5)
        self.candidate_state = tk.StringVar(value='Research')
        state = ttk.Combobox(row,textvariable=self.candidate_state,values=('Research','Promising','Investigating','Reviving','Passed'),state='readonly',width=14)
        state.pack(side='left')
        state.bind('<<ComboboxSelected>>',lambda e:self.notes.edit_modified(True))
        self.button(row,'Save to shortlist',self.save)
        self.button(row,'Check selected',self.check_selected,network=True)
        self.button(row,'Open on GitHub',self.open_browser)
        ttk.Label(bottom,text='Research notes: unique benefit • alternatives • repair effort • permission questions • ownership',style='Muted.TLabel').pack(anchor='w')
        self.notes = app.textbox(bottom,height=3,editable=True)
        self.notes.edit_modified(False)
        def layout(event):
            if event.height > 260:
                split.sashpos(0,int(event.height*0.32))
                split.unbind('<Configure>')
        split.bind('<Configure>',layout)
        self.after(100,self.poll)

    def button(self, row, title, command, network=False):
        button = ttk.Button(row,text=title,command=command)
        button.pack(side='left',padx=(0,6))
        if network:
            self.network_buttons.append(button)
        return button

    def guard(self):
        if self.selected and self.notes.edit_modified():
            answer = messagebox.askyesnocancel('Unsaved candidate notes','Save candidate notes before continuing?',parent=self)
            if answer is None:
                return False
            if answer:
                return self.save()
            self.notes.edit_modified(False)
        return True

    def start(self, operation, function):
        if self.busy or not self.guard():
            return
        self.busy = True
        for button in self.network_buttons:
            button.configure(state='disabled')
        self.info.set('Contacting GitHub… read-only requests; each request has a 12-second timeout.')
        def work():
            try:
                self.events.put((operation,function()))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            operation,result = self.events.get_nowait()
            self.busy = False
            for button in self.network_buttons:
                button.configure(state='normal')
            if operation == 'error':
                self.info.set('GitHub check failed: '+result+' Saved evidence is unchanged.')
            elif operation == 'search':
                self.store.save_search(result)
                if self.guard():
                    self.show_search(result)
            else:
                snapshot,requested = result
                self.store.save_check(snapshot,previous=requested)
                if self.guard():
                    self.show_items([snapshot])
                    self.tree.selection_set(snapshot['full_name'].casefold())
                    self.select()
                    self.info.set(f'Live check at {snapshot["checked_at"]} • {self.rate_text(snapshot.get("rate",{}))} • {len(snapshot["warnings"])} warnings; see evidence.')
                self.project_changed()
        except queue.Empty:
            pass
        except Exception as exc:
            self.info.set('Could not store or display GitHub evidence: '+str(exc))
        self.after(100,self.poll)

    @staticmethod
    def rate_text(rate):
        return f'API {rate.get("resource","unknown")}: {rate.get("remaining","unknown")}/{rate.get("limit","unknown")} requests remain; reset UTC {rate.get("reset","unknown")}'

    def search(self, page=1):
        query = self.query.get().strip() if page == 1 else self.current_query
        if not query:
            self.info.set('Run a first-page search before paging.')
            return
        if page < 1 or page > 40 or (page > 1 and self.payload and (page-1)*25 >= min(self.payload['total_count'],1000)):
            self.info.set('No further page within GitHub’s first 1,000 results. Narrow the query.')
            return
        self.start('search',lambda:self.client.search(query,page))

    def show_search(self, payload, cached=False):
        self.payload = payload
        self.current_query = payload['query']
        self.current_page = payload['page']
        self.query.set(payload['query'])
        self.show_items(payload['items'])
        prefix = 'CACHED — not refreshed' if cached else 'LIVE search'
        partial = ' • GitHub reports incomplete results' if payload['incomplete_results'] else ''
        self.info.set(f'{prefix}: {payload["checked_at"]} • Page {payload["page"]} • {payload["total_count"]:,} matches (first 1,000 accessible){partial} • {self.rate_text(payload.get("rate",{}))}')

    def cached_search(self):
        if not self.guard():
            return
        query = self.query.get().strip()
        page = self.current_page if query == self.current_query else 1
        payload = self.store.github_search(query,page)
        if payload:
            self.show_search(payload,cached=True)
        else:
            self.info.set('No saved search for this exact query and page. Run Search GitHub first.')

    def show_items(self, items):
        self.selected = None
        self.notes.delete('1.0','end')
        self.notes.edit_modified(False)
        self.app.set_text(self.detail,'Select a result to see its evidence and research-priority signals.')
        self.items = {x['full_name'].casefold():x for x in items}
        self.tree.delete(*self.tree.get_children())
        for key,item in sorted(self.items.items(),key=lambda entry:(-lead_signals(entry[1])[0],-entry[1]['stars'],entry[0])):
            status = self.store.candidate(key)
            self.tree.insert('','end',iid=key,values=(lead_signals(item)[0],item['full_name'],item['language'],item['stars'],(item.get('pushed_at') or 'Unknown')[:10],item['license'],status[0] if status else 'Unsaved'))

    def select(self,event=None):
        selection = self.tree.selection()
        if not selection or (self.selected and selection[0] == self.selected['full_name'].casefold()):
            return
        if not self.guard():
            if self.selected and self.tree.exists(self.selected['full_name'].casefold()):
                self.tree.selection_set(self.selected['full_name'].casefold())
            return
        self.selected = self.items[selection[0]]
        self.repo_var.set(self.selected['full_name'])
        self.app.set_text(self.detail,evidence_text(self.selected))
        saved = self.store.candidate(self.selected['full_name'])
        self.candidate_state.set(saved[0] if saved else 'Research')
        self.notes.delete('1.0','end')
        self.notes.insert('1.0',saved[1] if saved else '')
        self.notes.edit_modified(False)

    def save(self):
        if not self.selected:
            self.info.set('Select or check a repository first.')
            return False
        try:
            self.store.save_candidate(self.selected,self.candidate_state.get(),self.notes.get('1.0','end-1c'))
            self.notes.edit_modified(False)
            self.tree.set(self.selected['full_name'].casefold(),'state',self.candidate_state.get())
            self.info.set('Candidate and research notes saved locally. No GitHub repository was modified.')
            return True
        except Exception as exc:
            self.info.set('Could not save candidate: '+str(exc))
            return False

    def show_saved(self):
        if self.guard():
            self.show_items([item for item,_,_ in self.store.candidates()])
            self.info.set(f'SAVED SHORTLIST • {len(self.items)} candidates • Evidence may be stale; select and Check selected to refresh.')

    def check(self):
        try:
            name = repository_name(self.repo_var.get())
        except ValueError as exc:
            self.info.set(str(exc))
            return
        self.start('check',lambda:(self.client.check(name),name))

    def check_selected(self):
        if self.selected:
            self.repo_var.set(self.selected['full_name'])
            self.check()

    def use_origin(self):
        if not self.app.report:
            self.info.set('Open a local repository first, or paste a GitHub URL above.')
            return
        try:
            self.repo_var.set(local_origin(self.app.report.root))
            self.info.set('Origin read locally. Check repository to retrieve evidence; Link to local project to associate it.')
        except (OSError,ValueError) as exc:
            self.info.set(str(exc))

    def project_changed(self):
        root = self.app.report.root if self.app.report else None
        name = self.store.upstream(root) if root else None
        self.link_var.set(f'Local project: {self.app.report.name} • Linked GitHub upstream: {name or "none"}' if root else 'No local project selected. Paste owner/repository or a GitHub URL to check.')

    def link(self):
        if not self.app.report or not self.selected:
            self.info.set('Open a local project and select a GitHub result before linking.')
            return
        self.store.save_check(self.selected) if not self.store.github_check(self.selected['full_name']) else None
        self.store.link_upstream(self.app.report.root,self.selected['full_name'])
        self.project_changed()
        self.info.set('Upstream linked. Local report exports will include the saved GitHub evidence and its timestamp.')

    def show_linked(self):
        if not self.app.report or not self.guard():
            return
        name = self.store.upstream(self.app.report.root)
        snapshot = self.store.github_check(name) if name else None
        if snapshot:
            self.show_items([snapshot])
            self.tree.selection_set(snapshot['full_name'].casefold())
            self.select()
            self.info.set('SAVED upstream evidence — not refreshed. Check selected to retrieve current GitHub data.')
        else:
            self.info.set('No saved upstream evidence for this local project.')

    def open_browser(self):
        if self.selected:
            # Reconstruct a validated URL; never trust a remote html_url as a launch target.
            webbrowser.open('https://github.com/'+repository_name(self.selected['full_name']))

    def export(self):
        if not self.guard():
            return
        path = filedialog.asksaveasfilename(parent=self,title='Export GitRevival shortlist',initialfile='GitRevival-shortlist.md',defaultextension='.md',filetypes=[('Markdown','*.md'),('JSON','*.json')])
        if not path:
            return
        from pathlib import Path
        entries = [{'repository':item,'status':status,'notes':notes} for item,status,notes in self.store.candidates()]
        try:
            if path.lower().endswith('.json'):
                text = json.dumps(entries,indent=2,ensure_ascii=False)
            else:
                lines = ['# GitRevival — revival candidates','', 'Saved evidence; see each retrieval timestamp. Priorities are research leads, not feasibility assessments.','']
                for entry in entries:
                    lines += ['## '+entry['repository']['full_name'], '', 'Status: '+entry['status'], '', evidence_text(entry['repository']), '', 'Research notes:', entry['notes'], '']
                text = '\n'.join(lines)
            Path(path).write_text(text,encoding='utf-8')
            self.info.set('Saved shortlist exported, including evidence timestamps and research notes.')
        except OSError as exc:
            self.info.set('Export failed: '+str(exc))

"""Hover tooltips for Tk widgets, using only the standard library.

Every interactive control in GitRevival carries a tooltip (see
PROJECT_RULES.md). A tooltip is attached with add_tooltip(); the widget
remembers its text as ``_tooltip_text`` so tests can verify coverage.
"""
import tkinter as tk


class Tooltip:
    """Shows a small plain-words hint after the pointer rests on a widget."""

    def __init__(self, widget, text, delay=600):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._window = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')
        widget.bind('<Destroy>', self._hide, add='+')

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._window is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(f'+{x}+{y}')
        label = tk.Label(window, text=self.text, justify='left', wraplength=340,
                         bg='#2b4c50', fg='#e6edf3', font=('Segoe UI', 9),
                         padx=8, pady=5, relief='solid', borderwidth=1)
        label.pack()
        self._window = window

    def _hide(self, event=None):
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None


def add_tooltip(widget, text):
    """Attach a tooltip to a widget and record its text on the widget."""
    widget._tooltip_text = text
    widget._tooltip = Tooltip(widget, text)
    return widget


# Tooltip text for every button, keyed by the button's label. install_tooltips
# walks a window and covers any button whose label is listed here, including
# buttons built by the Discovery and Planning panels.
BUTTON_TOOLTIPS = {
    '+ Open repository': 'Open a local repository folder and inspect it. Nothing in the folder is run or changed.',
    'Find projects to revive': 'Jump to finding abandoned GitHub projects that may be worth reviving.',
    'Load demo': 'Inspect the small sample project included with GitRevival.',
    'Help': 'Open the built-in guide: how to use GitRevival, in plain words. Works offline (F1).',
    'Export report': 'Save the current inspection as a Markdown, JSON or CSV report. Reports include local paths and your notes — check before sharing.',
    'Rescan': 'Inspect the current repository again (F5). Task states and notes are kept.',
    'Save task & notes': 'Save the selected task state, priority, due date and notes. Notes also save on their own as you type.',
    'Search GitHub': 'Search GitHub for revival candidates. This is the only step that uses the network, and it only sends your search text.',
    'Saved shortlist': 'Show the candidates you saved, from this computer only. No network request.',
    'Check repository': 'Fetch live evidence for the named GitHub repository. Read-only; nothing is changed on GitHub.',
    'Use local origin': 'Fill in the GitHub address from the open project’s own Git settings, read locally.',
    'Link to local project': 'Connect the selected GitHub result to the open local project, so its saved evidence appears in that project’s reports.',
    'Previous page': 'Show the previous page of search results.',
    'Next page': 'Show the next page of search results (up to GitHub’s first 1,000 matches).',
    'Load cached search': 'Show the saved copy of this exact search from this computer, without contacting GitHub.',
    'Show linked evidence': 'Show the saved GitHub evidence linked to the open local project. Not refreshed.',
    'Export shortlist': 'Save your saved candidates, their evidence dates and your research notes as Markdown or JSON.',
    'Save to shortlist': 'Save this candidate, its research state and your notes on this computer.',
    'Check selected': 'Fetch fresh live evidence for the selected candidate from GitHub. Read-only.',
    'Open on GitHub': 'Open the selected repository’s GitHub page in your web browser.',
    'Add custom task': 'Add your own repair task to the current project. It is kept across rescans.',
    'Task history': 'Show the saved history of changes to the selected task.',
    'Refresh snapshots': 'Reload the list of saved scans for the current project.',
    'Back up workspace': 'Create a checked backup copy of all projects, tasks and notes. Keep it private — it contains local paths and notes.',
    'Close help': 'Close this guide.',
}


def install_tooltips(root):
    """Attach tooltips to every button under root whose label is known.

    Returns the number of buttons covered. Widgets that already carry a
    tooltip are left alone.
    """
    covered = 0
    stack = [root]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if getattr(widget, '_tooltip_text', None):
            covered += 1
            continue
        try:
            label = widget.cget('text')
        except tk.TclError:
            continue
        if isinstance(label, str) and label in BUTTON_TOOLTIPS and 'Button' in widget.winfo_class():
            add_tooltip(widget, BUTTON_TOOLTIPS[label])
            covered += 1
    return covered

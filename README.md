# GitRevival

A local desktop workbench for bringing old software projects back to life.

**Version 0.1.0 — first working milestone.** Python 3.11+ with Tcl/Tk is required. No third-party Python packages or connected accounts are required. Tested on Windows with Python 3.15 and Tk 9.0; other platforms are not yet validated.

## Start

On Windows, double-click **Start GitRevival.bat** or **launch.pyw**. Alternatively, open a terminal in this folder and run:

```powershell
python -m gitrevival.app
# Optionally open a repository immediately:
python -m gitrevival.app "C:\path\to\repository"
```

Choose **Load demo** to inspect a deliberately incomplete synthetic project. Choose **Open repository** to inspect your own local checkout. No clone or network request occurs.

## Workflow

1. Inspect a repository. Review **Scan scope** for exclusions and warnings.
2. Browse the **Repair backlog**. Each finding includes evidence, source location, confidence, and a suggested next step.
3. Use **Revival map** to navigate inspection areas. **Dependencies** lists directly declared dependencies extracted by supported parsers.
4. Set tasks to Queued, In progress, Blocked, Done or Dismissed. Add build commands, test evidence and decisions to notes; click **Save task & notes** or Ctrl+S.
5. Rescan after changes. Unchanged finding IDs retain task state and notes. Previously recorded findings remain in older exports; the current view shows current scan findings.
6. Export Markdown or JSON for working with a coding assistant or preparing a revival plan. Exports include local paths, manifest snippets and notes; review them before sharing.

Projects and notes are stored in `.local/workspace.sqlite3` beside the application. Back up that folder to retain your workspace; source packages exclude it. Keep the app in a writable folder. Notes are plain local SQLite data, not encrypted. Identical folder names can appear separately in the project list; the selected repository's full path appears above the tabs.

## Inspection coverage

- Node package declarations, lockfile presence and scripts.
- Python project dependencies, Poetry dependencies, requirements and interpreter constraints.
- Basic Cargo dependencies, Go module requirements and vcpkg manifests.
- CMake package declarations and minimum-version policy review.
- MSBuild/NuGet package references, .NET targets and Visual C++ toolsets.
- License-file discovery, missing README, Git submodule content and selected older GitHub Actions/runner patterns.

This is **static inspection**, not dependency resolution. It does not prove a dependency is broken, assess live upstream maintenance, query vulnerabilities, evaluate license compatibility, or run builds. Older declarations are review leads, not automatic failure verdicts. Task completion is a manual record and never a build-success claim.

The map groups findings by inspection area; it is not a transitive dependency graph. Parsers do not evaluate CMake, MSBuild properties, YAML, Python code, workspace/target Cargo tables, optional Python dependency groups or build conditions. Git metadata is excluded; commit age and remote archival status are not checked.

Reads are limited to selected text files: 15,000 inventoried files, 512 KB per inspected file, 12 MB total inspected text. Generated/vendor folders, virtual environments, symlinks and reparse directories are excluded. Scanning a live mutable tree is best effort; use a stable checkout for consistent results. Do not treat inspection as a sandbox or scan hostile files with elevated privileges.

## Development

```powershell
python -m unittest discover -s tests -v
```

The GUI smoke test creates and closes a real Tk window. Tests use temporary state. No project fixture is installed or executed.

Architecture: `analyzer.py` performs bounded read-only inspection; `store.py` saves task state and exports reports; `app.py` owns Tk UI and moves inspection to a worker thread. All Tk and SQLite work stays on the GUI thread.

## Next useful milestones

- Review explicit build-environment profiles and capture build logs in isolation.
- Optional upstream checks for canonical repositories, release status and advisories, with dated evidence.
- Richer dependency edges, baseline comparisons and source-file navigation.
- A discovery queue of candidate projects with benefits, alternatives, licensing questions and revival effort.
- A packaged Windows executable and CI across supported interpreter versions.

## Technology decision (2026-10-22)

Consulted the shared resource catalog's desktop SDK and language sections. Chose Python's standard-library Tkinter/ttk and SQLite: they support a local GUI and persistence without a package installation. Avalonia, Qt and Tauri remain candidates if richer native UI or executable packaging warrants additional dependencies. Confirmed local Tk 9.0.4 availability and checked the Python upstream documentation. No new catalog resource was discovered or added.

Sources: [Tkinter](https://docs.python.org/3/library/tkinter.html), [sqlite3](https://docs.python.org/3/library/sqlite3.html). Python and Tcl/Tk have their own upstream licenses; they are prerequisites and are not bundled in this source distribution.

MIT licensed. The demo is an original synthetic fixture and is not a vendored upstream project.

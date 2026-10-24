# GitRevival

A local desktop workbench for bringing old software projects back to life.

**Version 0.3.0 — planning, scan history, backups and headless inspection.** Python 3.11+ with Tcl/Tk is required. No third-party Python packages or connected accounts are required. Tested on Windows with Python 3.15 and Tk 9.0; other platforms are not yet validated.

## Windows portable download

The 0.3.0 release supplies `GitRevival-0.3.0-win-x64.zip` with isolated CPython 3.15.1/Tcl-Tk. Extract into a writable folder and run **Start GitRevival.bat**; no installed Python is required. To update, close the app, back up `.local`, then copy that folder into the new app folder. Source ZIPs retain the Python 3.11+ requirement below. Runtime notices and per-file hashes accompany the portable ZIP.

## Start

On Windows, double-click **Start GitRevival.bat** or **launch.pyw**. Alternatively, open a terminal in this folder and run:

```powershell
python -m gitrevival.app
# Optionally open a repository immediately:
python -m gitrevival.app "C:\path\to\repository"
```

Choose **Load demo** to inspect a deliberately incomplete synthetic project. Choose **Open repository** to inspect your own local checkout. Local inspection makes no network requests. **Discover & GitHub** offers explicit read-only network actions; no cloning occurs.

## Workflow

1. Inspect a repository. Review **Scan scope** for exclusions and warnings.
2. Browse the **Repair backlog**. Each finding includes evidence, source location, confidence, and a suggested next step.
3. Use **Revival map** to navigate inspection areas. **Dependencies** lists directly declared dependencies extracted by supported parsers.
4. Set tasks to Queued, In progress, Blocked, Done or Dismissed. Add build commands, test evidence and decisions to notes; click **Save task & notes** or Ctrl+S.
5. Rescan after changes. Unchanged finding IDs retain task state and notes. Previously recorded findings remain in older exports; the current view shows current scan findings.
6. Export Markdown or JSON for working with a coding assistant or preparing a revival plan. Exports include local paths, manifest snippets and notes; review them before sharing.

Projects and notes are stored in `.local/workspace.sqlite3` beside the application. Back up that folder to retain your workspace; source packages exclude it. Keep the app in a writable folder. Notes are plain local SQLite data, not encrypted. Identical folder names can appear separately in the project list; the selected repository's full path appears above the tabs.

## Planning and review improvements (0.3.0)

1. **Severity filter:** limit the backlog to Review or Info findings alongside existing search/state/category filters.
2. **Dependency search:** search extracted names, constraints, ecosystems and manifest paths.
3. **Sortable columns:** click any table heading to sort; click again to reverse. Numeric values sort numerically; version constraints sort as text when nonnumeric. Refreshing a table restores its default order.
4. **Completion progress:** the workspace sidebar shows Done/total tasks, including custom tasks. Dismissed tasks remain in the denominator. This records manual planning progress, not build success.
5. **Task priorities:** Low, Normal, High and Urgent are saved with notes and shown as sortable backlog columns.
6. **Due dates:** optional, validated YYYY-MM-DD calendar dates appear in the backlog and exports. Dates do not create reminders or background activity.
7. **Custom repair tasks:** Planning & history → Add custom task records a title and acceptance criteria. These are labeled Manual/Custom, persist across rescans and can be dismissed using the existing task states.
8. **Task change history:** select a task, then Planning & history → Task history. Each save records state, notes, priority, due date and UTC time. The newest 100 saves are displayed; older events remain in the workspace. History starts with this version.
9. **Scan snapshots:** the latest 20 static scans per project are retained. Existing projects gain their previous saved scan during automatic additive migration.
10. **Finding differences:** select exactly two scan snapshots to see added, removed, evidence-changed and unchanged findings. Comparison uses stable IDs and inspection fields. Removed findings may reflect exclusions, parsing changes or incomplete scans; they do not prove a repair. Snapshots do not contain historical task states.
11. **Workspace backups:** Planning & history → Back up workspace creates a new SQLite file using SQLite's consistent backup API and checks its integrity. Existing files are refused. To restore, close GitRevival, preserve the current workspace separately, then copy the backup to `.local/workspace.sqlite3`. Backups include local paths, notes and cached GitHub metadata; keep them private.
12. **CSV backlog exports:** Export report now offers CSV with states, priorities, dates, evidence and notes. Formula-like cells receive an apostrophe prefix for spreadsheet safety. Markdown/JSON also include priority and due dates.
13. **Headless inspection:** run the bounded static scanner without importing Tk, opening the workspace or contacting GitHub:

    ```powershell
    python -m gitrevival.cli inspect "C:\path\to\repository" --output scan.json
    ```

14. **Headless report comparison:** compare two GitRevival JSON reports (20 MB input limit each):

    ```powershell
    python -m gitrevival.cli compare before.json after.json --output changes.json
    ```

    CLI outputs must be new files. Inspection returns 0 on a completed bounded scan (review scope warnings); comparison returns 0 for no finding differences, 1 for differences, and either command returns 2 for errors. These codes do not verify a build.
15. **Keyboard review:** Ctrl+F focuses backlog search, F5 rescans, F1 shows shortcut help; Ctrl+O and Ctrl+S remain available.

## Inspection coverage

- Node package declarations, lockfile presence and scripts.
- Python project dependencies, Poetry dependencies, requirements and interpreter constraints.
- Basic Cargo dependencies, Go module requirements and vcpkg manifests.
- CMake package declarations and minimum-version policy review.
- MSBuild/NuGet package references, .NET targets and Visual C++ toolsets.
- License-file discovery, missing README, Git submodule content and selected older GitHub Actions/runner patterns.

Local inspection is **static inspection**, not dependency resolution. It does not prove a dependency is broken, query vulnerabilities, evaluate license compatibility, or run builds. The optional discovery view retrieves dated GitHub maintenance signals separately. Older declarations are review leads, not automatic failure verdicts. Task completion is a manual record and never a build-success claim.

The map groups findings by inspection area; it is not a transitive dependency graph. Parsers do not evaluate CMake, MSBuild properties, YAML, Python code, workspace/target Cargo tables, optional Python dependency groups or build conditions. Git metadata is excluded from the local scanner; the optional **Use local origin** action reads an ordinary `.git/config` without executing Git or loading included config files. For worktrees, paste the upstream manually.

Reads are limited to selected text files: 15,000 inventoried files, 512 KB per inspected file, 12 MB total inspected text. Generated/vendor folders, virtual environments, symlinks and reparse directories are excluded. Scanning a live mutable tree is best effort; use a stable checkout for consistent results. Do not treat inspection as a sandbox or scan hostile files with elevated privileges.

## Discover promising revival candidates

Open **Discover & GitHub** without opening a local repository. Choose a preset and click **Search GitHub**, or edit the GitHub repository search query directly. Presets include niche desktop GUIs, Windows tools, C++ libraries, Python tools and archived projects. The default GUI search looks for descriptions containing `gui`, 10–5,000 stars, no pushes for roughly two years, and non-forks; these are editable research filters, not abandonment claims. Archived repositories remain eligible.

Search pages contain up to 25 results. GitHub supplies pages sorted by stars; GitRevival orders each fetched page by its research-priority score. **Previous page** and **Next page** access up to GitHub's first 1,000 matches. Narrow the query for larger searches. Truncated results reported by GitHub are labeled. Search indexing and push dates do not establish maintenance status or whether a project needs revival.

Select a result to see timestamped metadata and the rationale for its **0–5 research-priority score**:

- 2 points when GitHub identifies a license other than `NOASSERTION`.
- 1 point for at least 25 stars, a weak historical-interest signal.
- 1 point when the last reported push is at least 730 days old.
- 1 point for declared topics, which provide clues about purpose.

This score is not a value, security, license compatibility or repair-feasibility assessment. A smaller or recently updated project may be a better choice. Assess unique benefit, maintained alternatives, fork permission, repair effort, platform support, security and long-term ownership in research notes. Set a candidate to Research, Promising, Investigating, Reviving or Passed, then **Save to shortlist**. **Saved shortlist** reads local data without contacting GitHub. **Export shortlist** writes Markdown or JSON with evidence dates and your notes.

**Check repository** accepts `owner/repository`, an HTTPS GitHub repository URL, or a GitHub SSH-style origin. **Check selected** refreshes a chosen candidate. Each live check requests:

- Repository metadata: current canonical name, archive/disabled/fork flags, parent, stars, last push, default branch and GitHub's detected SPDX license ID.
- The latest published non-prerelease release, if available. A release endpoint 404 is recorded as no matching release, not proof that the project has never released anything.
- One default-branch commit sample.
- The first five most recently updated open issue/PR entries, filtering pull requests out of the displayed sample. The metadata count is explicitly **issues + pull requests**; the sample is not a complete issue inventory.

Partial failures are retained alongside successful metadata. A denied/rate-limited request stops the remaining checks, shows reset/retry information when supplied, and never automatically retries. Each request has a 12-second network timeout and a 2 MB response limit. Reads are restricted to `api.github.com`; redirects outside that host are refused. No repository code, workflow or install hook is run. There is no background polling or scheduled monitoring.

**Use local origin** fills the repository field from the current local project's origin. **Link to local project** associates the selected result with the open local project. **Show linked evidence** loads its saved snapshot; local report exports include that evidence with its retrieval timestamp. Linking is explicit because a local fork's origin may differ from its intended upstream.

Successful searches and check snapshots are stored in the existing `.local/workspace.sqlite3` database. **Load cached search** reads the exact query and page locally and labels the result cached. Saved results are never silently presented as refreshed. Refreshing a shortlisted repository preserves research notes/status, including canonical repository renames; existing 0.1 workspaces migrate automatically. These are latest snapshots, not a full evidence history.

### GitHub access

Public access works without signing in. GitHub documents a 60-request/hour unauthenticated core budget and a separate search budget; actual returned rate headers are displayed. One full repository check normally costs four core requests. These budgets can also be consumed by other clients sharing the same IP.

For optional authenticated access, provide `GITREVIVAL_GITHUB_TOKEN` in the process environment before launching. The app reads only this explicit variable; it does not discover Git credentials, request account connections, or save the token to SQLite, exports or source. Requests remain GET-only. Grant only the read access needed. The app can access repositories permitted by that token; avoid exporting private metadata or sensitive research notes publicly.

API data is evidence supplied by GitHub, not a complete audit of upstream health, license texts, advisories, transitive dependencies or platform compatibility. GitHub's license detection does not establish permission to distribute all code/assets or compatibility with your intended product.

Upstream API documentation checked 2026-10-22: [repository search](https://docs.github.com/en/rest/search/search#search-repositories), [repository metadata](https://docs.github.com/en/rest/repos/repos#get-a-repository), [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api). Live public search and all four repository-check request paths were exercised on that date. HTTP uses Python's standard library; no new package dependency was adopted.

## Development

```powershell
python -m unittest discover -s tests -v
```

GUI smoke tests create and close real Tk windows, including asynchronous discovery/search/check/save/link/export flows. Tests use temporary state and mocked HTTP responses for deterministic failure and rate-limit coverage. No project fixture is installed or executed.

Architecture: `analyzer.py` performs bounded read-only inspection; `store.py` saves task state, candidates and evidence snapshots; `github.py` provides read-only API requests and explainable lead signals; `discovery.py` implements candidate research; `app.py` owns the main UI. Inspection and HTTP requests run in worker threads. All Tk and SQLite work stays on the GUI thread. Closing the window cancels pending UI callbacks; HTTP workers are daemon threads and hold no database connection.

## Next useful milestones

- Review explicit build-environment profiles and capture build logs in isolation.
- Optional advisory/license-text checks with dated evidence.
- Richer dependency edges, baseline comparisons and source-file navigation.
- More discovery signals and structured effort estimates validated against real revival work.
- A packaged Windows executable and CI across supported interpreter versions.

## Technology decision (2026-10-22)

Consulted the shared resource catalog's desktop SDK and language sections. Chose Python's standard-library Tkinter/ttk and SQLite: they support a local GUI and persistence without a package installation. Avalonia, Qt and Tauri remain candidates if richer native UI or executable packaging warrants additional dependencies. Confirmed local Tk 9.0.4 availability and checked the Python upstream documentation. No new catalog resource was discovered or added.

Sources: [Tkinter](https://docs.python.org/3/library/tkinter.html), [sqlite3](https://docs.python.org/3/library/sqlite3.html). Python and Tcl/Tk have their own upstream licenses; they are prerequisites and are not bundled in this source distribution.

MIT licensed. The demo is an original synthetic fixture and is not a vendored upstream project.

### Windows packaging

`python tools/package_windows.py --python-root PATH_TO_CPYTHON_3_15_1 --output NEW_PARENT` packages tracked sources and an isolated local runtime. No user state or site packages are copied. `python tools/test_portable.py --package PATH --results NEW_JSON` checks hashes, relocates to spaces/Unicode, exercises Tk, runs the complete test suite and CLI, and launches the windowed app with only System32 on PATH. Runtime notices, source URLs and hashes are under `licenses/runtime`. Interpreter binaries are unmodified; omitted optional tooling is documented in PORTABLE.txt.

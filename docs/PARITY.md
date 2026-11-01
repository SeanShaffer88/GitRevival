# GitRevival — Capability Parity

Scored only from code and test evidence. "GUI" is the desktop window, "CLI" is `python -m gitrevival.cli`, "Test" names the covering test file. Updated with the 0.5.0 CLI parity slice (2026-10-31).

| Capability | GUI | CLI | Evidence / test |
|---|---|---|---|
| Inspect a repository (bounded static scan) | Yes | Yes (`inspect`) | test_workbench, test_planning (headless) |
| Compare two JSON reports / scan snapshots | Yes (Planning & history) | Yes (`compare`) | test_planning |
| Repair backlog: filter, search, sort | Yes | No | test_workbench, test_planning (GUI) |
| Task state / priority / due date / notes | Yes (autosaves, 0.4.0) | No | test_workbench, test_planning, test_catchup |
| Custom repair tasks | Yes | No | test_planning |
| Task change history | Yes | No | test_planning |
| List saved projects | Yes (sidebar) | Yes (`projects`) | test_cli_parity |
| Scan snapshots (latest 20) and differences | Yes | Yes (`scans`, `diff-scans`, plus file-based `compare`) | test_planning, test_cli_parity |
| Export report (Markdown / JSON / CSV) | Yes | Yes (`export`, fresh inspection + saved task states) | test_workbench, test_planning, test_cli_parity |
| Workspace backup (checked, no overwrite) | Yes | Yes (`backup`) | test_planning, test_cli_parity |
| GitHub search + repository checks | Yes (explicit click) | No — deliberate: the CLI makes no network requests | test_github |
| Revival shortlist + research notes | Yes | Export only (`shortlist`); editing is GUI-only | test_github, test_cli_parity |
| Session restore: geometry, last project/tab, recents | Yes (0.4.0) | n/a | test_catchup |
| Tooltips on every interactive control | Yes (0.4.0) | n/a | test_catchup |
| Built-in plain-words guide (Help / F1) | Yes (0.4.0) | n/a | test_catchup |

## Parity plan

The 0.5.0 slice closed the planned gap: report export, workspace backup, snapshot listing/differences, project listing and shortlist export are all headless, dispatching the same store operations the GUI uses (the shortlist export itself moved into the store module so both surfaces produce identical files). What remains window-only, honestly: backlog browsing/editing, custom tasks, task history, and the GitHub discovery actions. The GitHub gap is deliberate — the command line makes no network requests, and changing that is its own decision, not a parity fix. Any future backlog/task CLI operations should likewise dispatch the store operations, not re-implement them.

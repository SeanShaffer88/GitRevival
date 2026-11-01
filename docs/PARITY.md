# GitRevival — Capability Parity

Scored only from code and test evidence. "GUI" is the desktop window, "CLI" is `python -m gitrevival.cli`, "Test" names the covering test file. Updated with the 0.4.0 catch-up slice (2026-10-31).

| Capability | GUI | CLI | Evidence / test |
|---|---|---|---|
| Inspect a repository (bounded static scan) | Yes | Yes (`inspect`) | test_workbench, test_planning (headless) |
| Compare two JSON reports / scan snapshots | Yes (Planning & history) | Yes (`compare`) | test_planning |
| Repair backlog: filter, search, sort | Yes | No | test_workbench, test_planning (GUI) |
| Task state / priority / due date / notes | Yes (autosaves, 0.4.0) | No | test_workbench, test_planning, test_catchup |
| Custom repair tasks | Yes | No | test_planning |
| Task change history | Yes | No | test_planning |
| Scan snapshots (latest 20) and differences | Yes | Partial (file-based `compare`) | test_planning |
| Export report (Markdown / JSON / CSV) | Yes | No | test_workbench, test_planning |
| Workspace backup (checked, no overwrite) | Yes | No | test_planning |
| GitHub search + repository checks | Yes (explicit click) | No | test_github |
| Revival shortlist + research notes + export | Yes | No | test_github |
| Session restore: geometry, last project/tab, recents | Yes (0.4.0) | n/a | test_catchup |
| Tooltips on every interactive control | Yes (0.4.0) | n/a | test_catchup |
| Built-in plain-words guide (Help / F1) | Yes (0.4.0) | n/a | test_catchup |

## Parity plan

CLI parity is the known gap. The planned 0.5.0 slice adds headless operations for report export, workspace backup, snapshot listing/differences and shortlist export, dispatching the same store operations the GUI uses — no GUI-only logic duplicated. Until then this file, not the README, is the honest record that those operations are window-only.

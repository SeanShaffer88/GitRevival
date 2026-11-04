# GitRevival — Capability Parity


Index catalogue hardening (source): GUI and CLI share bounded index-v2 parsing, an aggregate 50,000 stored-entry limit (duplicates included), and a 1,024 attempted-index limit with bounded warnings. Invalid packs are rejected whole; valid earlier catalogue entries remain available. Structural table/order/offset checks do not verify checksums or authenticity. Regression fixtures cover hostile counts, truncation, stale size metadata, large-offset references and cumulative limits. Recovery publication races / Windows protocol gap and delta resource hardening remain OPEN, unchanged by this patch. Portable packaging remains unverified: required CPython 3.15.1 is unavailable; local source checks use 3.15.2.
Scored only from code and test evidence. "GUI" is the desktop window, "CLI" is `python -m gitrevival.cli`, "Test" names the covering test file. Updated with the 0.10.0 forensics release (2026-11-01).

| Capability | GUI | CLI | Evidence / test |
|---|---|---|---|
| Inspect a repository (bounded static scan) | Yes | Yes (`inspect`) | test_workbench, test_planning (headless) |
| Compare two JSON reports / scan snapshots | Yes (Planning & history) | Yes (`compare`) | test_planning |
| Repair backlog: filter, search, sort | Yes | No | test_workbench, test_planning (GUI) |
| Internal dependency edges (in-project imports) | Yes (Dependencies tab) | Yes (`deps`, and in `inspect` output) | test_stage3 |
| Source navigation (view a file at a finding/import line) | Yes (read-only viewer) | No — a viewer is inherently graphical; the edges and line numbers behind it are in the CLI output | test_stage3 |
| License-text detection + advisories (unrecognized, copyleft, declared-vs-text mismatch) | Yes (backlog findings) | Yes (`deps`, and in `inspect` output) | test_stage3 |
| Task state / priority / due date / notes | Yes (autosaves, 0.4.0) | No | test_workbench, test_planning, test_catchup |
| Custom repair tasks | Yes | No | test_planning |
| Task change history | Yes | No | test_planning |
| List saved projects | Yes (sidebar) | Yes (`projects`) | test_cli_parity |
| Scan snapshots (latest 20) and differences | Yes | Yes (`scans`, `diff-scans`, plus file-based `compare`) | test_planning, test_cli_parity |
| Export report (Markdown / JSON / CSV) | Yes | Yes (`export`, fresh inspection + saved task states) | test_workbench, test_planning, test_cli_parity |
| Workspace backup (checked, no overwrite) | Yes | Yes (`backup`) | test_planning, test_cli_parity |
| GitHub search + repository checks | Yes (explicit click) | Search yes (`discover`, 0.9.0); checks GUI-only | test_github, test_slice1 |
| Revival shortlist + research notes | Yes | Export only (`shortlist`); editing is GUI-only | test_github, test_cli_parity |
| Plain-words find with ready-made hunts and verdicts | Yes (0.7.0) | Yes (`discover`, 0.9.0) with strict filters and NDJSON output |
| Revival potential evidence (unmet demand, last CI state, living forks, PR graveyard, contributor outreach) | Yes (0.8.0/0.9.0, part of Check) | No — Check is GUI-only; `discover` covers search |
| Maintainability profile + funding signals in the scan | Yes (backlog findings, 0.9.0) | Yes (in `inspect` output) | test_slice1 |
| Online dependency audit (registries, advisories, namespaces) | Yes (button, 0.9.0) | Yes (`audit`) | test_slice1 |
| Kickstart draft generation | Yes (button, 0.9.0) | Yes (`kickstart`) | test_slice1 |
| Git forensics: dangling-object scan + commit recovery | Yes (Git recovery tab, 0.10.0) | Yes (`git-scan`, `git-recover`) | test_gitforensics |
| Session restore: geometry, last project/tab, recents | Yes (0.4.0) | n/a | test_catchup |
| Tooltips on every interactive control | Yes (0.4.0) | n/a | test_catchup |
| Built-in plain-words guide (Help / F1) | Yes (0.4.0) | n/a | test_catchup |

## Parity plan

The 0.5.0 slice closed the planned gap: report export, workspace backup, snapshot listing/differences, project listing and shortlist export are all headless, dispatching the same store operations the GUI uses (the shortlist export itself moved into the store module so both surfaces produce identical files). What remains window-only, honestly: backlog browsing/editing, custom tasks, task history, and the GitHub repository Check action. The GitHub gap closed by owner decision in 0.9.0: `audit` and `discover` are explicit online commands (invoked, never background), while every other CLI command remains network-free. Any future backlog/task CLI operations should likewise dispatch the store operations, not re-implement them.

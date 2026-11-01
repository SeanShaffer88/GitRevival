# Changelog

## 0.6.0 — 2026-10-31

- Stage 3 A — dependency edges and source navigation: the inspector now resolves imports between files inside the project (Python absolute/relative/from imports; JavaScript/TypeScript relative imports and requires) into an internal dependency-edge list, capped at 2,000 with a scope warning. The Dependencies tab shows the edges; double-clicking an edge — or the new **View source** button on a finding — opens a read-only source viewer with the exact line marked.
- Stage 3 B — license-text and advisory checks: license files are matched against phrase fingerprints for MIT, BSD-2/BSD-3, Apache-2.0, GPL/LGPL/AGPL, MPL-2.0, ISC and the Unlicense. New advisories flag license text that matches nothing known, copyleft terms (with the obligations to review), and any mismatch between the license a manifest declares and the license text actually present. All checks are worded as research leads, never legal determinations.
- Reports, saved snapshots, exports and the new headless `deps` command carry the edges and license detections; workspaces saved by older versions still restore (the new lists default to empty).
- No new third-party dependency, and the inspector still never executes repository code.

## 0.5.0 — bundled into the 0.6.0 release (never published separately)

- Added headless workspace operations to the command line, sharing the same store operations as the window: `projects` (list saved projects as JSON), `export` (inspect, save the scan, and export a Markdown/JSON/CSV report with saved task states merged in), `backup` (checked workspace backup, existing destinations refused), `scans` (list a project's saved snapshots), `diff-scans` (compare two saved snapshots, with the same 0/1/2 exit-code convention as `compare`), and `shortlist` (export the saved shortlist as Markdown or JSON).
- The shortlist export itself moved into the shared store module, so the window and the command line produce identical files.
- All command-line file outputs must still be new files; errors exit with code 2. The command line still opens no window and makes no network requests — GitHub search and checks remain window-only by design.
- No new third-party dependency, and the inspector still never executes repository code.

## 0.4.0 — bundled into the 0.6.0 release (never published separately)

- Added tooltips for every interactive control in the window, in plain words.
- Task notes and candidate research notes now save automatically as you type; the workspace database uses SQLite write-ahead logging for safer sudden stops.
- The window restores its previous size, position, last project and tab on startup, and the sidebar gained a Recent projects list.
- Added a built-in plain-words guide (Help button or F1) covering the workflow, planning, backups, discovery, data storage and limits; it works offline.
- Added project paperwork: `PROJECT_RULES.md` (including the recorded 2026-10-31 decision to keep the Python standard-library stack), `QUALITY.md` and `docs/PARITY.md`.
- README gained a TL;DR, a troubleshooting section (including the owed real screenshot list) and a project-structure section.
- No new third-party dependency, no new network behaviour, and the inspector still never executes repository code.

## 0.3.0 — 2026-10-23

- Added all 15 planning/review improvements documented in README: severity/dependency filters, sorting, progress, priority/due dates, custom tasks, task history, scan snapshots/differences, SQLite backups, CSV exports, headless inspection/comparison and keyboard help.
- Kept the existing Python/Tk and SQLite stack; no third-party dependency or new network behavior.
- Additive workspace migration preserves existing notes and GitHub evidence. Latest 20 scans retained per project; task history begins with this version.
- Windows validation: 31 tests passed; 1 existing symlink test skipped because symlink creation is unavailable. Includes native Tk planning/discovery flows, old-schema migration, backup integrity, CSV formula escaping, snapshot retention and headless CLI subprocesses.

## 0.2.0 — 2026-10-22

- Added live read-only GitHub search and repository checks with dated metadata, release, commit and issue samples.
- Added discovery presets, paginated search, explainable research priorities, saved shortlists, research notes and shortlist exports.
- Added explicit local-upstream linking and saved GitHub evidence in local report exports.
- Added cached search, canonical rename handling, partial-failure reporting, request limits and optional environment-only authentication.
- Preserved existing local inspection/backlog state through additive SQLite schema migration.
- Added deterministic network/error tests and a real Tk discovery workflow test. Local validation: 24 tests passed, 1 skipped because Windows symlink creation was unavailable. Public API search and repository checks also completed successfully.

This milestone provides research evidence and planning. It does not verify revival feasibility, build success, dependency security or license compatibility.

## 0.1.0 — 2026-10-22

- First local static inspection, dependency inventory, revival map, repair backlog, saved notes and Markdown/JSON report exports.

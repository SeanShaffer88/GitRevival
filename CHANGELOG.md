# Changelog

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

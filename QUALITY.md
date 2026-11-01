# GitRevival — Quality Scorecard

Scored from evidence only (code read, tests run, release records), most recently for the 0.10.0 forensics release on 2026-11-01. Scores are 0–5 per dimension. Anything without evidence is marked Unverified, not scored up.

| Dimension | Score | Evidence |
|---|---|---|
| Correctness | 4 | Full gate green (see below); malformed-input, migration, backup and CLI paths are test-covered. No field report of a wrong scan result. |
| Safety of scanned code | 5 | Scanner never executes target code (test proves a raising `setup.py` is untouched), never follows symlinks, hard bounds with explicit warnings. |
| Privacy / network discipline | 5 | GET-only, host-pinned GitHub client; token env-only and never persisted; no telemetry or background requests; exports warn about private content. |
| Reliability of user data | 4 | SQLite WAL (0.4.0), additive migrations keep old notes (tested), consistent backups with integrity check and overwrite refusal (tested), notes autosave (0.4.0, tested). Crash behaviour on Windows is Unverified. |
| Usability | 3 | Useful in the first minute — from 0.7.0 the header leads with 'Find projects to revive': plain-words find, ready-made hunts, and plain verdicts on every result (tested). Search in both big lists, in-app plain-words guide and tooltips for every control (0.4.0, tested). Drag-and-drop is still missing; DPI/high-contrast behaviour on Windows is Unverified. |
| Command-line parity | 3 | Headless `inspect`/`compare` plus, from 0.5.0, `projects`, `export`, `backup`, `scans`, `diff-scans` and `shortlist`, all dispatching the shared store operations (test_cli_parity). 0.6.0 added `deps` (edges + license detections). Still window-only: backlog editing, custom tasks, task history, the source viewer, and GitHub discovery (the last deliberately — the CLI makes no network requests). |
| Feature depth | 3 | Declared dependency inventory plus, from 0.6.0, resolved in-project import edges with a source viewer, and license-text fingerprint checks with declared-vs-text mismatch and copyleft advisories (test_stage3). Discovery leads the product from 0.7.0 (plain-words query building and verdicts, test_discovery_first). 0.8.0 Slice 1 adds revival-potential evidence — unmet demand, last known healthy state, living-fork comparison — plus license permissiveness labels and extended CI bitrot findings (test_slice1). Edge resolution is text-level and covers Python + JavaScript/TypeScript only; other ecosystems' internal imports are not resolved yet. |
| Accessibility | 2 | Keyboard shortcuts and focus search exist; no verified screen-reader, high-contrast or 200%+ scaling evidence. Unverified on Windows. |
| Documentation | 4 | README covers workflow, limits, privacy and troubleshooting; rule sheet and parity matrix exist (0.4.0). First real screenshots (main window + scanned demo backlog) were added from the owner's 0.6.0 Windows run on 2026-10-31; the remaining captures are listed in the README. |
| Release discipline | 4 | 0.3.0 portable ZIP was hash- and CI-verified on two Windows versions before publishing. The release shape is a recorded owner waiver of the V2.0 matrix (see PROJECT_RULES.md), not silent drift. |
| Performance | 3 | Bounded scan design; CLI scan of this repository measures ~0.1 s locally. No large-repository (15,000-file) benchmark exists, so large-repo timing is Unverified. |

**Gate for the 0.10.0 forensics release (run 2026-11-01, Linux VM, Python 3.12 + Xvfb):** full suite **85/85 passed** (75 at 0.9.0 + 9 forensics tests with hand-built .git fixtures — loose/pack objects, delta chains, reflogs, damaged index, never-overwrite recovery, CLI git-scan/git-recover, the recovery tab — + 1 audit-button threading test). Windows CI is Verified at each pull request. Windows runtime behaviour of the app itself remains Unverified until the owner runs it.

**Known Fail-level items (not hidden):** accessibility evidence (2/5) and the remaining window-only operations listed under Command-line parity. Neither blocks this slice, whose scope is the items it fixes; both stay named in `docs/PARITY.md` and the README milestones.

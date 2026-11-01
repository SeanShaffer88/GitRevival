# GitRevival — Quality Scorecard

Scored from evidence only (code read, tests run, release records), most recently for the 0.4.0 catch-up slice on 2026-10-31. Scores are 0–5 per dimension. Anything without evidence is marked Unverified, not scored up.

| Dimension | Score | Evidence |
|---|---|---|
| Correctness | 4 | Full gate green (see below); malformed-input, migration, backup and CLI paths are test-covered. No field report of a wrong scan result. |
| Safety of scanned code | 5 | Scanner never executes target code (test proves a raising `setup.py` is untouched), never follows symlinks, hard bounds with explicit warnings. |
| Privacy / network discipline | 5 | GET-only, host-pinned GitHub client; token env-only and never persisted; no telemetry or background requests; exports warn about private content. |
| Reliability of user data | 4 | SQLite WAL (0.4.0), additive migrations keep old notes (tested), consistent backups with integrity check and overwrite refusal (tested), notes autosave (0.4.0, tested). Crash behaviour on Windows is Unverified. |
| Usability | 3 | Useful in the first minute, search in both big lists, in-app plain-words guide and tooltips for every control (0.4.0, tested). Drag-and-drop is still missing; DPI/high-contrast behaviour on Windows is Unverified. |
| Command-line parity | 2 | Headless `inspect` and `compare` only; planning, export, backup and shortlist operations are GUI-only. Tracked in `docs/PARITY.md`; closing this is the planned 0.5.0 slice. |
| Accessibility | 2 | Keyboard shortcuts and focus search exist; no verified screen-reader, high-contrast or 200%+ scaling evidence. Unverified on Windows. |
| Documentation | 4 | README covers workflow, limits, privacy and troubleshooting; rule sheet and parity matrix exist (0.4.0). Screenshots are owed (real captures only) — listed in the README. |
| Release discipline | 4 | 0.3.0 portable ZIP was hash- and CI-verified on two Windows versions before publishing. The release shape is a recorded owner waiver of the V2.0 matrix (see PROJECT_RULES.md), not silent drift. |
| Performance | 3 | Bounded scan design; CLI scan of this repository measures ~0.1 s locally. No large-repository (15,000-file) benchmark exists, so large-repo timing is Unverified. |

**Gate for the 0.4.0 slice (run 2026-10-31, Linux VM, Python 3.12 + Xvfb):** full suite **37/37 passed** (32 pre-existing + 5 new catch-up tests), and the headless CLI inspection of the demo project completed successfully. Windows runtime behaviour remains Unverified until the owner runs it.

**Known Fail-level items (not hidden):** CLI parity (2/5) and accessibility evidence (2/5). Neither blocks the 0.4.0 catch-up slice, whose scope is the items it fixes; both are named next-stage work in `docs/PARITY.md` and the README milestones, with CLI parity scheduled first.

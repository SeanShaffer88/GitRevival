# GitRevival — Project Rules

Prompt in force: The Elite Software Master Prompt v1.1 · Annexes: A (desktop) · C1/C2 (owner defaults, private copy only)
Purpose in one line: A local GUI workbench for inspecting old repositories and planning evidence-based revivals.
Frozen foundation: `gitrevival/analyzer.py` (bounded static scan, never executes target code) · `gitrevival/store.py` (SQLite workspace) · `gitrevival/github.py` (read-only GitHub evidence) · `gitrevival/discovery.py` + `gitrevival/planning.py` (UI panels) · `gitrevival/app.py` (main window) · `gitrevival/cli.py` (headless operations). New features are operations first, then a surface.
Build: none (pure Python standard library) · Full gate: `python -m unittest discover -s tests -v` (GUI tests need a display on non-Windows) · Test corpus: `tests/` plus the `demo/old-orbit` fixture.
Budgets: scan bounded at 15,000 files, 512 KB per inspected file, 12 MB total inspected text; GitHub requests 12 s timeout, 2 MB response cap, GET-only, host pinned to `api.github.com`.
Coverage floors: every safety path (bounds, no-execution, symlink refusal, token handling, backup integrity, migration) must stay test-covered; headline percentages are not claimed without a coverage run.

## Stack decision — V2.0 exemption (owner, 2026-10-31)

The Core Engineering Contract V2.0 (Rust/C++20 only for Windows projects) was adopted on 2026-10-30, after GitRevival 0.3.0 shipped. On 2026-10-31 the owner exempted GitRevival from that stack rule: it stays a Python standard-library program (Tkinter + SQLite, zero third-party packages), because the bounded, non-executing scanner and the small single-user workload gain nothing measurable from a rewrite. This is a recorded owner waiver, not a silent exception.

Release shape under the exemption: the Windows portable ZIP plus `SHA256SUMS.txt` remains the release shape. There is no Setup.exe or WiX MSI for this project; release notes must say so plainly rather than imply the V2.0 matrix was met. Releases are grouped and are never published without the owner's explicit confirmation.

## Special rules for this project

- The scanner never executes repository code, never follows symlinks or reparse directories, and never writes to a scanned repository. Any future feature that would run a project's commands needs its own owner decision and isolation design first.
- GitHub access is read-only, explicit (a click or a CLI command), and sends no background or scheduled requests. Tokens come only from the `GITREVIVAL_GITHUB_TOKEN` environment variable and are never stored.
- Honesty wording is part of the product: a scan is not a build, a license file is not clearance, and a task marked Done is a manual record, not verification. Do not soften or remove these statements.
- Every interactive control carries a tooltip; every capability should be reachable from the command line (CLI parity is tracked in `docs/PARITY.md` and closes in stages).
- Public docs (README, CHANGELOG, release notes) contain only factual product documentation.

Known limitations live at: README.md ("Inspection coverage" and "Next useful milestones") · Decision log: this file + CHANGELOG.md · QUALITY.md: `QUALITY.md`

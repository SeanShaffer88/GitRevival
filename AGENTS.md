# Working on GitRevival

Read `PROJECT_RULES.md` first — it holds the frozen module layout, the scan/GitHub safety rules, the budgets, and the recorded stack decision (Python standard library, owner-exempted from the V2.0 Rust/C++ rule on 2026-10-31).

Short version:

- Full gate before anything is called done: `python -m unittest discover -s tests -v` (GUI tests need a display outside Windows).
- Never make the scanner execute repository code, follow symlinks, or write to a scanned repository.
- GitHub access stays read-only, explicit, GET-only and host-pinned; tokens are environment-only.
- Keep the honesty wording: scan ≠ build, license file ≠ clearance, Done ≠ verified.
- Update `docs/PARITY.md`, `QUALITY.md` and the CHANGELOG in the same change as the behaviour they describe.
- Releases are grouped and need the owner's explicit confirmation first.

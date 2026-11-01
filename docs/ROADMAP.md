# GitRevival roadmap — status

Everything from both feature reviews (2026-10-31) has shipped: Slice 1 in
0.8.0, the rest in 0.9.0. This file now records what each item became and
the small parts that remain honestly open.

## Shipped

- **Revival Potential v2 (0.8.0).** Unmet demand, last known healthy
  state, living-fork comparison, license permissiveness labels, extended
  CI bitrot — all inside the repository Check.
- **PR Graveyard Miner (0.9.0).** Part of Check: open pull requests
  untouched for 6+ months that already carry approvals, with links.
- **Contributor Outreach Map (0.9.0).** Part of Check: the top
  contributors other than the owner, by commit count.
- **Maintainability & Ergonomics Profiler (0.9.0).** Part of the local
  scan: god files, test-harness presence, recorded coverage files, and
  documentation depth. Health comes from recorded evidence only — target
  code is never executed, so pass rates are not claimed.
- **Registry Abandonment & Namespace Audit (0.9.0).** The online audit
  (`audit` command / window button) checks PyPI, npm, crates.io, NuGet
  and RubyGems for declared dependencies and for the project's own
  package name, including `-ng`, `2` and `-rs` variant availability.
  Transfer policies are informational only; the tool never acts on them.
- **Vulnerability audit (0.9.0).** The same online audit matches exact
  declared versions against GitHub's published advisory database with
  plain GETs — no POST-only database and no stored token needed. Ranged
  versions are reported as not precisely checked rather than guessed.
- **Community Migration & Signal Beaconing (0.9.0).** The kickstart
  generator writes the backlink notice draft, the maintainer outreach
  letter and the ADOPTERS.md banner; sponsor triage starts from the
  scan's funding-signal finding. Drafts only — GitRevival never posts.
- **Revival Kickstart generator (0.9.0).** `kickstart` command / window
  button: ADOPTERS.md, OUTREACH.md, MODERNIZATION.md, BACKLINK.md,
  written into a chosen folder and never overwriting.
- **Headless CLI & filtering flags (0.9.0).** `gitrevival discover`
  with `--min-stars`, `--inactive-months` (single value or range),
  `--license`, `--lang`, `--has-passing-ci`, NDJSON or `--json` output.
  Approved as an explicit online command; all other CLI commands remain
  network-free. The menu's `--max-commits-behind` example is a fork
  metric, not a search filter — fork ahead/behind already appears in
  the repository Check's living-forks section.

## Open, honestly

- **Downstream blast radius, GitHub side.** crates.io dependent counts
  and npm weekly downloads ship in the audit. GitHub's dependency graph
  exposes no public read-only endpoint for a repository's dependents,
  so that side stays unavailable rather than scraped or guessed.
- **Trademark collision guard.** Registry name availability ships (see
  Namespace Audit). Trademark registers have no free plain-GET API, so
  no trademark claim is made either way.
- **Git forensics (parked by owner decision, 2026-10-31).** A pure-Python
  object/reflog/index forensics engine exists locally, unwired and
  untested, for a possible future advanced tab. Discovery stays the
  front door.

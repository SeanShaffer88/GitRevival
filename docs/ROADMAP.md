# GitRevival roadmap — future additions

Ideas recorded for later slices, in the owner's words first, with a short
feasibility note against GitRevival's standing rules (read-only network
access with plain GET requests, no tokens stored, target code is never
executed, every claim labelled as evidence or a lead). Nothing here is
scheduled until the owner picks it.

## From the first feature review (2026-10-31)

Slice 1 shipped in 0.8.0: unmet demand, last known healthy state, living
fork comparison, license permissiveness labels, extended CI bitrot.

- **PR Graveyard Miner (Slice 2 candidate).** Surface open pull requests
  with passing checks and review approvals but no maintainer action, and
  offer their patches as research leads for a revival.
  *Feasibility: read-only GETs, bounded per repository. Fits.*
- **Downstream dependency blast radius.** How many active projects still
  depend on this repository (GitHub dependency graph, package registries).
  *Feasibility: GitHub's dependency graph needs a signed-in token for
  most repositories, so this can only be a token-only extra, clearly
  labelled when unavailable.*
- **CVE & dependency vulnerability audit.** Parse lockfiles against
  vulnerability databases before touching the code.
  *Feasibility: the main databases answer POST queries or need a token,
  which breaks the GET-only, no-token-stored rule. Needs its own design
  decision before any work.*
- **Trademark / name collision guard.** Check the repository or binary
  name against package registries and app stores.
  *Feasibility: registry search APIs are plain GETs. Fits.*
- **Revival Kickstart generator.** Generate — never push — a
  modernization patch (current CI runners, toolchain minimums, dead
  badge links), an ADOPTERS.md fork-transition banner crediting the
  original authors, and a maintainer outreach letter requesting transfer
  or co-maintainer rights.
  *Feasibility: local file generation fits the read-only promise; the
  user applies everything themselves.*

## From the second feature review (2026-10-31)

### 1. Codebase Maintainability & Ergonomics Profiler

Before adopting a project, the resurrector needs to know how painful the
code is to read, refactor, and maintain:

- Architecture smells & LOC density: massive "god files" (e.g.
  4,000-line single-file binaries), deep complexity, excessive macro
  usage.
- Test suite health check: parse test coverage and pass rates. A project
  with 85% unit test coverage from two years ago is drastically easier
  to resurrect than one with zero harness.
- Documentation & spec completeness: existing architectural
  documentation (docs/, RFCs, design specs, well-commented public
  interfaces) versus repos that rely purely on tribal knowledge.

*Feasibility: god-file and documentation checks fit the bounded local
scan directly. Coverage/pass-rate parsing is limited to reading report
files and CI configuration — tests themselves are never run, so health
is reported from recorded evidence only, labelled as such.*

### 2. Registry Abandonment & Namespace Takeover Audit

A GitHub repo is only half the asset; the upstream package registry is
often where users actually consume it:

- Orphaned package detection: cross-reference the repository against
  npm, crates.io, PyPI, NuGet, and RubyGems. Flag packages published
  under an unmaintained name, dormant owner accounts, and registries
  whose policies allow requesting ownership transfer.
- Alternative namespace availability: if the original name cannot be
  transferred, query registry APIs for available revival variants
  (repo-ng, repo2, repo-rs).

*Feasibility: registry metadata and name-availability checks are plain
GETs. Transfer policies are informational text, verified at read time,
never acted on by the tool.*

### 3. Community Migration & Signal Beaconing

Once a project is revived, connecting to the existing user base without
spamming is critical:

- Stale issue / PR backlinker: draft an opt-in status notice for the
  most popular open issue threads ("A maintained fork addressing issue
  #42 has been spun up here with active CI").
- Backer / sponsor triage: detect whether the original repository had
  Open Collective, GitHub Sponsors, or Patreon backers who stopped
  contributing due to inactivity — latent financial support for a
  revival.
- Contributor outreach map: identify the top 3–5 historical PR
  contributors who aren't the primary owner — prime candidates to
  invite as co-maintainers or reviewers for the new fork.

*Feasibility: the backlinker generates draft text only — GitRevival
never posts to GitHub. Sponsor signals are limited to public evidence
(a FUNDING file in the local scan, public sponsor pages). The outreach
map is read-only contributor statistics from the API.*

### 4. Headless CLI & Filtering Flags

For a "dead simple" developer UX, discovery should also run headlessly,
with strict filters and pipe-friendly output:

- `--min-stars 100`, `--max-commits-behind 0`
- `--inactive-months 18-36` (old enough to be abandoned, new enough that
  dependencies aren't completely dead)
- `--license mit,apache-2.0`
- `--lang rust,c++,go`
- `--has-passing-ci`
- JSON/NDJSON export streamed to stdout for scripts, triage boards, and
  automated clone-and-build rigs.

*Feasibility: this needs its own decision — the command line currently
never uses the network by design (recorded in docs/PARITY.md), and
discovery is a network feature. If approved, it would be an explicitly
opt-in command (for example `gitrevival discover ...`) with the same
read-only client, rate-limit honesty, and no token storage as the GUI.*

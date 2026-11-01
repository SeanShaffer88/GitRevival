"""Revival kickstart drafts: generated text the user reviews and applies.

GitRevival never pushes, posts, or edits the target repository. This
module only writes four draft files into a folder the user chooses —
and refuses to overwrite anything already there:

- ADOPTERS.md — a fork-transition banner crediting the original authors.
- OUTREACH.md — a polite letter to the original maintainer.
- MODERNIZATION.md — a CI/toolchain modernization checklist with a
  current sample workflow, built from the scan's own findings.
- BACKLINK.md — a short, opt-in status notice draft for a popular open
  issue thread, to post by hand if it is welcome there.
"""
from __future__ import annotations

from pathlib import Path

FILES = ('ADOPTERS.md', 'OUTREACH.md', 'MODERNIZATION.md', 'BACKLINK.md')


def _write_new(path, text):
    with open(path, 'x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def generate_kickstart(report, snapshot, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    existing = [name for name in FILES if (output / name).exists()]
    if existing:
        raise ValueError(f'Refusing to overwrite existing drafts: {", ".join(existing)}. Choose another folder.')
    name = report.name
    upstream = (snapshot or {}).get('full_name') or '<owner/repository>'
    upstream_url = (snapshot or {}).get('html_url') or f'https://github.com/{upstream}'
    pushed = (snapshot or {}).get('pushed_at') or 'an unknown date'
    contributors = (snapshot or {}).get('top_contributors') or []
    credits = ', '.join(person['login'] for person in contributors[:3]) or 'the original contributors'

    adopters = f"""# This project is a maintained revival of {name}

The original project, [{upstream}]({upstream_url}), was last updated
on {pushed} and appears to need a new maintainer. This fork continues
its work in the open.

**Credit:** the original authors and contributors — including
{credits} — created everything that made this project worth reviving.
This fork claims none of their work as its own.

**For existing users:** releases from this fork are the maintained
line. Issue reports are welcome here; please mention the upstream
issue number when your report continues an old thread.

**For the original maintainer:** this revival exists because the
project matters. Transfer, co-maintenance, or a simple link from the
original repository would all be welcomed — see OUTREACH.md in the
revival repository for a standing invitation.
"""

    outreach = f"""Subject: Keeping {name} alive — a maintained fork, and an open invitation

Hello,

Thank you for {name}. I have been using/studying it, and I would like
to keep it working for the people who still rely on it. The repository
was last updated on {pushed}, so I have started a maintained fork that
fixes [the most pressing issues] while crediting you and the other
contributors as the original authors.

I am writing before announcing anything widely, because the best
outcome is yours to choose:

1. **Transfer** the repository (and, if you are willing, the package
   registry name) so its history and audience carry over directly.
2. **Co-maintain:** add me as a maintainer and I will do the work
   under your project's name and rules.
3. **Endorse the fork:** a one-line note in your README pointing users
   to the maintained fork.
4. **None of these** — I will keep the fork clearly separate and
   credited, and remove anything you object to.

No reply is also understood — maintaining a project is unpaid work
and life moves on. Either way, thank you for building it.

[Your name]
[Link to the fork and its first release]
"""

    automation = [f for f in report.findings if f.category == 'Automation']
    findings_block = '\n'.join(f'- [ ] {f.title} ({f.file or "project-wide"})' for f in automation) or '- [ ] No automation findings were recorded by the scan.'
    ecosystems = ', '.join(report.ecosystems) or 'not identified'
    modernization = f"""# Modernization checklist for {name}

Generated from the revival scan. Ecosystems seen: {ecosystems}.
Work through this in a branch, verify each step, and only then offer
it upstream or ship it in the fork.

## From the scan's automation findings

{findings_block}

## Baseline steps

- [ ] Replace retired runner labels with current images
      (ubuntu-latest, windows-latest, macos-latest).
- [ ] Update GitHub Actions to current majors
      (actions/checkout@v4, language setup actions at their latest).
- [ ] Remove or replace dead CI services (Travis CI, CircleCI 1.0,
      AppVeyor) and keep their test commands in the new workflow.
- [ ] Swap dead badge URLs in the README for the new CI's badges.
- [ ] Record the minimum supported toolchain versions in the README.

## Sample workflow (adapt the test command)

```yaml
name: CI
on:
  push:
  pull_request:
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - uses: actions/checkout@v4
      # Add your language setup action here, at its current major.
      - name: Run the test suite
        run: <your test command>
```
"""

    issues = (snapshot or {}).get('issues') or []
    if issues:
        first = issues[0]
        issue_ref = f"#{first['number']} ({first['title']})"
        issue_url = first.get('html_url') or upstream_url
    else:
        issue_ref = '#<number> (<issue title>)'
        issue_url = upstream_url
    backlink = f"""<!--
Draft status notice for the open issue {issue_ref}
({issue_url})

Post this by hand, once, only where it is genuinely useful — and only
if the thread is asking for a fix. Never post it across many threads.
-->

A maintained fork of this project is now available at
<your fork URL>, and it addresses this issue in <release or commit>.
The original project ({upstream}) appears unmaintained since
{pushed}; the fork credits the original authors and tracks upstream
issues so context is not lost. If you try it, feedback there is
welcome — and maintainers here are equally welcome to adopt the fix
directly.
"""

    drafts = {'ADOPTERS.md': adopters, 'OUTREACH.md': outreach,
              'MODERNIZATION.md': modernization, 'BACKLINK.md': backlink}
    for filename, text in drafts.items():
        _write_new(output / filename, text)
    return sorted(drafts)

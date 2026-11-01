"""License-text fingerprints: phrase matching over normalized license text.

Detection is a research lead, never a legal determination: it reports which
well-known license text a file most closely matches, based on distinctive
phrases that must all be present. Anything else is reported as Unknown so a
person reads the actual text.
"""
import re

# Order matters: narrower families are checked before the broader ones they
# resemble (LGPL and AGPL before GPL, BSD-3 before BSD-2).
FINGERPRINTS = [
    ('AGPL-3.0', ('gnu affero general public license', 'version 3')),
    ('LGPL-3.0', ('gnu lesser general public license', 'version 3')),
    ('LGPL-2.1', ('gnu lesser general public license', 'version 2 1')),
    ('GPL-3.0', ('gnu general public license', 'version 3')),
    ('GPL-2.0', ('gnu general public license', 'version 2')),
    ('Apache-2.0', ('apache license', 'version 2 0')),
    ('MPL-2.0', ('mozilla public license', 'version 2 0')),
    ('MIT', ('permission is hereby granted free of charge', 'the software is provided')),
    ('BSD-3-Clause', ('redistribution and use in source and binary forms', 'neither the name')),
    ('BSD-2-Clause', ('redistribution and use in source and binary forms',)),
    ('ISC', ('permission to use copy modify and or distribute this software',)),
    ('Unlicense', ('free and unencumbered software released into the public domain',)),
]

COPYLEFT = {'AGPL-3.0', 'LGPL-3.0', 'LGPL-2.1', 'GPL-3.0', 'GPL-2.0'}


def normalize(text):
    """Lowercase, turn punctuation into spaces, and collapse whitespace."""
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', text.lower())).strip()


def detect_license(text):
    """Return (spdx, matched phrase) or ('Unknown', '') when nothing matches."""
    normalized = normalize(text)
    for spdx, phrases in FINGERPRINTS:
        if all(phrase in normalized for phrase in phrases):
            return spdx, phrases[0]
    return 'Unknown', ''


def declared_matches(declared, detected):
    """True when a declared license value covers the detected license.

    Handles plain identifiers ('MIT'), common shorthands ('Apache 2.0',
    'GPLv3') and SPDX expressions ('MIT OR Apache-2.0'): the detected
    identifier, or a normalized form of it, must appear among the declared
    parts. Comparison is a heuristic string check, not a legal reading.
    """
    parts = re.split(r'\b(?:OR|AND)\b|[()]', declared.upper())
    candidates = {detected.upper(), detected.upper().replace('-', ' '),
                  detected.upper().replace('-', ''), detected.upper().split('-')[0]}
    if detected.startswith('GPL-'):
        candidates.add('GPLV' + detected.split('-')[1][0])
        candidates.add('GPL ' + detected.split('-')[1])
    if detected.startswith('LGPL-'):
        candidates.add('LGPLV' + detected.split('-')[1][0])
    if detected == 'Apache-2.0':
        candidates.update({'APACHE 2.0', 'APACHE2', 'ASL 2.0'})
    for part in parts:
        cleaned = re.sub(r'\s+', ' ', part).strip().rstrip('+')
        if cleaned in candidates:
            return True
    return False


PERMISSIVE = {'MIT', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0', 'ISC',
              'Unlicense', 'Zlib', '0BSD', 'CC0-1.0', 'MIT-0'}
WEAK_COPYLEFT = {'LGPL-2.1', 'LGPL-3.0', 'MPL-2.0', 'EPL-1.0', 'EPL-2.0'}
COPYLEFT = {'GPL-2.0', 'GPL-3.0', 'AGPL-3.0'}


def license_class(spdx):
    """Plain permissiveness label for one license identifier.

    A triage label only: it says how much legal care a revival needs at a
    glance, never what the license actually permits. Missing identifiers
    are the risky case, so they get their own label instead of a guess.
    """
    if not spdx or spdx in {'Unknown', 'NOASSERTION', 'None'}:
        return 'No licence identified'
    if re.search(r'\b(?:OR|AND)\b', spdx):
        return 'Multiple licences — read the text'
    base = spdx.rstrip('+')
    if base in PERMISSIVE:
        return 'Permissive'
    if base in WEAK_COPYLEFT:
        return 'Weak copyleft'
    if base in COPYLEFT:
        return 'Copyleft'
    return 'Other — read the text'

"""Permanent id arithmetic — the one place that knows how an id encodes a number.

An id is a label humans say out loud; a sequence is a number the allocator
increments. Everything painful about ids comes from those two facts being
implemented in more than one place, so they are implemented here, once.

`store.py` keeps `ID_WIDTH`/`ID_CEILING` for the DECIMAL intent ids an early
store already carries. They bound nothing new — intents are captured as ULIDs
now — but a store sitting near `INT-9999` still has a wall in front of its
existing form, which is the only thing those constants still describe. They are
not `SEQ_WIDTH`/`SEQ_CEILING` despite both widths being 4: one counts decimal
digits, the other base-32 characters, and nothing may compare across them.

The shape (the design behind it: `docs/identity-scheme-design.md`):

    RU-ORD-01A2
    │  │   └── sequence: four Crockford base-32 characters
    │  └────── segment: a domain — optional, permanent once minted
    └───────── kind

**Crockford base-32** (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`) drops I, L, O and U
precisely so they cannot be read as 1 and 0, and its characters ascend in ASCII
order — so for a FIXED width, lexicographic order is numeric order, and a plain
`ls` of `spec/ru/` lists a segment in allocation order.

Two consequences that are easy to miss and expensive to rediscover:

**Decimal ids are already valid base-32 ids.** `0142` decodes to 1346, not 142.
A store that adopted decimal widths and later allocates in base-32 therefore
needs NO migration: every legacy id keeps its spelling, decodes to a larger
number than it used to mean, and still sorts before every id allocated after
it. This is why §4.4 of the paper can promise that existing ids are never
rewritten. It is also why the store's rule is *never mixed BASES* rather than
never mixed widths — a store reading `0142` as 142 in one place and 1346 in
another has two allocators disagreeing about what is taken.

**Parsing is strict, and case is not folded.** Crockford's canonical decoder
accepts lowercase and maps I/L to 1 and O to 0. That leniency is right for a
serial number a human retypes and wrong for a filename: it would give one id
several legal spellings, and two spellings of one id is a collision class
wearing a convenience feature. So the confusables are refused, with a message
naming the digit that was probably meant.

`kind` is a parameter, but **RU is the only kind the SEQUENCE scheme governs**,
and that is a rule rather than an omission. The framework allocates a sequence
exactly where creation is already serialized — Gate 1 — and uses a ULID
everywhere it is not, which is why drafts and GAPs carry one. Intent capture has
no gate, so intents are ULID-shaped (`intent_pattern` below); giving them a
sequence would mean either inventing a gate for the least gateable act in the
process, or shipping a counter two branches can both read.
"""

from __future__ import annotations

import re

# Crockford base-32. Ordered by value, and ASCII-ascending — both properties
# are load-bearing, so this string is a published contract, not a detail.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
BASE = len(ALPHABET)

# The sequence width. Four characters hold 1,048,576 ids per segment, in the
# same four characters that held 10,000 under decimal. Like the old decimal
# width this is a ceiling rather than a tunable: it is compiled into every
# schema pattern and filename regex, so widening it is a store-wide migration.
SEQ_WIDTH = 4
SEQ_CEILING = BASE ** SEQ_WIDTH - 1              # RU-ZZZZ

# The alphabet as a regex, written in RANGES rather than by interpolating
# ALPHABET: it is embedded in checked-in schema patterns a human reads, and
# `[0-9A-HJKMNP-TV-Z]` is the spelling this codebase already uses for ULIDs.
# Two spellings of one set is a drift class, so a test pins them together.
SEQ_PATTERN = rf"[0-9A-HJKMNP-TV-Z]{{{SEQ_WIDTH}}}"

# A segment is a NAME, not a number, so it uses the full alphabet — excluding O
# from "ORDERS" would be absurd. It carries exactly one prohibition: it may not
# be something the sequence alphabet can spell. `RU-CART` would otherwise read
# as an id whose sequence is CART, and ids are chosen to be said out loud.
#
# The prohibition is narrow because the alphabet already does most of the work:
# I, L, O and U are excluded from sequences, so AUTH, ORDS, RISK and BILL were
# never ambiguous and stay available. Only an all-base-32 four-character name
# (CART, PYMT) is refused. Refusing by LENGTH instead would bar seven such
# names for a collision they cannot have — and segment names are a one-way
# door, so a name refused today is refused forever.
_SEGMENT_CORE = r"[A-Z][A-Z0-9]{1,7}"

# The rule has two forms because a segment has two contexts, and the ONLY
# difference between them is what follows the name: a separator inside an id, or
# nothing at all when it stands alone as a schema field or a registry entry.
# Both derive from one core and one alphabet, so the prohibition cannot drift.
SEGMENT_PATTERN = rf"(?!{SEQ_PATTERN}-){_SEGMENT_CORE}"        # inside an id
SEGMENT_ALONE = rf"^(?!{SEQ_PATTERN}$){_SEGMENT_CORE}$"        # a bare name

_SEGMENT = re.compile(SEGMENT_ALONE)
_VALUE = {char: value for value, char in enumerate(ALPHABET)}

# What a confusable character was probably meant to be. The whole point of the
# alphabet is that these four are unreadable in an id, so refusing them without
# saying which digit was intended wastes the guarantee.
_CONFUSABLE = {"I": "1", "L": "1", "O": "0", "U": "V"}


# A ULID as this store spells it: Crockford base-32, 26 characters. Same
# alphabet as a sequence and the same exclusions, so nothing needs a second
# reading rule — only the LENGTH differs, and that is what keeps a 4-character
# sequence and a 26-character ULID unambiguous inside one grammar. Every use
# site is anchored at both ends, so no input can satisfy both branches and no
# prefix of one is a whole match of the other.
ULID = "[0-9A-HJKMNP-TV-Z]{26}"

# An intent id. Two forms, permanently: a ULID for anything captured from here
# on, and the four-digit decimal an early store already carries. Both are legal
# forever — an intent is immutable and its id is cited by every RU compiled from
# it, so re-identifying one is a rewrite of somebody's history.
INTENT_BODY = rf"INT-(?:{ULID}|[0-9]{{4}})"


# How an RU cites the exact place in its intent that it compiles. LINE anchors
# only: a section anchor (`#S<slug>`) was in the grammar from the start and was
# never enforceable, because an intent is "any (MD, transcript)" and a pasted
# conversation has no headings to slugify. An anchor form nothing can verify is
# a preference wearing a syntax, so v0.16.0 retires it — line anchors are
# bounds-checked against the file and work on every capture format.
INTENT_ANCHOR = rf"{INTENT_BODY}#L[0-9]+(-[0-9]+)?"

INTENT_PATTERN = rf"^{INTENT_BODY}$"
"""The regex for an intent id.

    Intents are CAPTURED, never allocated: no verb mints one, because capture
    happens wherever a conversation happens — an analyst agent, a paste, a
    meeting note committed by hand. That is precisely the profile a ULID exists
    for, and the same reason drafts and GAPs carry one: collision-free with no
    coordination, from a process with no serialization point to coordinate at.

    The decimal form stays legal rather than being migrated. Every RU compiled
    from an intent cites it in `source_ref`, so renaming one would rewrite the
    provenance of requirements that are already stamped and reviewed."""


def permanent_body(kind: str) -> str:
    """The unanchored shape, for embedding in a larger alternation.

    Several schemas accept an RU id *or* a draft *or* a FEAT, so they need the
    shape without anchors. The capture groups ride along — JSON Schema ignores
    them, and one spelling that is slightly noisy in YAML beats two spellings
    that agree by hand."""
    return rf"{kind}-(?:({SEGMENT_PATTERN})-)?({SEQ_PATTERN})"


def permanent_pattern(kind: str) -> str:
    """The regex for one kind's permanent ids, segmented or not.

    The single source for the shape: the filename matchers in `store.py`, the
    `RU-…` patterns in the pack schemas, and every read-site that matches an id
    by hand. The schema patterns are literal strings in checked-in YAML and
    nothing generates them, so agreement is enforced by a meta-test rather than
    by construction — the same arrangement the field-charset patterns use, and
    for the same reason: they drifted once."""
    return rf"^{permanent_body(kind)}$"


def encode(number: int) -> str:
    """A sequence number as its fixed-width base-32 spelling."""
    if number < 0 or number > SEQ_CEILING:
        raise ValueError(
            f"sequence {number} is outside the {SEQ_WIDTH}-character range "
            f"(0..{SEQ_CEILING}, i.e. up to {ALPHABET[-1] * SEQ_WIDTH})")
    out = ""
    for _ in range(SEQ_WIDTH):
        number, remainder = divmod(number, BASE)
        out = ALPHABET[remainder] + out
    return out


def decode(sequence: str) -> int:
    """The number a sequence spells. Strict: the spelling must be canonical."""
    if len(sequence) != SEQ_WIDTH:
        raise ValueError(
            f"'{sequence}' is {len(sequence)} character(s); a sequence is exactly "
            f"{SEQ_WIDTH}, zero-padded (e.g. {encode(1)})")
    number = 0
    for char in sequence:
        # Fold for the DIAGNOSIS only — `l` and `L` are the same mistake, and
        # the reader of a lowercase id deserves the specific message too. The
        # value lookup below stays case-sensitive, so nothing is accepted here.
        if char.upper() in _CONFUSABLE:
            meant = _CONFUSABLE[char.upper()]
            raise ValueError(
                f"'{sequence}' contains {char}, which the base-32 alphabet excludes "
                f"so it can never be confused with {meant} — write {meant} if that "
                "is what was meant. Ids are matched byte-for-byte; a lenient "
                "reading would give one id two spellings.")
        if char not in _VALUE:
            raise ValueError(
                f"'{sequence}' contains {char!r}, which is not in the base-32 "
                f"alphabet ({ALPHABET}). Sequences are uppercase and unpunctuated.")
        number = number * BASE + _VALUE[char]
    return number


def split(identifier: str, kind: str) -> tuple[str | None, int]:
    """`('ORD', 418)` for `RU-ORD-01A2`; `(None, 418)` for `RU-01A2`.

    Raises `ValueError` for anything that is not a permanent id of this kind —
    including drafts, which carry ULIDs and are not sequence-allocated."""
    match = re.match(permanent_pattern(kind), identifier)
    if not match:
        # `SEQ_PATTERN` already excludes the confusables, so `RU-01O2` misses
        # the pattern outright and would be told only "that is not the shape" —
        # burying the one diagnosis the alphabet exists to deliver. Re-run the
        # tail through the decoder, which names the character and the digit it
        # was probably meant to be; it stays silent when the tail is fine.
        tail = identifier.rsplit("-", 1)[-1]
        if identifier.startswith(f"{kind}-") and len(tail) == SEQ_WIDTH:
            decode(tail)
        raise ValueError(
            f"'{identifier}' is not a permanent {kind} id. The shape is "
            f"{kind}-<SEGMENT>-<SEQUENCE> or {kind}-<SEQUENCE>, where the "
            f"sequence is {SEQ_WIDTH} base-32 characters (e.g. {kind}-{encode(1)}).")
    return match.group(1), decode(match.group(2))


def format_id(kind: str, segment: str | None, number: int) -> str:
    """The inverse of `split`, and the ONLY way ids should be constructed."""
    if segment is not None and not is_segment(segment):
        if re.fullmatch(SEQ_PATTERN, segment):
            raise ValueError(
                f"'{segment}' is a sequence spelling, so `{kind}-{segment}` would "
                f"read as an id rather than a segment. Most names are unaffected "
                "— the alphabet excludes I, L, O and U, so AUTH, ORDS and BILL "
                "are all available; pick one the sequence alphabet cannot spell.")
        raise ValueError(
            f"'{segment}' is not a segment name: uppercase, starting with a "
            "letter, 2-8 characters. Names are chosen once and never corrected "
            "— a segment can be added and closed, never renamed — so name it "
            "after a domain that outlives teams and services, not after a "
            "squad, a sprint or a deployable.")
    body = encode(number)
    return f"{kind}-{segment}-{body}" if segment else f"{kind}-{body}"


def is_segment(name: str) -> bool:
    return bool(_SEGMENT.match(name))

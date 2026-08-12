"""Permanent id arithmetic.

The properties asserted here are the ones the rest of the framework is allowed
to assume: round-tripping, sort-equals-allocation-order, and the promise that a
decimal store can start allocating base-32 without rewriting a single id.

RU is the only kind exercised. `ids` takes `kind` as a parameter, but intents
are deliberately undecided (design paper §6) — a test asserting `INT-0057`
splits into a base-32 sequence would settle that question by accident."""

import re

import pytest

from rqunit import ids

# A stride rather than the full million: dense enough that an off-by-one in the
# divmod loop cannot hide, cheap enough to stay in the unit suite.
_STRIDE = range(0, ids.SEQ_CEILING + 1, 97)


def test_encoding_round_trips_across_the_whole_range():
    for number in (*_STRIDE, ids.SEQ_CEILING):
        assert ids.decode(ids.encode(number)) == number


def test_sequences_are_fixed_width_and_zero_padded():
    """Width is what makes lexicographic order numeric order; a short spelling
    would sort `Z` after `0000` and silently corrupt allocation."""
    for number in (0, 1, ids.SEQ_CEILING):
        assert len(ids.encode(number)) == ids.SEQ_WIDTH


def test_lexicographic_order_is_allocation_order():
    """`ls spec/ru/` must list a segment chronologically — that is the whole
    reason the alphabet is ASCII-ascending rather than merely 32 characters."""
    spellings = [ids.encode(n) for n in _STRIDE]
    assert spellings == sorted(spellings)


def test_base32_preserves_the_meaning_and_order_of_every_decimal_id():
    """The no-migration promise, stated as the property it actually is.

    A decimal-spelled id re-read as base-32 must (a) never decode to LESS than
    it used to mean, so nothing already allocated appears free, (b) stay
    distinct from every other legacy id, and (c) keep its relative order. Given
    those three, a store can start allocating base-32 tomorrow and every
    existing filename, `verifies:` annotation, review directory and packet
    stays exactly as written. If this test ever fails, adopting base-32 becomes
    a store-wide rewrite of append-only history."""
    decimals = [f"{n:04d}" for n in range(0, 10_000, 7)]
    values = [ids.decode(d) for d in decimals]

    assert all(value >= int(spelling) for value, spelling in zip(values, decimals))
    assert len(set(values)) == len(values)
    assert values == sorted(values)


def test_ids_allocated_after_adoption_sort_after_every_legacy_id():
    """The other half of the promise: the first base-32 allocation continues
    the sequence rather than landing in the middle of it."""
    highest_legacy = ids.decode("9999")
    assert ids.encode(highest_legacy + 1) > "9999"


def test_the_ceiling_refuses_rather_than_wrapping():
    with pytest.raises(ValueError):
        ids.encode(ids.SEQ_CEILING + 1)


def test_confusable_characters_are_refused_by_name():
    """Excluding I, L, O and U earns nothing if the error does not say which
    digit was meant — the reader is looking at a character they cannot tell
    apart from another one."""
    for char, meant in (("I", "1"), ("L", "1"), ("O", "0"), ("U", "V")):
        with pytest.raises(ValueError) as caught:
            ids.decode(f"00{char}1")
        assert char in str(caught.value) and meant in str(caught.value)


def test_a_confusable_in_a_whole_id_still_gets_the_specific_diagnosis():
    """The sequence pattern excludes the confusables, so a bad id misses the
    regex before the decoder ever sees it — and the one message this alphabet
    exists to deliver is the one a reader with a bad filename would not get."""
    with pytest.raises(ValueError) as caught:
        ids.split("RU-01O2", "RU")
    assert "O" in str(caught.value) and "0" in str(caught.value)


def test_case_is_not_folded():
    """Crockford's decoder is case-insensitive; an id grammar must not be, or
    one id acquires several legal filenames. A lowercase confusable is the same
    mistake as an uppercase one and gets the same diagnosis."""
    with pytest.raises(ValueError):
        ids.decode("01a2")
    with pytest.raises(ValueError) as caught:
        ids.decode("01o2")
    assert "0" in str(caught.value)


def test_splitting_recovers_the_segment_and_the_number():
    assert ids.split("RU-ORD-01A2", "RU") == ("ORD", ids.decode("01A2"))
    assert ids.split("RU-01A2", "RU") == (None, ids.decode("01A2"))


def test_splitting_refuses_a_draft_and_says_what_a_permanent_id_looks_like():
    """Drafts carry ULIDs and are not sequence-allocated; asking for a draft's
    number is a caller bug, and the message has to teach the shape."""
    with pytest.raises(ValueError) as caught:
        ids.split("RU-draft-01K1TESTAAAAAAAAAAAAAAAA", "RU")
    assert "RU-" in str(caught.value) and str(ids.SEQ_WIDTH) in str(caught.value)


def test_formatting_is_the_inverse_of_splitting():
    for identifier in ("RU-ORD-01A2", "RU-01A2", "RU-ORDERMGT-ZZZZ"):
        segment, number = ids.split(identifier, "RU")
        assert ids.format_id("RU", segment, number) == identifier


def test_a_segment_may_not_be_something_the_sequence_alphabet_can_spell():
    """`RU-CART` would read as an id whose sequence is CART. The prohibition is
    exactly that and no wider: the alphabet's own exclusions already make most
    four-letter names unambiguous, and a segment refused today is refused
    forever."""
    assert not ids.is_segment("CART")          # all base-32 — a legal sequence
    assert not ids.is_segment("PYMT")
    assert ids.is_segment("AUTH")              # U is not in the alphabet
    assert ids.is_segment("ORDS")              # O is not either
    assert ids.is_segment("ORD") and ids.is_segment("ORDERMGT")


def test_segment_shape_keeps_names_and_numbers_apart():
    assert not ids.is_segment("X")             # too short to read as a domain
    assert not ids.is_segment("ord")           # ids are uppercase
    assert not ids.is_segment("0RD")           # must start with a letter
    assert not ids.is_segment("ORDER-MGT")     # the dash is the id's separator
    assert not ids.is_segment("ORDERMGMT")     # 9 characters


def test_the_segment_rule_has_one_spelling():
    """`is_segment` and the segment group inside `permanent_pattern` are the
    same rule; a second regex kept in lockstep by hand is how the grammar and
    the schemas drifted before."""
    pattern = re.compile(ids.permanent_pattern("RU"))
    for name in ("ORD", "AUTH", "CART", "X", "ord", "0RD", "ORDERMGMT"):
        embedded = pattern.match(f"RU-{name}-0001")
        assert bool(embedded) == ids.is_segment(name), name


def test_bad_segment_names_are_refused_with_the_reason_that_applies():
    """Two different mistakes; the reader has to be told which one they made,
    because one of them is fixable by picking any other name and the other
    means the name shape itself is wrong."""
    with pytest.raises(ValueError) as spelling:
        ids.format_id("RU", "CART", 1)
    assert "sequence" in str(spelling.value)

    with pytest.raises(ValueError) as shape:
        ids.format_id("RU", "checkout-squad", 1)
    assert "renamed" in str(shape.value)

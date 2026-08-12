"""L27 — a draft says which id space it belongs in, and means it.

An id carries a segment or it does not, and the absence is a **positive claim**:
this requirement governs the store rather than a domain. The claim is only worth
making if something notices when it is made by accident. Without this rule,
"unsegmented" quietly becomes where a requirement lands when the reviewer did
not decide, and a distinction that means something on Monday means nothing by
Friday. That is the failure the tag vocabulary is guarded against, and it is
worse here, because a tag can be re-cut and an id cannot.

The rule has two directions, because the mistake does.

**A standard draft with no segment** would be minted store-wide. `tier` is a
two-value enum, and the schema requires `scope.owns` with at least one entry for
standard tier while letting constitutional omit it — so "governs a domain" is
already the tier distinction, and no inference from ownership is needed. The
paper's §4.4 phrasing ("owns a segmented service") would have required deriving
the segment from `scope.owns`, which §4.2 forbids outright: segments and
services are many-to-many.

**A constitutional draft WITH a segment** is the same mistake mirrored, and the
more expensive one. The allocator honours the field regardless of tier, so this
mints a permanent segmented id for a store-wide invariant — inventing a `GOV`
segment to hold cross-cutting concerns, which the design paper names as
recreating the dumping ground under a nicer name.

**Drafts only, and that is the whole point.** A permanent id is permanent: an
active RU minted before its store adopted segments cannot acquire one, and never
will. Reporting it would be a warning with no available fix — the kind that
teaches people the tool is noise. A draft is the one moment the decision is
still free and costs a single line. The standing population is still covered,
because it only grows through activation and every entry passes through a draft.

Silent in a store that has declared no segments: a store may legitimately never
adopt them, and a rule that fires on a shape a consumer has not opted into is
demanding they adopt it rather than enforcing a decision they made.
"""

from ..errors import BadConfig
from ..segments import declared
from ..violations import Violation
from .base import lint, rel


@lint("L27")
def run(store):
    try:
        segments = declared(store.root)
    except BadConfig:
        # A registry this cannot parse is C16's to report, in C16's words. L27
        # is the first lint to read the file, so letting the error escape would
        # abandon the whole run — every other lint unreported — over one
        # mis-indented line.
        return []
    if not segments:
        return []                    # this store has not adopted segments

    out = []
    for ru in store.rus():
        if ru.status != "draft":
            continue                 # a permanent id cannot be given a segment
        wanted = ru.raw.get("segment")
        if ru.tier == "constitutional" and wanted:
            out.append(Violation(
                rule="L27", severity="warning", artifact=ru.id, path=rel(store, ru.path),
                message=(f"a constitutional draft asks for segment {wanted}, but "
                         "constitutional tier governs the store rather than a domain."),
                suggestion=("Drop `segment:` — the unsegmented id IS the claim that this "
                            "governs everything. If it really governs one domain, it is "
                            "not constitutional: drop the tier instead. A segment holding "
                            "cross-cutting concerns is the store-wide space with extra "
                            "steps, and the id is permanent from activation onward "
                            "(formats §1)."))
            )
        elif ru.tier != "constitutional" and not wanted:
            out.append(Violation(
                rule="L27", severity="warning", artifact=ru.id, path=rel(store, ru.path),
                message=("the draft declares no `segment`, so Gate 1 would allocate it an "
                         "unsegmented id — the store's way of saying it governs "
                         "everything rather than one domain."),
                suggestion=(f"Add `segment:` naming the domain it governs (one of "
                            f"{', '.join(sorted(segments))}). If it governs the store "
                            "rather than a domain, it is constitutional tier — set "
                            "`tier: constitutional` and drop `scope`, which L13 caps at "
                            "15 active so the tier cannot become the new dumping ground. "
                            "The id is permanent from activation onward (formats §1)."))
            )
    return out

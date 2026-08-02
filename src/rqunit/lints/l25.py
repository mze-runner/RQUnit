"""L25 — the shall-clause subject names a real service, and its own one.

Two claims about which service governs an RU have coexisted with nothing
reconciling them: the statement SUBJECT, and `scope.owns[0]` (documented in
store.py as a heuristic). The subject was never checked at all — the EARS
parser admits `the system` or any hyphenated lowercase word, purely by shape —
so `servcie-orders shall …` passed, and so did an RU whose subject named one
service while its scope named another.

That second case is a misfiled RU, and §5.3 already forbids it: "referencing is
read coupling, not governance — a consumer RU referencing a foreign endpoint
does not become its governor." The principle existed; it had no teeth.

Not a token. A service name already has a home in token syntax — the qualifier,
which L15 resolves — and brace-wrapping the subject would tax every statement
in the store to restate a fact the grammar already carries positionally.
"""

from ..violations import Violation
from .base import lint, rel, safe_parse

_WHOLE_SYSTEM = "the system"


@lint("L25")
def run(store):
    out = []
    services = set(store.manifests())
    for ru in store.rus():
        statement = safe_parse(ru)
        if statement is None:
            continue                       # L1 owns unparseable statements
        subject = (statement.system or "").strip()
        if not subject or subject.lower() == _WHOLE_SYSTEM:
            continue                       # store-wide behaviour claims no service

        if subject not in services:
            out.append(Violation(
                rule="L25", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"the statement is bound to '{subject}', which has no manifest.",
                suggestion=("Use the service's declared slug, or `the system` for behaviour that "
                            "is not one service's. A subject nothing declares cannot be governed, "
                            "and a typo here has been silent until now (§5.2).")))
            continue

        scope = store.scope_service(ru)
        if scope and scope != subject:
            out.append(Violation(
                rule="L25", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=(f"the statement obliges '{subject}', but the RU's scope owns "
                         f"'{scope}' — the RU is filed against a service it does not govern."),
                suggestion=("Move the RU to the owning service's scope, or restate it for the "
                            "service it actually governs. Referencing another service is read "
                            "coupling, not governance (§5.3).")))
    return out

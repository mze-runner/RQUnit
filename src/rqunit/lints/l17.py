"""L17 — fact restatement, the P8 teeth (spec §10.1, §3.2). A statement
containing a literal HTTP path, subject, wire-type name, or a scalar equal to
a reachable manifest value gets an error WITH the reference suggestion.
Exact-match only in v1 (donor note): fuzzy matching destroys trust; numeric
matches are word-bounded.

Scanning covers authored PROSE only — reference-token spans are masked first,
the same fix L2 received in v0.10.4. Without it, an RU that referenced a fact
CORRECTLY was told to reference it: `{audit:orders.cancelled}` tripped the
literal-subject scan whenever an audit code and a message subject shared a
string, which is an ordinary thing for them to do."""

import re

from ..violations import Violation
from .base import lint, manifest_value_leaves, prose, reachable_manifests, rel


@lint("L17")
def run(store):
    out = []
    for ru in store.rus():
        statement = prose(ru.raw["statement"])
        for manifest in reachable_manifests(store, ru):
            raw = manifest.raw
            for e in raw.get("endpoints") or []:
                if e["path"] in statement:
                    out.append(_v(store, ru, f"literal path '{e['path']}'", f"{{endpoint:{e['id']}}}"))
            for msg in raw.get("messages") or []:
                if re.search(rf"(?<![\w.]){re.escape(msg['subject'])}(?![\w.])", statement):
                    out.append(_v(store, ru, f"literal subject '{msg['subject']}'", f"{{message:{msg['id']}}}"))
                if msg["payload"] in statement:
                    out.append(_v(store, ru, f"wire type '{msg['payload']}'", f"{{message:{msg['id']}}}"))
            for channel in raw.get("channels") or []:
                for frame in channel.get("frames") or []:
                    if frame["payload"] in statement:
                        out.append(_v(store, ru, f"wire type '{frame['payload']}'",
                                      f"{{frame:{channel['id']}.{frame['id']}}}"))
            for dotted, value in manifest_value_leaves(raw.get("values") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    # Small integers (< 10) are skipped: "within 5 seconds" colliding
                    # with an unrelated manifest 5 is the false positive that destroys
                    # trust in the lint (donor L17 note) — exact-match plus magnitude.
                    if abs(value) < 10:
                        continue
                    if re.search(rf"\b{re.escape(str(value))}\b", statement):
                        out.append(_v(store, ru, f"literal value {value}", f"{{value:{dotted}}}"))
                elif isinstance(value, str) and len(value) >= 4 and value in statement:
                    out.append(_v(store, ru, f"literal value '{value}'", f"{{value:{dotted}}}"))
    return out


def _v(store, ru, what, token):
    return Violation(
        rule="L17", severity="error", artifact=ru.id, path=rel(store, ru.path),
        message=f"statement restates {what}, which is declared in a reachable manifest (P8: "
                "one fact, one place).",
        suggestion=f"Reference it instead: {token}.")

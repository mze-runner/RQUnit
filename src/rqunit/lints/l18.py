"""L18 — manifest hygiene (spec §5.2): schema validity is the loader's schema
stage; the lint surface here is that every surface entry's `ru:` link resolves
to an existing RU or FEAT (the manifest-side half of §6.6 traceability)."""

from ..violations import Violation
from .base import lint, rel

_SECTIONS = ("endpoints", "messages", "channels", "audit_events")


@lint("L18")
def run(store):
    out = []
    ru_ids = {ru.id for ru in store.rus()}
    feat_ids = {f.id for f in store.features()}
    for service, manifest in store.manifests().items():
        for section in _SECTIONS:
            for entry in manifest.raw.get(section) or []:
                link = entry.get("ru")
                if link is None:
                    continue  # schema stage rejects missing links where required
                entry_id = entry.get("id") or entry.get("code")
                if link.startswith("RU-") and link not in ru_ids:
                    out.append(_v(store, manifest, service, section, entry_id, link,
                                  "no such RU in spec/ru/"))
                elif link.startswith("FEAT-") and link not in feat_ids:
                    out.append(_v(store, manifest, service, section, entry_id, link,
                                  "no such FEAT in spec/features/"))
    return out


def _v(store, manifest, service, section, entry_id, link, why):
    return Violation(
        rule="L18", severity="error", artifact=f"{service}:{section}.{entry_id}",
        path=rel(store, manifest.path),
        message=f"ru link '{link}' dangles — {why}.",
        suggestion="Every surface entry names its governor (§6.6); create the FEAT/RU or fix the link.")

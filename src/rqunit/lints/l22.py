"""L22 — planned-surface backlink (spec §5.8, v0.10): every `planned: true`
surface entry's `ru:` link is not-done. An RU link must not compute done; a
FEAT link passes only while no member RU computes done (vacuously true for a
memberless FEAT — the migration-bridge case). Violation = either the surface
shipped without its Gate 1 flip, or verifications pass against a surface that
supposedly does not exist."""

from ..status import compute
from ..violations import Violation
from .base import lint, rel

_SECTIONS = ("endpoints", "messages", "channels")


@lint("L22")
def run(store):
    out = []
    rus = {ru.id: ru for ru in store.rus()}
    by_feature = {}
    for ru in store.rus():
        by_feature.setdefault(ru.raw.get("feature"), []).append(ru)
    for service, manifest in store.manifests().items():
        for section in _SECTIONS:
            for entry in manifest.raw.get(section) or []:
                if not entry.get("planned"):
                    continue
                link = entry.get("ru", "")
                done_ids = []
                if link.startswith("RU-") and link in rus:
                    if compute(store, rus[link]).done:
                        done_ids = [link]
                elif link.startswith("FEAT-"):
                    done_ids = [m.id for m in by_feature.get(link, []) if compute(store, m).done]
                if done_ids:
                    out.append(Violation(
                        rule="L22", severity="error",
                        artifact=f"{service}:{section}.{entry.get('id')}",
                        path=rel(store, manifest.path),
                        message=f"planned surface is governed by DONE requirement(s) "
                                f"{', '.join(done_ids)} — one of the two is lying (§5.8).",
                        suggestion="If the surface shipped, flip `planned` off at Gate 1 (mutating edit, "
                                   "impact report); if it did not, the verifications are false."))
    return out

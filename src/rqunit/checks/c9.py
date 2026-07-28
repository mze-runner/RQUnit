"""C9 — message topology (spec §10.2 v0.10, §5.8): every inbound subject
matches exactly one outbound declaration store-wide with an identical payload
type, unless `external: true`; multiple outbound declarers of one subject is
always an error; an `external` marker whose subject HAS an in-store declarer
is itself an error (a wrong marker does not get to disable the check).
Planned entries participate — topology is designed before it ships."""

from collections import defaultdict

from ..lints.base import rel
from ..violations import Violation
from .base import check


@check("C9")
def run(store):
    outbound = defaultdict(list)   # subject -> [(service, entry, manifest)]
    inbound = []
    for service, manifest in store.manifests().items():
        for entry in manifest.raw.get("messages") or []:
            if entry["direction"] == "outbound":
                outbound[entry["subject"]].append((service, entry, manifest))
            else:
                inbound.append((service, entry, manifest))
    out = []
    for subject, declarers in outbound.items():
        if len(declarers) > 1:
            who = ", ".join(f"{s}:{e['id']}" for s, e, _ in declarers)
            service, entry, manifest = declarers[0]
            out.append(_v(store, manifest, f"{service}:messages.{entry['id']}",
                          f"subject {subject} has {len(declarers)} outbound declarers ({who}) — exactly one service owns what it emits.",
                          "One producer per subject; move the fact to the owning service (§5.8)."))
    for service, entry, manifest in inbound:
        subject = entry["subject"]
        declarers = outbound.get(subject, [])
        artifact = f"{service}:messages.{entry['id']}"
        if entry.get("external"):
            if declarers:
                who = ", ".join(f"{s}:{e['id']}" for s, e, _ in declarers)
                out.append(_v(store, manifest, artifact,
                              f"marked external, but subject {subject} HAS an in-store outbound declarer ({who}) — "
                              "the wrong marker is silently exempting the pair from payload agreement.",
                              "Drop external: true (the producer is in-store), or fix the subject."))
            continue
        if not declarers:
            out.append(_v(store, manifest, artifact,
                          f"inbound subject {subject} has no in-store outbound declarer.",
                          "Declare the producer's outbound entry, or mark this inbound external: true "
                          "(producer outside the store — reviewed at Gate 1, §5.8)."))
            continue
        producer_service, producer, _ = declarers[0]
        if producer["payload"] != entry["payload"]:
            out.append(_v(store, manifest, artifact,
                          f"payload type '{entry['payload']}' disagrees with the declarer "
                          f"{producer_service}:messages.{producer['id']} ('{producer['payload']}') for subject {subject}.",
                          "Both ends must name the identical wire-contract type (C9)."))
    return out


def _v(store, manifest, artifact, message, suggestion):
    return Violation(rule="C9", severity="error", artifact=artifact,
                     path=rel(store, manifest.path), message=message, suggestion=suggestion)

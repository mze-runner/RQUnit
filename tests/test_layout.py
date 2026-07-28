"""Store layout (§12.1): the declared top-level directories, verified against
a fixture store. The consumer's own store is the consumer's business — what the
product owns is the CONTRACT that these are the directories a store may have."""

from pathlib import Path

from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"

DECLARED = {
    "framework", "intent", "ru", "features", "manifests",
    "models", "contracts", "gaps", "rationale", "reviews", "packets", "projections",
}


def test_a_store_uses_only_declared_directories():
    entries = {p.name for p in (VALID / "spec").iterdir() if p.name != ".DS_Store"}
    assert entries <= DECLARED, f"undeclared store directories: {entries - DECLARED}"


def test_the_loader_accepts_every_artifact_directory_it_declares():
    """Every directory the layout declares must either be loadable or be one
    the loader deliberately ignores — a directory nothing can read is a
    contract nobody can honour."""
    store = Store.load(VALID)
    assert store.rus() and store.manifests()      # the loader walked the tree

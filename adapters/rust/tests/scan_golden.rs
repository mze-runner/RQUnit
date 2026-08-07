#![allow(clippy::unwrap_used, clippy::expect_used)]
// test target: panics are test failures (rust-standards)

//! Scanner currency and determinism over the shared fixture trees.
//!
//! The committed `scanned-checks.json` beside each fixture tree is what the
//! Python suite consumes in artifact mode; these tests are what keep those
//! artifacts honest — the same staleness discipline the extractor's
//! `manifest_conformance` test applies to `actual-surface.json`.

use std::path::PathBuf;

use rqunit_adapter_rust::scan::render_checks;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(name)
}

/// verifies: infrastructure
#[test]
fn committed_scanned_checks_match_their_trees() {
    for (tree, expected) in [
        ("kit/scanner/tree", "kit/scanner/expected.json"),
        (
            "../../fixtures/store/traced",
            "../../fixtures/store/traced/scanned-checks.json",
        ),
    ] {
        let committed = std::fs::read_to_string(fixture(expected))
            .unwrap_or_else(|e| panic!("read {expected}: {e}"));
        let current = render_checks(&fixture(tree)).expect("scan the fixture tree");
        assert_eq!(
            committed, current,
            "{expected} is stale for {tree}: rerun `scan-checks --root <tree>` and commit"
        );
    }
}

/// verifies: infrastructure
#[test]
fn scanning_is_deterministic() {
    let root = fixture("kit/scanner/tree");
    assert_eq!(render_checks(&root).unwrap(), render_checks(&root).unwrap());
}

/// verifies: infrastructure
#[test]
fn a_tree_that_declares_no_rust_stack_observes_zero_checks() {
    let dir = std::env::temp_dir().join("rqunit-scan-undeclared");
    std::fs::create_dir_all(&dir).unwrap();
    let artifact = render_checks(&dir).unwrap();
    assert!(artifact.contains("\"checks\": []"));
}

/// verifies: infrastructure
#[test]
fn a_malformed_trace_scan_errors_instead_of_defaulting() {
    // A malformed glob list silently bent into patterns would let the gate
    // observe nonsense and report green.
    let dir = std::env::temp_dir().join("rqunit-scan-malformed");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("rqunit.toml"),
        "[stacks.rust]\ntrace_scan = \"not-a-list\"\n",
    )
    .unwrap();
    let err = render_checks(&dir).unwrap_err().to_string();
    assert!(err.contains("trace_scan"), "{err}");
}

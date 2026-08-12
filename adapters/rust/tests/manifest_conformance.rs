#![allow(clippy::unwrap_used, clippy::expect_used)]
// test target: panics are test failures (rust-standards) — clippy's test exemption does not reach helper fns in integration tests

//! Actual-surface currency (RU spec §5.6).
//!
//! The reconciliation itself moved to `rqunit conformance`, which owns every
//! judgment for every language. What remains here is the half only a Rust
//! toolchain can do: extract the real surface, and fail loudly when the
//! committed artifact no longer matches the code — the same staleness
//! discipline `rqunit generate check` applies to generated files.

use rqunit_adapter_rust::{artifact_path, render, workspace_root};

/// verifies: infrastructure
#[test]
fn committed_actual_surface_matches_the_code() {
    let root = workspace_root().expect("workspace root");
    if !root.join("rqunit.toml").exists() {
        // The product repository is not a consumer: there is no [stacks.rust]
        // composition here to extract against. This currency test is armed the
        // moment the crate is vendored into a workspace that carries one.
        eprintln!(
            "skipped: no rqunit.toml at {} — not a consumer workspace",
            root.display()
        );
        return;
    }
    let path = artifact_path(&root);
    let committed = std::fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "read {}: {e} — run `cargo run -p spec-conformance-tests --bin extract-surface`",
            path.display()
        )
    });
    let current = render(&root).expect("extract the current surface");
    assert_eq!(
        committed, current,
        "actual-surface.json is stale: the code's surface changed since it was written.\n\
         Regenerate and commit:\n  \
         cargo run -p spec-conformance-tests --bin extract-surface\n\
         Then reconcile against the manifests:\n  \
         cd spec-tools && uv run rqunit conformance"
    );
}

#![allow(clippy::unwrap_used, clippy::expect_used)]
// test target: panics are test failures (rust-standards)

//! Stripper currency plus the rewrite cases the compliance kit cannot reach.
//!
//! The kit proves the common shapes end to end (a whole line removed, survivors
//! kept, a check absent from the request untouched). These cover the edges an
//! off-ramp is judged by: an annotation that governs no test, and a file whose
//! bytes must come back unchanged except for the tokens named.

use std::path::PathBuf;

use rqunit_adapter_rust::strip::respond;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(name)
}

fn request(fn_name: &str, remove: &str) -> String {
    format!(
        r#"{{"contract_version":1,"checks":[{{"id":"x::y::{fn_name}",
           "path":"service-x/tests/sample_tests.rs","fn":"{fn_name}",
           "remove":[{remove}]}}]}}"#
    )
}

/// verifies: infrastructure
#[test]
fn committed_kit_expectation_matches_the_tree() {
    let committed = std::fs::read_to_string(fixture("kit/stripper/expected.json"))
        .expect("read kit/stripper/expected.json");
    let current = respond(
        &fixture("kit/stripper/tree"),
        &std::fs::read_to_string(fixture("kit/stripper/request.json")).unwrap(),
    )
    .expect("strip the kit tree");
    assert_eq!(
        committed, current,
        "kit/stripper/expected.json is stale: rerun strip-annotations over the kit tree and commit"
    );
}

/// verifies: infrastructure
#[test]
fn stripping_is_deterministic() {
    let root = fixture("kit/stripper/tree");
    let req = std::fs::read_to_string(fixture("kit/stripper/request.json")).unwrap();
    assert_eq!(respond(&root, &req).unwrap(), respond(&root, &req).unwrap());
}

/// verifies: infrastructure
#[test]
fn a_test_the_request_omits_keeps_its_annotation() {
    // The request is the complete instruction. A stripper that swept the file
    // it was handed would take annotations nobody judged stale.
    let out = respond(
        &fixture("kit/stripper/tree"),
        &request("traced_to_missing_ru", "\"RU-9999\""),
    )
    .unwrap();
    assert!(out.contains("verifies: RU-0001"), "{out}");
    assert!(!out.contains("RU-9999"), "{out}");
}

/// verifies: infrastructure
#[test]
fn a_token_the_annotation_does_not_carry_changes_nothing() {
    // Asked to remove something absent, the file must come back untouched —
    // and by contract an unchanged file is omitted entirely, so the operator's
    // count is the count of real edits.
    let out = respond(
        &fixture("kit/stripper/tree"),
        &request("traced_single", "\"RU-4242\""),
    )
    .unwrap();
    assert!(out.contains("\"files\": []"), "{out}");
    assert!(out.contains("\"stripped\": []"), "{out}");
}

/// verifies: infrastructure
#[test]
fn a_request_naming_a_missing_file_errors_instead_of_reporting_success() {
    let err = respond(
        &fixture("kit/stripper/tree"),
        r#"{"contract_version":1,"checks":[{"id":"x::y::z","path":"nope/absent.rs",
             "fn":"z","remove":["RU-0001"]}]}"#,
    )
    .unwrap_err()
    .to_string();
    assert!(err.contains("absent.rs"), "{err}");
}

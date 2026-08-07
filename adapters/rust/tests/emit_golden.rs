#![allow(clippy::unwrap_used, clippy::expect_used)]
// test target: panics are test failures (rust-standards)

//! Emitter currency, purity, and rendering semantics.
//!
//! The committed emit-response.json beside each fixture store is what the
//! Python suite consumes in artifact mode. The chain that keeps that honest:
//! a Python test pins the committed *request* to the live store; these tests
//! pin the committed *response* to the committed request. Either link going
//! stale is a red build.

use std::path::PathBuf;

use rqunit_adapter_rust::emit::respond;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// verifies: infrastructure
#[test]
fn committed_emit_responses_match_their_requests() {
    for store in ["fixtures/store/valid", "demo/order-management"] {
        let root = repo().join(store);
        let request = std::fs::read_to_string(root.join("emit-request.json"))
            .unwrap_or_else(|e| panic!("read {store}/emit-request.json: {e}"));
        let committed = std::fs::read_to_string(root.join("emit-response.json"))
            .unwrap_or_else(|e| panic!("read {store}/emit-response.json: {e}"));
        let current = respond(&request).expect("emit");
        assert_eq!(
            committed, current,
            "emit-response.json is stale for {store}: pipe emit-request.json through emit-suite and commit"
        );
    }
}

/// verifies: infrastructure
#[test]
fn emission_is_a_pure_function_of_the_request() {
    let root = repo().join("fixtures/store/valid");
    let request = std::fs::read_to_string(root.join("emit-request.json")).unwrap();
    assert_eq!(respond(&request).unwrap(), respond(&request).unwrap());
}

/// verifies: infrastructure
#[test]
fn every_plan_check_renders_exactly_one_ignored_test() {
    let root = repo().join("fixtures/store/valid");
    let request = std::fs::read_to_string(root.join("emit-request.json")).unwrap();
    let response: serde_json::Value = serde_json::from_str(&respond(&request).unwrap()).unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&request).unwrap();
    let planned: usize = parsed["plan"]["models"]
        .as_array()
        .unwrap()
        .iter()
        .map(|m| m["checks"].as_array().unwrap().len())
        .sum();
    let suite = response["files"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["path"].as_str().unwrap().contains("/tests/"))
        .and_then(|f| f["content"].as_str())
        .unwrap();
    assert_eq!(suite.matches("#[test]").count(), planned);
    assert_eq!(
        suite
            .matches("#[ignore = \"statechart shim pending")
            .count(),
        planned
    );
    assert_eq!(response["checks"].as_array().unwrap().len(), planned);
}

/// verifies: infrastructure
#[test]
fn paths_and_check_ids_honor_the_declared_conformance_crate() {
    // This synthetic request also carries the purity proof: the model below
    // exists in no store on disk, so a response can only come from the
    // request itself.
    let request = r#"{
      "contract_version": 1,
      "plan": { "contract_version": 1, "models": [
        { "model": "order-lifecycle", "model_hash": "sha256:0", "undeclared_event_policy": "error",
          "shim_registered": false, "verified_by": [], "checks": [
            { "kind": "invariant", "id": "invariant_no_open_orders", "state": "closed", "name": "no_open_orders" } ] } ] },
      "constants": {},
      "options": { "conformance_crate": "tools/conf" }
    }"#;
    let response: serde_json::Value = serde_json::from_str(&respond(request).unwrap()).unwrap();
    for file in response["files"].as_array().unwrap() {
        assert!(file["path"].as_str().unwrap().starts_with("tools/conf/"));
    }
    let id = response["checks"][0]["id"].as_str().unwrap();
    assert_eq!(
        id,
        "conf::generated_mdl_order_lifecycle::invariant_no_open_orders"
    );
}

/// verifies: infrastructure
#[test]
fn a_malformed_conformance_crate_errors_instead_of_defaulting() {
    // A typo silently bent into the default would emit a crate the consumer
    // never asked for, and the currency gate would bless it.
    let request = r#"{ "contract_version": 1,
      "plan": { "contract_version": 1, "models": [] },
      "constants": {}, "options": { "conformance_crate": 3 } }"#;
    let err = respond(request).unwrap_err().to_string();
    assert!(err.contains("conformance_crate"), "{err}");
}

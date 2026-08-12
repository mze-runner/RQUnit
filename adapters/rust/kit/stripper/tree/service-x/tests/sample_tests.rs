/// verifies: RU-0001
#[test]
fn traced_single() {}

/// Longer doc first.
/// verifies: RU-0001, RU-0002
#[tokio::test]
async fn traced_multi() {}

/// verifies: infrastructure
#[test]
fn plumbing_probe() {}

#[test]
#[ignore = "flaky upstream"]
fn untraced_with_extra_attr() {}

fn helper_not_a_test() {}

/// verifies: RU-9999
#[test]
fn traced_to_missing_ru() {}

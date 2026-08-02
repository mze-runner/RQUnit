---
description: Run every gate the product must pass — suite, CLI smoke, fixture-store health, and adapter build.
---

Run the full local gate and report results compactly. Stop at the first failure
that makes later stages meaningless (a broken suite makes CLI output moot).

```bash
uv run pytest -q

# The CLI must work as an installed tool, from anywhere in a store.
uv run rqunit --help

# The valid fixture store must stay clean under the full rule set — it is the
# product's own proof that a well-formed store passes.
uv run rqunit lint  --store fixtures/store/valid --format text
uv run rqunit check --store fixtures/store/valid --format text
uv run rqunit doctor --store fixtures/store/valid

# The demo store: the only place the whole vocabulary runs together.
uv run rqunit lint        --store demo/order-management --format text
uv run rqunit check       --store demo/order-management --format text
uv run rqunit conformance --store demo/order-management --format text

# Adapters build independently of the core.
cargo check --manifest-path adapters/rust/Cargo.toml
cargo clippy --manifest-path adapters/rust/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path adapters/rust/Cargo.toml --check
```

Report: pass/fail per stage, and for any failure the exact command that
reproduces it. Do not fix anything as part of this command — running the gate
and changing the code are separate acts, and conflating them hides which change
made the gate pass.

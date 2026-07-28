//! Writes `actual-surface.json` — what this codebase really exposes.
//!
//! Extraction runs in the stack's own build system, never from the framework
//! toolchain: `rqunit` reads the artifact and owns the diff, which is what
//! keeps the core free of every language toolchain it governs. Run after
//! changing routes or NATS publication, then commit the artifact.

use rqunit_adapter_rust::{artifact_path, render, workspace_root, Result};

fn main() {
    if let Err(e) = run() {
        eprintln!("extract-surface: {e}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let root = workspace_root()?;
    let path = artifact_path(&root);
    std::fs::write(&path, render(&root)?)?;
    println!("{}", path.display());
    Ok(())
}

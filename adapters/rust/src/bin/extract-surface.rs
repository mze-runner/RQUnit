//! The extractor role's entry point.
//!
//! Two invocations, one observation. With `--root <path>` it follows the
//! stdio role contract — artifact on stdout, logs on stderr, exit 0 ok /
//! 1 probe failure / 2 usage error — which is how core (and the compliance
//! kit) exec it. With no arguments it keeps the build-step form: discover
//! the workspace, write `actual-surface.json` where the config declares it,
//! and print the path — run after changing routes or NATS publication, then
//! commit the artifact. Extraction still runs in the stack's own build
//! system; the framework toolchain never builds this binary.

use std::path::Path;
use std::process::exit;

use rqunit_adapter_rust::{artifact_path, render, workspace_root, Result};

fn main() {
    let mut root = None;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--root" {
            let Some(value) = args.next() else {
                eprintln!("extract-surface: --root needs a path");
                exit(2);
            };
            root = Some(value);
        } else {
            // An ignored argument would silently fall through to build-step
            // mode and WRITE a file the caller never asked for.
            eprintln!("extract-surface: unknown argument '{arg}' (usage: extract-surface [--root <path>])");
            exit(2);
        }
    }
    if let Some(root) = root {
        match render(Path::new(&root)) {
            Ok(artifact) => print!("{artifact}"),
            Err(e) => {
                eprintln!("extract-surface: {e}");
                exit(1);
            }
        }
        return;
    }
    if let Err(e) = run_build_step() {
        eprintln!("extract-surface: {e}");
        exit(1);
    }
}

fn run_build_step() -> Result<()> {
    let root = workspace_root()?;
    let path = artifact_path(&root);
    std::fs::write(&path, render(&root)?)?;
    println!("{}", path.display());
    Ok(())
}

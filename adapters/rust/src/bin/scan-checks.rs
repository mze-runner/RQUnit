//! The scanner role's entry point (stdio contract: `--root <path>` in argv,
//! the scanned-checks artifact on stdout, logs on stderr; exit 0 ok /
//! 1 probe failure / 2 tool error).

use std::path::Path;
use std::process::exit;

use rqunit_adapter_rust::scan::render_checks;

fn main() {
    let mut root = None;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--root" {
            root = args.next();
        }
    }
    let Some(root) = root else {
        eprintln!("usage: scan-checks --root <path>");
        exit(2);
    };
    match render_checks(Path::new(&root)) {
        Ok(artifact) => print!("{artifact}"),
        Err(e) => {
            eprintln!("scan-checks: {e}");
            exit(1);
        }
    }
}

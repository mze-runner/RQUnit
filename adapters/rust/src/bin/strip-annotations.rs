//! The stripper role's entry point (stdio contract: `--root <path>` in argv,
//! the strip request on stdin, the stripped-files artifact on stdout, logs on
//! stderr; exit 0 ok / 1 probe failure / 2 tool error).

use std::io::Read;
use std::path::Path;
use std::process::exit;

use rqunit_adapter_rust::strip::respond;

fn main() {
    let mut root = None;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--root" {
            root = args.next();
        }
    }
    let Some(root) = root else {
        eprintln!("usage: strip-annotations --root <path> < strip-request.json");
        exit(2);
    };
    let mut request = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut request) {
        eprintln!("strip-annotations: read request: {e}");
        exit(2);
    }
    match respond(Path::new(&root), &request) {
        Ok(artifact) => print!("{artifact}"),
        Err(e) => {
            eprintln!("strip-annotations: {e}");
            exit(1);
        }
    }
}

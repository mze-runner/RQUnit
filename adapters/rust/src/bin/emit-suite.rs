//! The emitter role's entry point (stdio contract: the emit request on
//! stdin, the emitted-files response on stdout, logs on stderr; exit 0 ok /
//! 1 emit failure / 2 tool error). `--root` arrives per the role contract
//! but is deliberately unused: an emitter is a pure function of its request.

use std::io::Read;
use std::process::exit;

use rqunit_adapter_rust::emit::respond;

fn main() {
    let mut request = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut request) {
        eprintln!("emit-suite: read stdin: {e}");
        exit(2);
    }
    if request.trim().is_empty() {
        eprintln!("emit-suite: no emit request on stdin — this binary is invoked by rqunit generate, which supplies one");
        exit(2);
    }
    match respond(&request) {
        Ok(response) => print!("{response}"),
        Err(e) => {
            eprintln!("emit-suite: {e}");
            exit(1);
        }
    }
}

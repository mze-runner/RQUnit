//! Surface extraction — the Rust adapter's ONLY job (RU framework §5.6).
//!
//! This module observes what the code exposes and serializes it to
//! `actual-surface.json` (contract: rqunit `interfaces/actual-surface.schema.json`).
//! It deliberately makes NO judgment: nothing here knows what the manifest
//! declares, what a missing route means, or which divergence is acceptable.
//! `rqunit conformance` owns every one of those decisions, once, for all
//! languages — so adding a stack costs an extractor, not a reconciler.

use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

/// Extraction reads and parses files, both of which can fail for ordinary
/// reasons (a moved router, an unparseable source). Those are reported, never
/// panicked: this runs as a build step whose error message IS its interface.
pub type Result<T> = std::result::Result<T, Box<dyn Error>>;

/// Composition table: which router fn mounts where, under which access tier —
/// mirrors service-auth/http/src/routes/mod.rs. A moved route breaks loudly
/// on one side or the other rather than drifting silently.
const COMPOSITION: [(&str, &str, &str, &str); 7] = [
    (
        "service-auth/http/src/routes/mod.rs",
        "router",
        "",
        "public",
    ),
    (
        "service-auth/http/src/routes/account/mod.rs",
        "public_router",
        "/api/v1/account",
        "public",
    ),
    (
        "service-auth/http/src/routes/account/mod.rs",
        "scoped_router",
        "/api/v1/account",
        "scoped",
    ),
    (
        "service-auth/http/src/routes/account/mod.rs",
        "token_refresh_router",
        "/api/v1/account",
        "refresh",
    ),
    (
        "service-auth/http/src/routes/account/mod.rs",
        "router",
        "/api/v1/account",
        "protected",
    ),
    (
        "service-auth/http/src/routes/providers/native/mod.rs",
        "public_router",
        "/api/v1/providers/native",
        "public",
    ),
    (
        "service-auth/http/src/routes/providers/discord/mod.rs",
        "router",
        "/api/v1/providers/discord",
        "public",
    ),
];

/// Ratified divergences (§5.6). They ride in the artifact as reviewable data
/// rather than living as a constant in reconciler code — and `rqunit
/// conformance` still reports each one, with its justification, as a finding.
const EXCEPTIONS: [(&str, &str, &str, &str); 1] = [(
    "CF4",
    "service-auth",
    "GET /api/v1/healthz",
    "`internal` is a network-policy tier enforced at the ingress, not by route middleware; \
     the route is structurally public by design and Gate 1 ratified the difference.",
)];

const NATS_FAMILIES: [&str; 3] = ["account", "session", "notification"];

pub fn workspace_root() -> Result<PathBuf> {
    Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("crate must live one level under the workspace root")?
        .to_path_buf())
}

// ---------------------------------------------------------------- HTTP routes

/// `.route("<path>", get(h).post(h2))` occurrences inside one named router fn.
fn extract_routes(file: &Path, fn_name: &str) -> Result<Vec<(String, String)>> {
    let source = fs::read_to_string(file).map_err(|e| format!("read {}: {e}", file.display()))?;
    let ast = syn::parse_file(&source).map_err(|e| format!("parse {}: {e}", file.display()))?;
    let mut out = Vec::new();
    for item in ast.items {
        if let syn::Item::Fn(f) = item {
            if f.sig.ident == fn_name {
                collect_routes_in_block(&f.block, &mut out);
            }
        }
    }
    Ok(out)
}

fn collect_routes_in_block(block: &syn::Block, out: &mut Vec<(String, String)>) {
    struct V<'a> {
        out: &'a mut Vec<(String, String)>,
    }
    impl<'ast> syn::visit::Visit<'ast> for V<'_> {
        fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
            if call.method == "route" && call.args.len() == 2 {
                if let Some(path) = lit_str(&call.args[0]) {
                    for method in methods_of(&call.args[1]) {
                        self.out.push((method, path.clone()));
                    }
                }
            }
            syn::visit::visit_expr_method_call(self, call);
        }
    }
    syn::visit::Visit::visit_block(&mut V { out }, block);
}

fn lit_str(expr: &syn::Expr) -> Option<String> {
    if let syn::Expr::Lit(syn::ExprLit {
        lit: syn::Lit::Str(s),
        ..
    }) = expr
    {
        Some(s.value())
    } else {
        None
    }
}

/// Method chain: `get(h)` / `post(h).delete(h2)` → ["GET"] / ["POST", "DELETE"].
fn methods_of(expr: &syn::Expr) -> Vec<String> {
    const METHODS: [&str; 6] = ["get", "post", "put", "patch", "delete", "any"];
    match expr {
        syn::Expr::Call(call) => {
            if let syn::Expr::Path(p) = call.func.as_ref() {
                if let Some(segment) = p.path.segments.last() {
                    let name = segment.ident.to_string();
                    if METHODS.contains(&name.as_str()) {
                        return vec![name.to_uppercase()];
                    }
                }
            }
            Vec::new()
        }
        syn::Expr::MethodCall(chain) => {
            let mut methods = methods_of(&chain.receiver);
            let name = chain.method.to_string();
            if METHODS.contains(&name.as_str()) {
                methods.push(name.to_uppercase());
            }
            methods
        }
        _ => Vec::new(),
    }
}

// ---------------------------------------------------------------- NATS subjects

/// `pub const NAME: &str = "subject";` items across nats-contracts.
fn subject_constants(root: &Path) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();
    for family in NATS_FAMILIES {
        let path = root.join(format!("nats-contracts/src/{family}/subjects.rs"));
        let source =
            fs::read_to_string(&path).map_err(|e| format!("read {}: {e}", path.display()))?;
        let ast = syn::parse_file(&source).map_err(|e| format!("parse {}: {e}", path.display()))?;
        for item in ast.items {
            if let syn::Item::Const(c) = item {
                if let syn::Expr::Lit(syn::ExprLit {
                    lit: syn::Lit::Str(s),
                    ..
                }) = *c.expr
                {
                    out.insert(c.ident.to_string(), s.value());
                }
            }
        }
    }
    Ok(out)
}

fn published_subjects(root: &Path) -> Result<BTreeSet<String>> {
    let constants = subject_constants(root)?;
    let dir = root.join("service-auth/adapters/nats/src");
    let mut adapter_source = String::new();
    for entry in fs::read_dir(&dir).map_err(|e| format!("read {}: {e}", dir.display()))? {
        let path = entry?.path();
        if path.extension().is_some_and(|e| e == "rs") {
            adapter_source.push_str(
                &fs::read_to_string(&path).map_err(|e| format!("read {}: {e}", path.display()))?,
            );
        }
    }
    Ok(constants
        .into_iter()
        .filter(|(name, _)| adapter_source.contains(name.as_str()))
        .map(|(_, subject)| subject)
        .collect())
}

// ---------------------------------------------------------------- artifact

/// Render the actual-surface artifact. Deterministic: sorted keys throughout,
/// so the committed file only changes when the CODE's surface changes.
pub fn render(root: &Path) -> Result<String> {
    let mut routes: BTreeMap<(String, String), String> = BTreeMap::new();
    for (file, fn_name, prefix, tier) in COMPOSITION {
        for (method, path) in extract_routes(&root.join(file), fn_name)? {
            routes.insert((method, format!("{prefix}{path}")), tier.to_string());
        }
    }

    let endpoints: Vec<String> = routes
        .iter()
        .map(|((method, path), access)| {
            format!(
                "        {{ \"method\": \"{method}\", \"path\": \"{path}\", \"access\": \"{access}\" }}"
            )
        })
        .collect();
    let messages: Vec<String> = published_subjects(root)?
        .iter()
        .map(|subject| {
            format!("        {{ \"subject\": \"{subject}\", \"direction\": \"outbound\" }}")
        })
        .collect();
    let exceptions: Vec<String> = EXCEPTIONS
        .iter()
        .map(|(rule, service, target, justification)| {
            format!(
                "    {{\n      \"rule\": \"{rule}\",\n      \"service\": \"{service}\",\n      \
                 \"target\": \"{target}\",\n      \"justification\": \"{}\"\n    }}",
                justification.replace('"', "\\\"")
            )
        })
        .collect();

    Ok(format!(
        "{{\n  \"contract_version\": 1,\n  \"generated_by\": \"rqunit-adapter-rust {}\",\n  \
         \"services\": {{\n    \"service-auth\": {{\n      \"endpoints\": [\n{}\n      ],\n      \
         \"messages\": [\n{}\n      ]\n    }}\n  }},\n  \"exceptions\": [\n{}\n  ]\n}}\n",
        env!("CARGO_PKG_VERSION"),
        endpoints.join(",\n"),
        messages.join(",\n"),
        exceptions.join(",\n"),
    ))
}

pub fn artifact_path(root: &Path) -> PathBuf {
    root.join("spec-conformance-tests/actual-surface.json")
}

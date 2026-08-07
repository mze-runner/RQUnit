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

pub mod scan;

/// Extraction reads and parses files, both of which can fail for ordinary
/// reasons (a moved router, an unparseable source). Those are reported, never
/// panicked: this runs as a build step whose error message IS its interface.
pub type Result<T> = std::result::Result<T, Box<dyn Error>>;

/// The repo-specific inputs this extractor needs, read from the consumer's
/// `rqunit.toml`. They used to be `const` tables here, which put one
/// consumer's file paths, service name and domain vocabulary inside the
/// product. Composition is a fact about a repository, not about Rust or about
/// a web framework — so it is configuration, and the adapter is the thing that
/// stays generic.
#[derive(Default, Debug)]
pub struct StackConfig {
    /// Manifest service slug this extractor reports on.
    pub service: String,
    /// (file, router fn, path prefix, access tier) — which router mounts where.
    pub routers: Vec<(String, String, String, String)>,
    /// Files or directories declaring subject constants.
    pub subject_sources: Vec<String>,
    /// Sources whose code references those constants — what is really published.
    pub publisher_sources: Vec<String>,
    /// Where the artifact is written.
    pub actual_surface: String,
    /// Files or directories declaring audit-code constants.
    pub audit_code_sources: Vec<String>,
    /// Sources whose code references those constants — what is really recorded.
    pub audit_emitter_sources: Vec<String>,
}

fn strings(value: Option<&toml::Value>) -> Vec<String> {
    value
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

/// Read `[stacks.rust]` from `rqunit.toml` at the workspace root.
///
/// A missing file or table is an error rather than a default: an extractor
/// that guessed a composition would report a surface nobody declared, and the
/// reconciler would believe it.
pub fn load_config(root: &Path) -> Result<StackConfig> {
    let path = root.join("rqunit.toml");
    let source = fs::read_to_string(&path).map_err(|e| {
        format!(
            "read {}: {e} — the extractor needs [stacks.rust] to know which \
                              routers to walk",
            path.display()
        )
    })?;
    let doc: toml::Table = source
        .parse()
        .map_err(|e| format!("parse {}: {e}", path.display()))?;
    let rust = doc
        .get("stacks")
        .and_then(|s| s.get("rust"))
        .ok_or_else(|| format!("{}: no [stacks.rust] table", path.display()))?;

    let mut routers = Vec::new();
    if let Some(entries) = rust.get("routers").and_then(|r| r.as_array()) {
        for entry in entries {
            let get = |key: &str| entry.get(key).and_then(|v| v.as_str()).unwrap_or("");
            let (file, function) = (get("file"), get("function"));
            if file.is_empty() || function.is_empty() {
                return Err(format!(
                    "{}: every [[stacks.rust.routers]] needs `file` and `function` — an \
                     extractor cannot find a router it cannot name",
                    path.display()
                )
                .into());
            }
            routers.push((
                file.to_string(),
                function.to_string(),
                get("prefix").to_string(),
                get("access").to_string(),
            ));
        }
    }
    let messages = rust.get("messages");
    let audit = rust.get("audit");
    Ok(StackConfig {
        service: rust
            .get("service")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
        routers,
        subject_sources: strings(messages.and_then(|m| m.get("subject_sources"))),
        publisher_sources: strings(messages.and_then(|m| m.get("publisher_sources"))),
        // The write target is the extractor role's declared artifact
        // ([stacks.rust.adapter] extractor = { artifact = "..." }): core reads
        // the file exactly where this adapter says it wrote it.
        actual_surface: rust
            .get("adapter")
            .and_then(|a| a.get("extractor"))
            .and_then(|e| e.get("artifact"))
            .and_then(|v| v.as_str())
            .unwrap_or("spec-conformance-tests/actual-surface.json")
            .to_string(),
        audit_code_sources: strings(audit.and_then(|a| a.get("code_sources"))),
        audit_emitter_sources: strings(audit.and_then(|a| a.get("emitter_sources"))),
    })
}

pub fn workspace_root() -> Result<PathBuf> {
    Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("crate must live one level under the workspace root")?
        .to_path_buf())
}

// ---------------------------------------------------------------- HTTP routes

/// `.route("<path>", get(h).post(h2))` occurrences inside one named router fn.
fn extract_routes(file: &Path, fn_name: &str) -> Result<Vec<(String, String, Option<String>)>> {
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

/// The handler ident inside `get(handler)` / `post(handler)`, per method — the
/// only bridge from a route to the types it carries.
pub(crate) fn handlers_of(expr: &syn::Expr) -> Vec<(String, Option<String>)> {
    const METHODS: [&str; 6] = ["get", "post", "put", "patch", "delete", "any"];
    let ident_of = |call: &syn::ExprCall| -> Option<String> {
        call.args.first().and_then(|arg| match arg {
            syn::Expr::Path(p) => p.path.segments.last().map(|s| s.ident.to_string()),
            _ => None,
        })
    };
    match expr {
        syn::Expr::Call(call) => {
            if let syn::Expr::Path(p) = call.func.as_ref() {
                if let Some(segment) = p.path.segments.last() {
                    let name = segment.ident.to_string();
                    if METHODS.contains(&name.as_str()) {
                        return vec![(name.to_uppercase(), ident_of(call))];
                    }
                }
            }
            Vec::new()
        }
        syn::Expr::MethodCall(chain) => {
            let mut found = handlers_of(&chain.receiver);
            let name = chain.method.to_string();
            if METHODS.contains(&name.as_str()) {
                let handler = chain.args.first().and_then(|arg| match arg {
                    syn::Expr::Path(p) => p.path.segments.last().map(|s| s.ident.to_string()),
                    _ => None,
                });
                found.push((name.to_uppercase(), handler));
            }
            found
        }
        _ => Vec::new(),
    }
}

fn collect_routes_in_block(block: &syn::Block, out: &mut Vec<(String, String, Option<String>)>) {
    struct V<'a> {
        out: &'a mut Vec<(String, String, Option<String>)>,
    }
    impl<'ast> syn::visit::Visit<'ast> for V<'_> {
        fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
            if call.method == "route" && call.args.len() == 2 {
                if let Some(path) = lit_str(&call.args[0]) {
                    for (method, handler) in handlers_of(&call.args[1]) {
                        self.out.push((method, path.clone(), handler));
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

// ---------------------------------------------------------------- NATS subjects

/// `pub const NAME: &str = "value";` items across the configured sources.
///
/// Serves both async subjects and audit codes: they are the same shape of fact
/// — a string constant declared in one place and referenced where it is used —
/// so one scan answers both.
fn string_constants(root: &Path, sources: &[String]) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();
    for file in expand(root, sources) {
        let Ok(source) = fs::read_to_string(&file) else {
            continue;
        };
        let ast = syn::parse_file(&source).map_err(|e| format!("parse {}: {e}", file.display()))?;
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

/// Configured paths → the `.rs` files they name, directories walked.
fn expand(root: &Path, sources: &[String]) -> Vec<PathBuf> {
    let mut out = Vec::new();
    for source in sources {
        let path = root.join(source);
        if path.is_dir() {
            out.extend(source_files(&path));
        } else if path.is_file() {
            out.push(path);
        }
    }
    out.sort();
    out.dedup();
    out
}

/// A subject is PUBLISHED when publisher code references its constant —
/// naming a subject is not the same as emitting one.
fn published_subjects(root: &Path, config: &StackConfig) -> Result<BTreeSet<String>> {
    let constants = string_constants(root, &config.subject_sources)?;
    let mut publisher_source = String::new();
    for file in expand(root, &config.publisher_sources) {
        publisher_source.push_str(
            &fs::read_to_string(&file).map_err(|e| format!("read {}: {e}", file.display()))?,
        );
    }
    Ok(constants
        .into_iter()
        .filter(|(name, _)| publisher_source.contains(name.as_str()))
        .map(|(_, subject)| subject)
        .collect())
}

/// Audit codes the code actually records.
///
/// A route exists in a table; an emission is a call site. This proves the call
/// site EXISTS — it cannot prove the line ever runs, and saying otherwise would
/// turn a green run into a claim nobody checked.
fn recorded_audit_codes(root: &Path, config: &StackConfig) -> Result<BTreeSet<String>> {
    let constants = string_constants(root, &config.audit_code_sources)?;
    let mut emitter_source = String::new();
    for file in expand(root, &config.audit_emitter_sources) {
        emitter_source.push_str(
            &fs::read_to_string(&file).map_err(|e| format!("read {}: {e}", file.display()))?,
        );
    }
    Ok(constants
        .into_iter()
        .filter(|(name, _)| emitter_source.contains(name.as_str()))
        .map(|(_, code)| code)
        .collect())
}

// ---------------------------------------------------------------- artifact

/// Render the actual-surface artifact. Deterministic: sorted keys throughout,
/// so the committed file only changes when the CODE's surface changes.
pub fn render(root: &Path) -> Result<String> {
    let config = load_config(root)?;
    if config.service.is_empty() {
        return Err(
            "rqunit.toml: [stacks.rust] needs `service` — the artifact is keyed by \
                    manifest service slug, and an extractor must not guess it"
                .into(),
        );
    }
    let mut routes: BTreeMap<(String, String), (String, Option<String>)> = BTreeMap::new();
    for (file, fn_name, prefix, tier) in &config.routers {
        for (method, path, handler) in extract_routes(&root.join(file), fn_name)? {
            routes.insert(
                (method, format!("{prefix}{path}")),
                (tier.to_string(), handler),
            );
        }
    }

    // Shape resolution walks the sources the routers live in. A handler that
    // cannot be resolved yields no block at all — "not observed" is a distinct
    // answer from "carries nothing", and only the reconciler may act on it.
    let mut source_dirs: BTreeSet<PathBuf> = BTreeSet::new();
    for (file, _, _, _) in &config.routers {
        if let Some(parent) = root.join(file).parent() {
            source_dirs.insert(parent.to_path_buf());
        }
    }
    let mut files: Vec<PathBuf> = Vec::new();
    for dir in &source_dirs {
        files.extend(source_files(dir));
    }
    files.sort();
    files.dedup();
    let structs = struct_fields(&files);
    let signatures = handler_signatures(&files);

    let endpoints: Vec<String> = routes
        .iter()
        .map(|((method, path), (access, handler))| {
            let mut line = format!(
                "        {{ \"method\": \"{method}\", \"path\": \"{path}\", \"access\": \"{access}\""
            );
            if let Some((request, response)) = handler.as_ref().and_then(|h| signatures.get(h)) {
                if let Some(json) = shape_json(&shape_for(request.as_ref(), &structs)) {
                    line.push_str(&format!(", \"inbound\": {json}"));
                }
                if let Some(json) = shape_json(&shape_for(response.as_ref(), &structs)) {
                    line.push_str(&format!(", \"outbound\": {json}"));
                }
            }
            line.push_str(" }");
            line
        })
        .collect();
    let audit_events: Vec<String> = recorded_audit_codes(root, &config)?
        .iter()
        .map(|code| format!("        {{ \"code\": \"{code}\" }}"))
        .collect();
    let messages: Vec<String> = published_subjects(root, &config)?
        .iter()
        .map(|subject| {
            format!("        {{ \"subject\": \"{subject}\", \"direction\": \"outbound\" }}")
        })
        .collect();
    // No `exceptions` key: an extractor observes, and does not get to excuse
    // what it observed. Waivers are reviewed decisions and live in the store at
    // spec/framework/conformance-exceptions.yaml, where Gate 1 governs them.
    // `covers` states which families this run examined, so silence about a
    // family is never read as a denial.
    Ok(format!(
        "{{\n  \"contract_version\": 1,\n  \"generated_by\": \"rqunit-adapter-rust {}\",\n  \
         \"covers\": [\"endpoints\", \"messages\", \"audit_events\"],\n  \
         \"services\": {{\n    \"{}\": {{\n      \"endpoints\": [\n{}\n      ],\n      \
         \"messages\": [\n{}\n      ],\n      \
         \"audit_events\": [\n{}\n      ]\n    }}\n  }}\n}}\n",
        env!("CARGO_PKG_VERSION"),
        config.service,
        endpoints.join(",\n"),
        messages.join(",\n"),
        audit_events.join(",\n"),
    ))
}

pub fn artifact_path(root: &Path) -> PathBuf {
    let relative = load_config(root)
        .map(|c| c.actual_surface)
        .unwrap_or_else(|_| "spec-conformance-tests/actual-surface.json".to_string());
    root.join(relative)
}

// ---------------------------------------------------------------- shapes

/// One direction's observed shape: the handler's declared type and its field
/// names (contract: `observed_shape` in actual-surface.schema.json).
///
/// OBSERVATION ONLY. Whether a field is required, nullable, or must not leak
/// is a requirement question the manifest answers and tests prove; an adapter
/// reporting it would be judging. Absent means "not observed", never "empty" —
/// which is what lets `rqunit conformance` degrade to presence-only matching
/// instead of calling every declared field missing.
#[derive(Default, Clone)]
pub struct ObservedShape {
    pub type_name: Option<String>,
    pub fields: Option<Vec<String>>,
}

impl ObservedShape {
    fn is_empty(&self) -> bool {
        self.type_name.is_none() && self.fields.is_none()
    }
}

/// Every `struct Name { .. }` in a source tree, with its serde-visible field
/// names. Nested structs are flattened with dotted names so they line up with
/// the manifest's census, which spells nesting the same way.
pub(crate) fn struct_fields(files: &[PathBuf]) -> BTreeMap<String, Vec<(String, Option<String>)>> {
    let mut out = BTreeMap::new();
    for file in files {
        let Ok(source) = fs::read_to_string(file) else {
            continue;
        };
        let Ok(ast) = syn::parse_file(&source) else {
            continue;
        };
        for item in ast.items {
            let syn::Item::Struct(s) = item else { continue };
            let syn::Fields::Named(named) = &s.fields else {
                continue;
            };
            let mut fields = Vec::new();
            for field in &named.named {
                let Some(ident) = field.ident.as_ref() else {
                    continue;
                };
                if serde_skipped(&field.attrs) {
                    continue;
                }
                let name = serde_rename(&field.attrs).unwrap_or_else(|| ident.to_string());
                fields.push((name, inner_type_name(&field.ty)));
            }
            out.insert(s.ident.to_string(), fields);
        }
    }
    out
}

/// `#[serde(skip)]` / `#[serde(skip_serializing)]` — the field is not on the wire.
pub(crate) fn serde_skipped(attrs: &[syn::Attribute]) -> bool {
    attrs.iter().any(|a| {
        a.path().is_ident("serde")
            && a.meta
                .to_token_stream_string()
                .map(|s| s.contains("skip") && !s.contains("skip_serializing_if"))
                .unwrap_or(false)
    })
}

/// `#[serde(rename = "x")]` — the wire name differs from the Rust name, and the
/// manifest declares the wire name.
pub(crate) fn serde_rename(attrs: &[syn::Attribute]) -> Option<String> {
    for attr in attrs {
        if !attr.path().is_ident("serde") {
            continue;
        }
        let text = attr.meta.to_token_stream_string()?;
        if let Some(i) = text.find("rename = \"") {
            let rest = &text[i + "rename = \"".len()..];
            if let Some(end) = rest.find('"') {
                return Some(rest[..end].to_string());
            }
        }
    }
    None
}

trait MetaText {
    fn to_token_stream_string(&self) -> Option<String>;
}

impl MetaText for syn::Meta {
    fn to_token_stream_string(&self) -> Option<String> {
        match self {
            syn::Meta::List(list) => Some(list.tokens.to_string()),
            _ => None,
        }
    }
}

/// The innermost named type of `Json<T>`, `Option<T>`, `Vec<T>`, `Result<T, _>`
/// — the shape a wrapper carries, which is what the manifest declares.
pub(crate) fn inner_type_name(ty: &syn::Type) -> Option<String> {
    let syn::Type::Path(path) = ty else {
        return None;
    };
    let segment = path.path.segments.last()?;
    let name = segment.ident.to_string();
    if let syn::PathArguments::AngleBracketed(args) = &segment.arguments {
        for arg in &args.args {
            if let syn::GenericArgument::Type(inner) = arg {
                if let Some(found) = inner_type_name(inner) {
                    return Some(found);
                }
            }
        }
    }
    Some(name)
}

/// Every `.rs` file under a directory — handlers rarely live beside the router
/// that mounts them, so shape resolution needs the whole tree.
pub(crate) fn source_files(dir: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let Ok(entries) = fs::read_dir(dir) else {
        return out;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            out.extend(source_files(&path));
        } else if path.extension().is_some_and(|e| e == "rs") {
            out.push(path);
        }
    }
    out.sort();
    out
}

/// Handler signatures: fn name → (request type, response type), each the
/// innermost named type of whatever wrapper the framework uses.
///
/// A request type is read from a `Json<T>` parameter; a response type from the
/// return position. Handlers the walk cannot resolve simply do not appear —
/// omission is "not observed", and the reconciler treats it as such.
pub(crate) fn handler_signatures(
    files: &[PathBuf],
) -> BTreeMap<String, (Option<String>, Option<String>)> {
    let mut out = BTreeMap::new();
    for file in files {
        let Ok(source) = fs::read_to_string(file) else {
            continue;
        };
        let Ok(ast) = syn::parse_file(&source) else {
            continue;
        };
        for item in ast.items {
            let syn::Item::Fn(f) = item else { continue };
            let mut request = None;
            for arg in &f.sig.inputs {
                let syn::FnArg::Typed(typed) = arg else {
                    continue;
                };
                if let syn::Type::Path(path) = typed.ty.as_ref() {
                    if let Some(segment) = path.path.segments.last() {
                        if segment.ident == "Json" {
                            request = inner_type_name(typed.ty.as_ref());
                        }
                    }
                }
            }
            let response = match &f.sig.output {
                syn::ReturnType::Type(_, ty) => inner_type_name(ty),
                syn::ReturnType::Default => None,
            };
            if request.is_some() || response.is_some() {
                out.insert(f.sig.ident.to_string(), (request, response));
            }
        }
    }
    out
}

/// Flatten a struct into dotted wire names, following named members whose type
/// is itself a known struct. Depth-limited: a self-referential type would
/// otherwise walk forever, and a boundary that deep is not a census anyone
/// reviews.
pub(crate) fn flatten(
    type_name: &str,
    structs: &BTreeMap<String, Vec<(String, Option<String>)>>,
    prefix: &str,
    depth: usize,
    out: &mut Vec<String>,
) {
    if depth > 4 {
        return;
    }
    let Some(fields) = structs.get(type_name) else {
        return;
    };
    for (name, inner) in fields {
        let dotted = if prefix.is_empty() {
            name.clone()
        } else {
            format!("{prefix}.{name}")
        };
        out.push(dotted.clone());
        if let Some(inner) = inner {
            if inner != type_name && structs.contains_key(inner) {
                flatten(inner, structs, &dotted, depth + 1, out);
            }
        }
    }
}

pub(crate) fn shape_for(
    type_name: Option<&String>,
    structs: &BTreeMap<String, Vec<(String, Option<String>)>>,
) -> ObservedShape {
    let Some(type_name) = type_name else {
        return ObservedShape::default();
    };
    let mut fields = Vec::new();
    flatten(type_name, structs, "", 0, &mut fields);
    ObservedShape {
        type_name: Some(type_name.clone()),
        // A named type whose definition is out of reach yields a name and no
        // fields — still useful: CF8 needs identity, not a census.
        fields: if structs.contains_key(type_name) {
            Some(fields)
        } else {
            None
        },
    }
}

pub(crate) fn shape_json(shape: &ObservedShape) -> Option<String> {
    if shape.is_empty() {
        return None;
    }
    let mut parts = Vec::new();
    if let Some(name) = &shape.type_name {
        parts.push(format!("\"type_name\": \"{name}\""));
    }
    if let Some(fields) = &shape.fields {
        let names: Vec<String> = fields.iter().map(|f| format!("\"{f}\"")).collect();
        parts.push(format!("\"fields\": [{}]", names.join(", ")));
    }
    Some(format!("{{ {} }}", parts.join(", ")))
}

// ---------------------------------------------------------------- tests

#[cfg(test)]
mod tests {
    //! The extractor's contract is that it OBSERVES. These assert what it sees
    //! and, just as importantly, that it reports nothing when it cannot see —
    //! a guess here becomes a false divergence in every consumer's gate.
    use super::*;
    use std::io::Write;

    /// std-only scratch tree: the adapter's entire dependency budget is `syn`,
    /// and a test-only crate is still a crate every consumer has to resolve.
    fn tree(case: &str, files: &[(&str, &str)]) -> Vec<PathBuf> {
        let dir = std::env::temp_dir().join(format!("rqunit-extract-{case}"));
        let _ = fs::remove_dir_all(&dir);
        let mut paths = Vec::new();
        for (name, body) in files {
            let path = dir.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let mut f = fs::File::create(&path).unwrap();
            f.write_all(body.as_bytes()).unwrap();
            paths.push(path);
        }
        paths
    }

    const SOURCE: &str = r#"
        pub struct Money { pub amount: i64, pub currency: String }
        pub struct OrderView {
            pub id: String,
            pub total: Money,
            #[serde(rename = "placed_at")]
            pub placed: String,
            #[serde(skip)]
            pub internal_cost: i64,
        }
        pub struct NewOrder { pub sku: String }
        pub async fn get_order(Path(id): Path<String>) -> Json<OrderView> { todo!() }
        pub async fn place_order(Json(body): Json<NewOrder>) -> Result<Json<OrderView>, Error> { todo!() }
        pub async fn healthz() -> StatusCode { todo!() }
    "#;

    #[test]
    fn nested_structs_flatten_to_the_manifest_s_dotted_spelling() {
        let files = tree("nested", &[("src/lib.rs", SOURCE)]);
        let structs = struct_fields(&files);
        let shape = shape_for(Some(&"OrderView".to_string()), &structs);
        let fields = shape
            .fields
            .expect("OrderView is in reach, so its fields are observed");
        assert!(fields.contains(&"total.amount".to_string()));
        assert!(fields.contains(&"total.currency".to_string()));
    }

    #[test]
    fn serde_attributes_decide_the_wire_name_and_what_is_on_the_wire() {
        let files = tree("serde", &[("src/lib.rs", SOURCE)]);
        let structs = struct_fields(&files);
        let fields = shape_for(Some(&"OrderView".to_string()), &structs)
            .fields
            .unwrap();
        assert!(
            fields.contains(&"placed_at".to_string()),
            "rename wins: {fields:?}"
        );
        assert!(!fields.contains(&"placed".to_string()));
        assert!(
            !fields.contains(&"internal_cost".to_string()),
            "skip means not on the wire"
        );
    }

    #[test]
    fn wrappers_resolve_to_the_type_they_carry() {
        let files = tree("wrappers", &[("src/lib.rs", SOURCE)]);
        let signatures = handler_signatures(&files);
        let (request, response) = signatures.get("place_order").expect("handler found");
        assert_eq!(
            response.as_deref(),
            Some("OrderView"),
            "through Result<Json<T>, E>"
        );
        assert_eq!(
            request.as_deref(),
            Some("NewOrder"),
            "from the Json<T> parameter"
        );
    }

    #[test]
    fn an_unreachable_type_yields_identity_without_a_census() {
        // CF8 needs identity; CF7 needs fields. Reporting an empty field list
        // for a type we cannot see would make every declared field look absent.
        let files = tree("foreign", &[("src/lib.rs", SOURCE)]);
        let structs = struct_fields(&files);
        let shape = shape_for(Some(&"SomeForeignType".to_string()), &structs);
        assert_eq!(shape.type_name.as_deref(), Some("SomeForeignType"));
        assert!(shape.fields.is_none(), "unseen fields are not empty fields");
        assert!(shape_json(&shape).unwrap().contains("type_name"));
        assert!(!shape_json(&shape).unwrap().contains("fields"));
    }

    #[test]
    fn a_handler_with_no_body_types_is_not_reported_at_all() {
        let files = tree("nobody", &[("src/lib.rs", SOURCE)]);
        let signatures = handler_signatures(&files);
        let (request, response) = signatures.get("healthz").expect("handler found");
        assert!(request.is_none());
        assert_eq!(response.as_deref(), Some("StatusCode"));
        assert!(shape_json(&ObservedShape::default()).is_none());
    }

    const CONFIG: &str = r#"
        [stacks.rust]
        service = "service-orders"

        [stacks.rust.adapter]
        extractor = { artifact = "conformance/actual-surface.json" }

        [[stacks.rust.routers]]
        file = "http/src/routes/mod.rs"
        function = "router"
        prefix = "/api/v1/orders"
        access = "protected"

        [stacks.rust.messages]
        subject_sources = ["wire-contracts/src"]
        publisher_sources = ["adapters/nats/src"]
    "#;

    #[test]
    fn composition_comes_from_the_consumer_s_config_not_from_this_crate() {
        let files = tree("config", &[("rqunit.toml", CONFIG)]);
        let root = files[0].parent().unwrap();
        let config = load_config(root).expect("config reads");
        assert_eq!(config.service, "service-orders");
        assert_eq!(config.routers.len(), 1);
        let (file, function, prefix, access) = &config.routers[0];
        assert_eq!(
            (
                file.as_str(),
                function.as_str(),
                prefix.as_str(),
                access.as_str()
            ),
            (
                "http/src/routes/mod.rs",
                "router",
                "/api/v1/orders",
                "protected"
            )
        );
        assert_eq!(
            config.subject_sources,
            vec!["wire-contracts/src".to_string()]
        );
        assert_eq!(config.actual_surface, "conformance/actual-surface.json");
    }

    #[test]
    fn a_missing_config_is_an_error_never_a_guessed_composition() {
        // An extractor that guessed would report a surface nobody declared, and
        // the reconciler would believe it.
        let files = tree("noconfig", &[("src/lib.rs", SOURCE)]);
        let root = files[0].parent().unwrap().parent().unwrap();
        let err = load_config(root).expect_err("no rqunit.toml");
        assert!(err.to_string().contains("[stacks.rust]"), "{err}");
    }

    #[test]
    fn a_router_without_a_name_is_rejected() {
        let files = tree(
            "badrouter",
            &[(
                "rqunit.toml",
                "[stacks.rust]\nservice = \"s\"\n[[stacks.rust.routers]]\nfile = \"a.rs\"\n",
            )],
        );
        let root = files[0].parent().unwrap();
        let err = load_config(root).expect_err("router missing `function`");
        assert!(
            err.to_string()
                .contains("cannot find a router it cannot name"),
            "{err}"
        );
    }

    #[test]
    fn an_audit_code_counts_as_recorded_only_where_a_call_site_names_it() {
        // Declaring a code is not recording one. The whole point of CF10 is that
        // a service could declare twenty events and emit none.
        let files = tree(
            "audit",
            &[
                (
                    "codes/src/lib.rs",
                    r#"
                pub const ORDER_CANCELLED: &str = "orders.cancelled";
                pub const ORDER_REFUNDED: &str = "orders.refunded";
            "#,
                ),
                (
                    "app/src/cancel.rs",
                    r#"
                fn cancel() { audit(ORDER_CANCELLED, &ctx); }
            "#,
                ),
            ],
        );
        let root = files[0]
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let config = StackConfig {
            audit_code_sources: vec!["codes/src".into()],
            audit_emitter_sources: vec!["app/src".into()],
            ..Default::default()
        };
        let recorded = recorded_audit_codes(root, &config).expect("scan");
        assert!(recorded.contains("orders.cancelled"));
        assert!(
            !recorded.contains("orders.refunded"),
            "declared but never emitted: {recorded:?}"
        );
    }

    #[test]
    fn route_definitions_carry_their_handler_across_a_method_chain() {
        let expr: syn::Expr = syn::parse_str("get(get_order).post(place_order)").unwrap();
        let found = handlers_of(&expr);
        assert_eq!(
            found,
            vec![
                ("GET".to_string(), Some("get_order".to_string())),
                ("POST".to_string(), Some("place_order".to_string())),
            ]
        );
    }
}

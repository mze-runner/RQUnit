//! Test scanning — the Rust adapter's scanner role (contract: rqunit
//! `interfaces/scanned-checks.schema.json`).
//!
//! OBSERVATION ONLY. This module reports which `#[test]`/`#[tokio::test]`
//! functions exist under participating crates' `tests/` directories and what
//! each one's `/// verifies:` annotation claims. It decides nothing: whether
//! an annotation resolves, whether an untraced check blocks, and what "new"
//! means are all `rqunit trace`'s judgments, made once for every language.
//!
//! Which crates participate is consumer data — `trace_scan` in the target
//! tree's own `rqunit.toml`. A tree that declares no `[stacks.rust]` observes
//! zero checks: "nothing participates" is an observation, not an error.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use syn::visit::Visit;

use crate::Result;

pub struct ScannedCheck {
    pub id: String,
    pub path: String,
    pub fn_name: String,
    pub verifies: Vec<String>,
}

/// The consumer's `trace_scan` globs, or `None` when the tree declares no
/// `[stacks.rust]` table at all.
fn trace_scan(root: &Path) -> Result<Option<Vec<String>>> {
    let path = root.join("rqunit.toml");
    let Ok(source) = fs::read_to_string(&path) else {
        return Ok(None);
    };
    let doc: toml::Table = source
        .parse()
        .map_err(|e| format!("parse {}: {e}", path.display()))?;
    let Some(rust) = doc.get("stacks").and_then(|s| s.get("rust")) else {
        return Ok(None);
    };
    let patterns = match rust.get("trace_scan") {
        None => vec!["**/Cargo.toml".to_string()],
        // A malformed glob list silently bent into patterns would let the
        // gate observe nonsense and report green — the shape errors here,
        // where the key is read.
        Some(value) => {
            let entries = value.as_array().ok_or_else(|| {
                format!(
                    "{}: [stacks.rust] trace_scan must be a list of glob strings",
                    path.display()
                )
            })?;
            entries
                .iter()
                .map(|v| {
                    v.as_str().map(str::to_string).ok_or_else(|| {
                        format!(
                            "{}: [stacks.rust] trace_scan must be a list of glob strings",
                            path.display()
                        )
                        .into()
                    })
                })
                .collect::<Result<Vec<String>>>()?
        }
    };
    Ok(Some(patterns))
}

pub fn scan(root: &Path) -> Result<Vec<ScannedCheck>> {
    let Some(patterns) = trace_scan(root)? else {
        return Ok(Vec::new());
    };
    let mut manifests: BTreeSet<PathBuf> = BTreeSet::new();
    let mut files = Vec::new();
    walk(root, &mut files);
    for relative in &files {
        let text = relative.to_string_lossy().replace('\\', "/");
        if patterns.iter().any(|p| glob_match(p, &text)) {
            manifests.insert(root.join(relative));
        }
    }

    let mut out = Vec::new();
    let mut seen_dirs: BTreeSet<PathBuf> = BTreeSet::new();
    for manifest in manifests {
        let crate_dir = manifest.parent().unwrap_or(root).to_path_buf();
        let tests_dir = crate_dir.join("tests");
        if seen_dirs.contains(&crate_dir) || !tests_dir.is_dir() {
            continue;
        }
        seen_dirs.insert(crate_dir);
        let Some(package) = package_name(&manifest)? else {
            continue;
        };
        let mut sources = Vec::new();
        collect_rs(&tests_dir, &mut sources);
        sources.sort();
        for source in sources {
            out.extend(checks_in_file(root, &package, &source)?);
        }
    }
    Ok(out)
}

/// Render the artifact for one tree — the string the `scan-checks` binary
/// writes to stdout. Deterministic: a byte-for-byte function of the tree.
pub fn render_checks(root: &Path) -> Result<String> {
    let checks = scan(root)?;
    let lines: Vec<String> = checks
        .iter()
        .map(|c| {
            let verifies: Vec<String> = c
                .verifies
                .iter()
                .map(|v| format!("\"{}\"", escape(v)))
                .collect();
            format!(
                "    {{ \"id\": \"{}\", \"path\": \"{}\", \"fn\": \"{}\", \"verifies\": [{}] }}",
                escape(&c.id),
                escape(&c.path),
                escape(&c.fn_name),
                verifies.join(", ")
            )
        })
        .collect();
    let body = if lines.is_empty() {
        "[]".to_string()
    } else {
        format!("[\n{}\n  ]", lines.join(",\n"))
    };
    Ok(format!(
        "{{\n  \"contract_version\": 1,\n  \"generated_by\": \"rqunit-adapter-rust scan-checks {}\",\n  \"checks\": {}\n}}\n",
        env!("CARGO_PKG_VERSION"),
        body
    ))
}

fn package_name(manifest: &Path) -> Result<Option<String>> {
    let source =
        fs::read_to_string(manifest).map_err(|e| format!("read {}: {e}", manifest.display()))?;
    let doc: toml::Table = source
        .parse()
        .map_err(|e| format!("parse {}: {e}", manifest.display()))?;
    Ok(doc
        .get("package")
        .and_then(|p| p.get("name"))
        .and_then(|n| n.as_str())
        .map(str::to_string))
}

// Rust-specific knowledge this adapter is entitled to: `target/` is cargo's
// output directory, full of vendored Cargo.tomls that are nobody's tests.
fn walk(root: &Path, out: &mut Vec<PathBuf>) {
    fn inner(root: &Path, dir: &Path, out: &mut Vec<PathBuf>) {
        let Ok(entries) = fs::read_dir(dir) else {
            return;
        };
        let mut entries: Vec<_> = entries.flatten().map(|e| e.path()).collect();
        entries.sort();
        for path in entries {
            if path.is_dir() {
                if path
                    .file_name()
                    .is_some_and(|n| n == ".git" || n == "target")
                {
                    continue;
                }
                inner(root, &path, out);
            } else if let Ok(relative) = path.strip_prefix(root) {
                out.push(relative.to_path_buf());
            }
        }
    }
    inner(root, root, out);
}

fn escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn collect_rs(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_rs(&path, out);
        } else if path.extension().is_some_and(|e| e == "rs") {
            out.push(path);
        }
    }
}

// ---------------------------------------------------------------- glob match
//
// `trace_scan` needs path-segment globbing: `**` spans directories, `*` spans
// within one segment. Hand-rolled rather than a new dependency — the needed
// semantics are this small, and the compliance fixtures pin them.

fn glob_match(pattern: &str, path: &str) -> bool {
    let pat: Vec<&str> = pattern.split('/').collect();
    let segments: Vec<&str> = path.split('/').collect();
    seg_match(&pat, &segments)
}

fn seg_match(pat: &[&str], path: &[&str]) -> bool {
    match pat.first() {
        None => path.is_empty(),
        Some(&"**") => (0..=path.len()).any(|i| seg_match(&pat[1..], &path[i..])),
        Some(seg) => !path.is_empty() && wild(seg, path[0]) && seg_match(&pat[1..], &path[1..]),
    }
}

fn wild(pat: &str, s: &str) -> bool {
    if let Some(rest) = pat.strip_prefix('*') {
        (0..=s.len())
            .filter(|i| s.is_char_boundary(*i))
            .any(|i| wild(rest, &s[i..]))
    } else {
        match (pat.chars().next(), s.chars().next()) {
            (None, None) => true,
            (Some(p), Some(c)) if p == c => wild(&pat[p.len_utf8()..], &s[c.len_utf8()..]),
            _ => false,
        }
    }
}

// ---------------------------------------------------------------- extraction

struct TestVisitor<'a> {
    root: &'a Path,
    package: &'a str,
    file: &'a Path,
    out: Vec<ScannedCheck>,
}

impl<'ast> Visit<'ast> for TestVisitor<'_> {
    fn visit_item_fn(&mut self, item: &'ast syn::ItemFn) {
        if item.attrs.iter().any(is_test_attr) {
            let stem = self
                .file
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();
            let fn_name = item.sig.ident.to_string();
            let relative = self
                .file
                .strip_prefix(self.root)
                .unwrap_or(self.file)
                .to_string_lossy()
                .replace('\\', "/");
            self.out.push(ScannedCheck {
                id: format!("{}::{stem}::{fn_name}", self.package),
                path: relative,
                fn_name,
                verifies: verifies_of(&item.attrs),
            });
        }
        syn::visit::visit_item_fn(self, item);
    }
}

fn is_test_attr(attr: &syn::Attribute) -> bool {
    let segments: Vec<String> = attr
        .path()
        .segments
        .iter()
        .map(|s| s.ident.to_string())
        .collect();
    segments == ["test"] || segments == ["tokio", "test"]
}

/// The topmost `/// verifies:` doc line wins, transcribed verbatim into a
/// list — resolution is the framework's business.
fn verifies_of(attrs: &[syn::Attribute]) -> Vec<String> {
    for attr in attrs {
        if !attr.path().is_ident("doc") {
            continue;
        }
        if let syn::Meta::NameValue(nv) = &attr.meta {
            if let syn::Expr::Lit(syn::ExprLit {
                lit: syn::Lit::Str(text),
                ..
            }) = &nv.value
            {
                if let Some(rest) = text.value().trim().strip_prefix("verifies:") {
                    return rest
                        .split(',')
                        .map(str::trim)
                        .filter(|v| !v.is_empty())
                        .map(str::to_string)
                        .collect();
                }
            }
        }
    }
    Vec::new()
}

fn checks_in_file(root: &Path, package: &str, file: &Path) -> Result<Vec<ScannedCheck>> {
    let source = fs::read_to_string(file).map_err(|e| format!("read {}: {e}", file.display()))?;
    let ast = syn::parse_file(&source).map_err(|e| {
        format!(
            "parse {}: {e} — an unparseable test file cannot be observed",
            file.display()
        )
    })?;
    let mut visitor = TestVisitor {
        root,
        package,
        file,
        out: Vec::new(),
    };
    visitor.visit_file(&ast);
    Ok(visitor.out)
}

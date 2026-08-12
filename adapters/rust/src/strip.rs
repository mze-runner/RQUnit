//! Annotation removal — the Rust adapter's stripper role (contracts: rqunit
//! `interfaces/strip-request.schema.json` in, `stripped-files.schema.json`
//! out).
//!
//! The off-ramp. Adoption asked this codebase to carry `/// verifies:` doc
//! comments; taking them back is the same knowledge run backwards, so it
//! belongs here rather than in core — core stopped knowing what a Rust doc
//! comment is when the scanner left it.
//!
//! REWRITING ONLY. The request names exactly which tokens go, having been
//! decided against the store by the framework. This module never asks whether
//! an annotation is stale, never sweeps a file it was not handed, and returns
//! the new content as data for core to write.
//!
//! Text, not `syn`: re-emitting a parsed tree would reformat every file it
//! touches, turning a two-token deletion into an unreviewable diff. An
//! off-ramp people cannot read the diff of is an off-ramp nobody runs.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use serde_json::{json, Value};

use crate::Result;

const MARKER: &str = "verifies:";

pub fn respond(root: &Path, request_json: &str) -> Result<String> {
    let request: Value =
        serde_json::from_str(request_json).map_err(|e| format!("parse strip request: {e}"))?;
    let checks = request["checks"]
        .as_array()
        .ok_or("strip request carries no `checks` array")?;

    // path -> (fn name -> tokens to remove). Grouped so each file is read,
    // rewritten and written once no matter how many of its tests are named.
    let mut by_file: BTreeMap<String, BTreeMap<String, BTreeSet<String>>> = BTreeMap::new();
    let mut id_of: BTreeMap<(String, String), String> = BTreeMap::new();
    for check in checks {
        let path = string_at(check, "path")?;
        let name = string_at(check, "fn")?;
        let id = string_at(check, "id")?;
        let removals = check["remove"]
            .as_array()
            .ok_or_else(|| format!("check {id} carries no `remove` array"))?;
        let tokens: BTreeSet<String> = removals
            .iter()
            .filter_map(|t| t.as_str().map(str::to_string))
            .collect();
        by_file
            .entry(path.clone())
            .or_default()
            .insert(name.clone(), tokens);
        id_of.insert((path, name), id);
    }

    let mut files: Vec<(String, String)> = Vec::new();
    let mut stripped: BTreeSet<String> = BTreeSet::new();
    for (path, wanted) in &by_file {
        let full = root.join(path);
        let source =
            fs::read_to_string(&full).map_err(|e| format!("read {}: {e}", full.display()))?;
        let (rewritten, touched) = rewrite(&source, wanted);
        for name in touched {
            if let Some(id) = id_of.get(&(path.clone(), name)) {
                stripped.insert(id.clone());
            }
        }
        // A file whose content is unchanged is omitted by contract, so the
        // count core reports is the count of real edits.
        if rewritten != source {
            files.push((path.clone(), rewritten));
        }
    }

    let payload = json!({
        "contract_version": 1,
        "generated_by": format!("rqunit-adapter-rust strip-annotations {}", env!("CARGO_PKG_VERSION")),
        "files": files
            .into_iter()
            .map(|(path, content)| json!({"path": path, "content": content}))
            .collect::<Vec<_>>(),
        "stripped": stripped.into_iter().collect::<Vec<_>>(),
    });
    Ok(serde_json::to_string_pretty(&payload).map_err(|e| e.to_string())? + "\n")
}

fn string_at(value: &Value, key: &str) -> Result<String> {
    Ok(value[key]
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| format!("strip request check has no string `{key}`"))?)
}

/// The rewritten source, and the test names whose annotation actually changed.
fn rewrite(source: &str, wanted: &BTreeMap<String, BTreeSet<String>>) -> (String, Vec<String>) {
    let lines: Vec<&str> = source.lines().collect();
    let mut out: Vec<String> = Vec::with_capacity(lines.len());
    let mut touched: Vec<String> = Vec::new();
    let mut index = 0;

    while index < lines.len() {
        let line = lines[index];
        let Some(tokens) = annotation_tokens(line) else {
            out.push(line.to_string());
            index += 1;
            continue;
        };
        // Which test does this annotation govern? The doc block sits above
        // the attribute block, so the owning fn is the next one below.
        let Some(name) = following_fn(&lines, index) else {
            out.push(line.to_string());
            index += 1;
            continue;
        };
        let Some(remove) = wanted.get(&name) else {
            out.push(line.to_string());
            index += 1;
            continue;
        };
        let kept: Vec<&String> = tokens.iter().filter(|t| !remove.contains(*t)).collect();
        if kept.len() == tokens.len() {
            out.push(line.to_string()); // nothing of ours on this line
            index += 1;
            continue;
        }
        touched.push(name);
        // Everything removed: the marker itself goes, leaving no empty
        // annotation behind. Otherwise the survivors are re-rendered — a test
        // proving three requirements, one retired, keeps the other two.
        if !kept.is_empty() {
            let indent: String = line.chars().take_while(|c| c.is_whitespace()).collect();
            let rendered: Vec<String> = kept.into_iter().cloned().collect();
            out.push(format!("{indent}/// {MARKER} {}", rendered.join(", ")));
        }
        index += 1;
    }

    let mut rewritten = out.join("\n");
    if source.ends_with('\n') {
        rewritten.push('\n');
    }
    (rewritten, touched)
}

/// The tokens a `/// verifies:` line claims, or `None` for any other line.
fn annotation_tokens(line: &str) -> Option<Vec<String>> {
    let rest = line.trim_start().strip_prefix("///")?;
    let rest = rest.trim_start().strip_prefix(MARKER)?;
    Some(
        rest.split(',')
            .map(str::trim)
            .filter(|t| !t.is_empty())
            .map(str::to_string)
            .collect(),
    )
}

/// The name of the first `fn` below `from`, looking through the doc and
/// attribute lines that legitimately sit between. A blank line or a statement
/// ends the block: an annotation separated from its test governs nothing.
fn following_fn(lines: &[&str], from: usize) -> Option<String> {
    for line in lines.iter().skip(from + 1) {
        let trimmed = line.trim_start();
        if trimmed.starts_with("///") || trimmed.starts_with("#[") {
            continue;
        }
        return fn_name(trimmed);
    }
    None
}

fn fn_name(trimmed: &str) -> Option<String> {
    let after = trimmed.strip_prefix("pub ").unwrap_or(trimmed);
    let after = after.strip_prefix("async ").unwrap_or(after);
    let after = after.strip_prefix("fn ")?;
    let name: String = after
        .chars()
        .take_while(|c| c.is_alphanumeric() || *c == '_')
        .collect();
    (!name.is_empty()).then_some(name)
}

"""Management report — the perception layer.

Two halves, deliberately separated: `build_data` produces `report-data.json`
(a pinned contract, like actual-surface/test-plan), and `render_html` consumes
ONLY that dict. Nothing here computes a metric of its own — every number comes
from the same engines the gates use (status, lints, checks, trace, doctor), so
the report can never disagree with the tooling.

The split is also what makes the report survive a core rewrite: the HTML is a
string template over a JSON shape, portable verbatim.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .checks.base import run_checks
from .doctor import run as run_doctor
from .lints.base import run_lints
from .status import compute, gate2_records
from .store import Store

CONTRACT_VERSION = 1


# ------------------------------------------------------------ data contract

def _computed_label(store: Store, ru) -> str:
    s = compute(store, ru)
    if s.failing:
        return "failing"
    if s.blocked:
        return "blocked"
    if s.done:
        return "done"
    if s.debt:
        return "debt"
    return "pending"


def _framework_version(root: Path) -> str:
    path = Path(root) / "spec" / "framework" / "ru-framework-spec.md"
    if path.is_file():
        m = re.search(r"^\*\*Status:\*\*\s*(v[0-9][0-9.]*)", path.read_text(), re.M)
        if m:
            return m.group(1)
    return "unknown"


def _store_commit(root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True)
    return proc.stdout.strip() or "unversioned"


def build_data(store: Store, root: Path, now: str | None = None) -> dict:
    root = Path(root)
    rus = store.rus()
    active = [ru for ru in rus if ru.status == "active"]
    labels = {ru.id: _computed_label(store, ru) for ru in active}
    computed = {ru.id: compute(store, ru) for ru in active}

    # --- verification depth + debt
    depth: Counter = Counter()
    todos: Counter = Counter()
    for ru in active:
        for entry in ru.raw.get("verification") or []:
            kind = entry.get("type")
            depth[kind] += 1
            if str(entry.get("ref", "")).startswith("TODO("):
                todos[kind] += 1

    # --- Gate 1 sittings: a batch shares one stamp timestamp
    sittings: dict[tuple[str, str], int] = defaultdict(int)
    for ru in active:
        stamp = ru.raw.get("gate1_stamp")
        if stamp:
            sittings[(stamp["at"], stamp["by"])] += 1

    # --- Gate 2 verdicts
    verdicts: Counter = Counter()
    recent_reviews = []
    for ru in rus:
        for record in gate2_records(store, ru.id):
            verdicts[record.get("verdict", "?")] += 1
            recent_reviews.append({
                "ru": ru.id, "verdict": record.get("verdict"),
                "reviewer": record.get("reviewer"), "at": record.get("at", ""),
                "criterion": record.get("criterion", ""),
            })
    recent_reviews.sort(key=lambda r: r["at"], reverse=True)

    # --- per-feature and per-area rollups
    def _refs(group) -> tuple[int, int]:
        """(real refs, promised refs) — the completeness ratio a delivery lead
        actually wants: how much verification exists vs is still owed."""
        total = todo = 0
        for ru in group:
            for entry in ru.raw.get("verification") or []:
                total += 1
                if str(entry.get("ref", "")).startswith("TODO("):
                    todo += 1
        return total - todo, total

    features = []
    members = defaultdict(list)
    for ru in active:
        if ru.raw.get("feature"):
            members[ru.raw["feature"]].append(ru)
    for feat in store.features():
        group = members.get(feat.id, [])
        real, promised = _refs(group)
        features.append({
            "id": feat.id,
            "goal": " ".join(feat.raw.get("goal", "").split()),
            "total": len(group),
            "labels": dict(Counter(labels[ru.id] for ru in group)),
            "checks_real": real,
            "checks_total": promised,
        })
    features.sort(key=lambda f: (-f["total"], f["id"]))

    areas: dict[str, list] = defaultdict(list)
    for ru in active:
        areas[store.scope_service(ru) or "(unscoped)"].append(ru)
    area_rows = []
    for name, group in areas.items():
        real, promised = _refs(group)
        area_rows.append({
            "area": name, "total": len(group),
            "labels": dict(Counter(labels[ru.id] for ru in group)),
            "checks_real": real, "checks_total": promised,
        })
    area_rows.sort(key=lambda a: (-a["total"], a["area"]))

    # --- burn-down (the honest debt counters the gates already report)
    lint_violations = run_lints(store)
    check_violations = run_checks(store)
    burndown = {
        "coverage_warnings": sum(1 for v in lint_violations if v.rule == "L21"),
        "orphan_facts": sum(1 for v in check_violations if v.rule == "C7"),
        "suspect_links": sum(1 for v in lint_violations if v.rule == "L20"),
        "untraced_checks": None,
        "infrastructure_checks": None,
    }
    try:
        from .trace import build_report as trace_report
        tr = trace_report(store, root)
        burndown["untraced_checks"] = len(tr.untraced_checks)
        burndown["infrastructure_checks"] = len(tr.infrastructure)
    except Exception:
        pass  # trace scanning is consumer-configured; a report never fails on it

    gaps = store.gaps()
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "store": {
            "name": root.name,
            "commit": _store_commit(root),
            "framework_version": _framework_version(root),
        },
        "totals": {
            "rus": dict(Counter(ru.status for ru in rus)),
            "features": len(store.features()),
            "contracts": len(store.contracts()),
            "models": len(store.models()),
            "adrs": len(store.adrs()),
            "manifests": len(store.manifests()),
            "intents": len(store.intents()),
            "gaps_open": sum(1 for g in gaps if g.raw.get("status") == "open"),
            "gaps_blocking_open": sum(1 for g in gaps if g.raw.get("status") == "open"
                                      and g.severity == "blocking"),
            "gaps_resolved": sum(1 for g in gaps if g.raw.get("status") == "resolved"),
        },
        "status": {
            "labels": dict(Counter(labels.values())),
            "reviewed": sum(1 for s in computed.values() if s.reviewed),
            "suspect": sum(1 for s in computed.values() if s.suspect),
            "active_total": len(active),
        },
        "verification": {
            "depth": dict(depth),
            "todo_refs": dict(todos),
            "policy_violations": [
                {"ru": v.artifact, "severity": v.severity, "message": v.message}
                for v in lint_violations if v.rule == "L21"
            ],
        },
        "gates": {
            "sittings": [{"at": at, "by": by, "activated": count}
                         for (at, by), count in sorted(sittings.items())],
            "gate2": {"verdicts": dict(verdicts), "recent": recent_reviews[:10]},
        },
        "features": features,
        "areas": area_rows,
        "burndown": burndown,
        "health": [f.__dict__ for f in run_doctor(store, root)],
    }


# ------------------------------------------------------------ renderer

_LABEL_ORDER = ["done", "pending", "debt", "blocked", "failing"]
_LABEL_COLOR = {
    "done": "#2f9e6b", "pending": "#4c7fd4",
    "debt": "#c99a2e", "blocked": "#b8632f", "failing": "#c0392b",
}
# Framework vocabulary is precise but reads alarmingly to a lay audience:
# `blocked` means "carries a TODO verification ref", not "work is stuck".
_LABEL_GLOSS = {
    "done": "every check provably passes",
    "pending": "checks in place, pass-state not yet computed",
    "debt": "human judgment only",
    "blocked": "awaiting a promised check (TODO ref)",
    "failing": "stale hash or invalid stamp — needs attention",
}


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _donut(labels: dict, size: int = 168) -> str:
    total = sum(labels.values()) or 1
    radius, stroke = size / 2 - 16, 22
    circumference = 2 * 3.141592653589793 * radius
    parts, offset = [], 0.0
    for name in _LABEL_ORDER:
        value = labels.get(name)
        if not value:
            continue
        length = circumference * value / total
        parts.append(
            f'<circle class="seg" cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" '
            f'stroke="{_LABEL_COLOR.get(name, "#888")}" stroke-width="{stroke}" '
            f'stroke-dasharray="{length:.3f} {circumference - length:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 {size/2} {size/2})">'
            f'<title>{_esc(name)}: {value}</title></circle>')
        offset += length
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'role="img" aria-label="requirement status breakdown">{"".join(parts)}'
            f'<text x="50%" y="48%" class="donut-n">{total}</text>'
            f'<text x="50%" y="62%" class="donut-l">active RUs</text></svg>')


def _bar_row(row: dict, name: str, subtitle: str = "") -> str:
    labels, total = row["labels"], row["total"]
    segments = "".join(
        f'<span style="width:{100 * labels.get(k, 0) / (total or 1):.2f}%;'
        f'background:{_LABEL_COLOR.get(k, "#888")}" '
        f'title="{_esc(k)} — {_esc(_LABEL_GLOSS.get(k, ""))}: {labels.get(k, 0)}"></span>'
        for k in _LABEL_ORDER if labels.get(k))
    real, promised = row["checks_real"], row["checks_total"]
    pct = round(100 * real / promised) if promised else 0
    return (f'<tr><td><div class="nm">{_esc(name)}</div>'
            f'{f"<div class=sub>{_esc(subtitle)}</div>" if subtitle else ""}</td>'
            f'<td class="num">{total}</td>'
            f'<td class="barcell"><div class="bar">{segments}</div></td>'
            f'<td class="num"><div class="pct">{pct}%</div>'
            f'<div class="sub">{real}/{promised}</div></td></tr>')


def _kpi(value, label: str, hint: str = "", tone: str = "") -> str:
    return (f'<div class="kpi {tone}"><div class="v">{_esc(value)}</div>'
            f'<div class="l">{_esc(label)}</div>'
            f'{f"<div class=h>{_esc(hint)}</div>" if hint else ""}</div>')


def render_html(data: dict) -> str:
    store, totals, status = data["store"], data["totals"], data["status"]
    active_total = status["active_total"] or 1
    labels = status["labels"]
    verified_pct = round(100 * status["reviewed"] / active_total)
    depth = data["verification"]["depth"]
    todos = data["verification"]["todo_refs"]
    mechanical = sum(depth.get(k, 0) for k in ("contract", "test", "model"))
    sittings = data["gates"]["sittings"]
    peak = max((s["activated"] for s in sittings), default=1)
    warn_health = [h for h in data["health"] if h["severity"] == "warning"]

    promised = sum(depth.values())
    real = promised - sum(todos.values())
    completeness = round(100 * real / promised) if promised else 0
    kpis = "".join([
        _kpi(totals["rus"].get("active", 0), "governed requirements",
             f'{totals["rus"].get("superseded", 0)} superseded · {totals["rus"].get("draft", 0)} draft'),
        _kpi(f'{verified_pct}%', "fidelity-reviewed",
             f'{status["reviewed"]} of {active_total} passed Gate 1',
             "good" if verified_pct >= 80 else ""),
        _kpi(f'{completeness}%', "verification completeness",
             f'{real} of {promised} checks exist',
             "good" if completeness >= 80 else "warn" if completeness < 50 else ""),
        _kpi(sum(todos.values()), "tracked verification debt",
             "promised checks not yet written",
             "warn" if sum(todos.values()) else "good"),
        _kpi(len(sittings), "Gate 1 sittings", f'{sum(s["activated"] for s in sittings)} requirements activated'),
        _kpi(totals["gaps_blocking_open"], "blocking ambiguities",
             f'{totals["gaps_resolved"]} resolved · {totals["gaps_open"]} open',
             "warn" if totals["gaps_blocking_open"] else "good"),
    ])

    legend = "".join(
        f'<li><i style="background:{_LABEL_COLOR.get(k, "#888")}"></i>'
        f'<span class="lg"><b class="k">{_esc(k)}</b>'
        f'<em>{_esc(_LABEL_GLOSS.get(k, ""))}</em></span>'
        f'<b>{labels.get(k, 0)}</b></li>'
        for k in _LABEL_ORDER if labels.get(k))

    depth_rows = "".join(
        f'<tr><td>{_esc(k)}</td><td class="num">{depth.get(k, 0)}</td>'
        f'<td class="num">{todos.get(k, 0)}</td></tr>'
        for k in ("contract", "test", "model", "human") if depth.get(k) or todos.get(k))

    sitting_bars = "".join(
        f'<div class="tick" title="{_esc(s["at"])} · {_esc(s["by"])} · {s["activated"]} RUs">'
        f'<span style="height:{max(6, round(100 * s["activated"] / peak))}%"></span>'
        f'<em>{s["activated"]}</em></div>' for s in sittings) or '<p class="empty">no sittings recorded</p>'

    feature_rows = "".join(
        _bar_row(f, f["id"], f["goal"][:110])
        for f in data["features"] if f["total"]) or '<tr><td colspan="4" class="empty">no features</td></tr>'
    area_rows = "".join(_bar_row(a, a["area"]) for a in data["areas"])

    burn = data["burndown"]
    burn_cards = "".join(
        _kpi(v if v is not None else "—", k.replace("_", " "))
        for k, v in burn.items())

    health_rows = "".join(
        f'<li class="{_esc(h["severity"])}"><b>{_esc(h["kind"])}</b>{_esc(h["message"])}'
        f'<span>{_esc(h["suggestion"])}</span></li>' for h in data["health"]
    ) or '<li class="ok"><b>clear</b>no structural problems detected</li>'

    verdicts = data["gates"]["gate2"]["verdicts"]
    review_rows = "".join(
        f'<tr><td>{_esc(r["ru"])}</td><td><span class="pill {_esc(r["verdict"])}">'
        f'{_esc(r["verdict"])}</span></td><td>{_esc(r["reviewer"])}</td>'
        f'<td class="mono">{_esc(r["at"][:16])}</td><td>{_esc(r["criterion"][:80])}</td></tr>'
        for r in data["gates"]["gate2"]["recent"]
    ) or '<tr><td colspan="5" class="empty">no Gate 2 verdicts recorded yet</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Requirements report — {_esc(store["name"])}</title>
<style>
*{{box-sizing:border-box}}
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1b1f24;--dim:#5d6672;--line:#e3e6ea;--accent:#3a6ea5;--radius:14px}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14171a;--card:#1c2024;--ink:#e8eaed;--dim:#98a1ad;--line:#2b3138;--accent:#6ea8dc}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:40px 24px 72px}}
header{{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between;margin-bottom:28px}}
h1{{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}}
.meta{{color:var(--dim);font-size:13px}}
.meta b{{color:var(--ink);font-weight:600}}
.badge{{display:inline-block;padding:4px 11px;border-radius:99px;background:var(--accent);color:#fff;font-size:12px;font-weight:600;letter-spacing:.02em}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);margin:34px 0 12px;font-weight:700}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px}}
.kpi .v{{font-size:30px;font-weight:700;letter-spacing:-.03em;line-height:1.1}}
.kpi .l{{font-size:13px;color:var(--dim);margin-top:2px}}
.kpi .h{{font-size:11.5px;color:var(--dim);margin-top:7px;padding-top:7px;border-top:1px solid var(--line)}}
.kpi.good .v{{color:#2f9e6b}} .kpi.warn .v{{color:#c99a2e}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media (max-width:820px){{.two{{grid-template-columns:1fr}}}}
.donutwrap{{display:flex;align-items:center;gap:22px;flex-wrap:wrap}}
.donut-n{{text-anchor:middle;font-size:30px;font-weight:700;fill:var(--ink)}}
.donut-l{{text-anchor:middle;font-size:10.5px;fill:var(--dim);letter-spacing:.05em}}
.legend{{list-style:none;margin:0;padding:0;flex:1;min-width:150px}}
.legend li{{display:flex;align-items:center;gap:9px;padding:5px 0;font-size:13.5px;border-bottom:1px solid var(--line)}}
.legend li:last-child{{border:0}}
.legend i{{width:11px;height:11px;border-radius:3px;flex:none}}
.legend b{{margin-left:auto;font-variant-numeric:tabular-nums;padding-left:10px}}
.lg{{display:flex;flex-direction:column;min-width:0}}
.lg .k{{font-weight:600}}
.lg em{{font-style:normal;font-size:11.5px;color:var(--dim);line-height:1.35}}
.note{{margin:16px 0 0;padding-top:14px;border-top:1px solid var(--line);font-size:12.5px;color:var(--dim);line-height:1.6}}
.note b{{color:var(--ink);font-weight:600}}
.pct{{font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--dim);padding:0 10px 9px;font-weight:700}}
td{{padding:9px 10px;border-top:1px solid var(--line);vertical-align:middle}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.nm{{font-weight:600}}
.sub{{color:var(--dim);font-size:12px;margin-top:2px}}
.barcell{{width:44%}}
.bar{{display:flex;height:9px;border-radius:99px;overflow:hidden;background:var(--line)}}
.bar span{{display:block}}
.ticks{{display:flex;align-items:flex-end;gap:7px;height:132px;padding:8px 2px 0;overflow-x:auto}}
.tick{{flex:1;min-width:26px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}}
.tick span{{width:100%;background:linear-gradient(180deg,var(--accent),color-mix(in srgb,var(--accent) 55%,transparent));border-radius:5px 5px 0 0}}
.tick em{{font-style:normal;font-size:11px;color:var(--dim);margin-top:5px;font-variant-numeric:tabular-nums}}
.health{{list-style:none;margin:0;padding:0}}
.health li{{padding:11px 14px;border-left:3px solid var(--line);background:var(--card);border-radius:0 9px 9px 0;margin-bottom:8px;font-size:13.5px}}
.health li.warning{{border-color:#c99a2e}} .health li.info{{border-color:var(--accent)}} .health li.ok{{border-color:#2f9e6b}}
.health b{{display:inline-block;margin-right:9px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
.health span{{display:block;color:var(--dim);font-size:12.5px;margin-top:4px}}
.pill{{padding:2px 9px;border-radius:99px;font-size:11.5px;font-weight:600}}
.pill.pass{{background:rgba(47,158,107,.16);color:#2f9e6b}} .pill.fail{{background:rgba(192,57,43,.16);color:#c0392b}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--dim)}}
.empty{{color:var(--dim);font-style:italic;padding:14px 10px}}
footer{{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-size:12px}}
@media print{{body{{background:#fff}}.card,.kpi{{break-inside:avoid}}}}
</style></head><body><div class="wrap">

<header>
  <div>
    <h1>Requirements report — {_esc(store["name"])}</h1>
    <div class="meta">Store commit <b>{_esc(store["commit"])}</b> · framework
      <b>{_esc(store["framework_version"])}</b> · generated {_esc(data["generated_at"][:16])}</div>
  </div>
  <span class="badge">{_esc(totals["rus"].get("active", 0))} governed requirements</span>
</header>

<div class="kpis">{kpis}</div>

<h2>Requirement status</h2>
<div class="two">
  <div class="card"><div class="donutwrap">{_donut(labels)}<ul class="legend">{legend}</ul></div>
    <p class="note"><b>How to read this.</b> Status is <em>computed</em>, never asserted: a
    requirement counts as <b>done</b> only when every one of its checks provably passes.
    Mechanical pass-states (contract, test and model results) are not yet wired into the
    computation, so requirements whose checks exist and run still show as
    <b>pending</b> rather than done — the tooling refuses to claim a green it cannot prove.
    <b>Blocked</b> means a check has been promised but not yet written, which is tracked
    debt, not stalled delivery.</p>
  </div>
  <div class="card">
    <table><thead><tr><th>verification type</th><th class="num">entries</th><th class="num">still owed</th></tr></thead>
    <tbody>{depth_rows}</tbody></table>
    <p class="note">{status["suspect"]} suspect link(s) ·
      {len(data["verification"]["policy_violations"])} coverage-policy warning(s).
      Every requirement carries at least one verification hook by rule — an unverifiable
      requirement cannot be activated.</p>
  </div>
</div>

<h2>Gate 1 activity — requirements activated per sitting</h2>
<div class="card"><div class="ticks">{sitting_bars}</div></div>

<h2>Features</h2>
<div class="card"><table>
<thead><tr><th>feature</th><th class="num">RUs</th><th>status mix</th><th class="num">checks written</th></tr></thead>
<tbody>{feature_rows}</tbody></table></div>

<h2>Areas</h2>
<div class="card"><table>
<thead><tr><th>area</th><th class="num">RUs</th><th>status mix</th><th class="num">checks written</th></tr></thead>
<tbody>{area_rows}</tbody></table></div>

<h2>Burn-down</h2>
<div class="kpis">{burn_cards}</div>

<h2>Gate 2 verdicts — {verdicts.get("pass", 0)} pass · {verdicts.get("fail", 0)} fail</h2>
<div class="card"><table>
<thead><tr><th>RU</th><th>verdict</th><th>reviewer</th><th>at</th><th>criterion</th></tr></thead>
<tbody>{review_rows}</tbody></table></div>

<h2>Structural health — {len(warn_health)} warning(s)</h2>
<ul class="health">{health_rows}</ul>

<footer>Generated by <b>rqunit report</b> from the requirement store. Every figure is
computed by the same engines that gate commits — status, lints, checks, traceability,
and structural health. No number here is asserted by hand.</footer>
</div></body></html>
"""


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=False) + "\n"

"""Render the five `run-inventory` tables as one self-contained HTML page.

Infrastructure, like `run-inventory` itself (CLAUDE.md, "Asset coverage
inventory"): this makes no scientific claim and feeds no figure. It computes
nothing new either — every number here is already in a TSV under
`output_data/inventory/`; the page only saves a reader from holding five
tables' joins in their head.

Pure functions over DataFrames: no invoke context, no file I/O, and no
network — the page carries its own CSS and never loads a CDN, so it opens
offline. `tasks.py`'s `run-inventory-dashboard` reads the TSVs and writes the
string this returns.

Colours follow the `dataviz` skill's reference palette: a one-hue ordinal ramp
(blue steps 250/400/600) for the raw -> timeseries -> QC funnel, and the fixed
status pair (good `#0ca30c`, critical `#d03b3b`) for asset presence — always
paired with a text label, never colour alone.
"""

from html import escape

import pandas as pd

# The raw -> timeseries -> QC funnel is one ordinal ramp (blue steps 250/400/600
# of the `dataviz` reference palette). Both modes are selected, not flipped: on
# the light surface the ramp runs light -> dark, on the dark surface dark ->
# light, so every step keeps its 2:1 floor against the surface it is drawn on.
STAGES = (
    ("raw runs", "var(--stage-1)"),
    ("in timeseries", "var(--stage-2)"),
    ("in QC", "var(--stage-3)"),
)

_STYLE = """
.dash { color-scheme: light; --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b;
  --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --rule:rgba(11,11,11,0.10);
  --good:#0ca30c; --bad:#d03b3b;
  --stage-1:#86b6ef; --stage-2:#3987e5; --stage-3:#184f95;
  background:var(--plane); color:var(--ink); margin:0; padding:24px;
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .dash {
  color-scheme: dark; --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7;
  --grid:#2c2c2a; --rule:rgba(255,255,255,0.10);
  --stage-1:#184f95; --stage-3:#86b6ef; } }
:root[data-theme="dark"] .dash { color-scheme: dark; --surface:#1a1a19; --plane:#0d0d0d;
  --ink:#fff; --ink2:#c3c2b7; --grid:#2c2c2a; --rule:rgba(255,255,255,0.10);
  --stage-1:#184f95; --stage-3:#86b6ef; }
.dash h1 { font-size:20px; margin:0 0 4px; }
.dash h2 { font-size:14px; margin:0 0 12px; color:var(--ink2);
  text-transform:uppercase; letter-spacing:.06em; }
.dash .sub { color:var(--ink2); margin:0 0 24px; }
.dash section { background:var(--surface); border:1px solid var(--rule);
  border-radius:8px; padding:16px; margin-bottom:16px; }
.dash .tiles { display:grid; gap:16px 24px;
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }
.dash .tile .v { font-size:26px; font-weight:600; }
.dash .tile .k { color:var(--ink2); font-size:13px; }
.dash .tile .n { color:var(--muted); font-size:12px; }
.dash table { border-collapse:collapse; width:100%; font-size:13px;
  font-variant-numeric:tabular-nums; }
.dash th { text-align:left; font-weight:600; color:var(--ink2); padding:4px 10px 8px 0;
  border-bottom:1px solid var(--grid); }
.dash td { padding:4px 10px 4px 0; border-bottom:1px solid var(--grid); }
.dash td.n { text-align:right; }
.dash .ok { color:var(--good); } .dash .no { color:var(--bad); }
.dash td.track-cell { width:55%; }
.dash .track { display:flex; flex-direction:column; gap:2px; min-width:220px; }
.dash .bar { height:6px; border-radius:0 3px 3px 0; }
.dash .legend { display:flex; gap:16px; color:var(--ink2); font-size:13px;
  margin-bottom:12px; }
.dash .swatch { display:inline-block; width:10px; height:10px; border-radius:2px;
  margin-right:6px; }
.dash .empty { color:var(--ink2); }
.dash footer { color:var(--muted); font-size:12px; }
"""


def _flag(frame, column):
    """A table column of True/False as a real boolean Series, whatever the TSV
    round-trip left it as (bool, object, or all-NaN)."""
    if frame.empty or column not in frame:
        return pd.Series([], dtype=bool)
    values = frame[column]
    if values.dtype == bool:
        return values
    return values.astype(str).str.lower().isin(["true", "1", "1.0"])


def _pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "—"


def _tile(value, key, note=""):
    note_html = f'<div class="n">{escape(note)}</div>' if note else ""
    return (f'<div class="tile"><div class="v">{escape(str(value))}</div>'
            f'<div class="k">{escape(key)}</div>{note_html}</div>')


def _headline_html(run_inventory, sessions, min_usable_seconds):
    n_runs = len(run_inventory)
    n_ts = int(_flag(run_inventory, "in_timeseries").sum())
    n_qc = int(_flag(run_inventory, "in_qc").sum())
    n_sessions = len(sessions)
    n_conn = int(_flag(sessions, "has_connectome").sum())
    n_gated = int(_flag(sessions, "passes_gate").sum())
    tiles = [
        _tile(f"{n_runs:,}", "raw BIDS runs"),
        _tile(f"{n_ts:,}", "matched into timeseries", _pct(n_ts, n_runs)),
        _tile(f"{n_qc:,}", "matched into qa_figures QC", _pct(n_qc, n_runs)),
        _tile(f"{n_sessions:,}", "sessions acquired"),
        _tile(f"{n_conn:,}", "sessions with a connectome", _pct(n_conn, n_sessions)),
        _tile(f"{n_gated:,}", f"sessions past the {min_usable_seconds:g}s gate",
              _pct(n_gated, n_sessions)),
    ]
    return ('<section><h2>Headline</h2><div class="tiles">'
            + "".join(tiles) + "</div></section>")


def _empty_section(title, message):
    return f'<section><h2>{title}</h2><p class="empty">{message}</p></section>'


def _mark(present):
    return ('<td class="ok">&#10003; ok</td>' if present
            else '<td class="no">&#10007; missing</td>')


def _asset_grid_html(dataset_coverage, subjects):
    if dataset_coverage.empty:
        return _empty_section("Dataset &times; asset", "No dataset found.")
    subject_counts = (subjects.groupby("dataset")["subject"].nunique()
                      if not subjects.empty else pd.Series(dtype=int))
    header = ("<tr><th>dataset</th><th>raw BIDS</th><th>timeseries registered</th>"
              "<th>timeseries content</th><th>QC table</th><th>atlas tSNR</th>"
              "<th>connectome</th></tr>")
    rows = []
    for _, row in dataset_coverage.iterrows():
        dataset = str(row["dataset"])
        fetched = int(row["timeseries_content_subjects"])
        total = int(subject_counts.get(dataset, 0))
        content = f"{fetched}/{total} subjects" if total else f"{fetched} subjects"
        klass = "ok" if fetched else "no"
        rows.append(
            f"<tr><td>{escape(dataset)}</td>"
            + _mark(bool(row["bids_installed"]))
            + _mark(bool(row["timeseries_registered"]))
            + f'<td class="{klass}">{escape(content)}</td>'
            + _mark(bool(row["qc_table_populated"]))
            + _mark(bool(row["atlas_tsnr_populated"]))
            + _mark(bool(row["connectome_file_present"]))
            + "</tr>"
        )
    return ("<section><h2>Dataset &times; asset</h2><table>"
            + header + "".join(rows) + "</table></section>")


def _legend_html():
    swatches = "".join(
        f'<span><span class="swatch" style="background:{color}"></span>{escape(label)}</span>'
        for label, color in STAGES
    )
    return f'<div class="legend">{swatches}</div>'


def _coverage_bars_html(run_inventory):
    if run_inventory.empty:
        return _empty_section("Run coverage per dataset", "No run found.")
    grouped = run_inventory.assign(
        _ts=_flag(run_inventory, "in_timeseries"), _qc=_flag(run_inventory, "in_qc"),
    ).groupby("dataset").agg(raw=("run", "size"), ts=("_ts", "sum"), qc=("_qc", "sum"))
    grouped = grouped.sort_values("raw", ascending=False)
    widest = int(grouped["raw"].max()) or 1
    rows = []
    for dataset, row in grouped.iterrows():
        counts = [int(row["raw"]), int(row["ts"]), int(row["qc"])]
        bars = "".join(
            f'<div class="bar" title="{escape(label)}: {count:,}" '
            f'style="width:{100 * count / widest:.2f}%;background:{color}"></div>'
            for count, (label, color) in zip(counts, STAGES)
        )
        rows.append(
            f"<tr><td>{escape(str(dataset))}</td>"
            f'<td class="track-cell"><div class="track">{bars}</div></td>'
            f'<td class="n">{counts[0]:,} &rarr; {counts[1]:,} &rarr; {counts[2]:,}</td></tr>'
        )
    return ("<section><h2>Run coverage per dataset</h2>" + _legend_html()
            + "<table>" + "".join(rows) + "</table></section>")


def _match_level_html(run_inventory):
    if run_inventory.empty or "match_level" not in run_inventory:
        return ""
    counts = run_inventory["match_level"].value_counts()
    total = int(counts.sum())
    rows = "".join(
        f"<tr><td>{escape(str(level))}</td><td class='n'>{int(n):,}</td>"
        f"<td class='n'>{_pct(int(n), total)}</td></tr>"
        for level, n in counts.items()
    )
    return ("<section><h2>Join strength</h2><table>"
            "<tr><th>match level</th><th>runs</th><th>share</th></tr>"
            + rows + "</table><p class='empty'>How each raw run was matched against the "
            "timeseries/QC side: <code>exact</code> on all five entities, then the looser "
            "<code>no_run</code> and <code>no_session</code> tiers, then "
            "<code>unmatched</code>.</p></section>")


def _gaps_html(gaps):
    if gaps.empty:
        return _empty_section("Gaps", "No gap found.")
    rows = []
    for reason, block in gaps.groupby("reason"):
        datasets = sorted({str(d) for d in block["dataset"] if str(d)})
        shown = ", ".join(datasets[:12]) + (" …" if len(datasets) > 12 else "")
        rows.append(f"<tr><td>{escape(str(reason))}</td><td class='n'>{len(block):,}</td>"
                    f"<td>{escape(shown)}</td></tr>")
    return (f"<section><h2>Gaps ({len(gaps):,} rows)</h2><table>"
            "<tr><th>reason</th><th>rows</th><th>datasets</th></tr>"
            + "".join(rows) + "</table></section>")


def render_dashboard(run_inventory, sessions, subjects, dataset_coverage, gaps, *,
                     parcellation, min_usable_seconds, generated_at):
    """One self-contained HTML page summarising the five inventory tables."""
    n_datasets = dataset_coverage["dataset"].nunique() if not dataset_coverage.empty else 0
    n_subjects = subjects["subject"].nunique() if not subjects.empty else 0
    subtitle = (f"{n_datasets} datasets · {n_subjects} subjects · "
                f"{len(sessions):,} sessions · {len(run_inventory):,} raw runs · "
                f"parcellation {parcellation}")
    body = (_headline_html(run_inventory, sessions, min_usable_seconds)
            + _asset_grid_html(dataset_coverage, subjects)
            + _coverage_bars_html(run_inventory)
            + _match_level_html(run_inventory)
            + _gaps_html(gaps))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CNeuroMod asset inventory</title>
<style>{_STYLE}</style></head>
<body class="dash">
<h1>CNeuroMod asset inventory</h1>
<p class="sub">{escape(subtitle)}</p>
{body}
<footer>Rendered by <code>invoke run-inventory-dashboard</code> on
{escape(str(generated_at))} from the TSVs in <code>output_data/inventory/</code>.
It computes nothing new — read those tables for the full detail.</footer>
</body></html>
"""

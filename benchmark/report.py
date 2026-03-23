#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from statistics import mean

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
BENCH_PATTERNS = {
    "duration_seconds": re.compile(r"Test complete: ([0-9.]+) seconds\."),
    "successful_qps": re.compile(r"Successful throughput: ([0-9.]+) QPS\."),
    "attempted_qps": re.compile(r"Attempted throughput: ([0-9.]+) QPS\."),
    "insert_attempts": re.compile(r"Insert attempts: (\d+)"),
    "insert_successes": re.compile(r"Insert successes: (\d+)"),
    "insert_failures": re.compile(r"Insert failures: (\d+)"),
    "find_attempts": re.compile(r"Find attempts: (\d+)"),
    "find_successes": re.compile(r"Find successes: (\d+)"),
    "find_failures": re.compile(r"Find failures: (\d+)"),
    "total_records": re.compile(r"Total records inserted successfully: (\d+)"),
}
SIZE_RE = re.compile(r"([0-9.]+)\s*([KMGTP]?i?B)")
PERCENT_RE = re.compile(r"([0-9.]+)%")
MONGOSTAT_HEADER = "insert query update delete getmore command"
MONGOTOP_HEADER = "ns    total     read    write"
TARGET_NS = "stress_db.mongo_benchmark"

UNIT_FACTORS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
}


def parse_size_to_mib(text: str) -> float | None:
    match = SIZE_RE.search(text.strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    factor = UNIT_FACTORS.get(unit)
    if factor is None:
        return None
    return (value * factor) / (1024**2)


def parse_size_pair_to_mib(text: str) -> tuple[float | None, float | None]:
    parts = [part.strip() for part in text.split("/")]
    if len(parts) != 2:
        return (None, None)
    return parse_size_to_mib(parts[0]), parse_size_to_mib(parts[1])


def parse_percent(text: str) -> float | None:
    match = PERCENT_RE.search(text)
    return float(match.group(1)) if match else None


def parse_mongostat_bytes(token: str) -> float | None:
    mib = parse_size_to_mib(token)
    return mib


def parse_benchmark_output(path: Path) -> dict:
    content = path.read_text() if path.exists() else ""
    metrics: dict[str, float | int | str] = {"raw": content}
    for key, pattern in BENCH_PATTERNS.items():
        match = pattern.search(content)
        if not match:
            continue
        value = match.group(1)
        metrics[key] = float(value) if "." in value else int(value)
    return metrics


def parse_docker_stats(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    cleaned = ANSI_RE.sub("", path.read_text())
    seen = set()
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or "| CPU:" not in line:
            continue
        if line in seen:
            continue
        seen.add(line)
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 5:
            continue
        container = parts[0]
        cpu = parse_percent(parts[1])
        mem_used, mem_total = parse_size_pair_to_mib(parts[2].split(":", 1)[1])
        net_in, net_out = parse_size_pair_to_mib(parts[3].split(":", 1)[1])
        io_read, io_write = parse_size_pair_to_mib(parts[4].split(":", 1)[1])
        rows.append(
            {
                "container": container,
                "cpu_percent": cpu,
                "memory_used_mib": mem_used,
                "memory_total_mib": mem_total,
                "net_in_mib": net_in,
                "net_out_mib": net_out,
                "block_read_mib": io_read,
                "block_write_mib": io_write,
            }
        )
    return rows


def parse_mongostat(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.rstrip()
        if not line or line.startswith(MONGOSTAT_HEADER):
            continue
        parts = line.split()
        if len(parts) < 17:
            continue
        try:
            rows.append(
                {
                    "insert": int(parts[0].lstrip("*")),
                    "query": int(parts[1].lstrip("*")),
                    "command_local": int(parts[5].split("|")[0].lstrip("*")),
                    "dirty_percent": parse_percent(parts[6]) or 0.0,
                    "used_percent": parse_percent(parts[7]) or 0.0,
                    "net_in_kib": parse_mongostat_bytes(parts[13]),
                    "net_out_kib": parse_mongostat_bytes(parts[14]),
                    "connections": int(parts[15]),
                    "timestamp": " ".join(parts[16:]),
                }
            )
        except (ValueError, IndexError):
            continue
    return rows


def parse_mongotop(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    current_ts = None
    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if MONGOTOP_HEADER in line:
            parts = line.split()
            current_ts = parts[-1] if parts else None
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        namespace = parts[0]
        if namespace != TARGET_NS:
            continue
        try:
            rows.append(
                {
                    "timestamp": current_ts,
                    "namespace": namespace,
                    "total_ms": float(parts[1].replace("ms", "")),
                    "read_ms": float(parts[2].replace("ms", "")),
                    "write_ms": float(parts[3].replace("ms", "")),
                }
            )
        except ValueError:
            continue
    return rows


def metric_summary(values: list[float | None]) -> dict[str, float | None]:
    clean = [value for value in values if value is not None]
    if not clean:
        return {"min": None, "avg": None, "max": None}
    return {"min": min(clean), "avg": mean(clean), "max": max(clean)}


def fmt(value: float | int | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    return f"{value:,.{digits}f}{suffix}"


def chart_svg(series: list[tuple[str, list[float | None], str]], width: int = 900, height: int = 260) -> str:
    usable = [value for _, values, _ in series for value in values if value is not None]
    if not usable:
        return '<div class="empty-chart">No samples captured.</div>'
    max_points = max(len(values) for _, values, _ in series)
    max_value = max(usable)
    if max_value <= 0:
        max_value = 1.0
    left, right, top, bottom = 52, 20, 20, 32
    plot_w = width - left - right
    plot_h = height - top - bottom

    def x_pos(idx: int) -> float:
        if max_points <= 1:
            return left + plot_w / 2
        return left + (idx / (max_points - 1)) * plot_w

    def y_pos(value: float) -> float:
        return top + plot_h - (value / max_value) * plot_h

    grid = []
    labels = []
    for step in range(5):
        fraction = step / 4
        y = top + plot_h - fraction * plot_h
        val = max_value * fraction
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid" />')
        labels.append(f'<text x="{left - 10}" y="{y + 4:.1f}" class="axis-label">{val:.0f}</text>')

    paths = []
    legend = []
    for idx, (label, values, color) in enumerate(series):
        points = []
        for point_idx, value in enumerate(values):
            if value is None:
                continue
            points.append(f"{x_pos(point_idx):.2f},{y_pos(value):.2f}")
        if points:
            paths.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(points)}" />')
        legend.append(
            f'<div class="legend-item"><span class="legend-swatch" style="background:{color}"></span>{html.escape(label)}</div>'
        )

    axis = [
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis" />',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" class="axis" />',
        f'<text x="{left}" y="{height - 8}" class="axis-label">Samples</text>',
    ]

    return f'''<div class="chart-wrap">
<div class="legend">{"".join(legend)}</div>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Benchmark chart">
{"".join(grid)}
{"".join(labels)}
{"".join(axis)}
{"".join(paths)}
</svg>
</div>'''


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="empty">No data captured.</p>'
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_report(log_dir: Path, benchmark_name: str) -> str:
    bench = parse_benchmark_output(log_dir / "benchmark_output.log")
    docker_rows = parse_docker_stats(log_dir / "docker_stats.log")
    mongostat_rows = parse_mongostat(log_dir / "mongostat.log")
    mongotop_rows = parse_mongotop(log_dir / "mongotop.log")

    docker_cpu = metric_summary([row["cpu_percent"] for row in docker_rows])
    docker_mem = metric_summary([row["memory_used_mib"] for row in docker_rows])
    mongo_insert = metric_summary([row["insert"] for row in mongostat_rows])
    mongo_query = metric_summary([row["query"] for row in mongostat_rows])
    mongo_total = metric_summary([row["total_ms"] for row in mongotop_rows])

    summary_cards = [
        ("Duration", fmt(bench.get("duration_seconds"), suffix=" s")),
        ("Successful QPS", fmt(bench.get("successful_qps"))),
        ("Attempted QPS", fmt(bench.get("attempted_qps"))),
        ("Insert success / failure", f"{fmt(bench.get('insert_successes'), digits=0)} / {fmt(bench.get('insert_failures'), digits=0)}"),
        ("Find success / failure", f"{fmt(bench.get('find_successes'), digits=0)} / {fmt(bench.get('find_failures'), digits=0)}"),
        ("Total records", fmt(bench.get("total_records"), digits=0)),
    ]

    docker_table = render_table(
        ["Metric", "Min", "Average", "Max"],
        [
            ["Container CPU %", fmt(docker_cpu["min"]), fmt(docker_cpu["avg"]), fmt(docker_cpu["max"])],
            ["Container memory MiB", fmt(docker_mem["min"]), fmt(docker_mem["avg"]), fmt(docker_mem["max"])],
            ["mongostat inserts/s", fmt(mongo_insert["min"]), fmt(mongo_insert["avg"]), fmt(mongo_insert["max"])],
            ["mongostat queries/s", fmt(mongo_query["min"]), fmt(mongo_query["avg"]), fmt(mongo_query["max"])],
            ["mongotop total ms", fmt(mongo_total["min"]), fmt(mongo_total["avg"]), fmt(mongo_total["max"])],
        ],
    )

    benchmark_rows = render_table(
        ["Metric", "Value"],
        [
            ["Duration (seconds)", fmt(bench.get("duration_seconds"))],
            ["Successful throughput (QPS)", fmt(bench.get("successful_qps"))],
            ["Attempted throughput (QPS)", fmt(bench.get("attempted_qps"))],
            ["Insert attempts", fmt(bench.get("insert_attempts"), digits=0)],
            ["Insert successes", fmt(bench.get("insert_successes"), digits=0)],
            ["Insert failures", fmt(bench.get("insert_failures"), digits=0)],
            ["Find attempts", fmt(bench.get("find_attempts"), digits=0)],
            ["Find successes", fmt(bench.get("find_successes"), digits=0)],
            ["Find failures", fmt(bench.get("find_failures"), digits=0)],
            ["Total records inserted", fmt(bench.get("total_records"), digits=0)],
        ],
    )

    raw_output = html.escape(str(bench.get("raw", "")).strip())
    metadata = {
        "benchmark_name": benchmark_name,
        "log_dir": str(log_dir),
        "benchmark_metrics": {key: value for key, value in bench.items() if key != "raw"},
        "docker_samples": len(docker_rows),
        "mongostat_samples": len(mongostat_rows),
        "mongotop_samples": len(mongotop_rows),
    }

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(benchmark_name)} benchmark report</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0f172a; --panel:#111827; --muted:#94a3b8; --text:#e5e7eb; --accent:#38bdf8; --accent2:#a78bfa; --accent3:#34d399; --border:#1f2937; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background:linear-gradient(180deg,#020617,#0f172a 20%); color:var(--text); }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px 60px; }}
    h1,h2 {{ margin:0 0 16px; }}
    p {{ color: var(--muted); line-height: 1.6; }}
    .hero {{ display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:28px; }}
    .pill {{ display:inline-block; background:#082f49; color:#7dd3fc; padding:6px 10px; border-radius:999px; font-size:12px; letter-spacing:.04em; text-transform:uppercase; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin:20px 0 28px; }}
    .card, .panel {{ background:rgba(15,23,42,.82); border:1px solid var(--border); border-radius:18px; box-shadow:0 20px 40px rgba(2,6,23,.25); }}
    .card {{ padding:18px; }}
    .label {{ font-size:13px; color:var(--muted); margin-bottom:6px; }}
    .value {{ font-size:28px; font-weight:700; }}
    .panel {{ padding:20px; margin-top:18px; }}
    .panel-grid {{ display:grid; grid-template-columns:1fr; gap:18px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--border); }}
    th {{ color:#cbd5e1; font-weight:600; }}
    td {{ color:#e2e8f0; }}
    .grid line {{ stroke:#1e293b; stroke-width:1; }}
    .axis {{ stroke:#475569; stroke-width:1.5; }}
    .axis-label {{ fill:#94a3b8; font-size:12px; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:10px; }}
    .legend-item {{ display:flex; align-items:center; gap:8px; color:#cbd5e1; font-size:13px; }}
    .legend-swatch {{ width:12px; height:12px; border-radius:999px; display:inline-block; }}
    pre {{ background:#020617; border:1px solid var(--border); border-radius:14px; padding:14px; overflow:auto; color:#cbd5e1; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .empty, .empty-chart {{ color:var(--muted); padding:12px 0; }}
    .footer {{ margin-top:20px; font-size:13px; color:var(--muted); }}
  </style>
</head>
<body>
  <div class="container">
    <div class="hero">
      <div>
        <span class="pill">Benchmark report</span>
        <h1>{html.escape(benchmark_name)}</h1>
        <p>Human-readable performance report generated from benchmark output, docker stats, mongostat, and mongotop logs.</p>
      </div>
      <div class="panel" style="min-width:280px; margin-top:0;">
        <div class="label">Log directory</div>
        <div><code>{html.escape(str(log_dir))}</code></div>
      </div>
    </div>

    <section class="grid">
      {''.join(f'<div class="card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>' for label, value in summary_cards)}
    </section>

    <section class="panel-grid">
      <div class="panel">
        <h2>Container activity</h2>
        <p>Docker metrics sampled during the benchmark run.</p>
        {chart_svg([
            ('CPU %', [row['cpu_percent'] for row in docker_rows], '#38bdf8'),
            ('Memory MiB', [row['memory_used_mib'] for row in docker_rows], '#a78bfa'),
            ('Net in MiB', [row['net_in_mib'] for row in docker_rows], '#34d399'),
        ])}
        {docker_table}
      </div>

      <div class="panel">
        <h2>MongoDB throughput</h2>
        <p>mongostat samples show insert and query rates over time.</p>
        {chart_svg([
            ('Inserts/s', [row['insert'] for row in mongostat_rows], '#38bdf8'),
            ('Queries/s', [row['query'] for row in mongostat_rows], '#f59e0b'),
            ('Connections', [row['connections'] for row in mongostat_rows], '#34d399'),
        ])}
      </div>

      <div class="panel">
        <h2>MongoDB namespace load</h2>
        <p>mongotop samples for <code>{TARGET_NS}</code>.</p>
        {chart_svg([
            ('Total ms', [row['total_ms'] for row in mongotop_rows], '#38bdf8'),
            ('Read ms', [row['read_ms'] for row in mongotop_rows], '#a78bfa'),
            ('Write ms', [row['write_ms'] for row in mongotop_rows], '#34d399'),
        ])}
      </div>

      <div class="panel">
        <h2>Benchmark summary</h2>
        <p>Normalized totals parsed from the benchmark stdout.</p>
        {benchmark_rows}
      </div>

      <div class="panel">
        <h2>Raw benchmark output</h2>
        <pre>{raw_output or 'No benchmark output captured.'}</pre>
      </div>

      <div class="panel">
        <h2>Machine-readable metadata</h2>
        <pre>{html.escape(json.dumps(metadata, indent=2, sort_keys=True))}</pre>
      </div>
    </section>

    <div class="footer">Generated by <code>benchmark/report.py</code>.</div>
  </div>
</body>
</html>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an HTML benchmark report from collected logs.")
    parser.add_argument("log_dir", help="Directory that contains benchmark_output.log, docker_stats.log, mongostat.log, and mongotop.log")
    parser.add_argument("--benchmark-name", default="Mongo benchmark")
    args = parser.parse_args()

    log_dir = Path(args.log_dir).resolve()
    report_path = log_dir / "report.html"
    metadata_path = log_dir / "report.json"

    html_report = build_report(log_dir, args.benchmark_name)
    report_path.write_text(html_report)

    metadata = {
        "benchmark_name": args.benchmark_name,
        "log_dir": str(log_dir),
        "files": sorted(path.name for path in log_dir.iterdir()),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))

    print(f"Generated HTML report: {report_path}")
    print(f"Generated metadata file: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

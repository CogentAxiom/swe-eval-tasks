"""Dependency-free SVG charts for build output.

Each chart is a standalone SVG with its colours as CSS custom properties and a
dark-mode block, so it reads on GitHub in either theme. Marks follow one spec:
bars at most 24px thick with a 4px rounded data end, hairline grid, text in ink
tokens (never the series colour), selective labels.
"""
from __future__ import annotations

from html import escape

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
STYLE = """
<style>
  svg { --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7;
        --s1:#2a78d6; --o1:#86b6ef; --o2:#2a78d6; --o3:#104281; --ref:#c3c2b7; }
  @media (prefers-color-scheme: dark) {
    svg { --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835;
          --s1:#3987e5; --o1:#184f95; --o2:#3987e5; --o3:#b7d3f6; --ref:#383835; }
  }
  .t { font: 600 15px FONT; fill: var(--ink); }
  .st { font: 12px FONT; fill: var(--ink2); }
  .lab { font: 12px FONT; fill: var(--ink2); }
  .val { font: 12px FONT; fill: var(--ink); font-variant-numeric: tabular-nums; }
  .ax { font: 11px FONT; fill: var(--muted); font-variant-numeric: tabular-nums; }
</style>""".replace("FONT", FONT)

SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def _open(w: int, h: int, title: str, subtitle: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">',
        STYLE,
        f'<title>{escape(title)}</title>',
        f'<rect width="{w}" height="{h}" fill="var(--surface)"/>',
        f'<text class="t" x="16" y="26">{escape(title)}</text>',
        f'<text class="st" x="16" y="45">{escape(subtitle)}</text>' if subtitle else "",
    ]


def _hbar_path(x0: float, y: float, length: float, thick: float, r: float = 4.0) -> str:
    """A horizontal bar square at the baseline with a rounded data end."""
    if length <= 0:
        return ""
    r = min(r, length, thick / 2)
    x1 = x0 + length
    return (f'M{x0:.1f},{y:.1f} H{x1 - r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} '
            f'V{y + thick - r:.1f} Q{x1:.1f},{y + thick:.1f} {x1 - r:.1f},{y + thick:.1f} H{x0:.1f} Z')


def _vbar_path(x: float, y0: float, height: float, thick: float, r: float = 4.0) -> str:
    if height <= 0:
        return ""
    r = min(r, height, thick / 2)
    y1 = y0 - height
    return (f'M{x:.1f},{y0:.1f} V{y1 + r:.1f} Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f} '
            f'H{x + thick - r:.1f} Q{x + thick:.1f},{y1:.1f} {x + thick:.1f},{y1 + r:.1f} V{y0:.1f} Z')


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1
    import math
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


def hbar(rows: list[tuple[str, float]], title: str, subtitle: str = "", label_w: int = 250, width: int = 760, fmt=lambda v: f"{v:,.0f}") -> str:
    """Single-series horizontal bars, values at the tips."""
    thick, step, top = 16, 24, 64
    h = top + step * len(rows) + 36
    plot_w = width - label_w - 70
    vmax = _nice_max(max((v for _, v in rows), default=1))
    out = _open(width, h, title, subtitle)
    for i in range(5):
        x = label_w + plot_w * i / 4
        out.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{top + step * len(rows)}" stroke="var(--grid)" stroke-width="1"/>')
        out.append(f'<text class="ax" x="{x:.1f}" y="{top + step * len(rows) + 16}" text-anchor="middle">{fmt(vmax * i / 4)}</text>')
    for i, (name, v) in enumerate(rows):
        y = top + i * step + (step - thick) / 2
        length = plot_w * v / vmax
        out.append(f'<text class="lab" x="{label_w - 8}" y="{y + thick - 4}" text-anchor="end">{escape(name)}</text>')
        out.append(f'<path d="{_hbar_path(label_w, y, length, thick)}" fill="var(--s1)"><title>{escape(name)}: {fmt(v)}</title></path>')
        out.append(f'<text class="val" x="{label_w + length + 6:.1f}" y="{y + thick - 4}">{fmt(v)}</text>')
    out.append(f'<line x1="{label_w}" y1="{top - 6}" x2="{label_w}" y2="{top + step * len(rows)}" stroke="var(--axis)" stroke-width="1"/>')
    out.append("</svg>")
    return "\n".join(x for x in out if x)


def columns(cols: list[tuple[str, float]], title: str, subtitle: str = "", width: int = 760, height: int = 320, fmt=lambda v: f"{v:,.0f}", notes: list[str] | None = None) -> str:
    """Single-series columns, value on each cap."""
    top, bottom, left = 64, 56, 56
    plot_h = height - top - bottom
    plot_w = width - left - 24
    band = plot_w / max(1, len(cols))
    thick = min(24, band * 0.6)
    vmax = _nice_max(max((v for _, v in cols), default=1))
    out = _open(width, height, title, subtitle)
    base = top + plot_h
    for i in range(5):
        y = base - plot_h * i / 4
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        out.append(f'<text class="ax" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{fmt(vmax * i / 4)}</text>')
    for i, (name, v) in enumerate(cols):
        x = left + band * i + (band - thick) / 2
        hgt = plot_h * v / vmax
        out.append(f'<path d="{_vbar_path(x, base, hgt, thick)}" fill="var(--s1)"><title>{escape(name)}: {fmt(v)}</title></path>')
        out.append(f'<text class="val" x="{x + thick / 2:.1f}" y="{base - hgt - 6:.1f}" text-anchor="middle">{fmt(v)}</text>')
        for j, part in enumerate(name.split("\n")):
            out.append(f'<text class="ax" x="{x + thick / 2:.1f}" y="{base + 16 + 13 * j:.1f}" text-anchor="middle">{escape(part)}</text>')
    out.append(f'<line x1="{left}" y1="{base}" x2="{left + plot_w}" y2="{base}" stroke="var(--axis)" stroke-width="1"/>')
    out.append("</svg>")
    return "\n".join(x for x in out if x)


def stacked_levels(rows: list[tuple[str, list[int]]], title: str, subtitle: str = "", level_names=("0", "1", "2"), width: int = 760) -> str:
    """100% stacked bars for ordinal 0/1/2 levels, one row per dimension, with a legend."""
    label_w, thick, step, top = 150, 18, 30, 92
    plot_w = width - label_w - 40
    h = top + step * len(rows) + 30
    fills = ["var(--o1)", "var(--o2)", "var(--o3)"]
    out = _open(width, h, title, subtitle)
    lx = 16
    for k, nm in enumerate(level_names):
        out.append(f'<rect x="{lx}" y="58" width="12" height="12" rx="2" fill="{fills[k]}"/>')
        out.append(f'<text class="lab" x="{lx + 18}" y="68">{escape(nm)}</text>')
        lx += 18 + 8 * len(nm) + 28
    for i, (name, counts) in enumerate(rows):
        total = sum(counts) or 1
        y = top + i * step
        out.append(f'<text class="lab" x="{label_w - 8}" y="{y + thick - 5}" text-anchor="end">{escape(name)}</text>')
        x = label_w
        for k, c in enumerate(counts):
            w = plot_w * c / total
            gap = 2 if k < len(counts) - 1 and w > 2 else 0
            if w > 0:
                out.append(f'<rect x="{x:.1f}" y="{y}" width="{max(0, w - gap):.1f}" height="{thick}" fill="{fills[k]}">'
                           f'<title>{escape(name)} = {escape(level_names[k])}: {c:,} ({100 * c / total:.1f}%)</title></rect>')
                if w > 46:
                    ink = "#ffffff" if k > 0 else "var(--ink)"
                    out.append(f'<text x="{x + w / 2:.1f}" y="{y + thick - 5}" text-anchor="middle" style="font:11px {FONT};fill:{ink}">{100 * c / total:.0f}%</text>')
            x += w
    out.append("</svg>")
    return "\n".join(x for x in out if x)


def heatmap(row_names: list[str], col_names: list[str], cells: list[list[int]], title: str, subtitle: str = "", label_w: int = 250, cell: int = 34) -> str:
    """Sequential one-hue heatmap; zero cells recede to the surface; counts in cells that fit."""
    top = 150
    width = label_w + cell * len(col_names) + 24
    h = top + cell * len(row_names) + 20
    vmax = max((v for r in cells for v in r), default=1) or 1
    out = _open(width, h, title, subtitle)
    for j, cn in enumerate(col_names):
        x = label_w + j * cell + cell / 2
        out.append(f'<text class="ax" transform="translate({x:.1f},{top - 8}) rotate(-50)">{escape(cn)}</text>')
    for i, rn in enumerate(row_names):
        y = top + i * cell
        out.append(f'<text class="lab" x="{label_w - 8}" y="{y + cell / 2 + 4:.1f}" text-anchor="end">{escape(rn)}</text>')
        for j, v in enumerate(cells[i]):
            x = label_w + j * cell
            if v == 0:
                out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" fill="var(--grid)" opacity="0.35"><title>{escape(rn)} x {escape(col_names[j])}: 0</title></rect>')
                continue
            idx = min(len(SEQ) - 1, 2 + int((len(SEQ) - 3) * (v / vmax) ** 0.5))
            fill = SEQ[idx]
            ink = "#ffffff" if idx >= 7 else "#0b0b0b"
            out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="2" fill="{fill}"><title>{escape(rn)} x {escape(col_names[j])}: {v:,}</title></rect>')
            out.append(f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" text-anchor="middle" style="font:11px {FONT};fill:{ink}">{v}</text>')
    out.append("</svg>")
    return "\n".join(x for x in out if x)


def lorenz(values: list[int], title: str, subtitle: str = "", width: int = 520, height: int = 420, mark: tuple[float, str] | None = None) -> str:
    """Cumulative share of entries against cumulative share of units, most-loaded first, with the equality line."""
    top, left, size = 64, 56, min(width - 80, height - 110)
    vals = sorted(values, reverse=True)
    total = sum(vals) or 1
    pts, acc = [(0.0, 0.0)], 0
    for i, v in enumerate(vals, 1):
        acc += v
        pts.append((i / len(vals), acc / total))
    out = _open(width, height, title, subtitle)
    base = top + size
    for i in range(5):
        g = size * i / 4
        out.append(f'<line x1="{left}" y1="{base - g:.1f}" x2="{left + size}" y2="{base - g:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        out.append(f'<text class="ax" x="{left - 6}" y="{base - g + 4:.1f}" text-anchor="end">{25 * i}%</text>')
        out.append(f'<text class="ax" x="{left + g:.1f}" y="{base + 16}" text-anchor="middle">{25 * i}%</text>')
    out.append(f'<line x1="{left}" y1="{base}" x2="{left + size}" y2="{top}" stroke="var(--ref)" stroke-width="1"/>')
    d = " ".join(f"{'M' if k == 0 else 'L'}{left + size * x:.1f},{base - size * y:.1f}" for k, (x, y) in enumerate(pts))
    out.append(f'<path d="{d}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    if mark:
        fx, label = mark
        k = max(1, round(fx * len(vals)))
        x, y = pts[k]
        out.append(f'<circle cx="{left + size * x:.1f}" cy="{base - size * y:.1f}" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>')
        out.append(f'<text class="val" x="{left + size * x + 10:.1f}" y="{base - size * y + 16:.1f}">{escape(label)}</text>')
    out.append(f'<text class="ax" x="{left + size / 2:.1f}" y="{base + 36}" text-anchor="middle">share of units, most-loaded first</text>')
    out.append("</svg>")
    return "\n".join(x for x in out if x)

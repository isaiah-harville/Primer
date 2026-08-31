"""A very small SVG drawing kit for Primer's architecture diagrams.

Hand-written SVG rather than a diagramming library: the docs build then has
no system dependency on Graphviz, the output is a crisp vector at any zoom,
and the colours can follow the reader's light or dark theme, which a
rasterised diagram cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

FONT = (
    "ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Inter, Roboto, Helvetica, Arial, sans-serif"
)
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"

#: One accent per kind of thing, so the same colour always means the same
#: role across every diagram in the documentation.
KINDS: dict[str, tuple[str, str]] = {
    "client": ("#eef2ff", "#6366f1"),
    "edge": ("#fef3c7", "#d97706"),
    "service": ("#e0f2fe", "#0284c7"),
    "worker": ("#dcfce7", "#16a34a"),
    "store": ("#f1f5f9", "#64748b"),
    "external": ("#fae8ff", "#a855f7"),
    "state": ("#e0f2fe", "#0284c7"),
    "terminal": ("#dcfce7", "#16a34a"),
    "failure": ("#fee2e2", "#dc2626"),
    "note": ("#ffffff", "#cbd5e1"),
}


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    title: str
    subtitle: str = ""
    kind: str = "service"
    mono: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def port(self, side: str) -> tuple[float, float]:
        return {
            "top": (self.cx, self.y),
            "bottom": (self.cx, self.y + self.h),
            "left": (self.x, self.cy),
            "right": (self.x + self.w, self.cy),
        }[side]


@dataclass
class Theme:
    ink: str
    ink_muted: str
    edge: str
    group: str
    chip: str
    surface: str
    #: Panel fills are washed toward the surface on dark backgrounds; the
    #: light tints that read as gentle on white glare against dark.
    fill_opacity: float = 1.0


LIGHT = Theme(
    ink="#0f172a",
    ink_muted="#475569",
    edge="#94a3b8",
    group="#cbd5e1",
    chip="#ffffff",
    surface="#ffffff",
)

DARK = Theme(
    ink="#e2e8f0",
    ink_muted="#94a3b8",
    edge="#64748b",
    group="#334155",
    chip="#0f172a",
    surface="#0f172a",
    fill_opacity=0.18,
)


@dataclass
class Canvas:
    width: float
    height: float
    title: str
    parts: list[str] = field(default_factory=list)

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def box(self, box: Box) -> Box:
        fill, stroke = KINDS[box.kind]
        family = MONO if box.mono else FONT
        title_y = box.cy + (0 if not box.subtitle else -6)
        self.add(
            f'<g class="node"><rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" '
            f'rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.5" '
            f'class="fill-{box.kind}"/>'
            f'<text x="{box.cx}" y="{title_y}" text-anchor="middle" dominant-baseline="middle" '
            f'font-family="{family}" font-size="15" font-weight="600" class="ink">'
            f"{escape(box.title)}</text>"
        )
        if box.subtitle:
            self.add(
                f'<text x="{box.cx}" y="{box.cy + 14}" text-anchor="middle" '
                f'dominant-baseline="middle" font-family="{FONT}" font-size="12" '
                f'class="ink-muted">{escape(box.subtitle)}</text>'
            )
        self.add("</g>")
        return box

    def label(
        self,
        x: float,
        y: float,
        text: str,
        *,
        size: int = 13,
        anchor: str = "middle",
        weight: int = 500,
        muted: bool = True,
        mono: bool = False,
    ) -> None:
        family = MONO if mono else FONT
        self.add(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" dominant-baseline="middle" '
            f'font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'class="{"ink-muted" if muted else "ink"}">{escape(text)}</text>'
        )

    def chip(self, x: float, y: float, text: str, *, size: int = 12) -> None:
        """A label with a plate behind it, so a line never runs through words."""
        width = len(text) * size * 0.58 + 16
        self.add(
            f'<rect x="{x - width / 2}" y="{y - 11}" width="{width}" height="22" rx="7" '
            f'class="chip"/>'
        )
        self.label(x, y, text, size=size)

    def arrow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        label: str = "",
        dashed: bool = False,
        bend: float = 0.0,
        label_at: float = 0.5,
        label_dy: float = 0.0,
    ) -> None:
        (x1, y1), (x2, y2) = start, end
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        if bend:
            mx, my = (x1 + x2) / 2 + bend, (y1 + y2) / 2
            path = f"M {x1} {y1} Q {mx} {my} {x2} {y2}"
            lx, ly = (x1 + x2) / 2 + bend * 0.55, (y1 + y2) / 2
        else:
            path = f"M {x1} {y1} L {x2} {y2}"
            lx = x1 + (x2 - x1) * label_at
            ly = y1 + (y2 - y1) * label_at
        self.add(
            f'<path d="{path}" fill="none" class="edge" stroke-width="1.6"{dash} '
            f'marker-end="url(#arrow)"/>'
        )
        if label:
            self.chip(lx, ly + label_dy, label)

    def elbow(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        label: str = "",
        via_y: float | None = None,
        dashed: bool = False,
    ) -> None:
        """A right-angled connector, for links that must route around a box."""
        (x1, y1), (x2, y2) = start, end
        mid = via_y if via_y is not None else (y1 + y2) / 2
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        path = f"M {x1} {y1} L {x1} {mid} L {x2} {mid} L {x2} {y2}"
        self.add(
            f'<path d="{path}" fill="none" class="edge" stroke-width="1.6"{dash} '
            f'marker-end="url(#arrow)" stroke-linejoin="round"/>'
        )
        if label:
            self.chip((x1 + x2) / 2, mid, label)

    def route(
        self,
        points: list[tuple[float, float]],
        *,
        label: str = "",
        dashed: bool = False,
        label_at: int = 1,
        label_dy: float = 0.0,
    ) -> None:
        """A connector along explicit waypoints.

        Diagrams read badly when a line crosses a box, so the awkward links
        say exactly where they go rather than being left to a heuristic.
        """
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        path = " ".join(
            f"{'M' if index == 0 else 'L'} {x} {y}" for index, (x, y) in enumerate(points)
        )
        self.add(
            f'<path d="{path}" fill="none" class="edge" stroke-width="1.6"{dash} '
            f'marker-end="url(#arrow)" stroke-linejoin="round"/>'
        )
        if label:
            (x1, y1), (x2, y2) = points[label_at - 1], points[label_at]
            self.chip((x1 + x2) / 2, (y1 + y2) / 2 + label_dy, label)

    def group(self, x: float, y: float, w: float, h: float, title: str) -> None:
        """A dashed enclosure naming a boundary, drawn behind its contents."""
        self.parts.insert(
            0,
            f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" class="group" '
            f'stroke-dasharray="7 6" stroke-width="1.4"/>'
            f'<text x="{x + 18}" y="{y + 22}" font-family="{FONT}" font-size="12" '
            f'font-weight="700" letter-spacing="0.08em" class="ink-muted">'
            f"{escape(title.upper())}</text></g>",
        )

    def render(self, theme: Theme = LIGHT) -> str:
        body = "\n  ".join(self.parts)
        opening = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" role="img" '
            f'aria-label="{escape(self.title)}">'
        )
        return f"""{opening}
  <title>{escape(self.title)}</title>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" class="edge-head"/>
    </marker>
  </defs>
  <style>
    .ink {{ fill: {theme.ink}; }}
    .ink-muted {{ fill: {theme.ink_muted}; }}
    .edge {{ stroke: {theme.edge}; }}
    .edge-head {{ fill: {theme.edge}; }}
    .group {{ fill: none; stroke: {theme.group}; }}
    .chip {{ fill: {theme.chip}; }}
    .node rect {{ fill-opacity: {theme.fill_opacity}; }}
  </style>
  <rect width="{self.width}" height="{self.height}" fill="{theme.surface}" rx="14"/>
  {body}
</svg>
"""

    def write(self, path: Path) -> list[Path]:
        """Write a light and a dark file, named for Material's image suffixes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        written = []
        for suffix, theme in (("", LIGHT), ("-dark", DARK)):
            target = path.with_name(f"{path.stem}{suffix}{path.suffix}")
            target.write_text(self.render(theme))
            written.append(target)
        return written

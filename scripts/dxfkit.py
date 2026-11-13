"""dxfkit - helpers for 2D architectural / engineering drafting with ezdxf.

The one idea to keep in mind: geometry is drawn in real-world drawing units
(m, cm or mm), while everything that is *annotation* (text, dimension ticks,
grid bubbles, the title block) is sized in paper millimetres and converted with
Kit.mm(). That is what makes a drawing read correctly when plotted at its scale.

    from dxfkit import Kit
    kit = Kit(units="m", scale=100)
    kit.rect((0, 0), (4, 3), layer="wall")
    kit.dim_h((0, 0), (4, 0), y=-kit.mm(10))
    kit.text("غرفة", (2, 1.5), height_mm=3)
    kit.sheet(title="Plan", project="Villa")
    kit.save("out.dxf")
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

import ezdxf
from ezdxf import bbox, const, zoom
from ezdxf.enums import TextEntityAlignment

# Windows consoles default to a legacy code page; without this, printing an Arabic room
# name from a drawing script raises UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

UNIT_PER_MM = {"mm": 1.0, "cm": 0.1, "m": 0.001}
INSUNITS = {"mm": 4, "cm": 5, "m": 6}
PAPER_MM = {
    "A4": (297, 210),
    "A3": (420, 297),
    "A2": (594, 420),
    "A1": (841, 594),
    "A0": (1189, 841),
}
STYLE = "PLAN"
DIMSTYLE = "PLAN"

# key: (layer name, ACI colour, lineweight in 1/100 mm, linetype)
# Names follow the AIA / US National CAD Standard pattern most offices recognise.
LAYERS = {
    "wall": ("A-WALL", 7, 50, "Continuous"),
    "wall_fill": ("A-WALL-PATT", 253, 9, "Continuous"),
    "door": ("A-DOOR", 3, 25, "Continuous"),
    "window": ("A-GLAZ", 4, 25, "Continuous"),
    "stair": ("A-FLOR-STRS", 6, 18, "Continuous"),
    "furniture": ("A-FURN", 30, 13, "Continuous"),
    "fixture": ("A-FLOR-FIXT", 140, 13, "Continuous"),
    "column": ("S-COLS", 1, 50, "Continuous"),
    "beam": ("S-BEAM", 1, 35, "DASHED"),
    "footing": ("S-FNDN", 5, 35, "Continuous"),
    "slab": ("S-SLAB", 5, 35, "Continuous"),
    "section": ("A-SECT", 7, 50, "Continuous"),
    "ground": ("C-TOPO", 34, 35, "Continuous"),
    "rebar": ("S-RBAR", 1, 35, "Continuous"),
    "grid": ("S-GRID", 8, 13, "CENTER"),
    "site": ("C-PROP", 3, 35, "PHANTOM"),
    "hidden": ("A-DETL-HIDN", 8, 13, "DASHED"),
    "hatch": ("A-ANNO-PATT", 8, 9, "Continuous"),
    "dim": ("A-ANNO-DIMS", 2, 13, "Continuous"),
    "text": ("A-ANNO-TEXT", 7, 18, "Continuous"),
    "room": ("A-AREA-IDEN", 7, 18, "Continuous"),
    "symbol": ("A-ANNO-SYMB", 7, 18, "Continuous"),
    "title": ("A-ANNO-TTLB", 7, 35, "Continuous"),
}

CAPTIONS = {
    "en": {
        "office": "OFFICE",
        "client": "OWNER",
        "project": "PROJECT",
        "title": "DRAWING",
        "scale": "SCALE",
        "date": "DATE",
        "drawn_by": "DRAWN BY",
        "number": "SHEET",
        "north": "N",
    },
    "ar": {
        "office": "المكتب",
        "client": "المالك",
        "project": "المشروع",
        "title": "اسم اللوحة",
        "scale": "مقياس الرسم",
        "date": "التاريخ",
        "drawn_by": "رسم",
        "number": "رقم اللوحة",
        "north": "N",
    },
}


def _v(p) -> tuple[float, float]:
    return float(p[0]), float(p[1])


class Kit:
    """A drawing plus the conventions needed to draft on it consistently."""

    def __init__(
        self,
        units: str = "m",
        scale: float = 100,
        font: str = "arial.ttf",
        dxfversion: str = "R2013",
        layers: dict | None = None,
        dim_decimals: int | None = None,
        dim_factor: float = 1.0,
        doc=None,
    ):
        if units not in UNIT_PER_MM:
            raise ValueError(f"units must be one of {sorted(UNIT_PER_MM)}, got {units!r}")
        if scale <= 0:
            raise ValueError("scale must be positive (100 means 1:100)")
        self.units = units
        self.scale = float(scale)
        self.warnings: list[str] = []
        self.sheet_info: dict | None = None
        if doc is None:
            self.doc = ezdxf.new(dxfversion, setup=["linetypes"])
            self.doc.header["$INSUNITS"] = INSUNITS[units]
            self.doc.header["$MEASUREMENT"] = 1  # metric hatch patterns and linetypes
            self.doc.header["$LTSCALE"] = self.mm(10)
        else:  # drafting onto someone else's drawing: add what is missing, change nothing
            self.doc = doc
            from ezdxf.tools.standards import setup_linetypes

            setup_linetypes(doc)
        self.msp = self.doc.modelspace()

        # arial.ttf carries Arabic glyphs, so AutoCAD shapes Arabic text natively.
        if STYLE not in self.doc.styles:
            self.doc.styles.add(STYLE, font=font)

        self._layers = dict(LAYERS)
        for key, value in (layers or {}).items():
            if isinstance(value, str):  # rename only, keep colour / weight
                base = self._layers.get(key, (value, 7, 18, "Continuous"))
                self._layers[key] = (value, *base[1:])
            else:
                self._layers[key] = tuple(value)

        if dim_decimals is None:
            dim_decimals = {"m": 2, "cm": 0, "mm": 0}[units]
        if DIMSTYLE in self.doc.dimstyles:
            return
        self.doc.dimstyles.new(
            DIMSTYLE,
            dxfattribs={
                "dimtxsty": STYLE,
                "dimtxt": self.mm(2.2),
                "dimasz": self.mm(1.6),
                "dimtsz": self.mm(0.9),  # oblique architectural tick instead of arrows
                "dimexe": self.mm(1.2),
                "dimexo": self.mm(1.5),
                "dimdle": self.mm(1.0),
                "dimgap": self.mm(0.7),
                "dimtad": 1,  # text above the dimension line
                "dimtih": 0,
                "dimtoh": 0,
                "dimdec": dim_decimals,
                "dimzin": 0,  # keep trailing zeros: 4.00, not 4
                "dimlfac": dim_factor,
                "dimdsep": ord("."),
            },
        )

    @classmethod
    def open(cls, path, scale: float, units: str | None = None, **kwargs) -> "Kit":
        """Wrap an existing DXF so the same helpers can add to it.

        Units come from the file ($INSUNITS) unless given. Save under a new name afterwards.
        """
        doc = ezdxf.readfile(path)
        if units is None:
            units = {4: "mm", 5: "cm", 6: "m"}.get(doc.header.get("$INSUNITS", 0))
            if units is None:
                raise ValueError("the file does not declare mm, cm or m units; pass units= explicitly")
        return cls(units=units, scale=scale, doc=doc, **kwargs)

    # ------------------------------------------------------------------ scale
    def mm(self, paper_mm: float) -> float:
        """Paper millimetres -> drawing units at this drawing's plot scale."""
        return paper_mm * self.scale * UNIT_PER_MM[self.units]

    def real_mm(self, mm: float) -> float:
        """Real-world millimetres -> drawing units (e.g. a 40 mm door leaf)."""
        return mm * UNIT_PER_MM[self.units]

    def layer(self, key: str) -> str:
        """Resolve a layer key ('wall') or accept any literal layer name.

        Layers are created on first use, so a drawing only carries the ones it needs.
        """
        if key in self._layers:
            name, color, lw, lt = self._layers[key]
            if name not in self.doc.layers:
                self.doc.layers.add(name, color=color, lineweight=lw, linetype=lt)
            return name
        if key not in self.doc.layers:
            self.doc.layers.add(key, color=7)
        return key

    def _attribs(self, layer: str, **extra) -> dict:
        attribs = {"layer": self.layer(layer)}
        attribs.update({k: v for k, v in extra.items() if v is not None})
        return attribs

    # ------------------------------------------------------------- primitives
    def line(self, p1, p2, layer="0", linetype=None, color=None):
        return self.msp.add_line(_v(p1), _v(p2), dxfattribs=self._attribs(layer, linetype=linetype, color=color))

    def polyline(self, points: Iterable, layer="0", closed=False, linetype=None, color=None):
        pts = [_v(p) for p in points]
        if closed and len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        return self.msp.add_lwpolyline(pts, close=closed, dxfattribs=self._attribs(layer, linetype=linetype, color=color))

    def rect_points(self, at, size, rotation=0.0, anchor="corner") -> list[tuple[float, float]]:
        w, h = float(size[0]), float(size[1])
        x0, y0 = (-w / 2, -h / 2) if anchor == "center" else (0.0, 0.0)
        ca, sa = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        ax, ay = _v(at)
        corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
        return [(ax + x * ca - y * sa, ay + x * sa + y * ca) for x, y in corners]

    def rect(self, at, size, layer="0", rotation=0.0, anchor="corner", linetype=None, color=None):
        """Rectangle from its lower-left corner (or centre with anchor='center')."""
        return self.polyline(self.rect_points(at, size, rotation, anchor), layer, closed=True, linetype=linetype, color=color)

    def circle(self, center, radius, layer="0", linetype=None, color=None):
        return self.msp.add_circle(_v(center), float(radius), dxfattribs=self._attribs(layer, linetype=linetype, color=color))

    def arc(self, center, radius, start_deg, end_deg, layer="0", linetype=None, color=None):
        """Counter-clockwise arc from start_deg to end_deg."""
        return self.msp.add_arc(
            _v(center), float(radius), float(start_deg), float(end_deg),
            dxfattribs=self._attribs(layer, linetype=linetype, color=color),
        )

    def text(self, content, at, height_mm=2.5, layer="text", align="MIDDLE_CENTER", rotation=0.0, color=None):
        """Single-line text. height_mm is the height on paper."""
        t = self.msp.add_text(
            str(content),
            height=self.mm(height_mm),
            rotation=rotation,
            dxfattribs=self._attribs(layer, style=STYLE, color=color),
        )
        t.set_placement(_v(at), align=TextEntityAlignment[align])
        return t

    def mtext(self, content, at, height_mm=2.5, width=None, layer="text", attachment="TOP_LEFT", color=None):
        """Multi-line note. Use \\P for line breaks. width is in drawing units."""
        from ezdxf.enums import MTextEntityAlignment

        m = self.msp.add_mtext(
            str(content),
            dxfattribs=self._attribs(layer, style=STYLE, char_height=self.mm(height_mm), color=color),
        )
        if width:
            m.dxf.width = float(width)
        m.set_location(_v(at), attachment_point=MTextEntityAlignment[attachment])
        return m

    def hatch(self, exterior: Iterable, holes: Iterable[Iterable] = (), layer="hatch", pattern="SOLID",
              color=None, scale=1.0, angle=0.0):
        """Fill a polygon. pattern: SOLID, ANSI31, ANSI37, AR-CONC, AR-SAND, EARTH, ...

        `scale=1` gives a sensible density at any plot scale: texture patterns are sized in
        paper mm, while brick / tile / roof patterns (AR-B816, AR-HBONE, ...) are drawn true-size.
        """
        h = self.msp.add_hatch(
            color=256 if color is None else color,
            dxfattribs={"layer": self.layer(layer), "hatch_style": const.HATCH_STYLE_NESTED},
        )
        h.paths.add_polyline_path([_v(p) for p in exterior], is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL)
        for hole in holes:
            h.paths.add_polyline_path([_v(p) for p in hole], is_closed=True, flags=const.BOUNDARY_PATH_OUTERMOST)
        if pattern.upper() != "SOLID":
            h.set_pattern_fill(pattern.upper(), color=256 if color is None else color, angle=angle,
                               scale=self._pattern_unit(pattern.upper()) * scale)
        return h

    def _pattern_unit(self, name: str) -> float:
        # The AR-* definitions are 25-100x coarser than the ANSI ones, so they need their own base.
        if name in ("AR-CONC", "AR-SAND"):
            return self.mm(0.04)
        if name == "GRAVEL":
            return self.mm(0.12)
        if name == "EARTH":
            return self.mm(0.6)
        if name in ("GRASS", "SWAMP"):
            return self.mm(0.4)
        if name.startswith("AR-"):
            return self.real_mm(1.0)
        return self.mm(1.0)

    def break_line(self, p1, p2, layer="section"):
        """Line with a zig-zag at its middle: the "continues beyond" mark of sections and details."""
        p1, p2 = _v(p1), _v(p2)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        n = math.hypot(dx, dy) or 1.0
        dx, dy = dx / n, dy / n
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        a = self.mm(1.5)
        return self.polyline([
            p1,
            (mx - dx * a, my - dy * a),
            (mx - dx * a / 2 - dy * a, my - dy * a / 2 + dx * a),
            (mx + dx * a / 2 + dy * a, my + dy * a / 2 - dx * a),
            (mx + dx * a, my + dy * a),
            p2,
        ], layer)

    def leader(self, tip, text_at, content, height_mm=2.2, layer="text"):
        """Note with an arrowed pointer line from text_at to tip (plain lines and text).

        The text starts at text_at when that is to the right of the tip, and ends there when it
        is to the left, so it always runs away from the arrow. Allow about 0.8 x text height per
        character when checking that a note clears nearby dimensions.
        """
        tip, text_at = _v(tip), _v(text_at)
        self.line(text_at, tip, layer)
        ang = math.atan2(text_at[1] - tip[1], text_at[0] - tip[0])
        a = self.mm(2.0)
        for da in (0.35, -0.35):
            self.line(tip, (tip[0] + a * math.cos(ang + da), tip[1] + a * math.sin(ang + da)), layer)
        right = text_at[0] >= tip[0]
        gap = self.mm(1.0)
        self.text(content, (text_at[0] + (gap if right else -gap), text_at[1]), height_mm, layer,
                  align="MIDDLE_LEFT" if right else "MIDDLE_RIGHT")

    # ------------------------------------------------------------- dimensions
    def _dim_override(self, fixed_ext: bool) -> dict:
        # Fixed-length extension lines keep chains outside a plan from striking through it.
        return {"dimfxlon": 1, "dimfxl": self.mm(3.0)} if fixed_ext else {}

    def _short(self, span: float) -> bool:
        # A wall-thickness segment is narrower than its own number.
        return span < self._dim_text_width(span) + self.mm(1.0)

    def dim_h(self, p1, p2, y, layer="dim", text="<>", fixed_ext=False, location=None):
        """Horizontal dimension between p1 and p2 with the dimension line at height y.

        A number too wide for its segment is moved to the outer side of the dimension line
        (away from the measured points), where ticks and extension lines cannot strike it.
        """
        p1, p2 = _v(p1), _v(p2)
        if location is None and text == "<>" and self._short(abs(p2[0] - p1[0])):
            out = 1 if y >= (p1[1] + p2[1]) / 2 else -1
            location = ((p1[0] + p2[0]) / 2, y + out * self.mm(2.9))
        d = self.msp.add_linear_dim(
            base=(0, y), p1=_v(p1), p2=_v(p2), angle=0, text=text, dimstyle=DIMSTYLE, location=location,
            override=self._dim_override(fixed_ext), dxfattribs={"layer": self.layer(layer)},
        )
        d.render()
        return d

    def dim_v(self, p1, p2, x, layer="dim", text="<>", fixed_ext=False, location=None):
        """Vertical dimension between p1 and p2 with the dimension line at position x."""
        p1, p2 = _v(p1), _v(p2)
        if location is None and text == "<>" and self._short(abs(p2[1] - p1[1])):
            out = 1 if x >= (p1[0] + p2[0]) / 2 else -1
            location = (x + out * self.mm(2.9), (p1[1] + p2[1]) / 2)
        d = self.msp.add_linear_dim(
            base=(x, 0), p1=_v(p1), p2=_v(p2), angle=90, text=text, dimstyle=DIMSTYLE, location=location,
            override=self._dim_override(fixed_ext), dxfattribs={"layer": self.layer(layer)},
        )
        d.render()
        return d

    def dim_aligned(self, p1, p2, offset, layer="dim", text="<>", fixed_ext=False):
        """Dimension parallel to p1->p2, offset to the left of that direction (negative = right).

        Point order only decides which side the dimension line is on: the text always reads
        left-to-right or bottom-to-top, and horizontal / vertical cases get the same tidy
        handling of narrow numbers as dim_h / dim_v.
        """
        p1, p2, offset = _v(p1), _v(p2), float(offset)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        tol = 1e-9 * max(abs(dx), abs(dy), 1.0)
        if dx < -tol or (abs(dx) <= tol and dy < 0):  # would read upside-down: flip it
            p1, p2, offset = p2, p1, -offset
            dx, dy = -dx, -dy
        if abs(dy) <= tol:
            return self.dim_h(p1, p2, p1[1] + offset, layer, text, fixed_ext=fixed_ext)
        if abs(dx) <= tol:
            return self.dim_v(p1, p2, p1[0] - offset, layer, text, fixed_ext=fixed_ext)
        d = self.msp.add_aligned_dim(
            p1=p1, p2=p2, distance=offset, text=text, dimstyle=DIMSTYLE,
            override=self._dim_override(fixed_ext), dxfattribs={"layer": self.layer(layer)},
        )
        d.render()
        return d

    def dim_chain(self, values: Sequence[float], axis: str, at: float, origin: float = 0.0, layer="dim",
                  fixed_ext=True):
        """Chain of dimensions through sorted coordinates.

        axis='x': values are x coordinates, dimension line is horizontal at y=at, measured from y=origin.
        axis='y': values are y coordinates, dimension line is vertical at x=at, measured from x=origin.
        """
        vals = sorted({round(float(v), 6) for v in values})
        for a, b in zip(vals, vals[1:]):
            if b - a < 1e-6:
                continue
            if axis == "x":
                self.dim_h((a, origin), (b, origin), at, layer, fixed_ext=fixed_ext)
            else:
                self.dim_v((origin, a), (origin, b), at, layer, fixed_ext=fixed_ext)

    def _dim_text_width(self, value: float) -> float:
        style = self.doc.dimstyles.get(DIMSTYLE)
        label = f"{abs(value) * style.dxf.dimlfac:.{style.dxf.dimdec}f}"
        return sum(0.39 if ch == "." else 0.78 for ch in label) * style.dxf.dimtxt

    # -------------------------------------------------- structural / symbols
    def column(self, at, size=(0.3, 0.3), rotation=0.0, layer="column", fill=True, anchor="center"):
        """Column in plan. size=(bx, by) for rectangular, a single number for a round column."""
        if isinstance(size, (int, float)):
            r = float(size) / 2
            self.circle(at, r, layer)
            if fill:
                pts = [(at[0] + r * math.cos(math.radians(a)), at[1] + r * math.sin(math.radians(a))) for a in range(0, 360, 10)]
                self.hatch(pts, layer=layer, color=250)
            return
        pts = self.rect_points(at, size, rotation, anchor)
        if fill:
            self.hatch(pts, layer=layer, color=250)
        self.polyline(pts, layer, closed=True)

    def grid(self, xs: Sequence[float] = (), ys: Sequence[float] = (), x_labels=None, y_labels=None,
             bounds=None, overhang_mm=15.0, bubble_mm=4.0, stub_mm=6.0, layer="grid"):
        """Structural grid: centre lines with bubbles at the top (x grids) and left (y grids).

        bounds=(minx, miny, maxx, maxy) is the extent the lines must span (default: the grid itself).
        overhang_mm is how far the lines run past it on the bubble sides (leave room for dimension
        chains there); stub_mm is the short run-out on the other two sides.
        """
        xs, ys = [float(x) for x in xs], [float(y) for y in ys]
        if bounds is None:
            bounds = (min(xs or [0]), min(ys or [0]), max(xs or [0]), max(ys or [0]))
        minx, miny, maxx, maxy = bounds
        o, r, stub = self.mm(overhang_mm), self.mm(bubble_mm), self.mm(stub_mm)
        x_labels = x_labels or [str(i + 1) for i in range(len(xs))]
        y_labels = y_labels or [chr(ord("A") + i) for i in range(len(ys))]
        for x, label in zip(xs, x_labels):
            self.line((x, miny - stub), (x, maxy + o), layer)
            c = (x, maxy + o + r)
            self.circle(c, r, layer, linetype="Continuous")
            self.text(label, c, bubble_mm * 0.9, layer)
        for y, label in zip(ys, y_labels):
            self.line((minx - o, y), (maxx + stub, y), layer)
            c = (minx - o - r, y)
            self.circle(c, r, layer, linetype="Continuous")
            self.text(label, c, bubble_mm * 0.9, layer)

    def north_arrow(self, center, radius_mm=6.0, angle=90.0, layer="symbol"):
        """North arrow; angle is the direction of north in degrees (90 = up the sheet)."""
        cx, cy = _v(center)
        r = self.mm(radius_mm)
        a = math.radians(angle)
        tip = (cx + r * math.cos(a), cy + r * math.sin(a))
        b1 = (cx + r * 0.75 * math.cos(a + 2.5), cy + r * 0.75 * math.sin(a + 2.5))
        b2 = (cx + r * 0.75 * math.cos(a - 2.5), cy + r * 0.75 * math.sin(a - 2.5))
        self.circle((cx, cy), r, layer)
        self.hatch([tip, b1, (cx, cy)], layer=layer)
        self.polyline([tip, b1, (cx, cy), b2], layer, closed=True)
        self.text("N", (cx + (r + self.mm(2.2)) * math.cos(a), cy + (r + self.mm(2.2)) * math.sin(a)),
                  radius_mm * 0.5, layer)

    # ------------------------------------------------------------------ sheet
    def extents(self) -> tuple[float, float, float, float]:
        box = bbox.extents(self.msp, fast=True)
        if not box.has_data:
            return (0.0, 0.0, 0.0, 0.0)
        return (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)

    def sheet(self, size="auto", title="", project="", drawn_by="", date="", number="", client="", office="",
              language="en", north=None, paperspace=True, scale_text=None, orientation="auto"):
        """Frame the drawing with a border and title strip sized for a paper format.

        size="auto" picks the smallest of A4..A0 the drawing fits on at the current scale.
        orientation: "auto" (landscape unless portrait saves a sheet size), "landscape", "portrait".
        north=None draws no north arrow. Call this last, after all geometry and dimensions exist.
        """
        frame, strip, pad = 10.0, 22.0, 8.0  # paper mm: border margin, title strip height, clear space
        minx, miny, maxx, maxy = self.extents()
        need_w = (maxx - minx) + self.mm(2 * pad)
        need_h = (maxy - miny) + self.mm(2 * pad)

        def paper(name, portrait):
            w, h = PAPER_MM[name]
            return (h, w) if portrait else (w, h)

        def fits(name, portrait):
            w, h = paper(name, portrait)
            return need_w <= self.mm(w - 2 * frame) and need_h <= self.mm(h - 2 * frame - strip)

        orient = str(orientation).lower()
        if orient not in ("auto", "landscape", "portrait"):
            raise ValueError("orientation must be auto, landscape or portrait")
        turns = {"auto": (False, True), "landscape": (False,), "portrait": (True,)}[orient]
        order = ["A4", "A3", "A2", "A1", "A0"]
        requested = str(size).upper()
        if requested != "AUTO" and requested not in PAPER_MM:
            raise ValueError(f"unknown sheet size {size!r}; use auto or one of {order}")
        wanted = order if requested == "AUTO" else [requested]
        choice = next(((n, t) for n in wanted for t in turns if fits(n, t)), None)
        if choice is None:
            if requested == "AUTO":
                choice = ("A0", turns[0])
                self.warnings.append(
                    f"Drawing does not fit on A0 at 1:{self.scale:g}; use a smaller scale (e.g. 1:{self.scale * 2:g})."
                )
            else:
                choice = (requested, turns[0])
                bigger = next((n for n in order for t in turns if fits(n, t)), None)
                hint = f"it fits on {bigger}" if bigger else "it needs a smaller scale"
                self.warnings.append(f"Drawing overflows {requested} at 1:{self.scale:g}; {hint}.")
        chosen, portrait = choice
        pw, ph = paper(chosen, portrait)
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        x0 = cx - self.mm(pw) / 2
        y0 = cy - self.mm(frame + strip + (ph - 2 * frame - strip) / 2)
        W, H = self.mm(pw), self.mm(ph)
        f, s = self.mm(frame), self.mm(strip)

        self.rect((x0, y0), (W, H), layer="title", color=8)  # paper edge
        inner = self.rect((x0 + f, y0 + f), (W - 2 * f, H - 2 * f), layer="title")
        inner.dxf.const_width = 0
        self.line((x0 + f, y0 + f + s), (x0 + W - f, y0 + f + s), "title")

        cap = CAPTIONS.get(language, CAPTIONS["en"])
        scale_value = scale_text or f"1:{self.scale:g}"
        cells = []  # (caption, value, relative width)
        if office:
            cells.append((cap["office"], office, 2.4))
        if client:
            cells.append((cap["client"], client, 2.4))
        cells += [
            (cap["project"], project, 3.2),
            (cap["title"], title, 3.2),
            (cap["scale"], scale_value, 1.2),
            (cap["date"], date, 1.5),
            (cap["drawn_by"], drawn_by, 1.6),
            (cap["number"], number, 1.3),
        ]
        if north is not None:
            cells.append((None, None, 1.1))  # north arrow cell
        if language == "ar":
            cells.reverse()  # reads right to left

        total = sum(c[2] for c in cells)
        strip_w = W - 2 * f
        x = x0 + f
        base_y = y0 + f
        for i, (caption, value, weight) in enumerate(cells):
            w = strip_w * weight / total
            if i:
                self.line((x, base_y), (x, base_y + s), "title")
            if caption is None:
                self.north_arrow((x + w / 2, base_y + s * 0.42), radius_mm=6.0, angle=float(north), layer="title")
            else:
                self.text(caption, (x + w / 2, base_y + s * 0.78), 1.8, "title", color=8)
                self.text(value, (x + w / 2, base_y + s * 0.36), 3.0, "title")
            x += w

        self.sheet_info = {"size": chosen, "orientation": "portrait" if portrait else "landscape",
                           "scale": f"1:{self.scale:g}", "paper_mm": [pw, ph]}

        if paperspace:
            try:
                name = f"{chosen} 1-{self.scale:g}"
                if "Layout1" in self.doc.layout_names():
                    self.doc.layouts.rename("Layout1", name)
                    layout = self.doc.layout(name)
                else:
                    layout = self.doc.layouts.new(name)
                layout.page_setup(size=(pw, ph), margins=(0, 0, 0, 0), units="mm")
                # 2 mm larger than the paper all round, so the sheet-edge line never sits on
                # the clipping boundary of the viewport. The view scale is unchanged.
                layout.add_viewport(
                    center=(pw / 2, ph / 2), size=(pw + 4, ph + 4),
                    view_center_point=(x0 + W / 2, y0 + H / 2), view_height=H + self.mm(4),
                    dxfattribs={"layer": "Defpoints"},  # Defpoints never plots
                )
                self.sheet_info["layout"] = name
            except Exception as exc:  # the model-space sheet is still complete
                self.warnings.append(f"Paper-space layout skipped: {exc}")
        return self.sheet_info

    # ------------------------------------------------------------------- save
    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        zoom.extents(self.msp)
        auditor = self.doc.audit()
        if auditor.errors:
            self.warnings.append(f"ezdxf audit reported {len(auditor.errors)} unfixed error(s).")
        self.doc.saveas(path)
        return path

#!/usr/bin/env python3
"""Turn a JSON floor-plan spec into a layered, dimensioned DXF.

    python plan_to_dxf.py spec.json out.dxf --preview out.png

Walls are unioned into clean outlines (corners and T-junctions join themselves),
openings are cut out of them, room areas are measured from the enclosed spaces,
and exterior dimension chains are generated. The full spec is documented in
references/plan-spec.md. A JSON summary (rooms, areas, sheet, warnings) is
printed to stdout; read the warnings before trusting the drawing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from dxfkit import Kit  # noqa: E402

MITRE = dict(join_style="mitre", mitre_limit=10.0)


# ------------------------------------------------------------------ vectors
def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def length(a):
    return math.hypot(a[0], a[1])


def unit(a):
    n = length(a)
    return (a[0] / n, a[1] / n) if n else (0.0, 0.0)


def left(d):
    return (-d[1], d[0])


def angle(d):
    return math.degrees(math.atan2(d[1], d[0]))


def pt(p):
    return (float(p[0]), float(p[1]))


class Seg:
    """One straight piece of a wall centreline; openings are hosted on these."""

    def __init__(self, a, b, t, wall_id, index):
        self.a, self.b, self.t = a, b, t
        self.wall_id, self.index = wall_id, index
        self.length = length(sub(b, a))
        self.d = unit(sub(b, a))
        self.n = left(self.d)

    def project(self, p):
        u = max(0.0, min(self.length, dot(sub(p, self.a), self.d)))
        return u, length(sub(p, self.point(u)))

    def point(self, u):
        return add(self.a, mul(self.d, u))


# -------------------------------------------------------------------- walls
def build_walls(spec, units, warn):
    default_t = spec.get("defaults", {}).get("wall_thickness", {"m": 0.2, "cm": 20, "mm": 200}[units])
    walls = []
    for i, w in enumerate(spec.get("walls", [])):
        raw = w.get("points") or [w["from"], w["to"]]
        pts = []
        for p in raw:
            p = pt(p)
            if not pts or length(sub(p, pts[-1])) > 1e-9:
                pts.append(p)
        closed = bool(w.get("closed", False))
        if closed and len(pts) > 2 and length(sub(pts[0], pts[-1])) < 1e-9:
            pts.pop()
        if len(pts) < 2 or (closed and len(pts) < 3):
            warn(f"wall {w.get('id', i + 1)} has too few points and was skipped")
            continue
        walls.append({
            "id": str(w.get("id", f"W{i + 1}")),
            "pts": pts,
            "t": float(w.get("thickness", default_t)),
            "closed": closed,
            "ref": str(w.get("reference", "center")).lower(),
        })

    # Two separate walls ending on the same point leave a notched corner unless each
    # is run on by half the other's thickness. Polyline corners do not need this.
    open_center = [w for w in walls if not w["closed"] and w["ref"] == "center"]

    def outward(w, end):
        p = w["pts"]
        return unit(sub(p[0], p[1])) if end == 0 else unit(sub(p[-1], p[-2]))

    bodies, segs = [], []
    for w in walls:
        pts, t, ref = list(w["pts"]), w["t"], w["ref"]
        if w["closed"]:
            poly = Polygon(pts)
            if not poly.is_valid:
                warn(f"wall {w['id']}: closed outline crosses itself; result may be wrong")
                poly = poly.buffer(0)
            ccw = poly.exterior.is_ccw
            if ref == "left":
                ref = "outer" if ccw else "inner"
            elif ref == "right":
                ref = "inner" if ccw else "outer"
            if ref == "outer":
                body = poly.difference(poly.buffer(-t, **MITRE))
                shift = t / 2 if ccw else -t / 2  # centreline lies inside the outline
            elif ref == "inner":
                body = poly.buffer(t, **MITRE).difference(poly)
                shift = -t / 2 if ccw else t / 2
            else:
                if ref != "center":
                    warn(f"wall {w['id']}: unknown reference {ref!r}, using center")
                body = poly.buffer(t / 2, **MITRE).difference(poly.buffer(-t / 2, **MITRE))
                shift = 0.0
            edges = list(zip(pts, pts[1:] + pts[:1]))
        else:
            if ref in ("outer", "inner"):
                warn(f"wall {w['id']}: reference {ref!r} needs \"closed\": true; using center")
                ref = "center"
            if ref == "center":
                for end in (0, -1):
                    grow = 0.0
                    for o in open_center:
                        if o is w:
                            continue
                        for oend in (0, -1):
                            same = length(sub(w["pts"][end], o["pts"][oend])) < 1e-6
                            if same and abs(cross(outward(w, end), outward(o, oend))) > 1e-3:
                                grow = max(grow, o["t"] / 2)
                    if grow:
                        pts[end] = add(pts[end], mul(outward(w, end), grow))
                body = LineString(pts).buffer(t / 2, cap_style="flat", **MITRE)
                shift = 0.0
            elif ref in ("left", "right"):
                sign = 1 if ref == "left" else -1
                body = LineString(pts).buffer(sign * t, single_sided=True, cap_style="flat", **MITRE)
                shift = sign * t / 2
            else:
                warn(f"wall {w['id']}: unknown reference {ref!r}, using center")
                body = LineString(pts).buffer(t / 2, cap_style="flat", **MITRE)
                shift = 0.0
            edges = list(zip(w["pts"], w["pts"][1:]))
        if body.is_empty:
            warn(f"wall {w['id']} produced no geometry (thickness larger than the outline?)")
            continue
        bodies.append(body)
        for k, (a, b) in enumerate(edges):
            n = left(unit(sub(b, a)))
            segs.append(Seg(add(a, mul(n, shift)), add(b, mul(n, shift)), t, w["id"], k))
    union = unary_union(bodies) if bodies else Polygon()
    return union, segs


def polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def enclosed_rooms(union):
    return [Polygon(ring) for p in polygons(union) for ring in p.interiors]


# ----------------------------------------------------------------- openings
def locate(item, segs, kind, default_w, warn):
    w = float(item.get("width", default_w))
    label = item.get("tag") or item.get("at") or item.get("wall")
    if "at" in item:
        p = pt(item["at"])
        cands = [s for s in segs if s.wall_id == str(item["wall"])] if "wall" in item else segs
        if not cands:
            raise SystemExit(f"error: {kind} {label}: no wall with id {item.get('wall')!r}")
        seg = min(cands, key=lambda s: s.project(p)[1])
        u, off = seg.project(p)
        if off > max(seg.t * 1.5, 1e-6):
            warn(f"{kind} {label}: point is {off:.3g} away from the nearest wall ({seg.wall_id}); check coordinates")
    else:
        if "wall" not in item or "offset" not in item:
            raise SystemExit(f"error: {kind} needs either \"at\": [x, y] or \"wall\" + \"offset\"")
        idx = int(item.get("segment", 0))
        cands = [s for s in segs if s.wall_id == str(item["wall"]) and s.index == idx]
        if not cands:
            raise SystemExit(f"error: {kind}: wall {item['wall']!r} segment {idx} not found")
        seg, u = cands[0], float(item["offset"])
    if u - w / 2 < -1e-9 or u + w / 2 > seg.length + 1e-9:
        warn(f"{kind} {label}: width {w:g} runs past the end of wall {seg.wall_id}; move it or shorten it")
    return {"kind": kind, "seg": seg, "u": u, "c": seg.point(u), "w": w, "item": item}


def cut_shape(o):
    seg, c, hw = o["seg"], o["c"], o["w"] / 2
    hd = seg.t / 2 * 1.04  # a hair past both faces so the cut is always through
    a, b = mul(seg.d, hw), mul(seg.n, hd)
    return Polygon([add(sub(c, a), b), add(add(c, a), b), sub(add(c, a), b), sub(sub(c, a), b)])


def side_of(seg, c, target, default=1):
    if target is None:
        return default
    s = dot(sub(pt(target), c), seg.n)
    return 1 if s >= 0 else -1


def draw_door(kit, o):
    seg, c, w, item = o["seg"], o["c"], o["w"], o["item"]
    kind = str(item.get("type", "single")).lower()
    d, n, t = seg.d, seg.n, seg.t
    s = side_of(seg, c, item.get("swing_to"), 1 if str(item.get("swing", "left")).lower() == "left" else -1)
    if "hinge_near" in item:
        sigma = 1 if dot(sub(pt(item["hinge_near"]), c), d) >= 0 else -1
    else:
        sigma = 1 if str(item.get("hinge", "start")).lower() == "end" else -1
    leaf_t = kit.real_mm(40)

    def leaf(sig, lw):
        hinge = add(add(c, mul(d, sig * w / 2)), mul(n, s * t / 2))
        ldir, jdir = mul(n, s), mul(d, -sig)
        end = add(hinge, mul(ldir, lw))
        kit.polyline([hinge, end, add(end, mul(jdir, leaf_t)), add(hinge, mul(jdir, leaf_t))], "door", closed=True)
        a1, a2 = angle(ldir), angle(jdir)
        if cross(ldir, jdir) > 0:
            kit.arc(hinge, lw, a1, a2, "door")
        else:
            kit.arc(hinge, lw, a2, a1, "door")

    if kind == "single":
        leaf(sigma, w)
    elif kind == "double":
        leaf(-1, w / 2)
        leaf(1, w / 2)
    elif kind == "sliding":
        panel = w / 2 + w * 0.04
        for sig, off in ((-1, leaf_t / 2), (1, -leaf_t / 2)):
            start = add(add(c, mul(d, sig * w / 2)), mul(n, off))
            end = add(start, mul(d, -sig * panel))
            h = mul(n, leaf_t / 2)
            kit.polyline([add(start, h), add(end, h), sub(end, h), sub(start, h)], "door", closed=True)
    elif kind != "opening":
        kit.warnings.append(f"door type {kind!r} is unknown; drew a plain opening")
    if item.get("tag"):
        tag_side = side_of(seg, c, item.get("tag_to"), -s)
        kit.text(item["tag"], add(c, mul(n, tag_side * (t / 2 + kit.mm(3.2)))), 2.0, "door")


def draw_window(kit, o):
    seg, c, w, item = o["seg"], o["c"], o["w"], o["item"]
    a, b = mul(seg.d, w / 2), mul(seg.n, seg.t / 2)
    kit.polyline([add(sub(c, a), b), add(add(c, a), b), sub(add(c, a), b), sub(sub(c, a), b)], "window", closed=True)
    kit.line(sub(c, a), add(c, a), "window")
    if item.get("tag"):
        side = side_of(seg, c, item.get("tag_to"), 1)
        kit.text(item["tag"], add(c, mul(seg.n, side * (seg.t / 2 + kit.mm(3.2)))), 2.0, "window")


# -------------------------------------------------------------------- rooms
def area_m2(area, units):
    return area * {"m": 1.0, "cm": 1e-4, "mm": 1e-6}[units]


def label_rooms(kit, spec, rooms, units, warn):
    lang = spec.get("language", "en")
    show_area = spec.get("room_areas", True)
    show_size = spec.get("room_sizes", True)
    decimals = {"m": 2, "cm": 0, "mm": 0}[units]
    out = []
    owner = {}  # enclosed space -> first room name that claimed it
    for r in spec.get("rooms", []):
        at = pt(r["at"])
        poly = next((p for p in rooms if p.contains(Point(at))), None)
        info = {"name": r.get("name", "")}
        lines = []
        if poly is None:
            warn(f"room {r.get('name', at)!r}: label point is not inside a space fully enclosed by walls; no area")
        else:
            first = owner.setdefault(id(poly), info["name"])
            if first != info["name"]:
                warn(f"rooms {first!r} and {info['name']!r} are in the same enclosed space, so both show its "
                     f"whole area; a wall between them stops short of the wall it should meet")
            a = area_m2(poly.area, units)
            info["area_m2"] = round(a, 2)
            minx, miny, maxx, maxy = poly.bounds
            if abs(poly.area - (maxx - minx) * (maxy - miny)) < 0.01 * poly.area:
                info["size"] = [round(maxx - minx, 3), round(maxy - miny, 3)]
                if r.get("show_size", show_size):
                    lines.append(f"{maxx - minx:.{decimals}f} x {maxy - miny:.{decimals}f}")
            if r.get("show_area", show_area):
                lines.append(f"{a:.2f} م²" if lang == "ar" else f"{a:.2f} m²")
        h = float(r.get("height_mm", 3.0))
        y = at[1] + kit.mm(1.9) * len(lines)  # keep the block centred on the label point
        kit.text(info["name"], (at[0], y), h, "room")
        for line in lines:
            y -= kit.mm(3.8)
            kit.text(line, (at[0], y), 2.0, "room")
        out.append(info)
    return out


# --------------------------------------------------------------- dimensions
def uniq(vals):
    return sorted({round(float(v), 6) for v in vals})


SIDES = ("bottom", "top", "left", "right")
TIERS = ("openings", "rooms", "overall", "grid")


def auto_dimensions(kit, union, openings, rooms, grids, sides=SIDES, tiers=TIERS):
    """Exterior chains per side, nearest first: openings, room/wall breaks, overall, grid.

    The first chain sits 10 paper mm outside the building and each further tier 8 mm beyond.
    Returns {side: [{"tier": name, "segments": [lengths]}]} so the caller can report what was drawn.
    """
    minx, miny, maxx, maxy = union.bounds
    first, step = kit.mm(10), kit.mm(8)
    layout = {
        "bottom": ("x", minx, maxx, miny, -1),
        "top": ("x", minx, maxx, maxy, 1),
        "left": ("y", miny, maxy, minx, -1),
        "right": ("y", miny, maxy, maxx, 1),
    }
    report = {}
    for name in sides:
        axis, lo, hi, edge, sign = layout[name]
        ax = 0 if axis == "x" else 1
        pz = 1 - ax
        chains = []  # (tier name, coordinates)

        if "openings" in tiers:
            vals = []
            for o in openings:
                seg = o["seg"]
                if abs(seg.d[pz]) > 1e-6:
                    continue  # wall is not parallel to this side
                face = o["c"][pz] + sign * seg.t / 2
                if abs(face - edge) <= max(seg.t * 0.05, 1e-6):
                    vals += [o["c"][ax] - o["w"] / 2, o["c"][ax] + o["w"] / 2]
            if vals:
                chains.append(("openings", uniq(vals + [lo, hi])))

        if "rooms" in tiers:
            vals = []
            for r in rooms:
                b = r.bounds
                r_lo, r_hi = b[ax], b[ax + 2]
                near = b[pz + 2] if sign > 0 else b[pz]  # the room's face toward this side
                # Sweep the whole width of the room out to the building edge. If any other room
                # lies in that strip, this room is not in the row along this side. (A single ray
                # is not enough: it can slip through the wall between two rooms in front.)
                inset = (r_hi - r_lo) * 0.02
                p0, p1 = sorted((near, edge))
                if ax == 0:
                    strip = box(r_lo + inset, p0, r_hi - inset, p1)
                else:
                    strip = box(p0, r_lo + inset, p1, r_hi - inset)
                limit = 1e-6 * max(strip.area, 1e-12)
                if any(other is not r and other.intersection(strip).area > limit for other in rooms):
                    continue
                vals += [r_lo, r_hi]
            chain = uniq(vals + [lo, hi])
            if len(chain) > 2 and all(chain != c for _, c in chains):
                chains.append(("rooms", chain))

        if "overall" in tiers:
            chains.append(("overall", uniq([lo, hi])))

        grid_vals = (grids or {}).get(axis) or []
        if "grid" in tiers and len(grid_vals) > 1 and name in ("top", "left"):
            chains.append(("grid", uniq(grid_vals)))

        for i, (_, chain) in enumerate(chains):
            kit.dim_chain(chain, axis, edge + sign * (first + i * step), origin=edge)
        report[name] = [
            {"tier": tier, "segments": [round(b - a, 4) for a, b in zip(chain, chain[1:])]}
            for tier, chain in chains
        ]
    return report


def sheet_hint(kit, union, content, scale):
    """If the sheet came out large, say which scale would bring the plan down to A3.

    Annotation keeps its paper size at any scale; only the building shrinks.
    """
    unit = kit.mm(1.0)
    bw = (union.bounds[2] - union.bounds[0]) / unit  # building size in paper mm now
    bh = (union.bounds[3] - union.bounds[1]) / unit
    margin_w = (content[2] - content[0]) / unit - bw
    margin_h = (content[3] - content[1]) / unit - bh
    for s in (50, 75, 100, 125, 150, 200, 250, 500):
        if s <= scale:
            continue
        w = bw * scale / s + margin_w + 16
        h = bh * scale / s + margin_h + 16
        if any(w <= pw - 20 and h <= ph - 42 for pw, ph in ((420, 297), (297, 420))):
            return f"at 1:{s} this plan fits on A3"
    return None


def extra_dimensions(kit, items, union, warn):
    for d in items:
        if "offset_mm" in d:
            offset = kit.mm(float(d["offset_mm"]))  # paper millimetres, like the automatic tiers
        else:
            offset = float(d.get("offset", kit.mm(8)))
        if "section" in d:
            a, b = pt(d["section"][0]), pt(d["section"][1])
            hit = LineString([a, b]).intersection(union)
            direction = unit(sub(b, a))
            us = set()
            for g in getattr(hit, "geoms", [hit]):
                if g.geom_type == "LineString":
                    for p in g.coords:
                        us.add(round(dot(sub(p, a), direction), 6))
            us = sorted(us)
            if len(us) < 2:
                warn(f"dimension section {d['section']} does not cross any wall")
                continue
            points = [add(a, mul(direction, u)) for u in us]
        elif "chain" in d:
            points = [pt(p) for p in d["chain"]]
        elif "from" in d and "to" in d:
            points = [pt(d["from"]), pt(d["to"])]
        else:
            warn(f"dimension entry not understood: {d}")
            continue
        for p1, p2 in zip(points, points[1:]):
            if length(sub(p2, p1)) > 1e-9:
                kit.dim_aligned(p1, p2, offset, text=d.get("text", "<>"), fixed_ext=bool(d.get("fixed_ext", False)))


# ------------------------------------------------------- stairs and fixtures
class Frame:
    """Local coordinate frame: origin `at`, rotated by `rotation` degrees."""

    def __init__(self, at, rotation=0.0):
        self.o = pt(at)
        r = math.radians(rotation)
        self.c, self.s = math.cos(r), math.sin(r)

    def p(self, x, y):
        return (self.o[0] + x * self.c - y * self.s, self.o[1] + x * self.s + y * self.c)

    def rect(self, x0, y0, x1, y1):
        return [self.p(x0, y0), self.p(x1, y0), self.p(x1, y1), self.p(x0, y1)]

    def ellipse(self, cx, cy, rx, ry, n=32):
        return [self.p(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def draw_stair(kit, s):
    f = Frame(s["at"], float(s.get("direction", 0)))
    run, width, steps = float(s["length"]), float(s["width"]), int(s.get("steps", 10))
    kit.polyline(f.rect(0, 0, run, width), "stair", closed=True)
    for i in range(1, steps):
        x = run * i / steps
        kit.line(f.p(x, 0), f.p(x, width), "stair")
    y, a = width / 2, kit.mm(2.0)
    kit.circle(f.p(run * 0.5 / steps, y), kit.mm(0.6), "stair")
    kit.line(f.p(run * 0.5 / steps, y), f.p(run - run * 0.5 / steps, y), "stair")
    tip = (run - run * 0.5 / steps, y)
    kit.line(f.p(*tip), f.p(tip[0] - a, tip[1] + a * 0.45), "stair")
    kit.line(f.p(*tip), f.p(tip[0] - a, tip[1] - a * 0.45), "stair")
    if s.get("label", "UP"):
        kit.text(s.get("label", "UP"), f.p(-kit.mm(4), y), 2.0, "stair")


def draw_fixture(kit, fx, warn):
    kind = str(fx.get("type", "rect")).lower()
    layer = fx.get("layer", "fixture" if kind in ("wc", "basin", "bathtub", "shower", "sink") else "furniture")
    size = fx.get("size", [1, 1])
    w, h = (float(size), float(size)) if isinstance(size, (int, float)) else (float(size[0]), float(size[1]))
    f = Frame(fx["at"], float(fx.get("rotation", 0)))  # `at` is the centre; local +y is the back
    x, y = w / 2, h / 2

    def poly(points, closed=True):
        kit.polyline(points, layer, closed=closed)

    if kind == "bed":
        poly(f.rect(-x, -y, x, y))
        n = 2 if w > 1.2 * kit.real_mm(1000) else 1
        pw = w / n
        for i in range(n):
            px = -x + pw * i
            poly(f.rect(px + pw * 0.12, y - h * 0.24, px + pw * 0.88, y - h * 0.06))
        kit.line(f.p(-x, y - h * 0.32), f.p(x, y - h * 0.32), layer)
    elif kind == "sofa":
        poly(f.rect(-x, -y, x, y))
        kit.line(f.p(-x, y - h * 0.25), f.p(x, y - h * 0.25), layer)
        arm = min(w * 0.12, h * 0.3)
        kit.line(f.p(-x + arm, -y), f.p(-x + arm, y - h * 0.25), layer)
        kit.line(f.p(x - arm, -y), f.p(x - arm, y - h * 0.25), layer)
    elif kind == "table":
        if isinstance(size, (int, float)):
            kit.circle(f.p(0, 0), w / 2, layer)
        else:
            poly(f.rect(-x, -y, x, y))
    elif kind == "wc":
        poly(f.rect(-x, y - h * 0.28, x, y))
        poly(f.ellipse(0, -h * 0.14, w * 0.42, h * 0.36))
    elif kind in ("basin", "sink"):
        poly(f.rect(-x, -y, x, y))
        poly(f.ellipse(0, 0, w * 0.34, h * 0.3))
    elif kind == "bathtub":
        poly(f.rect(-x, -y, x, y))
        m = min(w, h) * 0.12
        poly(f.rect(-x + m, -y + m, x - m, y - m))
        kit.circle(f.p(x - 2.2 * m, 0), m * 0.35, layer)
    elif kind == "shower":
        poly(f.rect(-x, -y, x, y))
        kit.line(f.p(-x, -y), f.p(x, y), layer)
        kit.line(f.p(-x, y), f.p(x, -y), layer)
        kit.circle(f.p(0, 0), min(w, h) * 0.06, layer)
    else:
        if kind not in ("rect", "counter", "wardrobe", "kitchen"):
            warn(f"fixture type {kind!r} is unknown; drew a rectangle")
        poly(f.rect(-x, -y, x, y))
        if kind == "wardrobe":
            kit.line(f.p(-x, -y), f.p(x, y), layer)
    if fx.get("label"):
        kit.text(fx["label"], f.p(0, 0), float(fx.get("height_mm", 1.8)), layer, rotation=float(fx.get("text_rotation", 0)))


def draw_extras(kit, items, warn):
    for e in items:
        kind, layer = str(e.get("type", "")).lower(), e.get("layer", "0")
        lt = e.get("linetype")
        if kind == "line":
            kit.line(e["from"], e["to"], layer, linetype=lt)
        elif kind == "polyline":
            kit.polyline(e["points"], layer, closed=bool(e.get("closed", False)), linetype=lt)
        elif kind == "rect":
            kit.rect(e["at"], e["size"], layer, rotation=float(e.get("rotation", 0)), anchor=e.get("anchor", "corner"), linetype=lt)
        elif kind == "circle":
            kit.circle(e["center"], e["radius"], layer, linetype=lt)
        elif kind == "arc":
            kit.arc(e["center"], e["radius"], e["start"], e["end"], layer, linetype=lt)
        elif kind == "text":
            kit.text(e["text"], e["at"], float(e.get("height_mm", 2.5)), e.get("layer", "text"),
                     align=e.get("align", "MIDDLE_CENTER"), rotation=float(e.get("rotation", 0)))
        elif kind == "hatch":
            kit.hatch(e["points"], e.get("holes", []), e.get("layer", "hatch"), pattern=e.get("pattern", "SOLID"),
                      scale=float(e.get("scale", 1)), angle=float(e.get("angle", 0)))
            if e.get("outline", True):
                kit.polyline(e["points"], e.get("layer", "hatch"), closed=True)
        elif kind == "leader":
            kit.leader(e["tip"], e["at"], e["text"], float(e.get("height_mm", 2.2)), e.get("layer", "text"))
        else:
            warn(f"extras entry with unknown type {kind!r} was skipped")


# --------------------------------------------------------------------- main
def build(spec: dict, out_path, preview=None) -> dict:
    units = spec.get("units", "m")
    scale = float(spec.get("scale", 100))
    kit = Kit(units=units, scale=scale, layers=spec.get("layers"), font=spec.get("font", "arial.ttf"),
              dim_decimals=spec.get("dim_decimals"), dim_factor=float(spec.get("dim_factor", 1.0)))
    warn = kit.warnings.append
    defaults = spec.get("defaults", {})
    per_m = {"m": 1.0, "cm": 100.0, "mm": 1000.0}[units]

    union, segs = build_walls(spec, units, warn)
    rooms = enclosed_rooms(union)

    openings = []
    for kind, key, default_w in (("door", "doors", 0.9), ("window", "windows", 1.2), ("opening", "openings", 1.0)):
        for item in spec.get(key, []):
            if not segs:
                raise SystemExit("error: openings need walls to sit in")
            openings.append(locate(item, segs, kind, defaults.get(f"{kind}_width", default_w * per_m), warn))
    if openings:
        union_cut = union.difference(unary_union([cut_shape(o) for o in openings]))
    else:
        union_cut = union

    fill = str(spec.get("wall_fill", "solid")).lower()
    for poly in polygons(union_cut):
        ext = list(poly.exterior.coords)[:-1]
        holes = [list(r.coords)[:-1] for r in poly.interiors]
        if fill == "solid":
            kit.hatch(ext, holes, layer="wall_fill")
        elif fill not in ("none", "false", ""):
            kit.hatch(ext, holes, layer="wall_fill", pattern=fill, color=8, scale=float(spec.get("wall_fill_scale", 0.5)))
        kit.polyline(ext, "wall", closed=True)
        for hole in holes:
            kit.polyline(hole, "wall", closed=True)

    for o in openings:
        if o["kind"] == "door":
            draw_door(kit, o)
        elif o["kind"] == "window":
            draw_window(kit, o)

    for c in spec.get("columns", []):
        kit.column(c["at"], c.get("size", defaults.get("column_size", [0.3 * per_m, 0.3 * per_m])), float(c.get("rotation", 0)))
        if c.get("tag"):
            kit.text(c["tag"], (c["at"][0] + kit.mm(4), c["at"][1] + kit.mm(4)), 2.0, "column")
    for s in spec.get("stairs", []):
        draw_stair(kit, s)
    for fx in spec.get("fixtures", []):
        draw_fixture(kit, fx, warn)
    draw_extras(kit, spec.get("extras", []), warn)
    room_info = label_rooms(kit, spec, rooms, units, warn)

    dims = spec.get("dimensions", {"auto": True})
    if dims is True or dims is False:
        dims = {"auto": dims}
    grids = spec.get("grids")
    auto = dims.get("auto", True)
    if auto is True:
        sides = SIDES
    elif isinstance(auto, (list, tuple)):
        sides = tuple(x for x in SIDES if x in auto)
        for x in auto:
            if x not in SIDES:
                warn(f"dimensions.auto: unknown side {x!r}; use {list(SIDES)}")
    else:
        sides = ()
    tiers = tuple(dims.get("tiers", TIERS))
    for x in tiers:
        if x not in TIERS:
            warn(f"dimensions.tiers: unknown tier {x!r}; use {list(TIERS)}")
    chains = {}
    if sides and not union.is_empty:
        chains = auto_dimensions(kit, union, openings, rooms, grids, sides, tiers)
    extra_dimensions(kit, dims.get("extra", []), union, warn)

    if grids and (grids.get("x") or grids.get("y")):
        bounds = union.bounds if not union.is_empty else None
        deepest = max(len(chains.get("top", [])), len(chains.get("left", [])))
        overhang = 10 + 8 * deepest + 3 if deepest else 15
        kit.grid(grids.get("x", []), grids.get("y", []), grids.get("x_labels"), grids.get("y_labels"),
                 bounds=bounds, overhang_mm=overhang)

    content = kit.extents()  # everything drawn so far, before the sheet frame is added
    sheet = spec.get("sheet", {})
    if sheet is not False:
        sheet = dict(sheet or {})
        sheet.setdefault("language", spec.get("language", "en"))
        kit.sheet(**sheet)

    out = kit.save(out_path)
    pad = kit.mm(4)
    window = [round(content[0] - pad, 3), round(content[1] - pad, 3), round(content[2] + pad, 3), round(content[3] + pad, 3)]
    big_sheet = bool(kit.sheet_info) and kit.sheet_info["size"] in ("A2", "A1", "A0")
    summary = {
        "output": str(out),
        "units": units,
        "scale": f"1:{scale:g}",
        "sheet": kit.sheet_info,
        "overall_size": [round(union.bounds[2] - union.bounds[0], 3), round(union.bounds[3] - union.bounds[1], 3)] if not union.is_empty else None,
        "enclosed_spaces": len(rooms),
        "rooms": room_info,
        "total_room_area_m2": round(sum(r.get("area_m2", 0) for r in room_info), 2),
        "openings": {k: sum(1 for o in openings if o["kind"] == k) for k in ("door", "window", "opening")},
        "auto_dimensions": chains,
        "plan_window": window,
        "warnings": kit.warnings,
    }
    if big_sheet and not union.is_empty:
        hint = sheet_hint(kit, union, content, scale)
        if hint:
            summary["sheet_hint"] = hint
    if preview:
        from dxf_preview import render

        preview = Path(preview)
        summary["preview"] = str(render(out, preview))
        if big_sheet:  # on a large sheet the plan is too small to check, so add a close-up
            close = preview.with_name(preview.stem + "-plan" + preview.suffix)
            summary["preview_plan"] = str(render(out, close, window=window))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="JSON plan spec (see references/plan-spec.md)")
    ap.add_argument("out", help="output .dxf path")
    ap.add_argument("--preview", help="also render a .png or .pdf to look at")
    args = ap.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    summary = build(spec, args.out, args.preview)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

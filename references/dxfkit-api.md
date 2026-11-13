# dxfkit API, layers, hatches and editing recipes

`scripts/dxfkit.py` wraps ezdxf with the conventions a drawing needs. `kit.doc` and `kit.msp` are
the plain ezdxf document and model space, so anything ezdxf can do is still available.

## Contents

- [Creating a drawing](#creating-a-drawing)
- [Geometry](#geometry)
- [Text and notes](#text-and-notes)
- [Dimensions](#dimensions)
- [Hatches](#hatches)
- [Structural helpers and symbols](#structural-helpers-and-symbols)
- [Sheet and saving](#sheet-and-saving)
- [Layer keys](#layer-keys)
- [Recipes for common drawing types](#recipes-for-common-drawing-types)
- [Editing an existing DXF](#editing-an-existing-dxf)

## Creating a drawing

```python
import sys; sys.path.insert(0, r"<skill>/scripts")   # absolute path of the skill's scripts folder
from dxfkit import Kit

kit = Kit(units="m", scale=100)                 # units: "m" | "cm" | "mm"; scale 100 means 1:100
kit = Kit(units="mm", scale=20, dim_decimals=0) # a detail in millimetres
kit = Kit(units="m", scale=100, dim_factor=100, dim_decimals=0)  # drawn in m, dimensioned in cm
kit = Kit(units="m", scale=100, layers={"wall": "جدران"})        # rename a layer key
kit = Kit.open("existing.dxf", scale=100)       # add to someone's drawing; units read from the file
```

Two conversions carry the whole scale logic:

- `kit.mm(x)`: **paper** millimetres to drawing units. Use for every annotation size and every
  offset of a dimension line, bubble or note. `kit.mm(10)` is 10 mm on the printed sheet.
- `kit.real_mm(x)`: **real-world** millimetres to drawing units (a 40 mm door leaf, a 16 mm bar).

## Geometry

Every method takes a `layer` (a key from the table below or any literal name, created on first use)
and optional `linetype` (`"DASHED"`, `"CENTER"`, `"HIDDEN"`, `"PHANTOM"`, `"Continuous"`) and `color` (ACI).

| Call | Draws |
|---|---|
| `kit.line(p1, p2, layer)` | A line. |
| `kit.polyline(points, layer, closed=False)` | A lightweight polyline. |
| `kit.rect(at, size, layer, rotation=0, anchor="corner")` | Rectangle from its lower-left corner, or its centre with `anchor="center"`. |
| `kit.rect_points(at, size, rotation, anchor)` | The four corner points, for hatching the same rectangle. |
| `kit.circle(center, radius, layer)` | A circle. |
| `kit.arc(center, radius, start_deg, end_deg, layer)` | Counter-clockwise arc. |
| `kit.break_line(p1, p2, layer="section")` | Line with a zig-zag at its middle, for where a slab, wall or beam continues beyond the detail. |

## Text and notes

| Call | Notes |
|---|---|
| `kit.text(content, at, height_mm=2.5, layer="text", align="MIDDLE_CENTER", rotation=0)` | Single line. `align` is any ezdxf name: `LEFT`, `MIDDLE_LEFT`, `MIDDLE_RIGHT`, `TOP_CENTER`, `BOTTOM_LEFT`, … |
| `kit.mtext(content, at, height_mm=2.5, width=None, attachment="TOP_LEFT")` | Paragraph notes. `\\P` breaks a line; `width` (drawing units) wraps. |
| `kit.leader(tip, text_at, content, height_mm=2.2)` | Note with an arrowed pointer, drawn as plain lines and text. The arrow is at `tip`; the text starts at `text_at` when that is right of the tip and ends there when it is left of it, so it always runs away from the arrow. |

Usual paper heights: 1.8 to 2.0 for tags and captions, 2.5 for notes, 3 to 3.5 for room names,
4 to 5 for drawing titles. Arabic needs no special handling; AutoCAD shapes it from the TrueType font.

Text takes about 0.8 x its height per character, so a 30-character note at 2.2 mm is roughly 53 mm
long on paper (`kit.mm(53)` in drawing units). Use that to keep notes clear of dimension lines
before rendering, then confirm in the preview.

## Dimensions

| Call | Notes |
|---|---|
| `kit.dim_h(p1, p2, y)` | Horizontal distance, dimension line at height `y`. |
| `kit.dim_v(p1, p2, x)` | Vertical distance, dimension line at position `x`. |
| `kit.dim_aligned(p1, p2, offset)` | Parallel to p1→p2, `offset` to the left of that direction (negative: right). Point order only picks the side; the number always reads the right way up. |
| `kit.dim_chain(values, axis, at, origin=0)` | A row of dimensions through a list of coordinates (see below). |

```python
# Chain along the bottom of a plan whose outer face is at y = 0: breaks at x = 0, 0.2, 4.2, 4.4
kit.dim_chain([0, 0.2, 4.2, 4.4], axis="x", at=-kit.mm(10), origin=0)
# Chain up the left side of a plan whose outer face is at x = 0: breaks at y = 0, 3, 6
kit.dim_chain([0, 3, 6], axis="y", at=-kit.mm(10), origin=0)
```

`values` are the positions being dimensioned, `at` is where the dimension line runs (a y for
`axis="x"`, an x for `axis="y"`), and `origin` is the face being measured (the other coordinate of
the measured points), which decides which way the short extension lines point.

- Place dimension lines with paper offsets: `y = face_y - kit.mm(10)`, the next tier `kit.mm(8)`
  further out.
- Pass `text="R 0.50"` or `text="<> TYP."` to override or decorate the measured value (`<>` is the
  measurement).
- A number wider than its own segment (a 0.20 wall at 1:100) is moved automatically to the outer side
  of the dimension line.
- `dim_h`, `dim_v` and `dim_aligned` accept `fixed_ext=True` for short fixed-length extension
  lines; `dim_chain` uses them by default so exterior chains do not strike through the drawing.
  Use them whenever dimension lines are stacked in tiers.
- `dim_chain` always shows the measured values; for a custom text use `dim_h` / `dim_v` with `text=`.

## Hatches

```python
kit.hatch(exterior_points, holes=[hole_points, ...], layer="hatch", pattern="ANSI31", scale=1.0, angle=0)
```

`pattern="SOLID"` (default) fills. `scale=1` is tuned to a sensible density at any plot scale for
the patterns in the table; raise it to open a pattern up, lower it to tighten, and judge the result
in the preview (a thin strip wants a tighter pattern than a large area). A hatch has no outline, so
draw the boundary too, including the cut-off edges of fill and ground.

| Material | Pattern |
|---|---|
| Cut masonry / generic section | `ANSI31` (45° lines), `ANSI37` (cross-hatch) |
| Reinforced concrete | `AR-CONC` |
| Plain concrete, sand, plaster, screed | `AR-SAND` |
| Earth, backfill | `EARTH` |
| Gravel, hardcore | `GRAVEL` |
| Steel | `STEEL` or `ANSI32` |
| Insulation | `INSUL` |
| Brick and block in elevation (true size) | `AR-B816`, `AR-BRSTD`, `BRICK` |
| Tiles and paving (true size) | `AR-HBONE`, `AR-PARQ1`, `NET`, `SQUARE` |
| Grass, planting | `GRASS`, `SWAMP` |

## Structural helpers and symbols

| Call | Notes |
|---|---|
| `kit.column(at, size=(0.3, 0.6), rotation=0)` | Filled column centred on `at`; a single number is a round column's diameter. |
| `kit.grid(xs, ys, x_labels=None, y_labels=None, bounds=None, overhang_mm=15)` | Centre lines with bubbles at the top and left. `bounds=(minx, miny, maxx, maxy)` is what the lines must span. Raise `overhang_mm` to leave room for dimension tiers between the building and the bubbles. |
| `kit.north_arrow(center, radius_mm=6, angle=90)` | `angle` is the direction of north. |

## Sheet and saving

```python
info = kit.sheet(title="…", project="…", number="A-101")   # call after all geometry exists
kit.save("out.dxf")           # audits, zooms to extents, writes the file
print(info, kit.warnings)     # e.g. the drawing overflows the chosen sheet
```

`sheet()` frames whatever is already drawn, adds the title strip, and builds a paper-space layout
(named like `A3 1-100`, returned in `info["layout"]`) with a viewport at exactly the plot scale.

| Argument | Default | Meaning |
|---|---|---|
| `size` | `"auto"` | Smallest of A4 to A0 that fits, or a named size. |
| `orientation` | `"auto"` | Landscape unless portrait saves a sheet size; or `"landscape"` / `"portrait"`. |
| `title`, `project`, `number`, `drawn_by`, `date` | `""` | Title-strip cells; empty ones stay blank. |
| `client`, `office` | `""` | Extra cells, added only when given. |
| `language` | `"en"` | `"ar"` for Arabic captions, laid out right to left. |
| `north` | `None` | Direction of north in degrees (90 = up). `None` draws no north arrow. |
| `paperspace` | `True` | Build the paper layout. |

Printing Arabic from a script is safe: importing `dxfkit` switches stdout to UTF-8.

## Layer keys

Names follow the AIA / US National CAD Standard pattern. Any other string is used as a literal
layer name.

| Key | Layer | Use |
|---|---|---|
| `wall` | A-WALL | Wall outlines (0.50 mm) |
| `wall_fill` | A-WALL-PATT | Wall poché |
| `door` | A-DOOR | Doors and swings |
| `window` | A-GLAZ | Windows |
| `stair` | A-FLOR-STRS | Stairs |
| `furniture` | A-FURN | Furniture |
| `fixture` | A-FLOR-FIXT | Sanitary fixtures |
| `column` | S-COLS | Columns |
| `beam` | S-BEAM | Beams (dashed) |
| `footing` | S-FNDN | Foundations in plan |
| `slab` | S-SLAB | Slab edges and openings in plan |
| `section` | A-SECT | Anything cut in a section or detail: concrete, masonry, blinding (0.50 mm) |
| `ground` | C-TOPO | Ground line and levels in sections and elevations |
| `rebar` | S-RBAR | Reinforcement |
| `grid` | S-GRID | Grid lines (centre linetype) |
| `site` | C-PROP | Property and site lines (phantom) |
| `hidden` | A-DETL-HIDN | Hidden / above lines (dashed) |
| `hatch` | A-ANNO-PATT | Material hatches |
| `dim` | A-ANNO-DIMS | Dimensions |
| `text` | A-ANNO-TEXT | Notes |
| `room` | A-AREA-IDEN | Room names and areas |
| `symbol` | A-ANNO-SYMB | Section marks, north arrow, levels |
| `title` | A-ANNO-TTLB | Border and title block |

## Recipes for common drawing types

**Section or detail** (footing, slab edge, stair section): see `assets/example_footing_section.py`.
Draw everything that is cut as closed polylines on `section` with a material hatch (`AR-CONC`,
`AR-SAND`, `EARTH`), the ground line on `ground`, bars as polylines and small circles on `rebar`,
`kit.break_line` where an element continues, dimensions outside, leaders for notes. Use 1:20 or 1:25.
When copying the example to another folder, keep its lookup of the scripts folder or replace it
with the absolute path.

**Structural layout (columns and footings plan)**

```python
kit = Kit(units="m", scale=100)
xs, ys = [0, 5, 10], [0, 4, 8]
for x in xs:
    for y in ys:
        kit.rect((x, y), (1.6, 1.6), "footing", anchor="center")   # footing outline
        kit.column((x, y), (0.3, 0.6))
        kit.text("F1", (x + 1.0, y - 1.0), 2.0, "footing")
kit.grid(xs, ys, bounds=(-0.8, -0.8, 10.8, 8.8), overhang_mm=28)
kit.dim_chain(xs, "x", at=8.8 + kit.mm(12), origin=8.8)
kit.dim_chain(ys, "y", at=-0.8 - kit.mm(12), origin=-0.8)
kit.sheet(title="Foundation layout", number="S-101"); kit.save("foundations.dxf")
```

**Site plan**: plot boundary as a closed polyline on `site`, setback lines with `linetype="DASHED"`,
the building footprint on `wall` with a light `ANSI31` hatch, `dim_aligned` for boundary lengths and
setbacks, `north=` in `sheet()`. Use 1:200 or 1:500.

**Elevation**: ground line first, then the wall outline, openings as rectangles on `window` / `door`,
levels as short lines with `kit.text("+3.20", …)`, material hatches such as `AR-B816`. Heights must
come from the user; do not invent them.

**Schedule or table** (door schedule, column schedule): rows of `kit.rect` cells with `kit.text`
centred in each; keep row height at `kit.mm(7)` and text at 2.5.

## Editing an existing DXF

Inspect first (`scripts/dxf_inspect.py`), then work on the ezdxf document. Always `saveas` a new file.

```python
import ezdxf
from ezdxf.math import Matrix44, area

doc = ezdxf.readfile("in.dxf")
msp = doc.modelspace()

# find entities: by type, by layer, or both
walls = msp.query('LWPOLYLINE[layer=="A-WALL"]')
loose = msp.query('*[layer=="A-FURN" | layer=="A-FLOR-FIXT"]')

# change text
for t in msp.query("TEXT"):
    if t.dxf.text == "Bedroom":
        t.dxf.text = "غرفة نوم"
for m in msp.query("MTEXT"):
    m.text = m.text.replace("REV A", "REV B")

# move, rotate or scale a set of entities
for e in msp.query('*[layer=="A-FURN"]'):
    e.transform(Matrix44.translate(0.5, 0, 0))          # also Matrix44.z_rotate(radians), Matrix44.scale(k)

# layers: rename, recolour, switch off
doc.layers.get("0-OLD").rename("A-WALL")
doc.layers.get("A-GLAZ").color = 5
doc.layers.get("A-FURN").off()

# delete (copy the query to a list first)
for e in list(msp.query('*[layer=="TEMP"]')):
    msp.delete_entity(e)

# measure a closed polyline
pl = msp.query('LWPOLYLINE[layer=="A-AREA"]')[0]
print(abs(area([(x, y) for x, y, *_ in pl.get_points()])))

doc.saveas("out.dxf")
```

To add new, properly styled content to the file, wrap it instead of starting from ezdxf directly:

```python
kit = Kit.open("in.dxf", scale=100)        # units come from the file
kit.dim_h((0.25, 2), (4.9, 2), y=1.2)
kit.text("ملاحظة: …", (6, -4.5), 3.0)
kit.save("out.dxf")
```

Match what is already there: draw on the file's existing layers by passing their literal names, and
check an existing text's height (`t.dxf.height`) before choosing yours. If the file does not declare
units, work them out from a known dimension (a 0.9 door measuring 900 means millimetres) and pass
`units=` explicitly.

Files that fail to open normally are retried by `dxf_inspect.py` with ezdxf's recovery loader; use
`ezdxf.recover.readfile(path)` the same way in your own script.

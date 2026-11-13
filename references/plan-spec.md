# Floor-plan spec for `plan_to_dxf.py`

A JSON object. All coordinates and sizes are in the drawing `units`; only text heights
(`height_mm`) are paper millimetres. Every key except `walls` is optional.

## Contents

- [Top level](#top-level)
- [walls](#walls)
- [doors, windows, openings](#doors-windows-openings)
- [rooms](#rooms)
- [columns, grids, stairs](#columns-grids-stairs)
- [fixtures](#fixtures)
- [dimensions](#dimensions)
- [extras](#extras)
- [sheet](#sheet)
- [Output summary and warnings](#output-summary-and-warnings)

## Top level

| Key | Default | Meaning |
|---|---|---|
| `units` | `"m"` | `"m"`, `"cm"` or `"mm"`. Sets both the input unit and the DXF unit. |
| `scale` | `100` | Plot scale denominator (100 means 1:100). Sizes all annotation. |
| `language` | `"en"` | `"ar"` gives Arabic title-block captions (right to left) and `م²`. |
| `wall_fill` | `"solid"` | `"solid"` (grey poché), a hatch name such as `"ANSI31"`, or `"none"`. |
| `wall_fill_scale` | `0.5` | Density multiplier when `wall_fill` is a hatch pattern. |
| `defaults` | | `wall_thickness`, `door_width`, `window_width`, `opening_width`, `column_size`. |
| `room_areas` / `room_sizes` | `true` | Print area and clear size under each room name. |
| `dim_decimals` | 2 for m, 0 otherwise | Decimals on dimension text. |
| `dim_factor` | `1` | Multiplier on dimension text. Draw in m but dimension in cm: `"dim_factor": 100, "dim_decimals": 0`. |
| `layers` | AIA names | Rename layers: `{"wall": "جدران", "door": "ابواب"}`. Keys are listed in `dxfkit-api.md`. |
| `font` | `"arial.ttf"` | TrueType font for all text. Keep one that has Arabic glyphs if labels are Arabic. |

## walls

```json
{"id": "ext", "points": [[0,0],[12,0],[12,9],[0,9]], "closed": true, "thickness": 0.25, "reference": "outer"}
{"id": "p1", "points": [[5,0.125],[5,8.875]], "thickness": 0.15}
{"id": "p2", "from": [5,5], "to": [12,5]}
```

- `points` is a polyline; `from`/`to` is shorthand for a single segment. Corners inside one polyline
  are mitred cleanly, so draw a run of connected walls as one polyline.
- `reference` says what the points describe:
  - `"center"` (default): the wall centreline.
  - `"outer"` / `"inner"` (closed outlines only): the outside face (overall building size) or the
    inside face (clear internal size). Winding direction does not matter.
  - `"left"` / `"right"`: the wall body lies entirely to the left / right of the path, walking from
    the first point to the last. Useful for a boundary wall drawn along a property line.
- All walls are merged into one outline, so T-junctions and crossings clean themselves **as long as
  the walls overlap**. End a partition anywhere inside the body of the wall it meets. Two separate
  centre-referenced walls that end on the same point are extended to close the corner.
- A space counts as a room only if walls enclose it completely (doors and windows do not break the
  enclosure; they are cut afterwards).

## doors, windows, openings

Three lists with the same placement rules. `openings` are plain gaps with no leaf (arches, pass-throughs).

```json
{"at": [5, 2.5], "width": 0.9, "swing_to": [4, 2.5], "hinge_near": [5, 3.5], "tag": "D2"}
{"at": [2.5, 0.125], "width": 2.0, "tag": "W1", "tag_to": [2.5, -1]}
{"wall": "p1", "segment": 0, "offset": 3.0, "width": 0.9}
```

| Key | Meaning |
|---|---|
| `at` | Centre of the opening. Snaps to the nearest wall centreline; add `"wall": "<id>"` to force a wall. |
| `wall` + `offset` (+ `segment`) | Alternative to `at`: distance along that wall segment from its start point to the opening centre. |
| `width` | Clear width. Falls back to `defaults`. |
| `type` (doors) | `"single"` (default), `"double"`, `"sliding"`, `"opening"`. |
| `swing_to` (doors) | Any point on the side of the wall the door opens into, e.g. the room centre. |
| `hinge_near` (doors) | Any point closer to the hinge jamb than to the other jamb. |
| `swing` / `hinge` (doors) | Fallbacks if the two above are absent: `"left"`/`"right"` of the wall direction, and `"start"`/`"end"` of the segment. |
| `tag` | Short mark such as `D1`, `W2`. |
| `tag_to` | Point on the side where the tag should sit. Doors default to the side opposite the swing. |

For a wall referenced `"outer"`, the centreline is half a thickness inside the outline: an opening in
the bottom wall of a 0.25 thick outline starting at y=0 is at y=0.125. Snapping forgives small errors,
and a warning is printed if the point is more than 1.5 thicknesses from any wall.

## rooms

```json
{"name": "مجلس", "at": [2.5, 2.4]}
{"name": "Store", "at": [7, 1], "show_area": false, "show_size": false, "height_mm": 2.5}
```

`at` is where the label goes and must be inside the room. The script finds the enclosed space around
that point, measures its net area (wall faces, not centrelines) and, for rectangular rooms, its clear
size. Put the label where no furniture or door swing will sit.

## columns, grids, stairs

```json
"columns": [{"at": [0,0], "size": [0.3, 0.6], "rotation": 0, "tag": "C1"}, {"at": [5,5], "size": 0.4}],
"grids":   {"x": [0, 5, 8.5, 12], "y": [0, 5, 9], "x_labels": ["1","2","3","4"], "y_labels": ["A","B","C"]},
"stairs":  [{"at": [5.2, 0.3], "width": 1.2, "length": 3.0, "steps": 11, "direction": 90, "label": "UP"}]
```

- Column `at` is its centre; `size` is `[bx, by]`, or a single number for a round column.
- Grid bubbles go at the top (x grids) and left (y grids), outside the dimension chains. Labels
  default to 1, 2, 3 and A, B, C.
- Stair `at` is the corner where the flight starts; it runs `length` along `direction` (degrees,
  0 = +x, 90 = +y) and its `width` extends to the left of that direction.

## fixtures

```json
{"type": "bed", "at": [10.2, 3.9], "size": [1.8, 2.0], "rotation": 0}
{"type": "table", "at": [3, 3], "size": 1.2}
{"type": "counter", "at": [2.5, 8.45], "size": [4.6, 0.6], "label": "KITCHEN"}
```

Types: `bed`, `sofa`, `table` (a single-number size makes it round), `wc`, `basin`, `bathtub`,
`shower`, `counter`, `wardrobe`, `rect`. `at` is the centre, `size` is `[width, depth]`. Always
give `size`; usual values in metres: double bed 1.8 x 2.0, single 1.0 x 2.0, sofa 2.2 x 0.9,
WC 0.4 x 0.7, basin 0.6 x 0.45, bathtub 1.7 x 0.75, shower 0.9 x 0.9, wardrobe 1.8 x 0.6,
kitchen counter 0.6 deep. These are simple outline symbols; a counter has no sink or hob.
With `rotation: 0` the back of the piece (bed head, sofa back, WC tank) faces +y; use 90 to put the
back against a wall on the left, -90 on the right, 180 at the bottom.

## dimensions

```json
"dimensions": {
  "auto": true,
  "tiers": ["openings", "rooms", "overall", "grid"],
  "extra": [
    {"from": [0, 5], "to": [5, 5], "offset_mm": 8},
    {"chain": [[0,3],[2,3],[5,3]], "offset_mm": -8, "fixed_ext": true},
    {"section": [[-1, 7], [13, 7]], "offset_mm": 10}
  ]
}
```

**Automatic chains.** `auto` draws, on each of the four sides of the building's bounding box,
from the building outward:

1. `openings`: the doors and windows in that side's wall
2. `rooms`: the clear widths and wall thicknesses of the rooms that lie along that side
3. `overall`: the overall size
4. `grid`: the grid spacing (top and left only, if `grids` exist)

The first chain sits 10 paper mm outside the building and each further tier 8 mm beyond it; a tier
with nothing to show is skipped. Control it with:

- `"auto"`: `true` (all four sides, the default), `false`, or a list of sides such as
  `["bottom", "left"]`.
- `"tiers"`: the kinds of chain to draw, any subset of the four names above.
- `"dimensions": false` switches off automatic chains and takes no extras.

The summary's `auto_dimensions` shows exactly what was drawn, for example
`"left": [{"tier": "rooms", "segments": [0.2, 5.0, 0.1, 4.0, 0.2]}, …]`.

**Extra dimensions** are added on top of (or, with `"auto": false`, instead of) the automatic ones.
Each entry is one of:

- `from` / `to`: a single dimension between two points.
- `chain`: consecutive dimensions through a list of points.
- `section`: a line; every wall face it crosses is dimensioned. The quick way to dimension an
  interior run or the recessed wall of an L-shaped plan.

| Key | Meaning |
|---|---|
| `offset_mm` | Distance from the measured points to the dimension line in **paper millimetres** (preferred; 8 to 10 is usual). Positive puts the line to the left of the direction from the first point to the last, negative to the right. |
| `offset` | The same in drawing units, if you need the line at an exact position. |
| `fixed_ext` | `true` draws short extension lines instead of running them back to the measured points. Use it when stacking chains, so one tier's extension lines do not cross another tier's numbers. |
| `text` | Override the measured value, e.g. `"<> TYP."` (`<>` is the measurement). |

Point order only chooses the side of the dimension line. The number always reads left-to-right or
bottom-to-top, and a number too wide for its segment is moved clear of the ticks automatically.

## extras

Free geometry for anything the lists above do not cover (site boundary, landscape, notes).
`layer` is a layer key or any new layer name.

```json
{"type": "line", "from": [0,0], "to": [5,0], "layer": "site", "linetype": "DASHED"}
{"type": "polyline", "points": [[0,0],[5,0],[5,5]], "closed": false, "layer": "site"}
{"type": "rect", "at": [1,1], "size": [2,1], "rotation": 0, "anchor": "corner", "layer": "furniture"}
{"type": "circle", "center": [3,3], "radius": 0.5, "layer": "0"}
{"type": "arc", "center": [3,3], "radius": 1, "start": 0, "end": 90}
{"type": "text", "at": [6,-3], "text": "GROUND FLOOR PLAN", "height_mm": 5, "align": "MIDDLE_CENTER", "rotation": 0}
{"type": "hatch", "points": [[0,0],[3,0],[3,2],[0,2]], "pattern": "AR-SAND", "scale": 2, "layer": "L-PLNT"}
{"type": "leader", "tip": [6,7], "at": [9,8], "text": "TERRACE"}
```

## sheet

```json
"sheet": {"size": "auto", "project": "فيلا سكنية", "title": "مسقط الدور الأرضي", "number": "A-101",
          "drawn_by": "…", "date": "2026-01-15", "client": "…", "office": "…", "north": 90}
```

- `size`: `"auto"` (default) picks the smallest of A4 to A0 that the drawing fits on at the chosen
  scale; or name one. If it does not fit, the summary says which size or scale would.
- `orientation`: `"auto"` (default: landscape, unless turning the sheet to portrait saves a size),
  `"landscape"` or `"portrait"`.
- `north`: direction of north in degrees (90 = up the sheet). Adds a north arrow to the title strip.
- A paper-space layout named like `A3 1-100` is created with a viewport at exactly that scale, so
  the file plots without any setup. `"paperspace": false` skips it. `"sheet": false` omits the
  frame and title block entirely.

## Output summary and warnings

The script prints JSON:

| Key | Use it to |
|---|---|
| `sheet` | See the size, orientation, scale and the name of the paper layout. |
| `sheet_hint` | Present when the sheet is A2 or larger: the scale at which the plan fits A3. |
| `overall_size`, `enclosed_spaces` | Confirm the footprint and that every intended room is closed. |
| `rooms`, `total_room_area_m2` | Check each room's clear `size` and `area_m2` against the brief; report them to the user. |
| `auto_dimensions` | Verify every automatic chain as numbers, per side and tier. |
| `plan_window` | `[x0, y0, x1, y1]` of the plan without the sheet, ready for `dxf_preview.py --window`. |
| `preview`, `preview_plan` | The rendered images. `preview_plan` is a close-up written when the sheet is A2 or larger. |
| `warnings` | Problems found; fix them before delivering. |

Typical warnings and what they mean:

| Warning | Cause and fix |
|---|---|
| `label point is not inside a space fully enclosed by walls` | A wall stops short of the wall it should meet, or the label point is in a wall. Extend the partition into the other wall's body. |
| `rooms 'A' and 'B' are in the same enclosed space` | The wall between them does not reach the wall it should meet, so the two rooms are one space. |
| `point is … away from the nearest wall` | Opening coordinates are off the wall. Recompute the wall centreline. |
| `width … runs past the end of wall` | The opening is too close to a corner or wider than its wall segment. |
| `Drawing overflows A3 at 1:50; it fits on A2` | Use the suggested size, `"size": "auto"`, or a smaller scale. |

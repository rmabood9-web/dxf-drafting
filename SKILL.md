---
name: dxf-drafting
description: Draw 2D architectural and engineering drawings as real CAD files (DXF that opens in AutoCAD, BricsCAD, LibreCAD, ZWCAD). Floor plans with walls, doors, windows, room names and areas, dimension chains, structural grids, columns, stairs, furniture and a title block; also sections, footing and structural details, site plans. Reads and edits existing DXF files and renders any DXF to PNG or PDF. Use this whenever the user asks for a مخطط, مسقط أفقي, مخطط معماري, مخطط إنشائي, كروكي, لوحة أوتوكاد, قطاع or واجهة, or for a floor plan, blueprint, house or apartment layout, AutoCAD / DXF / DWG drawing or CAD file, or wants a sketch, photo or written description turned into a scaled, dimensioned drawing, even if they never say "DXF". Not for 3D models, Revit/BIM automation or software architecture diagrams.
---

# DXF drafting

Produce drawings a draftsperson would accept: true-size geometry on standard layers, annotation
sized for the plot scale, dimension chains, a title block, and a paper layout ready to print.

All scripts live in `scripts/` next to this file. In the commands below `<skill>` is the absolute
path of this skill's folder.

## Pick the path

| The user wants | Do this |
|---|---|
| A floor plan (rooms, walls, doors, windows) | Write a JSON spec, run `plan_to_dxf.py` |
| Anything else: section, elevation, footing or beam detail, structural layout, site plan | Write a short Python script on `dxfkit` |
| Changes to, or information from, a DXF they already have | `dxf_inspect.py` first, then edit with `ezdxf` |
| A picture of any DXF | `dxf_preview.py` |
| A DWG file | ezdxf cannot read DWG. Ask for a DXF export (AutoCAD: `SAVEAS` > DXF) |

## Setup (once per machine)

```bash
python -c "import ezdxf, shapely, matplotlib, arabic_reshaper, bidi" || python -m pip install ezdxf shapely matplotlib arabic-reshaper python-bidi
```

## Settle these before drawing

A drawing is only useful if its numbers are right, so pin down what you can and say what you assumed.

- **Units and scale.** Default to metres. Pick the scale that lands the drawing on A3 or A4, because
  that is what people print: 1:50 holds a plan up to about 16 x 9 m on A3 (the sheet turns to
  portrait by itself for a deep plan), 1:100 up to about 32 x 18 m, 1:200 beyond that and for site
  plans, 1:20 or 1:25 for details. Follow the user if they work in cm or mm.
- **Overall size and wall thicknesses.** If the user gave room sizes, treat them as clear internal
  sizes (the usual meaning) and add the walls on top. If thicknesses are missing, use 0.20 m
  exterior and 0.10 to 0.15 m partitions and say so.
- **Plot or building?** A size given for the land (أرض, plot) is not the building size. Apply the
  setbacks the user states; if they give none, say plainly that you drew the building to the full
  plot and that setbacks would shrink it.
- **Language.** Label the drawing in the user's language. Arabic works throughout; set
  `"language": "ar"` so the title block and area units are Arabic too.

Ask a question only when a wrong guess would waste the drawing (for example no dimensions at all).
Otherwise draw with stated assumptions; a first drawing to react to is worth more than a questionnaire.

## Floor plans

1. **Lay out coordinates.** Origin at the lower-left outer corner of the building, x to the right,
   y up. Work out wall centrelines on paper first; most mistakes are arithmetic here.
2. **Write the spec.** Minimal example (full reference: `references/plan-spec.md`, worked example:
   `assets/example-plan.json`):

   ```json
   {
     "units": "m", "scale": 100, "language": "ar",
     "walls": [
       {"id": "ext", "points": [[0,0],[8,0],[8,6],[0,6]], "closed": true, "thickness": 0.2, "reference": "outer"},
       {"id": "p1", "points": [[4,0.1],[4,5.9]], "thickness": 0.1}
     ],
     "doors":   [{"at": [4, 3], "width": 0.9, "swing_to": [5, 3], "hinge_near": [4, 4]}],
     "windows": [{"at": [2, 0.1], "width": 1.5}],
     "rooms":   [{"name": "غرفة", "at": [2, 3]}, {"name": "صالة", "at": [6, 3]}],
     "sheet":   {"project": "…", "title": "مسقط الدور الأرضي", "number": "A-101"}
   }
   ```
3. **Run it.**

   ```bash
   python <skill>/scripts/plan_to_dxf.py plan.json plan.dxf --preview plan.png
   ```
4. **Read the JSON summary it prints**, before the image:
   - `warnings` name the problem and the fix.
   - `rooms[].size` and `area_m2` against what the user asked for; `enclosed_spaces` should equal
     the number of rooms you intended.
   - `auto_dimensions` lists every chain that was drawn, per side and tier, as segment lengths.
     Check the `rooms` tier of each side against the rooms that actually lie along that side.
     Numbers are far easier to verify here than as small text in the image.
   - `sheet` and, if the sheet came out A2 or larger, `sheet_hint` (the scale that would fit A3).
     Prefer that scale unless the user asked for the larger one.
5. **Look at the preview** (Read the PNG) and check it as the user would: every room closed, every
   door swinging into the right room and not hitting anything, windows on exterior walls, labels
   clear of furniture and door swings. Where text is too small to read, render a close-up (see
   "Always look before you deliver"); on A2 and larger sheets the script writes one for you as
   `<name>-plan.png`.
6. Fix the spec and re-run until it is right. The spec is the source of truth; keep it next to the DXF.

What trips people up:

- **Exterior wall as one closed outline** with `"reference": "outer"` when the points are the overall
  outside size, `"inner"` when they are the clear inside size. Corners then join perfectly.
- **End a partition inside the wall it meets** (anywhere between that wall's two faces, the
  centreline is easiest). Walls are merged, so the junction cleans itself. A partition that stops
  short leaves a gap and the room will not be "enclosed" (no area, warning).
- **Openings sit on the wall centreline.** `at` is the centre of the opening; it snaps to the nearest
  wall. `swing_to` is any point in the room the door opens into; `hinge_near` is any point nearer to
  the hinge jamb. Give both, they are far less error-prone than left/right.
- **Fixtures** (`bed`, `sofa`, `wc`, `basin`, `bathtub`, `shower`, `table`, `counter`, `wardrobe`)
  are placed by their centre; rotation 0 puts their back (bed head, WC tank) toward +y.
- **Dimensions.** Automatic chains cover the four outer sides of the bounding box. Keep them and
  add to them rather than replacing them: `"auto": ["bottom", "left"]` limits the sides, `"tiers"`
  limits the kinds of chain, and `dimensions.extra` adds interior runs or the recessed walls of an
  L- or U-shaped plan (a `section` line dimensions every wall it crosses in one entry). Give extra
  offsets in paper millimetres with `offset_mm`.

## Other drawings with dxfkit

For anything that is not a floor plan, write a script. `dxfkit.Kit` handles layers, text style,
dimension style, hatch scales, title block and paper layout, so the script is only geometry.
Start from `assets/example_footing_section.py` (a complete, working section drawing) and read
`references/dxfkit-api.md` for the API, layer keys and hatch patterns.

```python
import sys; sys.path.insert(0, r"<skill>/scripts")   # absolute path to this skill's scripts folder
from dxfkit import Kit

kit = Kit(units="m", scale=20)
kit.polyline([(0, 0), (1.6, 0), (1.6, 0.5), (0, 0.5)], "section", closed=True)
kit.hatch([(0, 0), (1.6, 0), (1.6, 0.5), (0, 0.5)], pattern="AR-CONC")
kit.dim_h((0, 0), (1.6, 0), y=-kit.mm(10))          # offsets in paper mm via kit.mm()
kit.leader((0.8, 0.05), (2.2, -0.2), "RC FOOTING")
kit.sheet(title="Footing F1", number="S-201")        # call last
kit.save("footing.dxf")
```

The rule that keeps drawings legible at any scale: **geometry in real units, annotation in paper
millimetres through `kit.mm()`**. Text 2.5 mm high is `height_mm=2.5` whether the sheet is 1:20 or
1:200. Never hard-code a text height or dimension offset in drawing units.

## Existing DXF files

```bash
python <skill>/scripts/dxf_inspect.py drawing.dxf
```

It reports units, extents, layers with entity counts, blocks and texts, which is enough to find what
to change. Then edit with ezdxf and **save under a new name**; the user's original is their only copy.
Match the file's own layers, units and text heights instead of imposing this skill's defaults.
Editing recipes are in `references/dxfkit-api.md`. Preview before and after to confirm the change.

## Always look before you deliver

```bash
python <skill>/scripts/dxf_preview.py drawing.dxf drawing.png                      # plot style, black on white
python <skill>/scripts/dxf_preview.py drawing.dxf zoom.png --window 0 0 6 5        # close-up, in drawing units
python <skill>/scripts/dxf_preview.py drawing.dxf sheet.png --layout "A3 1-100"    # the paper layout tab
python <skill>/scripts/dxf_preview.py drawing.dxf drawing.pdf --color              # layer colours, shareable PDF
```

A DXF that saves without error can still be wrong (a door through a bed, a missing wall, a note
running through a dimension). The preview is the only check that catches that, so read the image
every time. A whole sheet shrinks small text below what you can read, so use `--window` on
junctions, openings and dimension chains rather than guessing; `plan_window` in the plan summary is
the window of the whole plan without the sheet. Arabic is reshaped for the preview only; AutoCAD
shapes it natively.

## Delivering

Give the user the `.dxf` and a `.png` or `.pdf` preview, and tell them in a few lines:

- units, scale and sheet size, and that the paper layout tab is set up to plot at that scale
- room areas and total (from the summary) for plans
- every assumption you made (wall thicknesses, door sizes, anything not in their brief)
- anything the script warned about that you could not resolve

Be straightforward about what this is: a drafted drawing of what was specified. It does not size
structure, check codes or replace an engineer's or architect's review. Two kinds of missing
information need different handling:

- **Engineering values** (bar sizes and spacing, member sizes, footing dimensions, concrete grades,
  bearing levels) must come from the user or their engineer. If they are missing, leave them off
  the drawing or label them "by engineer"; do not fill in plausible-looking numbers.
- **Geometry the drawing cannot exist without** (where the ground line sits in a section, how far
  blinding projects, whether a stated depth is overall) may be drawn at a conventional value, but
  mark it on the drawing as assumed or indicative and list it with your assumptions.

#!/usr/bin/env python3
"""Worked example of a custom drawing with dxfkit: section through an isolated footing.

    python example_footing_section.py out.dxf [out.png]

Copy this file as the starting point for any drawing the plan generator does not
cover (sections, details, structural plans, site plans). Change the numbers at the
top; everything below derives from them.

The sizes and reinforcement here are example values that only show how a drawing is
put together. On a real job they come from the engineer.
"""
import sys
from pathlib import Path

# Find dxfkit: next to this file inside the skill, or in the installed skill when the
# file has been copied elsewhere. Replace with the absolute scripts path if neither fits.
for _scripts in (Path(__file__).resolve().parents[1] / "scripts",
                 Path.home() / ".claude" / "skills" / "dxf-drafting" / "scripts"):
    if (_scripts / "dxfkit.py").exists():
        sys.path.insert(0, str(_scripts))
        break
from dxfkit import Kit  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "footing-section.dxf"

# ---- design values (metres) ------------------------------------------------
B, D = 1.60, 0.50        # footing width and depth
c, stub = 0.40, 1.00     # column width and height shown above the footing
pc = 0.10                # plain-concrete blinding thickness
cover = 0.05
ground = D + 0.60        # ground level above footing underside
bars = 8                 # bottom bars seen in section

kit = Kit(units="m", scale=20)  # details are drawn at 1:20 or 1:25

# ---- concrete --------------------------------------------------------------
blinding = [(-B / 2 - 0.1, -pc), (B / 2 + 0.1, -pc), (B / 2 + 0.1, 0), (-B / 2 - 0.1, 0)]
kit.hatch(blinding, layer="hatch", pattern="AR-SAND")
kit.polyline(blinding, "section", closed=True)

concrete = [(-B / 2, 0), (B / 2, 0), (B / 2, D), (c / 2, D), (c / 2, D + stub),
            (-c / 2, D + stub), (-c / 2, D), (-B / 2, D)]
kit.hatch(concrete, layer="hatch", pattern="AR-CONC")
kit.polyline(concrete, "section", closed=True)

# ---- ground line with an earth hatch band on each side of the column -------
for x0, x1 in ((-B / 2 - 0.5, -c / 2), (c / 2, B / 2 + 0.5)):
    kit.line((x0, ground), (x1, ground), "ground")
    kit.hatch([(x0, ground - 0.08), (x1, ground - 0.08), (x1, ground), (x0, ground)], layer="hatch", pattern="EARTH")

# ---- reinforcement ---------------------------------------------------------
y = cover
kit.polyline([(-B / 2 + cover, y + 0.15), (-B / 2 + cover, y), (B / 2 - cover, y), (B / 2 - cover, y + 0.15)], "rebar")
span = B - 2 * cover - 0.08
for i in range(bars):
    kit.circle((-B / 2 + cover + 0.04 + i * span / (bars - 1), y + 0.022), 0.008, "rebar")
for side in (-1, 1):
    x = side * (c / 2 - cover)
    kit.polyline([(x + side * 0.25, y + 0.04), (x, y + 0.04), (x, D + stub)], "rebar")

# ---- dimensions (offsets are paper millimetres, so they suit any scale) -----
kit.dim_h((-B / 2, 0), (B / 2, 0), y=-pc - kit.mm(10))
kit.dim_h((-c / 2, D + stub), (c / 2, D + stub), y=D + stub + kit.mm(8))
kit.dim_v((B / 2, 0), (B / 2, D), x=B / 2 + 0.1 + kit.mm(10))
kit.dim_v((B / 2 + 0.1, -pc), (B / 2 + 0.1, 0), x=B / 2 + 0.1 + kit.mm(10))
kit.dim_v((B / 2 + 0.5, 0), (B / 2 + 0.5, ground), x=B / 2 + 0.5 + kit.mm(10))

# ---- notes -----------------------------------------------------------------
kit.leader((0.45, y), (B / 2 + 0.45, -pc - kit.mm(4)), f"{bars} T16 @ 200 B.W.")
kit.leader((c / 2 - cover, D + stub * 0.6), (B / 2 + 0.3, D + stub * 0.75), "COLUMN STARTER BARS 4 T16")
kit.leader((-B / 2, -pc / 2), (-B / 2 - 0.55, -pc - kit.mm(6)), "P.C. BLINDING 100 mm")
kit.text("G.L.", (-B / 2 - 0.5 - kit.mm(5), ground), 2.5)
kit.text("SECTION A-A  -  ISOLATED FOOTING F1", (0, -pc - kit.mm(24)), 4.0)
kit.text("SCALE 1:20", (0, -pc - kit.mm(30)), 2.5)

kit.sheet(size="auto", project="Example", title="Footing F1 - section", number="S-201", drawn_by="dxfkit")
kit.save(out)
print(f"saved {out}  sheet={kit.sheet_info}  warnings={kit.warnings}")

if len(sys.argv) > 2:
    from dxf_preview import render

    print("preview:", render(out, sys.argv[2]))

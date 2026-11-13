#!/usr/bin/env python3
"""Render a DXF to PNG or PDF so the drawing can be looked at without CAD software.

    python dxf_preview.py plan.dxf plan.png            # plot-style: black lines on white
    python dxf_preview.py plan.dxf plan.pdf --color    # keep layer colours
    python dxf_preview.py plan.dxf out.png --layout "A3 1-100"
    python dxf_preview.py plan.dxf zoom.png --window 0 0 6 5   # close-up of a region (drawing units)

Arabic text is reshaped for the preview only (the DXF itself is never modified);
AutoCAD shapes Arabic by itself.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import ezdxf
from ezdxf import bbox

ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")


def _shape_arabic(doc) -> bool:
    """Join and reorder Arabic letters in memory so the renderer draws them correctly."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return False

    def fix(s: str) -> str:
        return get_display(arabic_reshaper.reshape(s)) if ARABIC.search(s) else s

    layouts = list(doc.layouts) + list(doc.blocks)
    for layout in layouts:
        for e in layout:
            kind = e.dxftype()
            if kind in ("TEXT", "ATTRIB", "ATTDEF"):
                e.dxf.text = fix(e.dxf.text)
            elif kind == "MTEXT":
                e.text = "\\P".join(fix(part) for part in e.text.split("\\P"))
    return True


def render(dxf_path, out_path, dpi: int = 150, color: bool = False, layout: str = "Model",
           long_side_in: float = 16.0, window=None) -> Path:
    """window=(x0, y0, x1, y1) in drawing units renders only that region, at full resolution."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(dxf_path)
    has_arabic = any(
        ARABIC.search(e.dxf.text) for e in doc.modelspace().query("TEXT") if e.dxf.hasattr("text")
    )
    if has_arabic and not _shape_arabic(doc):
        print("note: install arabic-reshaper and python-bidi for a correct Arabic preview "
              "(the DXF itself is fine).", file=sys.stderr)

    space = doc.modelspace() if layout == "Model" else doc.layout(layout)
    if window:
        x0, y0, x1, y1 = (float(v) for v in window)
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        aspect = (x1 - x0) / (y1 - y0) if y1 > y0 else 1.4
    else:
        box = bbox.extents(space, fast=True)
        aspect = (box.size.x / box.size.y) if box.has_data and box.size.y > 0 else 1.4
    size = (long_side_in, long_side_in / aspect) if aspect >= 1 else (long_side_in * aspect, long_side_in)

    fig = plt.figure(figsize=size)
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
    # adjust_figure=False keeps our figure size; otherwise the backend shrinks it to 4.8 in high.
    frontend = Frontend(ctx, MatplotlibBackend(ax, adjust_figure=False), config=cfg)
    if not color:
        # Plot-style: everything black except fills, which keep their grey tone.
        def plot_style(entity, props):
            if entity.dxftype() != "HATCH":
                props.color = "#000000"

        frontend.push_property_override_function(plot_style)
    frontend.draw_layout(space, finalize=True)
    if window:
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dxf")
    ap.add_argument("out", help="output .png or .pdf")
    ap.add_argument("--dpi", type=int, default=150, help="default 150 (2400 px on the long side)")
    ap.add_argument("--color", action="store_true", help="keep layer colours instead of plot-style black")
    ap.add_argument("--layout", default="Model", help="layout name (default: Model)")
    ap.add_argument("--window", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                    help="render only this region, given in drawing units")
    args = ap.parse_args()
    out = render(args.dxf, args.out, dpi=args.dpi, color=args.color, layout=args.layout, window=args.window)
    print(f"preview written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

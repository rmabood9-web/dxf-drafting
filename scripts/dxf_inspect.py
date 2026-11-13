#!/usr/bin/env python3
"""Summarise an existing DXF so it can be understood before editing it.

    python dxf_inspect.py drawing.dxf            # human-readable summary
    python dxf_inspect.py drawing.dxf --json     # same data as JSON
    python dxf_inspect.py drawing.dxf --texts 200

Reports DXF version, units, extents, layers with entity counts, entity types,
blocks, layouts and the text found in model space. DWG files are not DXF:
ask for a DXF export (AutoCAD: SAVEAS > DXF) or convert with ODA File Converter.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

import ezdxf
from ezdxf import bbox, recover

UNIT_NAMES = {0: "unitless", 1: "inches", 2: "feet", 4: "mm", 5: "cm", 6: "m", 7: "km"}


def load(path):
    if str(path).lower().endswith(".dwg"):
        raise SystemExit(
            "error: this is a DWG file. ezdxf reads DXF only. Export it as DXF "
            "(AutoCAD: SAVEAS > DXF, or the free ODA File Converter) and try again."
        )
    try:
        return ezdxf.readfile(path), []
    except ezdxf.DXFStructureError:
        doc, auditor = recover.readfile(path)  # tolerant loader for damaged files
        return doc, [f"file needed recovery; {len(auditor.errors)} error(s) remain"]


def inspect(path, max_texts=60) -> dict:
    doc, notes = load(path)
    msp = doc.modelspace()
    by_layer, by_type = Counter(), Counter()
    texts = []
    for e in msp:
        by_layer[e.dxf.layer] += 1
        by_type[e.dxftype()] += 1
        if e.dxftype() == "TEXT":
            where = e.get_placement()[1]  # the alignment point, wherever the text is anchored
            texts.append({"text": e.dxf.text, "at": [round(where.x, 3), round(where.y, 3)], "layer": e.dxf.layer})
        elif e.dxftype() == "MTEXT":
            where = e.dxf.insert
            texts.append({"text": e.plain_text(), "at": [round(where.x, 3), round(where.y, 3)], "layer": e.dxf.layer})
    box = bbox.extents(msp, fast=True)
    layers = []
    for layer in doc.layers:
        layers.append({
            "name": layer.dxf.name,
            "color": layer.color,
            "linetype": layer.dxf.linetype,
            "entities": by_layer.get(layer.dxf.name, 0),
            "off": layer.is_off(),
            "frozen": layer.is_frozen(),
        })
    blocks = [b.name for b in doc.blocks if not b.name.startswith("*")]
    return {
        "file": str(path),
        "dxf_version": doc.acad_release,
        "units": UNIT_NAMES.get(doc.header.get("$INSUNITS", 0), str(doc.header.get("$INSUNITS", 0))),
        "extents": {
            "min": [round(box.extmin.x, 3), round(box.extmin.y, 3)],
            "max": [round(box.extmax.x, 3), round(box.extmax.y, 3)],
            "size": [round(box.size.x, 3), round(box.size.y, 3)],
        } if box.has_data else None,
        "entity_count": len(msp),
        "entity_types": dict(by_type.most_common()),
        "layers": sorted(layers, key=lambda l: -l["entities"]),
        "blocks": blocks,
        "block_inserts": dict(Counter(e.dxf.name for e in msp.query("INSERT")).most_common()),
        "layouts": [name for name in doc.layout_names()],
        "text_count": len(texts),
        "texts": texts[:max_texts],
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dxf")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--texts", type=int, default=60, help="how many text items to list")
    args = ap.parse_args()
    info = inspect(args.dxf, args.texts)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    print(f"{info['file']}  ({info['dxf_version']}, units: {info['units']})")
    if info["extents"]:
        e = info["extents"]
        print(f"extents: {e['min']} to {e['max']}  size {e['size'][0]} x {e['size'][1]}")
    print(f"model space: {info['entity_count']} entities  {info['entity_types']}")
    print("layers (name, colour, linetype, entities):")
    for l in info["layers"]:
        state = " [off]" if l["off"] else (" [frozen]" if l["frozen"] else "")
        print(f"  {l['name']:<22} {l['color']:>3}  {l['linetype']:<12} {l['entities']:>6}{state}")
    if info["blocks"]:
        print(f"blocks: {', '.join(info['blocks'][:40])}")
    if info["block_inserts"]:
        print(f"block inserts: {info['block_inserts']}")
    print(f"layouts: {info['layouts']}")
    print(f"texts ({info['text_count']} total, showing {len(info['texts'])}):")
    for t in info["texts"]:
        print(f"  {t['at']}  [{t['layer']}]  {t['text']}")
    for n in info["notes"]:
        print(f"note: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

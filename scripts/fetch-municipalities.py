#!/usr/bin/env python3
"""
Regenerate src/data/metro-vancouver.municipalities.json from authoritative GIS data.

Source
------
Province of British Columbia - BC Data Catalogue:
"Municipalities - Legally Defined Administrative Areas of BC"
layer WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP
https://catalogue.data.gov.bc.ca/dataset/municipalities-legally-defined-administrative-areas-of-bc
Licence: Open Government Licence - British Columbia

We query the province's public WFS endpoint for every municipality whose
ADMIN_AREA_GROUP_NAME is "Metro Vancouver Regional District", keep the ones this
project makes selectable, then:
  1. project lon/lat -> local metres (equirectangular about the data centroid)
  2. simplify each ring (Ramer-Douglas-Peucker, tolerance in metres)
  3. centre on the bounding-box midpoint and apply one uniform scale to
     TARGET_WIDTH scene units
  4. write a compact JSON document (see src/data/README.md for the shape)

Usage:  python3 scripts/fetch-municipalities.py
Requires only the Python standard library + network access.
"""
from __future__ import annotations

import datetime
import json
import math
import subprocess
import urllib.parse
from pathlib import Path

WFS = "https://openmaps.gov.bc.ca/geo/pub/WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP/ows"
GROUP = "Metro Vancouver Regional District"
OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "metro-vancouver.municipalities.json"

# source ADMIN_AREA_NAME -> (id, display name). Only these are rendered.
NAME_MAP = {
    "City of Vancouver": ("vancouver", "Vancouver"),
    "City of Burnaby": ("burnaby", "Burnaby"),
    "City of Richmond": ("richmond", "Richmond"),
    "City of Surrey": ("surrey", "Surrey"),
    "City of New Westminster": ("new-westminster", "New Westminster"),
    "City of Coquitlam": ("coquitlam", "Coquitlam"),
    "City of Port Coquitlam": ("port-coquitlam", "Port Coquitlam"),
    "City of Port Moody": ("port-moody", "Port Moody"),
    "City of North Vancouver": ("north-vancouver-city", "City of North Vancouver"),
    "The Corporation of the District of North Vancouver": ("north-vancouver-district", "District of North Vancouver"),
    "District Municipality of West Vancouver": ("west-vancouver", "West Vancouver"),
    "City of Delta": ("delta", "Delta"),
    "City of White Rock": ("white-rock", "White Rock"),
    "City of Langley": ("langley-city", "City of Langley"),
    "The Corporation of the Township of Langley": ("langley-township", "Township of Langley"),
    "City of Maple Ridge": ("maple-ridge", "Maple Ridge"),
    "City of Pitt Meadows": ("pitt-meadows", "Pitt Meadows"),
}

TARGET_WIDTH = 40.0   # scene units across the full E-W extent
SIMPLIFY_M = 60.0     # RDP tolerance, metres
MIN_PART_AREA_M2 = 3e4  # drop sliver / artefact polygon parts


def fetch() -> dict:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "pub:WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "CQL_FILTER": f"ADMIN_AREA_GROUP_NAME = '{GROUP}'",
    }
    url = f"{WFS}?{urllib.parse.urlencode(params)}"
    # curl rather than urllib: portable TLS trust store on macOS
    out = subprocess.run(
        ["curl", "-fsS", "--max-time", "180", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def rdp(points: list[list[float]], eps: float) -> list[list[float]]:
    if len(points) < 3:
        return points

    def seg_dist(p, a, b):
        if a == b:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (
            (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        )
        t = max(0.0, min(1.0, t))
        proj = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return math.hypot(p[0] - proj[0], p[1] - proj[1])

    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = seg_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(points[: idx + 1], eps)[:-1] + rdp(points[idx:], eps)
    return [points[0], points[-1]]


def ring_area(ring: list[list[float]]) -> float:
    s = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def main() -> None:
    raw = fetch()

    # projection origin = mean of every vertex
    verts: list[list[float]] = []

    def collect(coords, depth):
        if depth == 0:
            verts.append(coords)
        else:
            for c in coords:
                collect(c, depth - 1)

    for f in raw["features"]:
        g = f["geometry"]
        collect(g["coordinates"], 2 if g["type"] == "Polygon" else 3)

    lon0 = sum(v[0] for v in verts) / len(verts)
    lat0 = sum(v[1] for v in verts) / len(verts)
    R = 111_320.0
    klon = R * math.cos(math.radians(lat0))

    def project(lon, lat):
        return [(lon - lon0) * klon, (lat - lat0) * R]

    def clean_ring(ring):
        r = [project(*pt) for pt in ring]
        if r[0] == r[-1]:
            r = r[:-1]
        r = rdp(r + [r[0]], SIMPLIFY_M)
        if r and r[0] == r[-1]:
            r = r[:-1]
        return r

    features = []
    for f in raw["features"]:
        src = f["properties"]["ADMIN_AREA_NAME"]
        if src not in NAME_MAP:
            continue
        slug, label = NAME_MAP[src]
        g = f["geometry"]
        raw_polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        polygons = []
        for poly in raw_polys:
            outer = clean_ring(poly[0])
            if len(outer) < 3 or abs(ring_area(outer)) < MIN_PART_AREA_M2:
                continue
            if ring_area(outer) < 0:
                outer.reverse()
            holes = []
            for h in poly[1:]:
                hr = clean_ring(h)
                if len(hr) < 3 or abs(ring_area(hr)) < MIN_PART_AREA_M2:
                    continue
                if ring_area(hr) > 0:
                    hr.reverse()
                holes.append(hr)
            polygons.append({"outer": outer, "holes": holes})
        features.append(
            {"id": slug, "name": label, "source_name": src, "polygons": polygons}
        )

    features.sort(key=lambda ft: ft["id"])

    xy = [
        p
        for ft in features
        for pg in ft["polygons"]
        for ring in (pg["outer"], *pg["holes"])
        for p in ring
    ]
    minx = min(p[0] for p in xy)
    maxx = max(p[0] for p in xy)
    miny = min(p[1] for p in xy)
    maxy = max(p[1] for p in xy)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    scale = TARGET_WIDTH / (maxx - minx)

    def xf(p):
        return [round((p[0] - cx) * scale, 4), round((p[1] - cy) * scale, 4)]

    for ft in features:
        for pg in ft["polygons"]:
            pg["outer"] = [xf(p) for p in pg["outer"]]
            pg["holes"] = [[xf(p) for p in h] for h in pg["holes"]]

    doc = {
        "meta": {
            "description": "Legal municipal boundaries for the main Metro Vancouver municipalities, simplified and projected to local scene units for 3D rendering.",
            "source": 'Province of British Columbia — BC Data Catalogue: "ABMS Municipalities (legally defined administrative areas of BC)" (WHSE_LEGAL_ADMIN_BOUNDARIES.ABMS_MUNICIPALITIES_SP)',
            "source_url": "https://catalogue.data.gov.bc.ca/dataset/municipalities-legally-defined-administrative-areas-of-bc",
            "source_licence": "Open Government Licence – British Columbia",
            "access": f"WFS GetFeature, outputFormat=application/json, srsName=EPSG:4326, filtered to ADMIN_AREA_GROUP_NAME = '{GROUP}'",
            "retrieved": datetime.date.today().isoformat(),
            "projection": {
                "type": "local-equirectangular",
                "origin_lon": round(lon0, 6),
                "origin_lat": round(lat0, 6),
                "note": "lon/lat -> metres (equirectangular about origin) -> centred on bbox midpoint -> uniform scale. +x = East, +y = North.",
            },
            "simplify_tolerance_m": SIMPLIFY_M,
            "units_per_metre": round(scale, 8),
            "bounds": {
                "width": round((maxx - minx) * scale, 4),
                "height": round((maxy - miny) * scale, 4),
            },
        },
        "municipalities": features,
    }

    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    pts = sum(
        len(r)
        for ft in features
        for pg in ft["polygons"]
        for r in (pg["outer"], *pg["holes"])
    )
    print(f"wrote {len(features)} municipalities / {pts} points -> {OUT.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main()

"""Prepare the supplied GIS files for the static smartphone-friendly viewer."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.shutil import copy as raster_copy
from rasterio.windows import Window, from_bounds


MAX_MOSAIC_EDGE = 4096
CONTOUR_TOLERANCE_M = 0.12
PROFILE_STEP = 4


def simplify_line(
    coordinates: list[list[float]], tolerance: float
) -> list[list[float]]:
    if len(coordinates) <= 2:
        return coordinates

    keep = bytearray(len(coordinates))
    keep[0] = keep[-1] = 1
    tolerance_sq = tolerance * tolerance
    segments = [(0, len(coordinates) - 1)]

    while segments:
        first, last = segments.pop()
        ax, ay = coordinates[first][:2]
        bx, by = coordinates[last][:2]
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        farthest_index = -1
        farthest_distance_sq = tolerance_sq

        for index in range(first + 1, last):
            px, py = coordinates[index][:2]
            if length_sq:
                fraction = max(
                    0.0,
                    min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq),
                )
                nearest_x = ax + fraction * dx
                nearest_y = ay + fraction * dy
            else:
                nearest_x, nearest_y = ax, ay
            distance_sq = (px - nearest_x) ** 2 + (py - nearest_y) ** 2
            if distance_sq > farthest_distance_sq:
                farthest_index = index
                farthest_distance_sq = distance_sq

        if farthest_index >= 0:
            keep[farthest_index] = 1
            segments.append((first, farthest_index))
            segments.append((farthest_index, last))

    return [coordinate for index, coordinate in enumerate(coordinates) if keep[index]]


def ring_area(ring: list[list[float]]) -> float:
    return abs(
        sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(ring, ring[1:])
        )
        / 2.0
    )


def polygon_metrics(polygon: list[list[list[float]]]) -> dict[str, float]:
    area = sum(
        ring_area(ring) * (1 if ring_index == 0 else -1)
        for ring_index, ring in enumerate(polygon)
    )
    perimeter = sum(
        math.fsum(
            math.hypot(second[0] - first[0], second[1] - first[1])
            for first, second in zip(ring, ring[1:])
        )
        for ring in polygon
    )
    return {"area_m2": area, "perimeter_m": perimeter}


def prepare_mosaic(source: Path, output: Path) -> dict[str, float | int]:
    with rasterio.open(source) as mosaic:
        scale = min(
            1.0,
            MAX_MOSAIC_EDGE / mosaic.width,
            MAX_MOSAIC_EDGE / mosaic.height,
        )
        width = max(1, round(mosaic.width * scale))
        height = max(1, round(mosaic.height * scale))
        pixels = mosaic.read(
            out_shape=(mosaic.count, height, width),
            resampling=Resampling.bilinear,
        )
        transform = mosaic.transform * Affine.scale(
            mosaic.width / width, mosaic.height / height
        )
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": mosaic.count,
            "dtype": "uint8",
            "crs": mosaic.crs,
            "transform": transform,
        }
        with MemoryFile() as memory_file:
            with memory_file.open(**profile) as temporary:
                temporary.write(pixels)
            with memory_file.open() as temporary:
                raster_copy(
                    temporary,
                    str(output),
                    driver="WEBP",
                    QUALITY="88",
                    METHOD="5",
                )

        auxiliary = output.with_suffix(output.suffix + ".aux.xml")
        if auxiliary.exists():
            auxiliary.unlink()

        return {
            "left": mosaic.bounds.left,
            "bottom": mosaic.bounds.bottom,
            "right": mosaic.bounds.right,
            "top": mosaic.bounds.top,
            "width": width,
            "height": height,
            "res_x": transform.a,
            "res_y": transform.e,
            "origin_x": transform.c,
            "origin_y": transform.f,
            "source_width": mosaic.width,
            "source_height": mosaic.height,
        }


def prepare_dsm(
    source: Path,
    mosaic_source: Path,
    mosaic_metadata: dict[str, float | int],
    output_dir: Path,
) -> dict[str, Any]:
    with rasterio.open(source) as dsm, rasterio.open(mosaic_source) as mosaic:
        if dsm.crs != mosaic.crs:
            raise ValueError("O DSM e o mosaico precisam usar o mesmo CRS.")
        overlap = (
            max(dsm.bounds.left, mosaic.bounds.left),
            max(dsm.bounds.bottom, mosaic.bounds.bottom),
            min(dsm.bounds.right, mosaic.bounds.right),
            min(dsm.bounds.top, mosaic.bounds.top),
        )
        left, bottom, right, top = overlap
        if left >= right or bottom >= top:
            raise ValueError("DSM e mosaico não têm área em comum.")

        window = from_bounds(left, bottom, right, top, transform=dsm.transform)
        window = window.round_offsets().round_lengths().intersection(
            Window(0, 0, dsm.width, dsm.height)
        )
        values = dsm.read(1, window=window).astype(np.float32)
        valid = np.isfinite(values)
        if dsm.nodata is not None:
            valid &= values != dsm.nodata
        if not valid.any():
            raise ValueError("O recorte do DSM não contém elevações válidas.")

        values[~valid] = np.nan
        transform = dsm.window_transform(window)
        np.save(output_dir / "dsm_cm.npy", values)
        profile = write_profile_dem(
            values,
            valid,
            transform,
            float(np.nanmin(values)),
            float(np.nanmax(values)),
            output_dir / "profile-dem.png",
        )
        return {
            "crs": dsm.crs.to_string(),
            "width": int(values.shape[1]),
            "height": int(values.shape[0]),
            "res_x": transform.a,
            "res_y": transform.e,
            "origin_x": transform.c,
            "origin_y": transform.f,
            "z_min": float(np.nanmin(values)),
            "z_max": float(np.nanmax(values)),
            "valid_pixel_count": int(valid.sum()),
            "total_pixel_count": int(values.size),
            "mosaic": mosaic_metadata,
            "profile_dem": profile,
        }


def write_profile_dem(
    values: np.ndarray,
    valid: np.ndarray,
    transform: Affine,
    z_min: float,
    z_max: float,
    output: Path,
) -> dict[str, float | int]:
    sampled = values[::PROFILE_STEP, ::PROFILE_STEP]
    sampled_valid = valid[::PROFILE_STEP, ::PROFILE_STEP]
    value_range = z_max - z_min
    encoded = np.zeros(sampled.shape, dtype=np.uint16)
    if value_range > 0:
        encoded[sampled_valid] = np.rint(
            (sampled[sampled_valid] - z_min) * (65535.0 / value_range)
        ).astype(np.uint16)

    rgb = np.empty((3, *sampled.shape), dtype=np.uint8)
    rgb[0] = (encoded >> 8).astype(np.uint8)
    rgb[1] = (encoded & 0xFF).astype(np.uint8)
    rgb[2] = sampled_valid.astype(np.uint8) * 255
    profile_transform = transform * Affine.scale(PROFILE_STEP, PROFILE_STEP)
    profile = {
        "driver": "GTiff",
        "width": int(sampled.shape[1]),
        "height": int(sampled.shape[0]),
        "count": 3,
        "dtype": "uint8",
        "transform": profile_transform,
    }
    with MemoryFile() as memory_file:
        with memory_file.open(**profile) as temporary:
            temporary.write(rgb)
        with memory_file.open() as temporary:
            raster_copy(temporary, str(output), driver="PNG", ZLEVEL="6")

    auxiliary = output.with_suffix(output.suffix + ".aux.xml")
    if auxiliary.exists():
        auxiliary.unlink()
    return {
        "width": int(sampled.shape[1]),
        "height": int(sampled.shape[0]),
        "step": PROFILE_STEP,
        "origin_x": transform.c,
        "origin_y": transform.f,
        "res_x": profile_transform.a,
        "res_y": profile_transform.e,
        "z_min": z_min,
        "z_max": z_max,
        "valid_pixel_count": int(sampled_valid.sum()),
    }


def prepare_contours(source: Path, output: Path) -> int:
    with source.open(encoding="utf-8-sig") as stream:
        collection = json.load(stream)

    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{source.name} precisa ser um GeoJSON FeatureCollection.")

    for feature in collection["features"]:
        properties = feature.get("properties", {})
        elevation = properties.get("ELEV")
        geometry = feature.get("geometry") or {}
        if not isinstance(elevation, (int, float)):
            raise ValueError("Toda curva de nível precisa ter um ELEV numérico.")
        if geometry.get("type") != "LineString":
            raise ValueError("As curvas de nível precisam ser geometria LineString.")
        geometry["coordinates"] = simplify_line(
            geometry["coordinates"], CONTOUR_TOLERANCE_M
        )

    with output.open("w", encoding="utf-8") as stream:
        json.dump(collection, stream, ensure_ascii=False, separators=(",", ":"))
    return len(collection["features"])


def prepare_hydrology(source: Path, output: Path) -> int:
    with source.open(encoding="utf-8-sig") as stream:
        collection = json.load(stream)
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{source.name} precisa ser um GeoJSON FeatureCollection.")

    crs_name = collection.get("crs", {}).get("properties", {}).get("name", "")
    if "31985" not in crs_name:
        raise ValueError("Os corpos hídricos precisam estar no CRS EPSG:31985.")
    supported_types = {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}
    for feature in collection.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in supported_types:
            raise ValueError(
                f"Geometria hidrográfica não suportada: {geometry.get('type')}."
            )

    with output.open("w", encoding="utf-8") as stream:
        json.dump(collection, stream, ensure_ascii=False, separators=(",", ":"))
    return len(collection["features"])


def prepare_boundary(source: Path, output: Path) -> dict[str, Any]:
    with source.open(encoding="utf-8-sig") as stream:
        collection = json.load(stream)
    if collection.get("type") != "FeatureCollection" or not collection.get("features"):
        raise ValueError(f"{source.name} não contém feições.")

    parts: list[dict[str, float]] = []
    x_values: list[float] = []
    y_values: list[float] = []
    for feature in collection["features"]:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "MultiPolygon":
            raise ValueError("A poligonal precisa ser uma geometria MultiPolygon.")
        for polygon in geometry["coordinates"]:
            parts.append(polygon_metrics(polygon))
            for ring in polygon:
                x_values.extend(point[0] for point in ring)
                y_values.extend(point[1] for point in ring)

    totals = {
        "area_m2": math.fsum(part["area_m2"] for part in parts),
        "perimeter_m": math.fsum(part["perimeter_m"] for part in parts),
    }
    bounds = {
        "left": min(x_values),
        "bottom": min(y_values),
        "right": max(x_values),
        "top": max(y_values),
    }
    collection["properties"] = {
        "crs": "EPSG:31985",
        "unit": "metre",
        "parts": parts,
        "bounds": bounds,
        **totals,
    }
    with output.open("w", encoding="utf-8") as stream:
        json.dump(collection, stream, ensure_ascii=False, separators=(",", ":"))
    return {**totals, "parts": parts, "bounds": bounds}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=(
            "Folder containing dsm_cm.tif, mosaico.tif, cv.geojson, "
            "poligonal.geojson and corpos_hidricos.geojson"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
        help="Folder for optimized static web assets",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    mosaic = prepare_mosaic(args.source_dir / "mosaico.tif", args.output_dir / "mosaico.webp")
    dsm = prepare_dsm(
        args.source_dir / "dsm_cm.tif",
        args.source_dir / "mosaico.tif",
        mosaic,
        args.output_dir,
    )
    contours = prepare_contours(
        args.source_dir / "cv.geojson", args.output_dir / "contours.geojson"
    )
    boundary = prepare_boundary(
        args.source_dir / "poligonal.geojson", args.output_dir / "boundary.geojson"
    )
    hydrology = prepare_hydrology(
        args.source_dir / "corpos_hidricos.geojson",
        args.output_dir / "hydro.geojson",
    )

    (args.output_dir / "dsm_cm.json").write_text(
        json.dumps(dsm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "site-stats.json").write_text(
        json.dumps(
            {
                "crs": "EPSG:31985",
                "unit": "metre",
                "hydrology_features": hydrology,
                "mosaic_bounds": {
                    "left": mosaic["left"],
                    "bottom": mosaic["bottom"],
                    "right": mosaic["right"],
                    "top": mosaic["top"],
                },
                **boundary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Mosaico: {mosaic['width']} x {mosaic['height']} px")
    print(f"DSM: {dsm['width']} x {dsm['height']} px, {dsm['valid_pixel_count']} pixels válidos")
    print(f"Curvas ELEV: {contours}")
    print(f"Corpos hídricos: {hydrology} feições")
    print(
        f"Poligonal: {boundary['area_m2']:.2f} m², "
        f"{boundary['perimeter_m']:.2f} m de perímetro"
    )


if __name__ == "__main__":
    main()

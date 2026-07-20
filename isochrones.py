# ISOCHRONES
# Backend: OpenRouteService API (https://openrouteservice.org)
# Install: pip install openrouteservice

from __future__ import annotations

import os
import time
import warnings
from typing import Optional

import geopandas as gpd
import openrouteservice as ors
import pandas as pd
from shapely.geometry import shape


# ORS allows max 5 locations per isochrone request and 40 requests/minute
ORS_MAX_LOCATIONS   = 5
ORS_RATE_LIMIT      = 40        # requests per minute
ORS_RATE_SLEEP      = 60 / ORS_RATE_LIMIT



def get_client(api_key: str) -> ors.Client:
    return ors.Client(key=api_key)



def _fetch_isochrones_batch(
    client: ors.Client,
    locations: list[tuple[float, float]],
    trip_times: list[int],        
    smoothing: float = 0.5,
) -> list[dict]:
    response = client.isochrones(
        locations=locations,
        profile="foot-walking",
        range_type="time",
        range=[t * 60 for t in sorted(trip_times, reverse=True)],
        smoothing=smoothing,
        attributes=["area"],
    )
    return response.get("features", [])



def compute_isochrones_for_points(
    points_gdf: gpd.GeoDataFrame,
    api_key: str,
    trip_times: list[int] = [5, 10, 15],
    id_column: str = "piazza_id",
    output_dir: Optional[str] = None,
    output_prefix: str = "isochrone",
    smoothing: float = 0.5,
    batch_size: int = ORS_MAX_LOCATIONS,
) -> dict[int, gpd.GeoDataFrame]:
    client = get_client(api_key)

    # ensure points are in EPSG:4326 (ORS expects lon/lat)
    points = points_gdf.copy()
    if id_column not in points.columns:
        points = points.reset_index(drop=True)
        points[id_column] = points.index
    points = points.to_crs("EPSG:4326")

    coords_all = [(row.geometry.x, row.geometry.y) for _, row in points.iterrows()]
    attrs_all  = [
        {k: v for k, v in row.to_dict().items() if k != "geometry"}
        for _, row in points.iterrows()
    ]

    records_by_time: dict[int, list[dict]] = {t: [] for t in trip_times}
    n_points   = len(coords_all)
    n_batches  = (n_points + batch_size - 1) // batch_size
    n_skipped  = 0
    completed  = 0

    print(f"Sending {n_batches} requests to ORS for {n_points} points "
          f"({batch_size} locations/request)...")

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end   = min(start + batch_size, n_points)

        batch_coords = coords_all[start:end]
        batch_attrs  = attrs_all[start:end]

        try:
            features = _fetch_isochrones_batch(client, batch_coords, trip_times, smoothing)
        except Exception as e:
            warnings.warn(f"Batch {batch_idx+1}/{n_batches} failed: {e}. Skipping {len(batch_coords)} points.")
            n_skipped += len(batch_coords)
            time.sleep(ORS_RATE_SLEEP)
            continue

        n_times = len(trip_times)
        for feat_idx, feature in enumerate(features):
            loc_idx  = feat_idx // n_times 
            time_val = feature["properties"]["value"] // 60

            if loc_idx >= len(batch_attrs):
                continue

            geom = shape(feature["geometry"])
            if geom is None or geom.is_empty:
                continue

            records_by_time[time_val].append({
                **batch_attrs[loc_idx],
                "geometry": geom,
            })

        completed += len(batch_coords)
        print(f"  [{completed}/{n_points}] done (batch {batch_idx+1}/{n_batches})")

        # Respect rate limit
        if batch_idx < n_batches - 1:
            time.sleep(ORS_RATE_SLEEP)

    if n_skipped:
        print(f"  Warning: {n_skipped} points skipped due to API errors.")

    results: dict[int, gpd.GeoDataFrame] = {}
    for trip_time, records in records_by_time.items():
        if records:
            results[trip_time] = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
        else:
            results[trip_time] = gpd.GeoDataFrame(
                columns=list(points_gdf.columns) + ["geometry"],
                geometry="geometry",
                crs="EPSG:4326",
            )
            warnings.warn(f"No valid isochrone returned for trip_time={trip_time} min.")

    if output_dir is not None:
        save_isochrones(results, output_dir, prefix=output_prefix)

    return results


def save_isochrones(
    results: dict[int, gpd.GeoDataFrame],
    output_dir: str,
    prefix: str = "isochrone",
) -> dict[int, str]:
    os.makedirs(output_dir, exist_ok=True)
    saved_paths: dict[int, str] = {}
    for trip_time, gdf in results.items():
        filename = f"{prefix}_{trip_time}min.geojson"
        filepath = os.path.join(output_dir, filename)
        gdf.to_file(filepath, driver="GeoJSON")
        saved_paths[trip_time] = filepath
        print(f"  Saved: {filepath} ({len(gdf)} features)")
    return saved_paths


def load_isochrones(
    output_dir: str,
    trip_times: list[int],
    prefix: str = "isochrone",
) -> dict[int, gpd.GeoDataFrame]:
    results = {}
    for trip_time in trip_times:
        filepath = os.path.join(output_dir, f"{prefix}_{trip_time}min.geojson")
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        results[trip_time] = gpd.read_file(filepath)
        print(f"  Loaded: {filepath} ({len(results[trip_time])} features)")
    return results

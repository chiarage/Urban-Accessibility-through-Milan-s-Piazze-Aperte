#Download from Overture Maps, for the Milan area:
#  - roads:      theme=transportation, type=segment, subtype=road
#  - squares:    theme=base, type=land_use, subtype=piazze pavimentate (sempre incluse) + piazze-giardino (park/managed-grass, solo se il nome contiene "piazza"/"piazzale")
#  - places:     theme=places, type=place (POIs: shops, restaurants, schools, healthcare facilities...)
#  - divisions:  theme=divisions, type=division_area (municipal/neighbourhood boundaries)
#  - transit_infra: theme=base, type=infrastructure, subtype=transit (fermate bus, piattaforme, stop_position)

#Standalone script: it does not require any other external files or datasets.

#Requirements:
#    pip install overturemaps shapely --break-system-packages

import json
import os

import shapely
from shapely import wkb as shapely_wkb
from shapely.ops import unary_union
from overturemaps import record_batch_reader

OUTPUT_DIR = "./data/raw/overture"

# Milano bounding box (west, south, east, north)
MILANO_BBOX = (9.0420, 45.3870, 9.2840, 45.5350)

CLIP_TO_COMUNE = True

COMUNE_NAME = "Milano"
COMUNE_SUBTYPES = {"locality", "localadmin"}

SQUARE_SUBTYPE_CLASS_ALWAYS = {
    ("pedestrian", "pedestrian"),
    ("pedestrian", "plaza"),
}

SQUARE_SUBTYPE_CLASS_IF_NAMED = {
    ("park", "park"),
    ("managed", "grass"),
}

SQUARE_NAME_KEYWORDS = ("piazza", "piazzale")

PLACE_CATEGORY_GROUPS = {
    "shops": [
        "shop", "store", "retail", "supermarket", "boutique", "market",
        "grocery", "clothing", "bookstore", "shopping",
    ],
    "food_drink": [
        "restaurant", "cafe", "bar", "bakery", "food", "pizzeria",
        "pub", "coffee", "gelato", "pasticceria",
    ],
    "education": [
        "school", "college_university", "university", "college", "kindergarten", "education",
        "library", "preschool", "elementary_school", "middle_school", "high_school",
    ],
    "healthcare": [
        "hospital", "pharmacy", "clinic", "doctor", "dentist", "health",
        "medical",
    ],
    "transit": [
        "transit", "station", "bus_stop", "train", "subway", "airport",
    ],
}

TRANSIT_INFRA_CLASSES = {
    "bus_stop", "stop_position", "platform",
    "station", "subway_entrance", "halt",
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def get_primary_name(names_field):
    #Extract the main name from Overture's 'names' field
    if isinstance(names_field, dict):
        return names_field.get("primary") or ""
    return ""


def geometry_from_wkb(geom_bytes):
    if geom_bytes is None:
        return None
    geom = shapely_wkb.loads(geom_bytes)
    return json.loads(shapely.to_geojson(geom))


def download(overture_type, label):
    print(f"[overture] Downloading '{overture_type}' ({label}) per bbox Milano {MILANO_BBOX} ...")
    reader = record_batch_reader(overture_type, bbox=MILANO_BBOX)

    if reader is None:
        print(f"[overture] [{label}] Download failed: no reader returned.")
        return None

    table = reader.read_all().combine_chunks()
    print(f"[overture] [{label}] Loaded {table.num_rows} rows.")
    return table.to_pandas()


def save_geojson(features, filename):
    geojson = {"type": "FeatureCollection", "features": features}
    out_path = os.path.join(OUTPUT_DIR, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    n_with_name = sum(1 for ft in features if ft["properties"].get("name"))
    print(f"  -> {out_path}: {len(features)} feature, {n_with_name} with name")


# ---------------------------------------------------------------------------
# Municipal border
# ---------------------------------------------------------------------------
def get_milano_comune_polygon():
    df = download("division_area", "municipal border")
    if df is None:
        return None

    names = df["names"].apply(get_primary_name)
    mask = (names.str.lower() == COMUNE_NAME.lower()) & (
        df["subtype"].isin(COMUNE_SUBTYPES)
    )
    subset = df[mask]

    if len(subset) == 0:
        print(f"[overture] WARNING: No division_area found for "
              f"'{COMUNE_NAME}' with subtype in {COMUNE_SUBTYPES}. "
              f"Cutout on the municipal border skipped.")
        return None

    if len(subset) > 1:
        print(f"[overture] WARNING: found {len(subset)} division_area "
              f"for '{COMUNE_NAME}' (subtype: "
              f"{subset['subtype'].unique().tolist()}). Union of "
              f"all polygons found.")

    polys = [shapely_wkb.loads(g) for g in subset["geometry"]]
    polygon = unary_union(polys)
    print(f"[overture] Milan municipal border uploaded "
          f"({len(subset)} polygons, subtype: "
          f"{subset['subtype'].unique().tolist()}).")
    return polygon


def clip_to_polygon(df, polygon, label):
    if polygon is None or len(df) == 0:
        return df

    geoms = df["geometry"].apply(shapely_wkb.loads)
    mask = geoms.apply(polygon.intersects)
    filtered = df[mask]
    print(f"[overture] [{label}] Clipping on the municipal border: "
          f"{len(filtered)}/{len(df)} maintained row.")
    return filtered


# ---------------------------------------------------------------------------
# 1. Roads
# ---------------------------------------------------------------------------
def road_feature(row):
    geometry = geometry_from_wkb(row.get("geometry"))
    if geometry is None:
        return None

    properties = {
        "id": row.get("id"),
        "name": get_primary_name(row.get("names")),
        "class": row.get("class"),
        "subtype": row.get("subtype"),
        "subclass": row.get("subclass"),
        "road_surface": row.get("surface"),
    }
    properties = {k: v for k, v in properties.items() if v not in (None, "")}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def download_roads(comune_polygon=None):
    df = download("segment", "roads")
    if df is None:
        return

    df = df[df["subtype"] == "road"]
    print(f"[overture] {len(df)} segments with subtype='road'.")

    if CLIP_TO_COMUNE and comune_polygon is not None:
        df = clip_to_polygon(df, comune_polygon, "roads")

    features = [road_feature(r) for r in df.to_dict(orient="records")]
    features = [f for f in features if f is not None]
    save_geojson(features, "milano_roads_overture.geojson")


# ---------------------------------------------------------------------------
# 2. Squares
# ---------------------------------------------------------------------------
def square_feature(row):
    geometry = geometry_from_wkb(row.get("geometry"))
    if geometry is None:
        return None

    properties = {
        "id": row.get("id"),
        "name": get_primary_name(row.get("names")),
        "class": row.get("class"),
        "subtype": row.get("subtype"),
        "surface": row.get("surface"),
    }
    properties = {k: v for k, v in properties.items() if v not in (None, "")}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def download_squares(comune_polygon=None):
    df = download("land_use", "squares")
    if df is None:
        return

    names_lower = df["names"].apply(get_primary_name).str.lower()
    pairs = list(zip(df["subtype"], df["class"]))

    mask_always = [p in SQUARE_SUBTYPE_CLASS_ALWAYS for p in pairs]
    mask_if_named = [
        (p in SQUARE_SUBTYPE_CLASS_IF_NAMED)
        and any(kw in name for kw in SQUARE_NAME_KEYWORDS)
        for p, name in zip(pairs, names_lower)
    ]
    mask = [a or b for a, b in zip(mask_always, mask_if_named)]

    n_always = sum(mask_always)
    n_named = sum(mask_if_named)
    df = df[mask]
    print(f"[overture] {n_always} paved squares (always included) + "
          f"{n_named} garden squares (name with 'square/piazzale') = "
          f"{len(df)} total polygons recognized as squares.")

    if CLIP_TO_COMUNE and comune_polygon is not None:
        df = clip_to_polygon(df, comune_polygon, "squares")

    features = [square_feature(r) for r in df.to_dict(orient="records")]
    features = [f for f in features if f is not None]
    save_geojson(features, "milano_squares_overture.geojson")


# ---------------------------------------------------------------------------
# 3. Places (POI)
# ---------------------------------------------------------------------------
def get_place_category(row):
    categories = row.get("categories")
    if isinstance(categories, dict):
        primary = categories.get("primary")
        if primary:
            return primary
    return row.get("basic_category") or ""


def get_place_address(row):
    addresses = row.get("addresses")
    if isinstance(addresses, (list, tuple)) and addresses:
        return addresses[0].get("freeform") or ""
    return ""


def place_feature(row):
    geometry = geometry_from_wkb(row.get("geometry"))
    if geometry is None:
        return None

    properties = {
        "id": row.get("id"),
        "name": get_primary_name(row.get("names")),
        "category": get_place_category(row),
        "address": get_place_address(row),
        "confidence": row.get("confidence"),
    }
    properties = {k: v for k, v in properties.items() if v not in (None, "")}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def download_places(comune_polygon=None):
    df = download("place", "places")
    if df is None:
        return

    if CLIP_TO_COMUNE and comune_polygon is not None:
        df = clip_to_polygon(df, comune_polygon, "places")

    df["_category_lower"] = df.apply(
        lambda r: get_place_category(r.to_dict()).lower(), axis=1
    )

    all_features = [place_feature(r) for r in df.to_dict(orient="records")]
    all_features = [f for f in all_features if f is not None]
    save_geojson(all_features, "milano_places_overture_all.geojson")

    print("[overture] Places subdivision by category:")
    for group_name, keywords in PLACE_CATEGORY_GROUPS.items():
        mask = df["_category_lower"].apply(
            lambda cat, kws=keywords: any(kw in cat for kw in kws)
        )
        subset = df[mask]
        print(f"[overture] {group_name}: {len(subset)} rows found.")

        features = [place_feature(r) for r in subset.to_dict(orient="records")]
        features = [f for f in features if f is not None]
        save_geojson(features, f"milano_{group_name}_overture.geojson")


# ---------------------------------------------------------------------------
# 3b. Transit infrastructure
# ---------------------------------------------------------------------------
def transit_infra_feature(row):
    geometry = geometry_from_wkb(row.get("geometry"))
    if geometry is None:
        return None

    properties = {
        "id": row.get("id"),
        "name": get_primary_name(row.get("names")),
        "class": row.get("class"),
        "subtype": row.get("subtype"),
    }
    properties = {k: v for k, v in properties.items() if v not in (None, "")}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def download_transit_infra(comune_polygon=None):
    df = download("infrastructure", "transit_infra")
    if df is None:
        return []

    df = df[(df["subtype"] == "transit") & (df["class"].isin(TRANSIT_INFRA_CLASSES))]
    print(f"[overture] {len(df)} feature infrastructure recognized as "
          f"transit (class in {sorted(TRANSIT_INFRA_CLASSES)}).")

    if CLIP_TO_COMUNE and comune_polygon is not None:
        df = clip_to_polygon(df, comune_polygon, "transit_infra")

    features = [transit_infra_feature(r) for r in df.to_dict(orient="records")]
    features = [f for f in features if f is not None]
    return features



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    comune_polygon = None
    if CLIP_TO_COMUNE:
        comune_polygon = get_milano_comune_polygon()
        print()

    download_roads(comune_polygon)
    print()
    download_squares(comune_polygon)
    print()
    download_places(comune_polygon)
    print()


if __name__ == "__main__":
    main()

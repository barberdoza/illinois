#!/usr/bin/env python3
"""
Pulls active Illinois barbering/cosmetology *business* licenses (salons and
shops, not individual practitioners) from IDFPR's "Professional Licensing"
dataset on data.illinois.gov (Socrata), and builds a county-level rollup.

Why there's no map with individual shop pins here: IDFPR's dataset does not
publish street addresses -- only city, state, ZIP, and county. There's
nothing to geocode down to a shop-level pin, so this app deliberately
aggregates at the county level instead. County centroid coordinates come
from the U.S. Census Bureau's public Gazetteer file (no key needed), not
from IDFPR.

No API key is required for either data.illinois.gov or the Gazetteer file.

Usage:
    python scripts/fetch_data.py
"""
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

RESOURCE_ID = "pzzh-kp68"  # IDFPR "Professional Licensing"
METADATA_URL = f"https://data.illinois.gov/api/views/{RESOURCE_ID}.json"
BASE_URL = f"https://data.illinois.gov/resource/{RESOURCE_ID}.json"

GAZETTEER_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_counties_national.zip"

PAGE_SIZE = 5000

NEEDED_COLUMNS = [
    "License Type", "Description", "License Status", "Business",
    "City", "County",
]

# IDFPR issues a single combined "Salon/Shop Registration" covering
# cosmetology, esthetics, nail technology, hair braiding, and barbering
# together (68 Ill. Admin. Code 1175, Subpart M) -- so, like Texas, this may
# turn out to be one bucket rather than a real barber/salon split. We check
# for both possibilities rather than assuming, and log anything we don't
# recognize instead of dropping it.
CATEGORY_LABELS = {
    "BARBER": "Barber Shop (if separately described)",
    "SALON_SHOP": "Salon / Shop Registration",
    "UNKNOWN": "Unclassified (flagged for review)",
}


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "il-shop-directory/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise RuntimeError(f"data.illinois.gov request failed: {e.code} {body[:300]} ({url})")


def get_field_map():
    meta = _get_json(METADATA_URL)
    by_name = {c["name"]: c["fieldName"] for c in meta.get("columns", [])}
    missing = [c for c in NEEDED_COLUMNS if c not in by_name]
    if missing:
        raise RuntimeError(f"Expected columns not found in IDFPR dataset metadata: {missing}")
    return by_name


def fetch_all_records(fields):
    lt, desc, status, biz, city, county = (
        fields["License Type"], fields["Description"], fields["License Status"],
        fields["Business"], fields["City"], fields["County"],
    )
    select_fields = ",".join([lt, desc, status, biz, city, county])
    where = (
        f"upper({biz})='Y' and upper({status})='ACTIVE' and ("
        f"upper({lt}) like '%BARBER%' or upper({lt}) like '%COSMET%' or "
        f"upper({lt}) like '%ESTHET%' or upper({lt}) like '%NAIL%' or "
        f"upper({lt}) like '%HAIR%' or upper({lt}) like '%BCE%' or "
        f"upper({desc}) like '%BARBER%' or upper({desc}) like '%COSMET%' or "
        f"upper({desc}) like '%SALON%' or upper({desc}) like '%ESTHET%' or "
        f"upper({desc}) like '%NAIL%' or upper({desc}) like '%HAIR%'"
        f")"
    )

    records = fetch_with_where(fields, where)

    if not records:
        print("  No records matched the keyword filter. Running a diagnostic query "
              "to see what License Type/Description values actually exist for "
              "active businesses, so we can fix the filter instead of guessing again...")
        return _diagnostic_sample(fields)

    return records


def fetch_with_where(fields, where):
    lt, desc, status, biz, city, county = (
        fields["License Type"], fields["Description"], fields["License Status"],
        fields["Business"], fields["City"], fields["County"],
    )
    select_fields = ",".join([lt, desc, status, biz, city, county])
    records = []
    offset = 0
    while True:
        params = {
            "$select": select_fields, "$where": where,
            "$limit": PAGE_SIZE, "$offset": offset, "$order": ":id",
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        batch = _get_json(url)
        if not batch:
            break
        records.extend(batch)
        print(f"  fetched {len(records)} records so far...")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def _diagnostic_sample(fields):
    """Our keyword filter matched nothing. Rather than fail silently with an
    empty dataset (which is what happened before this fallback existed),
    pull a broad sample of active businesses and print every distinct
    License Type we actually see -- that tells us the real value to filter
    on instead of guessing blind a second time."""
    lt, desc, status, biz = fields["License Type"], fields["Description"], fields["License Status"], fields["Business"]
    where = f"upper({biz})='Y' and upper({status})='ACTIVE'"
    params = {"$select": f"{lt},{desc}", "$where": where, "$limit": 50000, "$group": lt}
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    try:
        sample = _get_json(url)
    except RuntimeError as e:
        print(f"    diagnostic query also failed: {e}", file=sys.stderr)
        return []

    print(f"  Found {len(sample)} distinct active-business License Type values. Listing all of them:")
    for row in sample:
        print(f"    {row.get(lt)!r}")
    print("  None of these were auto-selected -- update the keyword filter in "
          "fetch_all_records() once you know which one(s) cover barbering/cosmetology, "
          "then re-run.")
    return []


def classify(license_type, description):
    lt = (license_type or "").upper()
    desc = (description or "").upper()
    combined = f"{lt} {desc}"

    if any(kw in combined for kw in ("SCHOOL", "TEACHER", "CE SPONSOR", "INSTRUCTOR")):
        return None  # education/continuing-ed, not a shop -- excluded

    if "BARBER" in desc and "SHOP" in desc and "SALON" not in desc:
        return "BARBER"
    if "SALON" in combined or "SHOP" in combined or "REGISTRATION" in desc:
        return "SALON_SHOP"
    return "UNKNOWN"


def fetch_county_centroids():
    """U.S. Census Bureau Gazetteer file: real county centroids, no API key,
    covers every state so this is reusable if we ever add more states."""
    req = urllib.request.Request(GAZETTEER_URL, headers={"User-Agent": "il-shop-directory/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        zip_bytes = resp.read()

    centroids = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        inner_name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        with zf.open(inner_name) as f:
            text = io.TextIOWrapper(f, encoding="latin-1")
            reader = csv.DictReader(text, delimiter="\t")
            for row in reader:
                row = {k.strip(): v.strip() for k, v in row.items()}
                if row.get("USPS") != "IL":
                    continue
                name = row["NAME"]  # e.g. "Cook"
                try:
                    lat = float(row["INTPTLAT"])
                    lon = float(row["INTPTLONG"])
                except (KeyError, ValueError):
                    continue
                centroids[name] = (lat, lon)
    return centroids


def main():
    print("Looking up IDFPR dataset field names...")
    fields = get_field_map()

    print("Fetching active business-level barbering/cosmetology licenses...")
    raw = fetch_all_records(fields)
    print(f"Total candidate records pulled: {len(raw)}")

    if not raw:
        print("ERROR: zero records matched, even after the diagnostic fallback. "
              "Not overwriting data/il_shops.json with an empty/misleading result -- "
              "check the diagnostic output above, fix the keyword filter in "
              "fetch_all_records(), and re-run.", file=sys.stderr)
        sys.exit(1)

    lt_f, desc_f, county_f = fields["License Type"], fields["Description"], fields["County"]

    print("Fetching Illinois county centroids from the Census Bureau Gazetteer...")
    centroids = fetch_county_centroids()
    print(f"  loaded {len(centroids)} county centroids")

    rollup = {}
    unknown_types = {}
    excluded_count = 0
    unmatched_county_count = 0

    for row in raw:
        category = classify(row.get(lt_f), row.get(desc_f))
        if category is None:
            excluded_count += 1
            continue
        if category == "UNKNOWN":
            key = f"{row.get(lt_f) or ''} | {row.get(desc_f) or ''}"
            unknown_types[key] = unknown_types.get(key, 0) + 1

        county = (row.get(county_f) or "Unknown").strip().title()
        bucket = rollup.setdefault(county, {code: 0 for code in CATEGORY_LABELS})
        bucket[category] += 1

    rollup_out = []
    for county, counts in sorted(rollup.items()):
        centroid = centroids.get(county)
        if not centroid:
            unmatched_county_count += 1
        entry = {
            "county": county,
            "total": sum(counts.values()),
            "lat": centroid[0] if centroid else None,
            "lon": centroid[1] if centroid else None,
        }
        entry.update(counts)
        rollup_out.append(entry)
    rollup_out.sort(key=lambda r: -r["total"])

    print(f"Classified into {len(rollup_out)} counties "
          f"({excluded_count} school/CE records excluded, "
          f"{sum(unknown_types.values())} unclassified, "
          f"{unmatched_county_count} counties had no centroid match).")

    print("Real License Type | Description breakdown for unclassified records (top 20):")
    for key, count in sorted(unknown_types.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {count:>6}  {key}")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Illinois Dept. of Financial & Professional Regulation (IDFPR) via data.illinois.gov (Socrata Open Data)",
        "source_url": f"https://data.illinois.gov/dataset/professional-licensing/{RESOURCE_ID}",
        "centroid_source": "U.S. Census Bureau 2024 Gazetteer Files",
        "is_sample": False,
        "categories": CATEGORY_LABELS,
        "excluded_school_or_ce_records": excluded_count,
        "unclassified_license_types": unknown_types,
        "rollup": rollup_out,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "il_shops.json")
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    print(f"Wrote {out_path}: {len(rollup_out)} counties, "
          f"{sum(r['total'] for r in rollup_out)} total shops.")


if __name__ == "__main__":
    main()

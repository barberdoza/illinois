# IL Shop Directory

A static web app showing licensed **barbering and cosmetology businesses**
in Illinois: a searchable county-level rollup, a ranking chart, and a
county-level bubble map.

Data comes from the Illinois Department of Financial and Professional
Regulation's **"Professional Licensing"** dataset on `data.illinois.gov`
(Socrata) — the same 1.2M-record registry that covers 100+ IDFPR-licensed
professions, filtered down to barbering/cosmetology *business* licenses.

**No API key needed.** Same as NY, this one's free and key-less.

The repo ships with **sample placeholder data** (`data/il_shops.json`,
synthetic, clearly labeled) so the site works the moment you deploy it.

## Why this one has no per-shop map pins

Unlike NY (which publishes coordinates) or TX (which at least publishes
street addresses we could geocode), **IDFPR's dataset only includes city,
state, ZIP, and county** — no street address at all. There's nothing to
geocode down to an individual shop's location.

So instead of pins, the map here shows **one circle per county**, sized by
total shop count — using real county centroid coordinates pulled from the
U.S. Census Bureau's public Gazetteer file (also free, no key). This is
also just simpler and faster to run than the TX app: no geocoding pipeline,
no retries, no hour-long workflow runs.

## A likely finding, not (necessarily) a bug

Illinois law (68 Ill. Admin. Code 1175, Subpart M) issues a single combined
**"Salon/Shop Registration"** covering cosmetology, esthetics, nail
technology, hair braiding, *and* barbering under one certificate. So, like
what we found in Texas, there's a real chance every shop ends up in one
`SALON_SHOP` bucket rather than splitting cleanly into Barber vs. Salon. If
that happens, it's very likely accurate, not broken — check the Action's
log output ("Real License Type | Description breakdown") to confirm what
IDFPR's data actually contains before assuming something's wrong.

## 1. Run the data fetch

No signup required. Go to **Actions → Update IL shop data → Run workflow**.
This runs `scripts/fetch_data.py`, which:
1. Pulls active, business-level (not individual-practitioner) licenses
   matching barbering/cosmetology/esthetics/nail/hair-braiding keywords
2. Classifies each into Barber / Salon-Shop / Unclassified, excluding
   schools and continuing-education providers entirely
3. Downloads the Census Bureau's county centroid file and joins it in
4. Writes `data/il_shops.json` and commits it

This should run in well under a minute — there's no slow geocoding step.
It's scheduled to re-run every Monday; adjust the `cron` line in
`.github/workflows/update-data.yml` if you want a different cadence.

You can also run it locally:

```bash
python3 scripts/fetch_data.py
```

## 2. Turn on GitHub Pages

**Settings → Pages → Build and deployment → Source: Deploy from a branch →
Branch: `main`, folder: `/ (root)`**

## How it's put together

```
index.html          the page
css/style.css        styling (shares Boulevard brand tokens with the other apps)
js/app.js             search, rollup table, ranking chart, and the county bubble map
data/il_shops.json    the dataset the page reads (static JSON, no server needed)
scripts/fetch_data.py pulls + classifies fresh data, joins in county centroids
.github/workflows/    scheduled + on-demand data refresh
```

### Data notes

- "Shops" means business-level licenses only (`Business` = `Y` in IDFPR's
  data), not individual practitioner licenses (Cosmetologist, Barber,
  Esthetician, Nail Technician, Hair Braider, etc.).
- County names come from IDFPR's own `County` field.
- If the "Unclassified" banner shows up with real data, the
  `unclassified_license_types` field in the output JSON (and the Action's
  log) lists exactly which License Type / Description combos didn't match
  anything — that's the first place to look before changing `classify()`
  in `scripts/fetch_data.py`.

## Customizing

- **Refine the category mapping:** edit `classify()` in
  `scripts/fetch_data.py`.
- **Bubble sizing:** `radiusFor()` in `js/app.js`.
- **Colors/fonts:** all in the `:root` block at the top of `css/style.css` —
  Boulevard's brand system, same as the other apps.

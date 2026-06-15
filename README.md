# WaterAreaForJEJSST

Toktogul Reservoir and Kyrgyzstan water resources GIS analysis project.

This repository contains the processing scripts, generated interactive HTML dashboards, reports, previews, and lightweight vector extracts used for the water-resource maps.

## Main Outputs

- `output/dashboard.html` - Toktogul Reservoir hydrological dashboard.
- `output/integrated_map.html` - Central Asia transboundary water resources map.
- `output/kyrgyzstan_water_map.html` - Kyrgyzstan water resources and basin map.
- `output/map_dashboard.html` - map dashboard view.
- `output/REPORT.md` - remote-sensing processing report.
- `output/中亚跨境水资源综合分析平台.pptx` - presentation deck.

## Local Preview

From the project root:

```bash
python3 -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000/output/kyrgyzstan_water_map.html
```

## Data Notes

Large raw and intermediate geospatial files are intentionally excluded from Git:

- root `43T_*.tif` and `44T_*.tif` Dynamic World/Sentinel-derived tiles
- `output/mosaics/*.tif`
- `processed_output/*.tif`
- `*.osm.pbf`
- `*.nc`

These files are too large for normal GitHub storage and should be kept locally or published through a data-release channel such as GitHub Releases, cloud object storage, Zenodo, or Git LFS with sufficient quota.

The repository keeps smaller generated artifacts and vector extracts such as `output/osm_lines.gpkg` and `output/osm_polys.gpkg` so the interactive maps remain usable.

## Recent GIS Fixes

- Tightened Chu/Chui River matching to avoid accidental matches against mountain streams and canal names.
- Moved `Кочкор` and `Жоон-Арык` into the Chu basin as source streams.
- Restricted Naryn and Talas mainline layers to exact river-name matches.
- Corrected Chatkal routing to `Chatkal -> Chirchiq -> Syr Darya`.
- Corrected Kokshaal routing toward the Aksu/Tarim system.


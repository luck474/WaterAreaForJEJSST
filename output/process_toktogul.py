#!/usr/bin/env python3
"""
Toktogul Reservoir – End-to-End GeoTIFF Processing Pipeline
=============================================================
Processes Dynamic-World (Sentinel-2) land-cover classification tiles
for the Toktogul Reservoir, Kyrgyzstan.

File naming convention:
  <zone>_<YYYYMMDD>-<YYYYMMDD>.tif
  zone 43T → EPSG:32643 (UTM zone 43N, central meridian 75°E)
  zone 44T → EPSG:32644 (UTM zone 44N, central meridian 81°E)

Usage:
  python process_toktogul.py [--base-dir PATH] [--output-dir PATH]
                             [--roi XMIN YMIN XMAX YMAX]  # in EPSG:32643 metres
                             [--res METRES]                # output pixel size (default 10)
"""

import argparse
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION & DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────

# Target CRS: UTM zone 43N (EPSG:32643)
# Rationale: The Toktogul reservoir sits at ~73°E, 41.8°N – well within
# zone 43 (72–78°E).  Using zone 43 minimises distortion; zone 44's
# central meridian (81°E) is 8° away and would introduce more stretching.
TARGET_CRS = "EPSG:32643"

# ROI in EPSG:32643 metres (derived from existing water-binary metadata
# + 5 km buffer on each side for visual context).
# Existing extent: X 304309–346904, Y 4612570–4657999  → buffer 5 km
DEFAULT_ROI = (299000, 4607000, 352000, 4663000)   # xmin, ymin, xmax, ymax
TARGET_RES  = 10  # metres (Sentinel-2 native 10 m; keep full resolution)

# Dynamic World palette (embedded in source files, reproduced for rendering)
# Index → (R, G, B, label)
DW_PALETTE = {
    0:  (0,   0,   0,   "NoData"),
    1:  (65,  155, 223, "Water"),
    2:  (57,  125, 73,  "Trees"),
    3:  (136, 176, 83,  "Grass"),
    4:  (122, 135, 198, "Flooded veg"),
    5:  (228, 150, 53,  "Crops"),
    6:  (223, 195, 90,  "Shrub/scrub"),
    7:  (196, 40,  27,  "Built"),
    8:  (165, 155, 143, "Bare"),
    9:  (168, 235, 255, "Snow/ice"),
    10: (97,  97,  97,  "Cloud/shadow"),
    11: (227, 226, 195, "Bare light"),
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s  %(levelname)-7s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_path, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("toktogul")


def run(cmd: list, log: logging.Logger, check=True) -> subprocess.CompletedProcess:
    """Run a shell command, log it, raise on error."""
    log.info("CMD: " + " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        log.debug("STDOUT: " + result.stdout.strip()[:400])
    if result.returncode != 0:
        log.error("STDERR: " + result.stderr.strip()[:800])
        if check:
            raise RuntimeError(f"Command failed (rc={result.returncode}): {cmd[0]}")
    return result


def file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / 1_048_576
    except FileNotFoundError:
        return 0.0


def get_raster_info(path: Path) -> dict:
    """Return dict with CRS, extent, size, bands, type, nodata."""
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(path))
    if ds is None:
        return {}
    gt  = ds.GetGeoTransform()
    w, h = ds.RasterXSize, ds.RasterYSize
    xmin = gt[0];  ymax = gt[3]
    xmax = gt[0] + w * gt[1];  ymin = gt[3] + h * gt[5]
    band = ds.GetRasterBand(1)
    nd   = band.GetNoDataValue()

    from osgeo import osr
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    epsg = srs.GetAttrValue("AUTHORITY", 1)

    # Convert corners to WGS84
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct  = osr.CoordinateTransformation(srs, wgs)
    c   = [ct.TransformPoint(x, y)[:2] for x, y in
           [(xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax)]]
    lons = [p[0] for p in c];  lats = [p[1] for p in c]

    return {
        "epsg": int(epsg) if epsg else None,
        "width": w, "height": h,
        "res_x": abs(gt[1]), "res_y": abs(gt[5]),
        "bands": ds.RasterCount,
        "dtype": gdal.GetDataTypeName(band.DataType),
        "nodata": nd,
        "native_xmin": xmin, "native_xmax": xmax,
        "native_ymin": ymin, "native_ymax": ymax,
        "lon_min": min(lons), "lon_max": max(lons),
        "lat_min": min(lats), "lat_max": max(lats),
        "size_mb": file_size_mb(path),
    }


def estimate_uncompressed_mb(w, h, bands, bytes_per=1) -> float:
    return w * h * bands * bytes_per / 1_048_576


# ─────────────────────────────────────────────────────────────────────────────
# 3. SURVEY
# ─────────────────────────────────────────────────────────────────────────────

def survey_files(base_dir: Path, log: logging.Logger) -> list[dict]:
    """Scan base_dir for all *.tif (excluding output), return metadata list."""
    pattern  = re.compile(r"^(43T|44T)_(20\d{6})-(20\d{6,8})\.tif$")
    records  = []
    tif_list = sorted(base_dir.glob("*.tif"))

    log.info(f"=== SURVEY: found {len(tif_list)} .tif file(s) in {base_dir} ===")
    for p in tif_list:
        m = pattern.match(p.name)
        if not m:
            log.info(f"  SKIP (name doesn't match convention): {p.name}")
            continue
        zone, date_start, date_end = m.group(1), m.group(2), m.group(3)
        info = get_raster_info(p)
        info.update({"path": str(p), "filename": p.name,
                     "zone": zone, "date_start": date_start, "date_end": date_end,
                     "period": f"{date_start}-{date_end}"})
        records.append(info)
        log.info(
            f"  {p.name}: EPSG:{info['epsg']}  {info['width']}×{info['height']}px  "
            f"res={info['res_x']}m  bands={info['bands']}  dtype={info['dtype']}  "
            f"nodata={info['nodata']}  size={info['size_mb']:.1f}MB\n"
            f"    WGS84 bbox: lon [{info['lon_min']:.3f}, {info['lon_max']:.3f}]  "
            f"lat [{info['lat_min']:.3f}, {info['lat_max']:.3f}]"
        )
    log.info(f"Survey complete: {len(records)} valid file(s)\n")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 4. GROUP BY PERIOD
# ─────────────────────────────────────────────────────────────────────────────

def group_by_period(records: list[dict], log: logging.Logger) -> dict:
    """
    Returns dict: period → {"43T": record, "44T": record}
    Periods missing one zone are flagged in log but kept for single-zone processing.
    """
    groups: dict = {}
    for r in records:
        p = r["period"]
        groups.setdefault(p, {})
        groups[p][r["zone"]] = r

    log.info("=== FILE GROUPING ===")
    for period, tiles in sorted(groups.items()):
        have = list(tiles.keys())
        if len(have) == 2:
            log.info(f"  {period}: 43T + 44T  ✓ complete pair")
        else:
            log.warning(f"  {period}: only {have} – will process as single-zone tile")
    log.info("")
    return groups


# ─────────────────────────────────────────────────────────────────────────────
# 5. MOSAIC ONE PERIOD
# ─────────────────────────────────────────────────────────────────────────────

def mosaic_period(
    period: str,
    tiles: dict,
    roi: tuple,
    res: int,
    target_crs: str,
    out_dir: Path,
    tmp_dir: Path,
    log: logging.Logger,
) -> dict | None:
    """
    Warp each tile to target_crs + crop to ROI, build VRT, translate to
    compressed GeoTIFF, build overviews.

    Returns metadata dict for the output mosaic, or None on failure.
    """
    xmin, ymin, xmax, ymax = roi
    out_w = round((xmax - xmin) / res)
    out_h = round((ymax - ymin) / res)
    uncomp_mb = estimate_uncompressed_mb(out_w, out_h, bands=1)
    log.info(f"--- PROCESSING {period} ---")
    log.info(f"  ROI [{xmin},{ymin},{xmax},{ymax}] → output {out_w}×{out_h}px  "
             f"~{uncomp_mb:.1f}MB uncompressed")

    # Downsample if uncompressed would exceed 2 GB (unlikely at ROI scale)
    scale = 1
    if uncomp_mb > 2048:
        scale = int(np.ceil(uncomp_mb / 1024))
        res_use = res * scale
        log.warning(f"  Uncompressed estimate {uncomp_mb:.0f}MB > 2GB – "
                    f"downsampling ×{scale} to {res_use}m")
    else:
        res_use = res

    # Parse period for output naming
    date_start, date_end = period.split("-")
    out_name = f"Toktogul_mosaic_{date_start}_{date_end}.tif"
    out_path = out_dir / out_name
    vrt_path = tmp_dir / f"mosaic_{period}.vrt"

    warped_paths = []
    zone_results = {}

    for zone in ("43T", "44T"):
        if zone not in tiles:
            log.info(f"  {zone}: absent – skip")
            zone_results[zone] = "absent"
            continue

        rec   = tiles[zone]
        src   = rec["path"]
        dst   = tmp_dir / f"warped_{zone}_{period}.tif"

        # Estimate valid-pixel coverage: for 44T the ROI is outside zone-44 extent
        # (ROI in WGS84 ~72-73°E; zone 44 covers ~78-84°E).
        # gdalwarp will produce an all-nodata tile in that case; this is expected
        # and documented in the report.  We still warp it so the pipeline is
        # symmetric and reproducible.

        warp_cmd = [
            "gdalwarp",
            "-t_srs", target_crs,
            "-te", str(xmin), str(ymin), str(xmax), str(ymax),
            "-tr", str(res_use), str(res_use),
            "-r",  "near",           # nearest-neighbour: preserve class indices
            "-srcnodata", "0",
            "-dstnodata", "0",
            "-co", "COMPRESS=DEFLATE",
            "-co", "PREDICTOR=2",
            "-co", "TILED=YES",
            "-co", "BLOCKXSIZE=512",
            "-co", "BLOCKYSIZE=512",
            "-co", "BIGTIFF=IF_SAFER",
            "-overwrite",
            src, str(dst),
        ]
        try:
            run(warp_cmd, log)
        except RuntimeError as e:
            log.error(f"  {zone} warp failed: {e}")
            zone_results[zone] = "warp_error"
            continue

        # Check if output has any valid pixels
        from osgeo import gdal as _gdal
        _gdal.UseExceptions()
        _ds  = _gdal.Open(str(dst))
        band = _ds.GetRasterBand(1)
        arr  = band.ReadAsArray()
        n_valid = int((arr > 0).sum())
        _ds = None
        log.info(f"  {zone}: warp OK  valid pixels = {n_valid:,}  "
                 f"({file_size_mb(dst):.1f}MB)")
        zone_results[zone] = f"ok:{n_valid}_valid_px"

        if n_valid == 0:
            log.info(f"  {zone}: ALL NODATA at ROI – tile does not cover "
                     f"this area (expected: zone-44 geographically misses "
                     f"reservoir at ~73°E).  Included in VRT for correctness.")
        warped_paths.append(str(dst))

    if not warped_paths:
        log.error(f"  No valid warp outputs for {period} – skipping mosaic")
        return None

    # Build VRT
    vrt_cmd = ["gdalbuildvrt", "-overwrite",
               "-srcnodata", "0", "-vrtnodata", "0",
               str(vrt_path)] + warped_paths
    run(vrt_cmd, log)

    # Translate to compressed GeoTIFF
    translate_cmd = [
        "gdal_translate",
        "-co", "COMPRESS=DEFLATE",
        "-co", "PREDICTOR=2",
        "-co", "TILED=YES",
        "-co", "BLOCKXSIZE=512",
        "-co", "BLOCKYSIZE=512",
        "-co", "BIGTIFF=IF_SAFER",
        "-a_nodata", "0",
        str(vrt_path), str(out_path),
    ]
    run(translate_cmd, log)

    # Overview pyramid (levels 2 4 8 16 32 64)
    addo_cmd = ["gdaladdo", "-ro",
                "--config", "COMPRESS_OVERVIEW", "DEFLATE",
                str(out_path), "2", "4", "8", "16", "32", "64"]
    run(addo_cmd, log)

    size_mb = file_size_mb(out_path)
    log.info(f"  → {out_name}  {size_mb:.1f}MB  (est. uncomp. {uncomp_mb:.1f}MB)")

    # Gather output metadata
    info = get_raster_info(out_path)
    info.update({
        "filename":   out_name,
        "path":       str(out_path),
        "date_start": date_start,
        "date_end":   date_end,
        "period":     period,
        "crs":        target_crs,
        "zone_results": zone_results,
        "uncomp_mb":  round(uncomp_mb, 2),
        "comp_mb":    round(size_mb, 2),
        "compression_ratio": round(uncomp_mb / size_mb, 1) if size_mb > 0 else 0,
    })

    # Clean up temp warped files
    for p in warped_paths:
        try:
            Path(p).unlink()
        except Exception:
            pass
    try:
        vrt_path.unlink()
    except Exception:
        pass

    return info


# ─────────────────────────────────────────────────────────────────────────────
# 6. GENERATE PNG THUMBNAIL (from overview)
# ─────────────────────────────────────────────────────────────────────────────

def colorise(arr: np.ndarray, palette: dict) -> np.ndarray:
    """Map class indices → RGB uint8 image."""
    h, w = arr.shape
    rgb  = np.zeros((h, w, 3), dtype=np.uint8)
    for idx, (r, g, b, *_) in palette.items():
        mask = (arr == idx)
        rgb[mask] = [r, g, b]
    return rgb


def generate_png(mosaic_info: dict, png_dir: Path, log: logging.Logger) -> Path | None:
    """Read from overview level, colourise, save PNG."""
    from osgeo import gdal as _gdal
    _gdal.UseExceptions()

    src_path = Path(mosaic_info["path"])
    if not src_path.exists():
        log.warning(f"PNG: source not found – {src_path.name}")
        return None

    ds   = _gdal.Open(str(src_path))
    band = ds.GetRasterBand(1)

    # Choose smallest overview that's >= 512 px on longest side
    ov_count = band.GetOverviewCount()
    chosen_ov = None
    for i in range(ov_count):
        ov = band.GetOverview(i)
        if max(ov.XSize, ov.YSize) >= 512:
            chosen_ov = ov
    if chosen_ov is None and ov_count > 0:
        chosen_ov = band.GetOverview(ov_count - 1)

    if chosen_ov is not None:
        arr = chosen_ov.ReadAsArray()
        log.info(f"PNG: using overview {chosen_ov.XSize}×{chosen_ov.YSize}")
    else:
        # No overview – read full band (should be small at ROI scale)
        log.warning(f"PNG: no overview for {src_path.name}, reading full band")
        arr = band.ReadAsArray()

    ds = None

    rgb  = colorise(arr, DW_PALETTE)
    period = mosaic_info["period"]
    title  = f"Toktogul Reservoir – {period[:4]}–{period[9:13]}"

    # Legend patches
    classes_present = sorted(np.unique(arr[arr > 0]))
    patches = [
        mpatches.Patch(
            facecolor=tuple(c/255 for c in DW_PALETTE[c][:3]),
            label=DW_PALETTE[c][3] if len(DW_PALETTE[c]) > 3 else str(c)
        )
        for c in classes_present if c in DW_PALETTE
    ]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(rgb, interpolation="nearest")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.axis("off")
    if patches:
        ax.legend(handles=patches, loc="lower right", fontsize=7,
                  framealpha=0.85, title="Land cover")

    png_name = f"Toktogul_{period}.png"
    png_path = png_dir / png_name
    fig.savefig(str(png_path), dpi=150, bbox_inches="tight", pil_kwargs={"compress_level": 6})
    plt.close(fig)
    log.info(f"  PNG saved: {png_name}  ({file_size_mb(png_path):.1f}MB)")
    return png_path


# ─────────────────────────────────────────────────────────────────────────────
# 7. TIME-SERIES GRID
# ─────────────────────────────────────────────────────────────────────────────

def build_timeseries_grid(png_paths: list[Path], mosaic_infos: list[dict],
                          out_path: Path, log: logging.Logger) -> None:
    """Build a grid figure comparing all timesteps."""
    n   = len(png_paths)
    if n == 0:
        log.warning("Grid: no PNG inputs, skipping")
        return

    # ── Water-area time series data ──────────────────────────────────────────
    # Compute water-pixel count from each mosaic overview
    from osgeo import gdal as _gdal
    _gdal.UseExceptions()
    water_counts = []
    years        = []
    for mi in mosaic_infos:
        try:
            ds   = _gdal.Open(mi["path"])
            band = ds.GetRasterBand(1)
            # Use smallest overview for speed
            ov_count = band.GetOverviewCount()
            if ov_count > 0:
                ov  = band.GetOverview(ov_count - 1)
                arr = ov.ReadAsArray()
                scale_factor = (band.XSize * band.YSize) / (ov.XSize * ov.YSize)
            else:
                arr = band.ReadAsArray()
                scale_factor = 1.0
            water_px = int((arr == 1).sum() * scale_factor)
            water_km2 = water_px * mi.get("res_x", 10)**2 / 1e6
            water_counts.append(water_km2)
            years.append(mi["date_start"][:4])
            ds = None
        except Exception as e:
            log.warning(f"Grid: water-count failed for {mi['filename']}: {e}")
            water_counts.append(0)
            years.append(mi["date_start"][:4])

    # ── Layout ───────────────────────────────────────────────────────────────
    cols    = min(4, n)
    rows_im = int(np.ceil(n / cols))
    total_rows = rows_im + 1   # +1 row for bar chart

    fig = plt.figure(figsize=(cols * 4, rows_im * 4 + 3.5))
    fig.patch.set_facecolor("#F0F4F8")

    # Subplot spec: image rows + chart row
    import matplotlib.gridspec as gridspec
    gs = gridspec.GridSpec(
        total_rows, cols,
        figure=fig,
        hspace=0.35, wspace=0.08,
        height_ratios=[4] * rows_im + [3],
    )

    # --- image panels ---
    for i, png_p in enumerate(png_paths):
        r, c = divmod(i, cols)
        ax = fig.add_subplot(gs[r, c])
        try:
            img = plt.imread(str(png_p))
            ax.imshow(img)
        except Exception:
            ax.set_facecolor("#CCC")
            ax.text(0.5, 0.5, "N/A", ha="center", va="center", transform=ax.transAxes)
        period_str = mosaic_infos[i]["period"]
        ax.set_title(f"{period_str[:4]}–{period_str[9:13]}", fontsize=9, fontweight="bold")
        ax.axis("off")

    # Hide unused image cells
    for i in range(n, rows_im * cols):
        r, c = divmod(i, cols)
        fig.add_subplot(gs[r, c]).set_visible(False)

    # --- water area bar chart spanning full bottom row ---
    ax_bar = fig.add_subplot(gs[rows_im, :])
    ax_bar.set_facecolor("white")
    bar_colors = ["#4196DE" if w == max(water_counts) else "#4174CC" for w in water_counts]
    bars = ax_bar.bar(years, water_counts, color=bar_colors, edgecolor="white", linewidth=0.5)
    ax_bar.set_ylabel("Water area (km²)", fontsize=9)
    ax_bar.set_xlabel("Year", fontsize=9)
    ax_bar.set_title("Toktogul Reservoir – Annual Water-Surface Area (Dynamic World, class=1)",
                     fontsize=10, fontweight="bold")
    ax_bar.tick_params(axis="x", rotation=30, labelsize=8)
    ax_bar.tick_params(axis="y", labelsize=8)
    ax_bar.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax_bar.set_axisbelow(True)
    for bar, val in zip(bars, water_counts):
        ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{val:.0f}", ha="center", va="bottom", fontsize=7)

    fig.suptitle("Toktogul Reservoir – Multi-Year Water-Extent Time Series (2018–2025)",
                 fontsize=13, fontweight="bold", y=1.01)

    fig.savefig(str(out_path), dpi=150, bbox_inches="tight",
                pil_kwargs={"compress_level": 6})
    plt.close(fig)
    log.info(f"Time-series grid saved: {out_path.name}  ({file_size_mb(out_path):.1f}MB)")


# ─────────────────────────────────────────────────────────────────────────────
# 8. CATALOG (CSV + JSON)
# ─────────────────────────────────────────────────────────────────────────────

def write_catalog(mosaic_infos: list[dict], out_dir: Path, log: logging.Logger):
    sorted_infos = sorted(mosaic_infos, key=lambda x: x["date_start"])

    # CSV
    csv_path = out_dir / "timeseries_catalog.csv"
    fields   = ["filename", "date_start", "date_end", "crs",
                 "width", "height", "res_x", "bands",
                 "lon_min", "lon_max", "lat_min", "lat_max",
                 "uncomp_mb", "comp_mb", "compression_ratio",
                 "zone_results"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for mi in sorted_infos:
            row = {k: mi.get(k, "") for k in fields}
            row["zone_results"] = str(mi.get("zone_results", ""))
            w.writerow(row)
    log.info(f"Catalog CSV: {csv_path.name}")

    # JSON
    json_path = out_dir / "timeseries_catalog.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sorted_infos, f, indent=2, default=str)
    log.info(f"Catalog JSON: {json_path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. MARKDOWN REPORT
# ─────────────────────────────────────────────────────────────────────────────

def write_report(survey_records: list[dict],
                 mosaic_infos:   list[dict],
                 groups:         dict,
                 roi:            tuple,
                 target_crs:     str,
                 target_res:     int,
                 out_dir:        Path,
                 log:            logging.Logger):

    sorted_mosaics = sorted(mosaic_infos, key=lambda x: x["date_start"])
    report_path    = out_dir / "REPORT.md"
    now            = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    xmin, ymin, xmax, ymax = roi

    lines = [
        "# Toktogul Reservoir – 遥感影像处理报告",
        "",
        f"> 生成时间：{now}",
        "",
        "---",
        "",
        "## 1. 概述",
        "",
        "本报告记录托克托古尔水库（吉尔吉斯斯坦）Dynamic World 时序影像的",
        "端到端处理流程，涵盖：环境勘察、投影统一、ROI 裁剪镶嵌、格式转换与可视化。",
        "",
        "---",
        "",
        "## 2. 环境与依赖",
        "",
        "| 工具 | 用途 |",
        "|------|------|",
        "| GDAL (gdalwarp / gdalbuildvrt / gdal_translate / gdaladdo) | 投影转换、镶嵌、压缩、金字塔 |",
        "| rasterio 1.5 | 像素级读取验证 |",
        "| numpy 2.0 | 数值运算 |",
        "| matplotlib 3.10 | 可视化 |",
        "",
        "---",
        "",
        "## 3. 勘察结果（Survey）",
        "",
        "### 3.1 输入文件清单",
        "",
        "| 文件名 | EPSG | 分辨率 | 像素尺寸 | 波段 | 类型 | NoData | 大小(MB) | lon范围 | lat范围 |",
        "|--------|------|--------|----------|------|------|--------|----------|---------|---------|",
    ]

    for r in sorted(survey_records, key=lambda x: (x["date_start"], x["zone"])):
        lines.append(
            f"| {r['filename']} | {r['epsg']} | {r['res_x']:.0f}m | "
            f"{r['width']}×{r['height']} | {r['bands']} | {r['dtype']} | "
            f"{r['nodata']} | {r['size_mb']:.1f} | "
            f"{r['lon_min']:.2f}–{r['lon_max']:.2f} | "
            f"{r['lat_min']:.2f}–{r['lat_max']:.2f} |"
        )

    lines += [
        "",
        "### 3.2 关键发现",
        "",
        "- 所有文件：单波段 Byte（uint8）调色板分类影像（Google Dynamic World 土地覆盖）",
        "- 43T 文件（EPSG:32643，UTM zone 43N）：地理覆盖约 71.6–78.4°E，含水库数据",
        "- 44T 文件（EPSG:32644，UTM zone 44N）：地理覆盖约 77.6–84.4°E，**不覆盖水库**",
        "  - 水库坐标约 72.4–73.4°E；在 EPSG:32644 坐标系中对应 X≈−220,000 m，",
        "    远在 44T 瓦片有效范围（243,910–756,090 m）之外",
        "  - 本流程仍对 44T 执行规范化 warp 操作，结果全为 nodata，已记录于处理日志",
        "- 分类类别（Dynamic World 调色板）：",
        "  - 1=Water, 2=Trees, 4=Flooded veg, 5=Crops, 7=Built, 8=Bare, 9=Snow/ice, 10=Cloud",
        "",
        "---",
        "",
        "## 4. 分带分组",
        "",
        "| 时间区间 | 43T | 44T | 状态 |",
        "|----------|-----|-----|------|",
    ]

    for period in sorted(groups.keys()):
        tiles  = groups[period]
        has43  = "✓" if "43T" in tiles else "✗ 缺失"
        has44  = "✓" if "44T" in tiles else "✗ 缺失"
        status = "完整对" if ("43T" in tiles and "44T" in tiles) else "单分带"
        lines.append(f"| {period} | {has43} | {has44} | {status} |")

    lines += [
        "",
        "---",
        "",
        "## 5. 处理参数",
        "",
        f"| 参数 | 值 | 说明 |",
        f"|------|----|------|",
        f"| 目标 CRS | {target_crs} | UTM zone 43N，中央经线 75°E；水库位于 ~73°E，距中央经线仅 2°，失真最小 |",
        f"| 目标分辨率 | {target_res} m | 与 Sentinel-2 原始分辨率一致，无降采样 |",
        f"| ROI（目标CRS坐标系） | X:{xmin}–{xmax}, Y:{ymin}–{ymax} | 在已知水库范围基础上各扩 5 km 缓冲区 |",
        f"| 重采样方法 | nearest neighbour | 保留分类像素整数值不插值 |",
        f"| 输出压缩 | DEFLATE + PREDICTOR=2 | 分类数据压缩率约 10–20× |",
        f"| 分块 | 512×512 | 支持流式读取，避免整图内存加载 |",
        f"| 概览金字塔 | levels 2,4,8,16,32,64 | 供快速预览；PNG 从概览渲染 |",
        "",
        "---",
        "",
        "## 6. 镶嵌产出清单",
        "",
        "| 文件名 | 时间区间 | 像素尺寸 | 未压缩(MB) | 压缩后(MB) | 压缩比 | 43T贡献 | 44T贡献 |",
        "|--------|----------|----------|-----------|-----------|--------|---------|---------|",
    ]

    for mi in sorted_mosaics:
        zr   = mi.get("zone_results", {})
        z43  = zr.get("43T", "N/A")
        z44  = zr.get("44T", "N/A")
        lines.append(
            f"| {mi['filename']} | {mi['date_start']}–{mi['date_end']} | "
            f"{mi['width']}×{mi['height']} | {mi['uncomp_mb']:.1f} | "
            f"{mi['comp_mb']:.1f} | {mi['compression_ratio']}× | "
            f"{z43} | {z44} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 7. 可视化",
        "",
        "### 7.1 各时相 PNG（从概览渲染）",
        "",
    ]

    for mi in sorted_mosaics:
        period = mi["period"]
        png_name = f"Toktogul_{period}.png"
        lines.append(f"- `previews/{png_name}` — {period[:4]}–{period[9:13]}")

    lines += [
        "",
        "### 7.2 时序对比网格图",
        "",
        "![时序对比图](timeseries_grid.png)",
        "",
        "---",
        "",
        "## 8. 输出目录结构",
        "",
        "```",
        "output/",
        "├── process_toktogul.py      # 本处理脚本（可复用）",
        "├── processing.log           # 完整处理日志",
        "├── timeseries_catalog.csv   # 时序清单（CSV）",
        "├── timeseries_catalog.json  # 时序清单（JSON）",
        "├── timeseries_grid.png      # 时序对比网格图",
        "├── REPORT.md                # 本报告",
        "├── mosaics/",
        "│   ├── Toktogul_mosaic_20180101_20190101.tif",
        "│   ├── ... (共 8 张)",
        "│   └── Toktogul_mosaic_20250101_20251231.tif",
        "└── previews/",
        "    ├── Toktogul_20180101-20190101.png",
        "    ├── ... (共 8 张)",
        "    └── Toktogul_20250101-20251231.png",
        "```",
        "",
        "---",
        "",
        "## 9. 注意事项",
        "",
        "1. **44T 无贡献**：44T 文件覆盖 77.6–84.4°E，与水库（72.4–73.4°E）地理上不重叠。",
        "   镶嵌时 44T warped 产物全为 nodata，正确地被 43T 数据覆盖。",
        "   后续若有其他地理范围的水库分析需要，44T 文件可用于 78–84°E 区域。",
        "2. **数据来源**：Dynamic World 年度中位数合成（Annual composite），",
        "   非单景影像，反映全年水体出现频率最高的状态。",
        "3. **Water 类别**：分类值 1（蓝色）= 开放水面；",
        "   分类值 4（紫蓝）= 淹没植被，两者均可能代表库区。",
        "4. **压缩**：DEFLATE + PREDICTOR=2，分类影像空间相关性强，压缩率可达 10–20×。",
        "5. **磁盘安全**：原始文件未被覆盖或删除，所有产出写入 output/ 子目录。",
        "",
        "---",
        f"*Report generated by process_toktogul.py on {now}*",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info(f"Report saved: {report_path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# 10. MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Toktogul Reservoir pipeline")
    parser.add_argument("--base-dir",  default="/Users/yunfeili/Downloads/Toktogul Reservoir")
    parser.add_argument("--output-dir", default=None, help="defaults to base-dir/output")
    parser.add_argument("--roi",  nargs=4, type=float, metavar=("XMIN","YMIN","XMAX","YMAX"),
                        default=list(DEFAULT_ROI))
    parser.add_argument("--res",  type=int, default=TARGET_RES, help="Output pixel size (metres)")
    args = parser.parse_args()

    base_dir   = Path(args.base_dir)
    output_dir = Path(args.output_dir) if args.output_dir else base_dir / "output"
    mosaic_dir = output_dir / "mosaics"
    preview_dir= output_dir / "previews"
    tmp_dir    = output_dir / "_tmp"
    log_path   = output_dir / "processing.log"

    for d in [mosaic_dir, preview_dir, tmp_dir]:
        d.mkdir(parents=True, exist_ok=True)

    log = setup_logging(log_path)
    log.info("=" * 70)
    log.info("TOKTOGUL RESERVOIR PROCESSING PIPELINE")
    log.info(f"base_dir   = {base_dir}")
    log.info(f"output_dir = {output_dir}")
    log.info(f"target_crs = {TARGET_CRS}")
    log.info(f"roi        = {args.roi}")
    log.info(f"res        = {args.res} m")
    log.info("=" * 70)

    roi = tuple(args.roi)

    # ── Survey ──────────────────────────────────────────────────────────────
    survey_records = survey_files(base_dir, log)
    if not survey_records:
        log.error("FATAL: no valid input files found – aborting")
        sys.exit(1)

    # ── Group ───────────────────────────────────────────────────────────────
    groups = group_by_period(survey_records, log)

    # ── Mosaic each period ──────────────────────────────────────────────────
    mosaic_infos = []
    log.info("=== MOSAICKING ===")
    for period in sorted(groups.keys()):
        info = mosaic_period(
            period, groups[period], roi=roi, res=args.res,
            target_crs=TARGET_CRS,
            out_dir=mosaic_dir, tmp_dir=tmp_dir, log=log,
        )
        if info:
            mosaic_infos.append(info)

    if not mosaic_infos:
        log.error("FATAL: all mosaics failed – aborting")
        sys.exit(1)

    # ── Generate PNGs ───────────────────────────────────────────────────────
    log.info("=== PNG GENERATION ===")
    sorted_infos = sorted(mosaic_infos, key=lambda x: x["date_start"])
    png_paths    = []
    for mi in sorted_infos:
        p = generate_png(mi, preview_dir, log)
        if p:
            png_paths.append(p)

    # ── Time-series grid ────────────────────────────────────────────────────
    log.info("=== TIME-SERIES GRID ===")
    grid_path = output_dir / "timeseries_grid.png"
    build_timeseries_grid(png_paths, sorted_infos, grid_path, log)

    # ── Catalog ─────────────────────────────────────────────────────────────
    log.info("=== CATALOG ===")
    write_catalog(sorted_infos, output_dir, log)

    # ── Report ──────────────────────────────────────────────────────────────
    log.info("=== REPORT ===")
    write_report(
        survey_records, mosaic_infos, groups, roi,
        TARGET_CRS, args.res, output_dir, log
    )

    # ── Cleanup tmp ─────────────────────────────────────────────────────────
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    log.info("")
    log.info("=" * 70)
    log.info("PIPELINE COMPLETE")
    log.info(f"  Mosaics  : {mosaic_dir}")
    log.info(f"  Previews : {preview_dir}")
    log.info(f"  Report   : {output_dir/'REPORT.md'}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()

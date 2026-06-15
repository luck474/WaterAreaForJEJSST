#!/usr/bin/env python3
"""
ERA5 月均气温 + 降水下载脚本
================================
覆盖吉尔吉斯斯坦 + 塔里木盆地上游范围：
  bbox = [68, 38, 82, 45]  (lon_min, lat_min, lon_max, lat_max)

前提：
  pip install cdsapi
  在 ~/.cdsapirc 中填入 CDS API Key（注册 https://cds.climate.copernicus.eu 后免费获取）

用法：
  python3 download_era5.py
"""

import cdsapi
from pathlib import Path

OUT = Path("/Users/yunfeili/Downloads/Toktogul Reservoir/climate_data")
OUT.mkdir(exist_ok=True)

# 研究区域：吉尔吉斯+天山+塔里木上游
AREA = [45, 68, 38, 82]   # North / West / South / East

client = cdsapi.Client()

YEARS = [str(y) for y in range(1979, 2026)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]

# ── 月均 2m 气温 ──────────────────────────────────────────────────────────────
print("下载月均气温 (1979-2025)…")
client.retrieve(
    "reanalysis-era5-single-levels-monthly-means",
    {
        "product_type": "monthly_averaged_reanalysis",
        "variable": "2m_temperature",
        "year": YEARS,
        "month": MONTHS,
        "time": "00:00",
        "area": AREA,
        "format": "netcdf",
    },
    str(OUT / "era5_t2m_monthly_1979_2025.nc"),
)

# ── 月均降水量 ────────────────────────────────────────────────────────────────
print("下载月均降水 (1979-2025)…")
client.retrieve(
    "reanalysis-era5-single-levels-monthly-means",
    {
        "product_type": "monthly_averaged_reanalysis",
        "variable": "total_precipitation",
        "year": YEARS,
        "month": MONTHS,
        "time": "00:00",
        "area": AREA,
        "format": "netcdf",
    },
    str(OUT / "era5_precip_monthly_1979_2025.nc"),
)

print("\n✅ ERA5 下载完成 →", OUT)
print("   下一步：运行 analyze_climate_flow.py 做相关性分析")

#!/bin/bash
# 挂机下载脚本 — 关闭终端也继续运行
# 用法：bash output/overnight_download.sh
# 日志：climate_data/download.log

set -e
BASE="/Users/yunfeili/Downloads/Toktogul Reservoir"
LOG="$BASE/climate_data/download.log"
mkdir -p "$BASE/climate_data"

echo "====== 开始挂机下载 $(date) ======" | tee -a "$LOG"

# ── 任务1：ERA5-Land 降水 + 积雪 + 径流（1981–2024）─────────────────────────
ERA5_OUT="$BASE/climate_data/era5_land_hydro_1981_2024.nc"
if [ ! -f "$ERA5_OUT" ]; then
  echo "[$(date +%H:%M)] 下载 ERA5-Land 水文变量..." | tee -a "$LOG"
  python3 - << 'PYEOF' 2>&1 | tee -a "$LOG"
import cdsapi, sys, time
from pathlib import Path

out = Path("/Users/yunfeili/Downloads/Toktogul Reservoir/climate_data/era5_land_hydro_1981_2024.nc")
c = cdsapi.Client()

for attempt in range(10):
    try:
        c.retrieve("reanalysis-era5-land-monthly-means", {
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": [
                "total_precipitation",
                "snowfall",
                "runoff",
                "snow_depth_water_equivalent",
                "snowmelt",
            ],
            "year":  [str(y) for y in range(1981, 2025)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time":  ["00:00"],
            "area":  [45, 68, 38, 82],
            "data_format": "netcdf",
        }, str(out))
        print(f"✅ ERA5-Land 下载成功: {out.stat().st_size//1024//1024} MB")
        sys.exit(0)
    except Exception as e:
        err = str(e)
        wait = min(30 * (attempt + 1), 300)
        print(f"⚠️  第{attempt+1}次失败: {err[:100]}")
        print(f"   等待 {wait}s 后重试...")
        time.sleep(wait)

print("❌ ERA5-Land 下载失败，已重试10次")
sys.exit(1)
PYEOF
else
  echo "[$(date +%H:%M)] ERA5-Land 已存在，跳过" | tee -a "$LOG"
fi

# ── 任务2：RGI 7.0 冰川轮廓（中亚）── 直接 HTTP，不需要轮询 ─────────────────
RGI_OUT="$BASE/climate_data/rgi70_CentralAsia.zip"
if [ ! -f "$RGI_OUT" ]; then
  echo "[$(date +%H:%M)] 下载 RGI 7.0 冰川数据（中亚）..." | tee -a "$LOG"
  # RGI 7.0 区域 13 = 中亚 (Central Asia)
  curl -L --retry 5 --retry-delay 10 --max-time 300 \
    "https://nsidc.org/data/files/RGI7/rgi70-regions/rgi70-14_rgi70-13.zip" \
    -o "$RGI_OUT" 2>&1 | tee -a "$LOG" || \
  # 备用镜像
  curl -L --retry 5 --retry-delay 10 --max-time 300 \
    "https://www.glims.org/RGI/rgi70/14_rgi70-CentralAsia.zip" \
    -o "$RGI_OUT" 2>&1 | tee -a "$LOG" && \
  echo "✅ RGI 下载成功" | tee -a "$LOG"
else
  echo "[$(date +%H:%M)] RGI 已存在，跳过" | tee -a "$LOG"
fi

# ── 任务3：重新生成地图（如果有新数据）──────────────────────────────────────
echo "[$(date +%H:%M)] 重新生成地图..." | tee -a "$LOG"
cd "$BASE" && python3 output/download_and_build.py 2>&1 | tee -a "$LOG"

echo "====== 挂机下载完成 $(date) ======" | tee -a "$LOG"
echo "请用 open '$BASE/output/integrated_map.html' 查看升级版地图"

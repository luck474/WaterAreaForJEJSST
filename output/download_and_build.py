#!/usr/bin/env python3
"""
ERA5 下载 + 地图自动升级一体化脚本
=====================================
运行后自动：
  1. 下载 ERA5 月均气温 + 降水（1979–2024，吉尔吉斯+天山区域）
  2. 计算气候指标（距平、趋势、年际方差）
  3. 重新生成 integrated_map.html（精度升级版）

区域：[68°E–82°E, 38°N–45°N]  覆盖吉尔吉斯斯坦 + 萨雷扎兹流域 + 塔里木盆地上游
大小估算：约 80–120 MB（月均数据比日数据小很多）
"""

import cdsapi, netCDF4 as nc4
import numpy as np
from pathlib import Path
import subprocess, sys, json

BASE    = Path("/Users/yunfeili/Downloads/Toktogul Reservoir")
OUT     = BASE / "output"
CLIMATE = BASE / "climate_data"
CLIMATE.mkdir(exist_ok=True)

AREA   = [45, 68, 38, 82]   # N W S E
YEARS  = [str(y) for y in range(1979, 2025)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DATASET = "reanalysis-era5-single-levels-monthly-means"

# ── 1. 下载 ──────────────────────────────────────────────────────────────────
def retrieve_with_retry(c, dataset, params, dest, label, max_attempts=5):
    """Wrap cdsapi.retrieve with retry on transient SSL/network errors."""
    import time
    for attempt in range(1, max_attempts + 1):
        try:
            c.retrieve(dataset, params, str(dest))
            print(f"   ✅ {label} 保存至 {dest}")
            return
        except Exception as e:
            err = str(e)
            if attempt < max_attempts and any(k in err for k in ("SSL", "ConnectionError", "Timeout", "EOF", "Max retries")):
                wait = 15 * attempt
                print(f"   ⚠️  第{attempt}次尝试失败（{err[:80]}），{wait}s 后重试…")
                time.sleep(wait)
            else:
                raise

def download():
    c = cdsapi.Client()

    t2m_path    = CLIMATE / "era5_t2m_monthly_1979_2024.nc"
    precip_path = CLIMATE / "era5_precip_monthly_1979_2024.nc"

    if not t2m_path.exists():
        print("⬇️  下载气温数据（2m temperature）…")
        retrieve_with_retry(c, DATASET, {
            "product_type": "monthly_averaged_reanalysis",
            "variable":     "2m_temperature",
            "year":  YEARS, "month": MONTHS, "time": "00:00",
            "area":  AREA,  "data_format": "netcdf",
        }, t2m_path, "气温")
    else:
        print(f"   ✅ 气温文件已存在，跳过下载")

    if not precip_path.exists():
        print("⬇️  下载降水数据（total precipitation）…")
        retrieve_with_retry(c, DATASET, {
            "product_type": "monthly_averaged_reanalysis",
            "variable":     "total_precipitation",
            "year":  YEARS, "month": MONTHS, "time": "00:00",
            "area":  AREA,  "data_format": "netcdf",
        }, precip_path, "降水")
    else:
        print(f"   ✅ 降水文件已存在，跳过下载")

    return t2m_path, precip_path

# ── 2. 处理 ERA5 → 气候指标 ─────────────────────────────────────────────────
def process_era5(t2m_path, precip_path):
    print("\n📊 处理 ERA5 数据…")

    # ── 气温 ──
    ds_t = nc4.Dataset(str(t2m_path))
    # 找时间变量
    time_var = next(v for v in ["valid_time","time"] if v in ds_t.variables)
    times  = nc4.num2date(ds_t.variables[time_var][:],
                          units=ds_t.variables[time_var].units,
                          calendar=getattr(ds_t.variables[time_var],'calendar','standard'))
    lons   = np.array(ds_t.variables["longitude"][:])
    lats   = np.array(ds_t.variables["latitude"][:])
    t2m_k  = np.array(ds_t.variables["t2m"][:])   # (time, lat, lon), Kelvin
    ds_t.close()

    t2m_c = t2m_k - 273.15  # → Celsius
    yrs_nc = np.array([t.year for t in times])
    mos_nc = np.array([t.month for t in times])

    # 年均气温（流域平均）
    # 定义纳伦+萨雷扎兹流域核心区
    lat_mask = (lats >= 40) & (lats <= 43)
    lon_mask = (lons >= 70) & (lons <= 81)
    basin_t  = t2m_c[:, np.ix_(np.where(lat_mask)[0], np.where(lon_mask)[0])].mean(axis=(1,2))

    # 年均
    ann_temps = {}
    for yr in range(1979, 2025):
        idx = yrs_nc == yr
        if idx.sum() > 0:
            ann_temps[yr] = float(basin_t[idx].mean())

    # 基准期 1981-2010 均值
    baseline_t = np.mean([v for k,v in ann_temps.items() if 1981<=k<=2010])

    # 年均气温距平
    temp_anom_annual = {yr: round(v - baseline_t, 2) for yr, v in ann_temps.items()}

    # 近年（2018-2024）逐像素距平（用于地图叠加）
    base_mask = (yrs_nc >= 1981) & (yrs_nc <= 2010)
    recent_mask = yrs_nc >= 2018
    baseline_grid = t2m_c[base_mask].mean(axis=0)
    recent_grid   = t2m_c[recent_mask].mean(axis=0)
    anom_grid     = recent_grid - baseline_grid

    # ── 降水 ──
    ds_p = nc4.Dataset(str(precip_path))
    time_var_p = next(v for v in ["valid_time","time"] if v in ds_p.variables)
    times_p = nc4.num2date(ds_p.variables[time_var_p][:],
                           units=ds_p.variables[time_var_p].units,
                           calendar=getattr(ds_p.variables[time_var_p],'calendar','standard'))
    precip_raw = np.array(ds_p.variables["tp"][:])   # m/day or m/hr
    ds_p.close()

    yrs_p = np.array([t.year for t in times_p])
    # 换算为 mm/month（ERA5 月均值单位是 m/s，乘以秒数）
    precip_mm = precip_raw * 1000 * 30.44 * 86400  # rough mm/month

    # 流域平均年降水
    basin_p = precip_mm[:, np.ix_(np.where(lat_mask)[0], np.where(lon_mask)[0])].mean(axis=(1,2))
    ann_precip = {}
    for yr in range(1979, 2025):
        idx = yrs_p == yr
        if idx.sum() > 0:
            ann_precip[yr] = float(basin_p[idx].sum())  # mm/yr

    baseline_p = np.mean([v for k,v in ann_precip.items() if 1981<=k<=2010])
    precip_anom_annual = {yr: round((v-baseline_p)/baseline_p*100, 1) for yr,v in ann_precip.items()}

    # ── 生成地图叠加 GeoJSON（降采样格点）──
    step = 2
    lo_grid, la_grid = np.meshgrid(lons, lats)
    era5_pts = []
    for i in range(0, anom_grid.shape[0], step):
        for j in range(0, anom_grid.shape[1], step):
            v = float(anom_grid[i, j])
            if not np.isnan(v):
                era5_pts.append({
                    "type": "Feature",
                    "geometry": {"type": "Point",
                                 "coordinates": [float(lo_grid[i,j]), float(la_grid[i,j])]},
                    "properties": {"anom": round(v, 2)},
                })

    # ── 45年趋势线 ──
    yr_arr = np.array(sorted(ann_temps.keys()))
    ta_arr = np.array([ann_temps[y] for y in yr_arr])
    slope  = float(np.polyfit(yr_arr, ta_arr, 1)[0])  # °C/yr

    print(f"   气温基准（1981-2010）：{baseline_t:.2f}°C")
    print(f"   近年（2018-2024）平均距平：+{np.mean([temp_anom_annual.get(y,0) for y in range(2018,2025)]):.2f}°C")
    print(f"   45年趋势：+{slope*10:.3f}°C/decade")
    print(f"   降水基准：{baseline_p:.0f} mm/yr")
    print(f"   格点数：{len(era5_pts)}")

    return {
        "temp_anom_annual": {str(k):v for k,v in temp_anom_annual.items()},
        "precip_anom_annual": {str(k):v for k,v in precip_anom_annual.items()},
        "era5_pts": era5_pts,
        "slope_per_decade": round(slope*10, 3),
        "baseline_t": round(baseline_t, 2),
        "baseline_p": round(baseline_p, 0),
        "lons": lons.tolist(),
        "lats": lats.tolist(),
    }

# ── 3. 重新生成地图 ─────────────────────────────────────────────────────────
def rebuild_map(era5_data):
    print("\n🗺️  重新生成地图（ERA5 精度版）…")
    result = subprocess.run(
        [sys.executable, str(OUT / "generate_integrated_map.py")],
        capture_output=True, text=True, cwd=str(BASE)
    )
    if result.returncode != 0:
        print("地图生成失败:", result.stderr[-500:])
    else:
        print(result.stdout)

    # 保存 ERA5 处理结果供地图脚本读取
    era5_cache = CLIMATE / "era5_processed.json"
    save_data = {
        "temp_anom_annual": era5_data["temp_anom_annual"],
        "precip_anom_annual": era5_data["precip_anom_annual"],
        "slope_per_decade": era5_data["slope_per_decade"],
        "baseline_t": era5_data["baseline_t"],
        "baseline_p": era5_data["baseline_p"],
        "era5_pts_count": len(era5_data["era5_pts"]),
    }
    era5_cache.write_text(json.dumps(save_data, ensure_ascii=False, indent=2))
    print(f"   ERA5 缓存保存至 {era5_cache}")

    # 直接把 ERA5 数据注入地图 HTML
    html_path = OUT / "integrated_map.html"
    html = html_path.read_text(encoding="utf-8")

    era5_fc = {"type":"FeatureCollection","features":era5_data["era5_pts"]}
    era5_js_inject = (
        f"const ERA5_READY = true;\n"
        f"const ERA5_LAYERS = {{temp_anom: {json.dumps(era5_fc,separators=(',',':'))}}};\n"
        f"const ERA5_STATS = {json.dumps({'slope':era5_data['slope_per_decade'],'baseline_t':era5_data['baseline_t'],'temp_anom_annual':era5_data['temp_anom_annual'],'precip_anom_annual':era5_data['precip_anom_annual']},ensure_ascii=False)};\n"
    )

    # 替换占位符
    html = html.replace(
        "const ERA5_READY = false; const ERA5_LAYERS = {};",
        era5_js_inject
    )

    # 更新气温距平数组（用 ERA5 实测替换文献估算）
    yrs_map = [2018,2019,2020,2021,2022,2023,2024,2025]
    real_anoms = [era5_data["temp_anom_annual"].get(str(y), None) for y in yrs_map]
    if all(v is not None for v in real_anoms):
        old_line = f"const TEMP_ANOM={json.dumps([0.8,0.9,1.1,0.7,1.0,1.3,1.4,1.5])};"
        new_line = f"const TEMP_ANOM={json.dumps([round(v,2) for v in real_anoms])};  // ERA5 实测"
        html = html.replace(old_line, new_line)
        print(f"   气温距平已更新为 ERA5 实测值: {[round(v,2) for v in real_anoms]}")

    html_path.write_text(html, encoding="utf-8")
    print(f"   ✅ integrated_map.html 已升级至 ERA5 精度版（{html_path.stat().st_size//1024} KB）")

# ══ Main ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("ERA5 下载 + 地图升级流程")
    print("=" * 60)

    t2m_path, precip_path = download()
    era5_data = process_era5(t2m_path, precip_path)
    rebuild_map(era5_data)

    print("\n" + "=" * 60)
    print("✅  完成！请刷新 integrated_map.html 查看 ERA5 精度升级版")
    print(f"   气候趋势：{era5_data['slope_per_decade']:+.3f}°C/十年（45年实测）")
    print("=" * 60)

#!/usr/bin/env python3
"""
Toktogul Reservoir – GIS Analysis Map Generator
================================================
栅格 → 矢量（gdal.Polygonize）→ GeoJSON → Leaflet 卫星底图

产出：output/gis_map.html
  · 8 年水面边界（矢量多边形，可逐年切换）
  · 2018→2025 水面变化检测（消退/新增/稳定三类矢量）
  · 2025 年土地覆盖分类（农田/建设/植被/积雪 独立图层）
  · 左侧图层控制面板 + 实时统计
  · 底部 Chart.js 折线图（面积 + 积雪）
  · 点击要素显示详细属性
"""

import json
from pathlib import Path
from osgeo import gdal, ogr, osr
import numpy as np

gdal.UseExceptions()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE   = Path("/Users/yunfeili/Downloads/Toktogul Reservoir")
OUT    = BASE / "output"
MOSAIC = OUT  / "mosaics"

PERIODS = [
    ("20180101","20190101","2018"),
    ("20190101","20200101","2019"),
    ("20200101","20210101","2020"),
    ("20210101","20220101","2021"),
    ("20220101","20230101","2022"),
    ("20230101","20240101","2023"),
    ("20240101","20241231","2024"),
    ("20250101","20251231","2025"),
]

# ── Reservoir params ──────────────────────────────────────────────────────────
P = dict(total=19.5, useful=14.1, dead=5.4, full_area=284.0, dead_area=50.0)

def vol(A):
    if A <= P["dead_area"]: return P["dead"]
    r = min((A - P["dead_area"]) / (P["full_area"] - P["dead_area"]), 1.0)
    return round(P["dead"] + P["useful"] * r**1.5, 2)

def util(V):
    return round((V - P["dead"]) / P["useful"] * 100, 1)

# ── Water level estimation (area → elevation) ─────────────────────────────────
# Linear interpolation from known points:
# full pool 284 km² → 902 m;  dead pool 50 km² → 820 m
def elev(A):
    A = max(50.0, min(284.0, A))
    return round(820 + (A - 50) / (284 - 50) * (902 - 820), 1)

# ── Pre-computed regional snow ────────────────────────────────────────────────
REG_SNOW = dict(zip(
    ["2018","2019","2020","2021","2022","2023","2024","2025"],
    [4264.3,6996.7,7669.2,3908.9,4331.8,7911.0,6680.4,2654.1]
))

# ── Core: raster → vector ─────────────────────────────────────────────────────
def read_ov(path, ov_level):
    ds   = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    ov   = band.GetOverview(ov_level)
    ov_w, ov_h = ov.XSize, ov.YSize
    arr  = np.frombuffer(ov.ReadRaster(), dtype=np.uint8).reshape(ov_h, ov_w)
    gt   = ds.GetGeoTransform()
    proj = ds.GetProjection()
    sx   = ds.RasterXSize / ov_w
    sy   = ds.RasterYSize / ov_h
    ov_gt = (gt[0], gt[1]*sx, gt[2], gt[3], gt[4], gt[5]*sy)
    ds = None
    return arr, ov_gt, proj, ov_w, ov_h

def make_mem_raster(arr, gt, proj):
    drv = gdal.GetDriverByName('MEM')
    h, w = arr.shape
    mem  = drv.Create('', w, h, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(gt); mem.SetProjection(proj)
    mb   = mem.GetRasterBand(1)
    mb.WriteArray(arr); mb.SetNoDataValue(0)
    return mem

def polygonize_to_wgs84(mem_ds, proj_wkt, simplify_m=120, min_km2=0.2, class_val=1):
    """Polygonize mem_ds band-1, simplify, reproject to WGS84."""
    src_srs = osr.SpatialReference(); src_srs.ImportFromWkt(proj_wkt)
    tgt_srs = osr.SpatialReference(); tgt_srs.ImportFromEPSG(4326)
    tgt_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    xfm = osr.CoordinateTransformation(src_srs, tgt_srs)

    mem_ogr = ogr.GetDriverByName('MEM').CreateDataSource('')
    lyr     = mem_ogr.CreateLayer('', srs=src_srs)
    lyr.CreateField(ogr.FieldDefn('v', ogr.OFTInteger))
    gdal.Polygonize(mem_ds.GetRasterBand(1), None, lyr, 0, [], callback=None)

    feats = []
    for feat in lyr:
        if feat.GetField('v') != class_val: continue
        g = feat.GetGeometryRef()
        if g is None or g.IsEmpty(): continue
        area_m2 = g.GetArea()
        if area_m2 < min_km2 * 1e6: continue
        s = g.Simplify(simplify_m)
        if s is None or s.IsEmpty(): continue
        s.Transform(xfm)
        feats.append((area_m2, json.loads(s.ExportToJson())))
    mem_ogr.Destroy()
    return feats   # list of (area_m2, geom_dict)

# ─────────────────────────────────────────────────────────────────────────────
print("Vectorising water boundaries (all 8 years)…")
# ─────────────────────────────────────────────────────────────────────────────
OV_LVL = 2   # 663×700 px → ~80 m effective pixel

water_geojson = {}   # year → GeoJSON FeatureCollection string
stats = {}           # year → dict

for start, end, yr in PERIODS:
    path = MOSAIC / f"Toktogul_mosaic_{start}_{end}.tif"

    # Full-res stats
    ds_full  = gdal.Open(str(path))
    arr_full = ds_full.GetRasterBand(1).ReadAsArray()
    km2      = 100 / 1e6
    water_km2 = float((arr_full == 1).sum() * km2)
    V = vol(water_km2); U = util(V); EL = elev(water_km2)
    stats[yr] = dict(
        water=round(water_km2,1), vol=V, util=U, elev=EL,
        crops=round(float((arr_full==5).sum()*km2),1),
        built=round(float((arr_full==7).sum()*km2),1),
        trees=round(float((arr_full==2).sum()*km2),1),
        snow =round(float((arr_full==9).sum()*km2),1),
        reg_snow=REG_SNOW[yr],
    )
    ds_full = None

    # Vectorise water
    arr_ov, ov_gt, proj, ow, oh = read_ov(path, OV_LVL)
    water_mask = (arr_ov == 1).astype(np.uint8)
    mem = make_mem_raster(water_mask, ov_gt, proj)
    feats_raw = polygonize_to_wgs84(mem, proj, simplify_m=120)
    mem = None

    features = [
        {"type":"Feature",
         "geometry": gd,
         "properties": {"year": yr, "area_km2": round(a/1e6,2),
                        "vol_km3": V, "util_pct": U, "elev_m": EL}}
        for a, gd in feats_raw
    ]
    water_geojson[yr] = json.dumps({"type":"FeatureCollection","features":features})
    sz = len(water_geojson[yr]) / 1024
    print(f"  {yr}: {len(features)} polygon(s)  {water_km2:.1f} km²  {sz:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
print("Vectorising change detection (2018 vs 2025)…")
# ─────────────────────────────────────────────────────────────────────────────
path18 = MOSAIC / f"Toktogul_mosaic_{PERIODS[0][0]}_{PERIODS[0][1]}.tif"
path25 = MOSAIC / f"Toktogul_mosaic_{PERIODS[-1][0]}_{PERIODS[-1][1]}.tif"

arr18, ov_gt18, proj18, ow, oh = read_ov(path18, OV_LVL)
arr25, ov_gt25, _,     _,  _  = read_ov(path25, OV_LVL)

w18 = (arr18 == 1); w25 = (arr25 == 1)
# 3-class change raster: 1=stable, 2=lost, 3=gained
change_arr = np.zeros((oh, ow), dtype=np.uint8)
change_arr[w18 &  w25] = 1
change_arr[w18 & ~w25] = 2
change_arr[~w18 & w25] = 3

change_feats = {1:[], 2:[], 3:[]}
for cls in (1, 2, 3):
    mask = (change_arr == cls).astype(np.uint8)
    mem  = make_mem_raster(mask, ov_gt18, proj18)
    for a, gd in polygonize_to_wgs84(mem, proj18, simplify_m=120, min_km2=0.15):
        change_feats[cls].append({
            "type":"Feature","geometry":gd,
            "properties":{"change": ["","stable","lost","gained"][cls],
                          "area_km2": round(a/1e6,2)}
        })
    mem = None

change_geojson = json.dumps({
    "type":"FeatureCollection",
    "features": change_feats[1] + change_feats[2] + change_feats[3]
})
stable_km2 = round(sum(f["properties"]["area_km2"] for f in change_feats[1]),1)
lost_km2   = round(sum(f["properties"]["area_km2"] for f in change_feats[2]),1)
gained_km2 = round(sum(f["properties"]["area_km2"] for f in change_feats[3]),1)
print(f"  Stable:{stable_km2} km²  Lost:{lost_km2} km²  Gained:{gained_km2} km²")
print(f"  GeoJSON: {len(change_geojson)/1024:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
print("Vectorising land-cover classes (2025)…")
# ─────────────────────────────────────────────────────────────────────────────
path_lc = MOSAIC / f"Toktogul_mosaic_{PERIODS[-1][0]}_{PERIODS[-1][1]}.tif"
arr_lc, ov_gt_lc, proj_lc, _, _ = read_ov(path_lc, OV_LVL)

LC_CLASSES = {
    "crops":  (5,  "农田",   0.2),
    "built":  (7,  "建设用地",0.1),
    "trees":  (2,  "植被",   0.2),
    "snow":   (9,  "积雪/冰川",0.1),
}
lc_geojson = {}
for key, (cls_val, label, min_km2) in LC_CLASSES.items():
    mask = (arr_lc == cls_val).astype(np.uint8)
    mem  = make_mem_raster(mask, ov_gt_lc, proj_lc)
    feats_raw = polygonize_to_wgs84(mem, proj_lc, simplify_m=150, min_km2=min_km2)
    mem  = None
    feats = [{"type":"Feature","geometry":gd,
              "properties":{"class":label,"area_km2":round(a/1e6,2)}}
             for a, gd in feats_raw]
    lc_geojson[key] = json.dumps({"type":"FeatureCollection","features":feats})
    total = round(sum(a for a,_ in feats_raw)/1e6,1)
    print(f"  {label}: {len(feats)} polygons  {total} km²  {len(lc_geojson[key])/1024:.1f} KB")

# ─────────────────────────────────────────────────────────────────────────────
print("Building HTML…")
# ─────────────────────────────────────────────────────────────────────────────
YRS       = [y for _,_,y in PERIODS]
WATER_A   = [stats[y]["water"]  for y in YRS]
VOL_A     = [stats[y]["vol"]    for y in YRS]
UTIL_A    = [stats[y]["util"]   for y in YRS]
SNOW_R    = [stats[y]["reg_snow"] for y in YRS]
ELEV_A    = [stats[y]["elev"]   for y in YRS]

latest = stats[YRS[-1]]

# Embed GeoJSON as JS variables
js_water = ";\n".join(
    f'const GJ_WATER_{yr} = {water_geojson[yr]}'
    for yr in YRS
) + ";"
js_water_map = "{" + ",".join(f'"{yr}": GJ_WATER_{yr}' for yr in YRS) + "}"

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>托克托古尔水库 · GIS 分析地图</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --dark:#07121c; --panel:#0d1e2e; --border:#1a3352;
  --cyan:#00c8f0; --blue:#1a8cff; --txt:#cce5f6; --txt2:#5a8aaa;
  --green:#2dc653; --orange:#f4a261; --red:#e63946; --snow:#a8d8ea;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;font-family:'Segoe UI',system-ui,sans-serif;
  font-size:13px;background:var(--dark);color:var(--txt);overflow:hidden}}

/* ── Layout ── */
#app{{display:flex;flex-direction:column;height:100vh}}
#topbar{{
  flex:0 0 50px;display:flex;align-items:center;
  background:rgba(7,18,28,.95);border-bottom:1px solid var(--border);
  padding:0 16px;gap:20px;z-index:1000;
}}
#topbar h1{{font-size:15px;font-weight:700;color:#fff;white-space:nowrap}}
#topbar h1 span{{color:var(--cyan)}}
.tkpi{{border-left:1px solid var(--border);padding-left:16px;white-space:nowrap}}
.tkpi .v{{font-size:16px;font-weight:800;line-height:1}}
.tkpi .l{{font-size:10px;color:var(--txt2)}}

#main{{display:flex;flex:1;overflow:hidden}}

/* ── Sidebar ── */
#sidebar{{
  flex:0 0 260px;background:var(--panel);border-right:1px solid var(--border);
  overflow-y:auto;display:flex;flex-direction:column;
}}
.sb-sect{{padding:14px 14px 10px;border-bottom:1px solid var(--border)}}
.sb-sect h3{{font-size:11px;font-weight:700;letter-spacing:.8px;
  color:var(--cyan);text-transform:uppercase;margin-bottom:10px}}

/* Year buttons */
.yr-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}}
.yb{{
  padding:5px 2px;border-radius:6px;border:1px solid var(--border);
  background:transparent;color:var(--txt2);cursor:pointer;font-size:12px;
  font-weight:600;text-align:center;transition:all .15s;
}}
.yb:hover{{background:#1a3352;color:var(--txt)}}
.yb.active{{background:var(--blue);border-color:var(--cyan);color:#fff}}

/* Layer toggles */
.layer-item{{
  display:flex;align-items:center;gap:8px;
  padding:6px 4px;border-radius:6px;cursor:pointer;
  transition:background .15s;
}}
.layer-item:hover{{background:rgba(255,255,255,.04)}}
.layer-item input{{cursor:pointer;accent-color:var(--cyan)}}
.layer-dot{{width:12px;height:12px;border-radius:3px;flex-shrink:0}}
.layer-name{{flex:1;color:var(--txt);font-size:12px}}
.layer-cnt{{font-size:11px;color:var(--txt2)}}

/* Opacity slider */
.opacity-row{{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:11px;color:var(--txt2)}}
input[type=range]{{flex:1;accent-color:var(--cyan)}}

/* Stats box */
.stat-row{{display:flex;justify-content:space-between;
  padding:5px 0;border-bottom:1px solid rgba(26,51,82,.6);font-size:12px}}
.stat-row:last-child{{border-bottom:none}}
.stat-lbl{{color:var(--txt2)}}
.stat-val{{font-weight:700}}

/* Legend */
.legend-item{{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:11px}}
.ld{{width:20px;height:12px;border-radius:2px;flex-shrink:0}}

/* ── Map ── */
#map-col{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#map{{flex:1;}}

/* ── Bottom chart strip ── */
#chart-strip{{
  flex:0 0 130px;background:rgba(7,18,28,.95);
  border-top:1px solid var(--border);
  display:flex;gap:0;
}}
.cs-chart{{flex:1;padding:8px 12px;border-right:1px solid var(--border);display:flex;flex-direction:column}}
.cs-chart:last-child{{border-right:none}}
.cs-chart h4{{font-size:10px;color:var(--txt2);font-weight:600;
  letter-spacing:.5px;margin-bottom:4px;text-transform:uppercase;flex:0 0 auto}}
.chart-wrap{{position:relative;flex:1;min-height:0}}

/* Leaflet popup */
.custom-popup .leaflet-popup-content-wrapper{{
  background:#0d1e2e;border:1px solid #1a3352;border-radius:10px;
  color:#cce5f6;box-shadow:0 4px 20px rgba(0,0,0,.5);
}}
.custom-popup .leaflet-popup-tip{{background:#0d1e2e}}
.popup-title{{font-size:14px;font-weight:700;color:#00c8f0;margin-bottom:8px}}
.popup-row{{display:flex;justify-content:space-between;gap:16px;
  padding:3px 0;border-bottom:1px solid rgba(26,51,82,.5);font-size:12px}}
.popup-row:last-child{{border-bottom:none}}
.popup-lbl{{color:var(--txt2)}}
.popup-val{{font-weight:700}}

/* Scrollbar */
#sidebar::-webkit-scrollbar{{width:4px}}
#sidebar::-webkit-scrollbar-thumb{{background:#1a3352;border-radius:2px}}
</style>
</head>
<body>
<div id="app">

<!-- ── TOPBAR ── -->
<div id="topbar">
  <h1>🏔 托克托古尔水库 <span>GIS 分析地图</span></h1>
  <div class="tkpi"><div class="v" id="tk-yr" style="color:var(--cyan)">2025</div><div class="l">当前年份</div></div>
  <div class="tkpi"><div class="v" id="tk-area">{latest['water']}</div><div class="l">水面面积 km²</div></div>
  <div class="tkpi"><div class="v" id="tk-vol">{latest['vol']}</div><div class="l">蓄水量 km³</div></div>
  <div class="tkpi"><div class="v" id="tk-util" style="color:var(--orange)">{latest['util']}%</div><div class="l">库容利用率</div></div>
  <div class="tkpi"><div class="v" id="tk-elev">{latest['elev']}</div><div class="l">估算水位 m</div></div>
  <div class="tkpi"><div class="v" style="color:var(--red)">{round(stats[YRS[-1]]['water']-stats[YRS[0]]['water'],1)}</div><div class="l">2018→2025 Δkm²</div></div>
</div>

<div id="main">

<!-- ── SIDEBAR ── -->
<div id="sidebar">

  <!-- 年份选择 -->
  <div class="sb-sect">
    <h3>📅 水面边界年份</h3>
    <div class="yr-grid">
      {"".join(f'<button class="yb{" active" if yr==YRS[-1] else ""}" onclick="setYear(\'{yr}\')">{yr}</button>' for yr in YRS)}
    </div>
    <div style="margin-top:10px">
      <div class="opacity-row">
        <span>透明度</span>
        <input type="range" min="10" max="95" value="65" id="waterOpacity"
               oninput="setWaterOpacity(this.value/100)">
        <span id="opVal">65%</span>
      </div>
    </div>
  </div>

  <!-- 图层控制 -->
  <div class="sb-sect">
    <h3>🗂 图层管理</h3>

    <div class="layer-item" onclick="toggleLayer('change')">
      <input type="checkbox" id="cb-change" checked>
      <div class="layer-dot" style="background:none;border:2px dashed #e63946"></div>
      <span class="layer-name">水面变化 2018→2025</span>
    </div>
    <div style="padding-left:34px;margin-top:2px;margin-bottom:6px;font-size:11px;color:var(--txt2)">
      <span style="color:#4196DE">■</span> 稳定 {stable_km2} km²
      <span style="color:#e63946;margin-left:6px">■</span> 消退 {lost_km2} km²
      <span style="color:#2dc653;margin-left:6px">■</span> 新增 {gained_km2} km²
    </div>

    <div class="layer-item" onclick="toggleLayer('crops')">
      <input type="checkbox" id="cb-crops">
      <div class="layer-dot" style="background:#e49633;opacity:.75"></div>
      <span class="layer-name">农田 2025</span>
      <span class="layer-cnt">{stats[YRS[-1]]['crops']} km²</span>
    </div>

    <div class="layer-item" onclick="toggleLayer('built')">
      <input type="checkbox" id="cb-built">
      <div class="layer-dot" style="background:#c4281b;opacity:.75"></div>
      <span class="layer-name">建设用地 2025</span>
      <span class="layer-cnt">{stats[YRS[-1]]['built']} km²</span>
    </div>

    <div class="layer-item" onclick="toggleLayer('trees')">
      <input type="checkbox" id="cb-trees">
      <div class="layer-dot" style="background:#3d7d49;opacity:.75"></div>
      <span class="layer-name">植被 2025</span>
      <span class="layer-cnt">{stats[YRS[-1]]['trees']} km²</span>
    </div>

    <div class="layer-item" onclick="toggleLayer('snow')">
      <input type="checkbox" id="cb-snow">
      <div class="layer-dot" style="background:#a8d8ea;opacity:.8"></div>
      <span class="layer-name">积雪/冰川 2025</span>
      <span class="layer-cnt">{stats[YRS[-1]]['snow']} km²</span>
    </div>
  </div>

  <!-- 实时统计 -->
  <div class="sb-sect">
    <h3>📊 当前年份统计</h3>
    <div class="stat-row"><span class="stat-lbl">水面面积</span><span class="stat-val" id="s-area">—</span></div>
    <div class="stat-row"><span class="stat-lbl">估算蓄水量</span><span class="stat-val" id="s-vol">—</span></div>
    <div class="stat-row"><span class="stat-lbl">估算水位</span><span class="stat-val" id="s-elev">—</span></div>
    <div class="stat-row"><span class="stat-lbl">库容利用率</span>
      <span class="stat-val"><span id="s-util">—</span></span></div>
    <div class="stat-row"><span class="stat-lbl">本地积雪</span><span class="stat-val" id="s-snow">—</span></div>
    <div class="stat-row"><span class="stat-lbl">农田面积</span><span class="stat-val" id="s-crops">—</span></div>
    <div class="stat-row"><span class="stat-lbl">建设用地</span><span class="stat-val" id="s-built">—</span></div>
  </div>

  <!-- 图例 -->
  <div class="sb-sect">
    <h3>📌 图例</h3>
    <div class="legend-item"><div class="ld" style="background:#4196DE;opacity:.75"></div>水面边界（当前年份）</div>
    <div class="legend-item"><div class="ld" style="background:#4196DE;border:2px solid #fff;opacity:.5"></div>稳定水面（2018&2025均有）</div>
    <div class="legend-item"><div class="ld" style="background:#e63946;opacity:.75"></div>消退水面（2018有→2025无）</div>
    <div class="legend-item"><div class="ld" style="background:#2dc653;opacity:.75"></div>新增水面（2018无→2025有）</div>
    <div class="legend-item"><div class="ld" style="background:#e49633;opacity:.7"></div>农田（2025）</div>
    <div class="legend-item"><div class="ld" style="background:#c4281b;opacity:.7"></div>建设用地（2025）</div>
    <div class="legend-item"><div class="ld" style="background:#3d7d49;opacity:.7"></div>植被（2025）</div>
    <div class="legend-item"><div class="ld" style="background:#a8d8ea;opacity:.8"></div>积雪/冰川（2025）</div>
  </div>

  <!-- 数据来源 -->
  <div class="sb-sect" style="font-size:11px;color:var(--txt2);line-height:1.7">
    <h3>ℹ️ 数据说明</h3>
    <b style="color:var(--txt)">来源：</b>Google Dynamic World / Sentinel-2<br>
    <b style="color:var(--txt)">分辨率：</b>10 m（矢量化自 80 m 概览）<br>
    <b style="color:var(--txt)">投影：</b>WGS84 (EPSG:4326)<br>
    <b style="color:var(--txt)">简化：</b>120 m 容差（Douglas-Peucker）<br>
    <b style="color:var(--txt)">蓄水量：</b>面积-库容曲线（±15% 误差）<br>
    <b style="color:var(--txt)">水位：</b>线性内插（820–902 m）<br>
  </div>

</div><!-- /sidebar -->

<!-- ── MAP + CHART ── -->
<div id="map-col">
  <div id="map"></div>

  <!-- Bottom chart strip -->
  <div id="chart-strip">
    <div class="cs-chart">
      <h4>水面面积 &amp; 蓄水量</h4>
      <div class="chart-wrap"><canvas id="c1"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>估算水位（m）</h4>
      <div class="chart-wrap"><canvas id="c2"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>区域积雪 / 冰川（km²）</h4>
      <div class="chart-wrap"><canvas id="c3"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>库容利用率（%）</h4>
      <div class="chart-wrap"><canvas id="c4"></canvas></div>
    </div>
  </div>
</div>

</div><!-- /main -->
</div><!-- /app -->

<script>
// ══ GeoJSON data ══════════════════════════════════════════════════
{js_water}
const GJ_WATER_MAP = {js_water_map};
const GJ_CHANGE    = {change_geojson};
const GJ_CROPS     = {lc_geojson['crops']};
const GJ_BUILT     = {lc_geojson['built']};
const GJ_TREES     = {lc_geojson['trees']};
const GJ_SNOW      = {lc_geojson['snow']};

const STATS = {json.dumps(stats)};
const YRS   = {json.dumps(YRS)};
const WATER_A={json.dumps(WATER_A)};
const VOL_A  ={json.dumps(VOL_A)};
const UTIL_A ={json.dumps(UTIL_A)};
const SNOW_R ={json.dumps(SNOW_R)};
const ELEV_A ={json.dumps(ELEV_A)};

// ══ Leaflet map ═══════════════════════════════════════════════════
const map = L.map('map',{{center:[41.84,72.89],zoom:11,
  zoomControl:true,attributionControl:true}});

// Satellite base
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'© Esri / Maxar',maxZoom:18}}).addTo(map);

// Place name labels (ESRI – free, no auth)
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'© Esri',opacity:.7,maxZoom:18}}).addTo(map);

// ══ Layer factory ═════════════════════════════════════════════════
function makePopup(props, title) {{
  let rows = '';
  for (const [k, v] of Object.entries(props)) {{
    const labels={{year:'年份',area_km2:'面积 (km²)',vol_km3:'蓄水量 (km³)',
                   util_pct:'库容利用率 (%)',elev_m:'估算水位 (m)',
                   change:'变化类型',class:'地物类型'}};
    const lbl = labels[k] || k;
    rows += `<div class="popup-row"><span class="popup-lbl">${{lbl}}</span>
             <span class="popup-val">${{v}}</span></div>`;
  }}
  return `<div class="popup-title">${{title}}</div>${{rows}}`;
}}

let waterOpacity = 0.65;
let currentWaterLayer = null;

function makeWaterLayer(yr) {{
  return L.geoJSON(GJ_WATER_MAP[yr], {{
    style: {{
      color:'#00b4d8', weight:2.5,
      fillColor:'#4196DE', fillOpacity: waterOpacity,
    }},
    onEachFeature(f, lyr) {{
      const p = f.properties;
      lyr.bindPopup(makePopup(p, `🌊 水面边界 ${{p.year}}`), {{className:'custom-popup'}});
      lyr.on('mouseover', () => lyr.setStyle({{fillOpacity: Math.min(waterOpacity+0.25, 1)}}));
      lyr.on('mouseout',  () => lyr.setStyle({{fillOpacity: waterOpacity}}));
    }}
  }});
}}

// Change detection layer
const changeColors = {{stable:'#4196DE', lost:'#e63946', gained:'#2dc653'}};
const changeLayer = L.geoJSON(GJ_CHANGE, {{
  style: f => ({{
    color: changeColors[f.properties.change] || '#888',
    weight: 1.5,
    fillColor: changeColors[f.properties.change] || '#888',
    fillOpacity: 0.55,
    dashArray: f.properties.change==='stable' ? '4,3' : null,
  }}),
  onEachFeature(f, lyr) {{
    const typeNames={{stable:'稳定水面',lost:'消退水面',gained:'新增水面'}};
    lyr.bindPopup(makePopup(f.properties, `🔄 ${{typeNames[f.properties.change]||'变化'}}`),
                 {{className:'custom-popup'}});
  }}
}}).addTo(map);

// Land cover layers (hidden by default)
function makeLcLayer(geojson, color, alpha) {{
  return L.geoJSON(geojson, {{
    style: {{color: color, weight:1, fillColor:color, fillOpacity:alpha}},
    onEachFeature(f,lyr){{
      lyr.bindPopup(makePopup(f.properties,`🌍 ${{f.properties.class||'地物'}}`),{{className:'custom-popup'}});
    }}
  }});
}}
const lcLayers = {{
  crops: makeLcLayer(GJ_CROPS, '#e49633', 0.55),
  built: makeLcLayer(GJ_BUILT, '#c4281b', 0.60),
  trees: makeLcLayer(GJ_TREES, '#3d7d49', 0.50),
  snow:  makeLcLayer(GJ_SNOW,  '#a8d8ea', 0.60),
}};
const layerState = {{change:true, crops:false, built:false, trees:false, snow:false}};

// ══ Control functions ════════════════════════════════════════════
function setYear(yr) {{
  if (currentWaterLayer) map.removeLayer(currentWaterLayer);
  currentWaterLayer = makeWaterLayer(yr);
  currentWaterLayer.addTo(map);

  // Update buttons
  document.querySelectorAll('.yb').forEach(b => b.classList.toggle('active', b.textContent===yr));

  // Update topbar
  const s = STATS[yr];
  document.getElementById('tk-yr').textContent   = yr;
  document.getElementById('tk-area').textContent  = s.water + ' km²';
  document.getElementById('tk-vol').textContent   = s.vol   + ' km³';
  const uel = document.getElementById('tk-util');
  uel.textContent = s.util + '%';
  uel.style.color = s.util>=80?'#2dc653':s.util>=60?'#f4a261':'#e63946';
  document.getElementById('tk-elev').textContent  = s.elev  + ' m';

  // Update sidebar stats
  document.getElementById('s-area').textContent  = s.water + ' km²';
  document.getElementById('s-vol').textContent   = s.vol   + ' km³';
  document.getElementById('s-elev').textContent  = s.elev  + ' m';
  const su = document.getElementById('s-util');
  su.textContent = s.util + '%';
  su.style.color = s.util>=80?'#2dc653':s.util>=60?'#f4a261':'#e63946';
  document.getElementById('s-snow').textContent  = s.snow   + ' km²';
  document.getElementById('s-crops').textContent = s.crops  + ' km²';
  document.getElementById('s-built').textContent = s.built  + ' km²';

  // Highlight chart point
  highlightYear(yr);
}}

function setWaterOpacity(val) {{
  waterOpacity = val;
  document.getElementById('opVal').textContent = Math.round(val*100) + '%';
  if (currentWaterLayer) {{
    currentWaterLayer.setStyle({{fillOpacity: waterOpacity}});
  }}
}}

function toggleLayer(name) {{
  layerState[name] = !layerState[name];
  document.getElementById('cb-'+name).checked = layerState[name];
  if (name === 'change') {{
    layerState[name] ? changeLayer.addTo(map) : map.removeLayer(changeLayer);
  }} else {{
    layerState[name] ? lcLayers[name].addTo(map) : map.removeLayer(lcLayers[name]);
  }}
}}
// Init: click event bubbles from parent div, toggle checkbox
document.querySelectorAll('.layer-item').forEach(el => {{
  el.addEventListener('click', e => {{
    if (e.target.type !== 'checkbox') {{
      const cb = el.querySelector('input[type=checkbox]');
      cb.checked = !cb.checked;
    }}
  }});
}});

// ══ Init ════════════════════════════════════════════════════════
setYear('{YRS[-1]}');

// ══ Charts ══════════════════════════════════════════════════════
Chart.defaults.color = '#5a8aaa';
Chart.defaults.borderColor = 'rgba(26,51,82,.5)';
Chart.defaults.font.family = "'Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size   = 10;

const CHART_OPTS = {{
  responsive:true, maintainAspectRatio:false,
  interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{display:false}},
    tooltip:{{backgroundColor:'#0d1e2e',borderColor:'#1a3352',borderWidth:1,padding:8}}}},
  animation:false,
}};

const chartData = (datasets) => ({{labels:YRS, datasets}});

const c1 = new Chart('c1',{{type:'line', data:chartData([
  {{data:WATER_A,borderColor:'#4196DE',backgroundColor:'rgba(65,150,222,.15)',
    fill:true,tension:.4,pointRadius:3,borderWidth:2,yAxisID:'yA',label:'km²'}},
  {{data:VOL_A,  borderColor:'#00c8f0',fill:false,tension:.4,
    pointRadius:3,borderWidth:2,borderDash:[4,2],yAxisID:'yV',label:'km³'}},
]),options:{{...CHART_OPTS,scales:{{
  yA:{{position:'left', grid:{{color:'rgba(26,51,82,.5)'}},min:180,max:310}},
  yV:{{position:'right',grid:{{drawOnChartArea:false}},min:10,max:22}},
  x:{{grid:{{color:'rgba(26,51,82,.3)'}},ticks:{{maxRotation:0}}}},
}}}}}});

const c2 = new Chart('c2',{{type:'line', data:chartData([
  {{data:ELEV_A,borderColor:'#f4a261',backgroundColor:'rgba(244,162,97,.15)',
    fill:true,tension:.4,pointRadius:3,borderWidth:2}},
]),options:{{...CHART_OPTS,scales:{{
  y:{{grid:{{color:'rgba(26,51,82,.5)'}},min:820,max:910,
     ticks:{{callback:v=>v+' m'}}}},
  x:{{grid:{{display:false}},ticks:{{maxRotation:0}}}},
}}}}}});

const c3 = new Chart('c3',{{type:'bar', data:chartData([
  {{data:SNOW_R,backgroundColor:'rgba(168,216,234,.55)',
    borderColor:'#a8d8ea',borderWidth:1.5,borderRadius:3}},
]),options:{{...CHART_OPTS,scales:{{
  y:{{grid:{{color:'rgba(26,51,82,.5)'}}}},
  x:{{grid:{{display:false}},ticks:{{maxRotation:0}}}},
}}}}}});

const UTIL_COLORS = UTIL_A.map(u=>u>=80?'rgba(45,198,83,.7)':u>=60?'rgba(244,162,97,.7)':'rgba(230,57,70,.7)');
const c4 = new Chart('c4',{{type:'bar', data:chartData([
  {{data:UTIL_A,backgroundColor:UTIL_COLORS,
    borderColor:UTIL_COLORS.map(c=>c.replace('.7','1')),
    borderWidth:1.5,borderRadius:3}},
]),options:{{...CHART_OPTS,scales:{{
  y:{{grid:{{color:'rgba(26,51,82,.5)'}},min:0,max:110,ticks:{{callback:v=>v+'%'}}}},
  x:{{grid:{{display:false}},ticks:{{maxRotation:0}}}},
}}}}}});

// Highlight active year in charts
const allCharts = [c1,c2,c3,c4];
function highlightYear(yr) {{
  const idx = YRS.indexOf(yr);
  allCharts.forEach(ch => {{
    if (!ch.options.plugins.annotation) ch.options.plugins.annotation={{}};
    // Just update point radius for visual emphasis
    if (ch.data.datasets[0]) {{
      const r = ch.data.datasets[0].pointRadius;
      if (Array.isArray(r)) {{
        ch.data.datasets[0].pointRadius = YRS.map((_,i)=> i===idx?6:3);
      }} else {{
        ch.data.datasets[0].pointRadius = YRS.map((_,i)=> i===idx?6:3);
      }}
      ch.update('none');
    }}
  }});
}}
highlightYear('{YRS[-1]}');
</script>
</body>
</html>"""

out = OUT / "gis_map.html"
out.write_text(HTML, encoding="utf-8")
sz = out.stat().st_size / 1024
print(f"\n✅  gis_map.html  →  {sz:.0f} KB")
print(f"    open '{out}'")

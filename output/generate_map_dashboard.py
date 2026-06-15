#!/usr/bin/env python3
"""
Toktogul Reservoir – Map-Heavy Dashboard
生成以地图为核心的可视化页面：
  • Leaflet 卫星底图 + 水面覆盖年度叠加图层（逐年切换 / 自动播放）
  • 拖拽式前后对比滑块（2018 vs 2025）
  • 2018→2025 水面变化检测图（失去=红 / 保留=蓝 / 新增=绿）
  • 8 年胶片式时间轴（点击切换主图）
  • 紧凑型水文图表（面积 + 蓄水量 / 积雪 / 利用率）
Output: output/map_dashboard.html
"""

import base64, io, json
from pathlib import Path
from osgeo import gdal, osr
import numpy as np
from PIL import Image

# ── Paths ────────────────────────────────────────────────────────────────────
BASE    = Path("/Users/yunfeili/Downloads/Toktogul Reservoir")
OUT     = BASE / "output"
MOSAIC  = OUT  / "mosaics"

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

# ── Reservoir parameters ──────────────────────────────────────────────────────
P = dict(total=19.5, useful=14.1, dead=5.4,
         full_area=284.0, dead_area=50.0)

def vol(A):
    if A <= P["dead_area"]: return P["dead"]
    r = min((A - P["dead_area"]) / (P["full_area"] - P["dead_area"]), 1.0)
    return round(P["dead"] + P["useful"] * r**1.5, 2)

def util(V):
    return round((V - P["dead"]) / P["useful"] * 100, 1)

# ── Pre-computed regional snow (full 43T overview) ────────────────────────────
REG_SNOW  = dict(zip(
    ["2018","2019","2020","2021","2022","2023","2024","2025"],
    [4264.3,6996.7,7669.2,3908.9,4331.8,7911.0,6680.4,2654.1]
))
REG_WATER = dict(zip(
    ["2018","2019","2020","2021","2022","2023","2024","2025"],
    [23418.1,23367.5,23193.4,23081.1,23091.9,22934.0,23001.5,22822.7]
))

# ── Dynamic World palette (index→RGBA) ────────────────────────────────────────
DW = {
    0:  (0,   0,   0,   0),    # nodata: transparent
    1:  (65,  155, 223, 255),  # Water
    2:  (57,  125, 73,  255),  # Trees
    3:  (136, 176, 83,  255),  # Grass
    4:  (122, 135, 198, 255),  # Flooded veg
    5:  (228, 150, 53,  255),  # Crops
    6:  (223, 195, 90,  255),  # Shrub
    7:  (196, 40,  27,  255),  # Built
    8:  (165, 155, 143, 255),  # Bare
    9:  (168, 235, 255, 255),  # Snow/ice
    10: (97,  97,  97,  255),  # Cloud
    11: (227, 226, 195, 255),  # Bare light
}

def arr_to_rgba(arr: np.ndarray, palette: dict, default: tuple=(0,0,0,0)) -> np.ndarray:
    h, w = arr.shape
    out  = np.full((h, w, 4), default, dtype=np.uint8)
    for cls, rgba in palette.items():
        out[arr == cls] = rgba
    return out

def to_b64(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, fmt, optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def open_overview(path: Path, ov_level: int) -> np.ndarray:
    ds   = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    ov   = band.GetOverview(ov_level)
    arr  = ov.ReadAsArray()
    ds   = None
    return arr

def get_wgs84_bounds(path: Path):
    """Return [[S,W],[N,E]] in WGS84."""
    ds  = gdal.Open(str(path))
    gt  = ds.GetGeoTransform()
    w, h = ds.RasterXSize, ds.RasterYSize
    xmin, xmax = gt[0], gt[0] + w*gt[1]
    ymax, ymin = gt[3], gt[3] + h*gt[5]

    src = osr.SpatialReference(); src.ImportFromWkt(ds.GetProjection())
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tgt = osr.SpatialReference(); tgt.ImportFromEPSG(4326)
    tgt.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct  = osr.CoordinateTransformation(src, tgt)
    ds  = None

    corners = [(xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax)]
    pts     = [ct.TransformPoint(x, y)[:2] for x,y in corners]
    lons    = [p[0] for p in pts]; lats = [p[1] for p in pts]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]

# ════════════════════════════════════════════════════════════════════
#  RENDER ALL IMAGES
# ════════════════════════════════════════════════════════════════════
print("Rendering images…")

first_mosaic = MOSAIC / f"Toktogul_mosaic_{PERIODS[0][0]}_{PERIODS[0][1]}.tif"
BOUNDS = get_wgs84_bounds(first_mosaic)
print(f"  Map bounds: {BOUNDS}")

# Storage per year
stats       = {}    # year → {water, vol, util, snow_local, crops, built, trees, bare}
water_b64   = {}    # year → base64 RGBA water-only overlay
full_b64    = {}    # year → base64 full-DW classified image (thumbnail)
thumb_b64   = {}    # year → tiny thumbnail (for filmstrip)

OV_OVERLAY = 2   # 663×700  (water overlay on Leaflet)
OV_COMPARE = 1   # 1325×1400 (before/after comparison slider)
OV_THUMB   = 3   # 332×350  (filmstrip thumbnails)

for start, end, yr in PERIODS:
    path = MOSAIC / f"Toktogul_mosaic_{start}_{end}.tif"

    # Stats from full raster
    ds   = gdal.Open(str(path)); band = ds.GetRasterBand(1)
    full_arr = band.ReadAsArray(); ds = None
    km2 = 100/1e6   # 10m × 10m pixel
    water_km2 = float((full_arr==1).sum()*km2)
    V  = vol(water_km2); U = util(V)
    stats[yr] = dict(
        water=round(water_km2,1), vol=V, util=U,
        crops=round(float((full_arr==5).sum()*km2),1),
        built=round(float((full_arr==7).sum()*km2),1),
        trees=round(float((full_arr==2).sum()*km2),1),
        bare =round(float(((full_arr==8)|(full_arr==11)).sum()*km2),1),
        snow =round(float((full_arr==9).sum()*km2),1),
        reg_snow=REG_SNOW[yr], reg_water=REG_WATER[yr],
    )

    # ── Water-only RGBA overlay (for Leaflet) ──
    arr_ov = open_overview(path, OV_OVERLAY)
    pal_water = {k: (0,0,0,0) for k in range(12)}
    pal_water[1] = (65, 155, 223, 195)   # water: semi-transparent blue
    rgba_ov = arr_to_rgba(arr_ov, pal_water)
    water_b64[yr] = to_b64(Image.fromarray(rgba_ov, 'RGBA'))

    # ── Full-DW image at compare resolution ──
    arr_cmp = open_overview(path, OV_COMPARE)
    rgba_cmp = arr_to_rgba(arr_cmp, DW)
    full_b64[yr] = to_b64(Image.fromarray(rgba_cmp, 'RGBA'))

    # ── Tiny thumbnail ──
    arr_th = open_overview(path, OV_THUMB)
    rgba_th = arr_to_rgba(arr_th, DW)
    img_th  = Image.fromarray(rgba_th, 'RGBA')
    thumb_b64[yr] = to_b64(img_th)

    print(f"  {yr}: {water_km2:.1f} km²  {V} km³  {U}%")

# ── Change detection: 2018 vs 2025 ──
print("Building change-detection map…")
path_18 = MOSAIC / f"Toktogul_mosaic_{PERIODS[0][0]}_{PERIODS[0][1]}.tif"
path_25 = MOSAIC / f"Toktogul_mosaic_{PERIODS[-1][0]}_{PERIODS[-1][1]}.tif"
a18 = open_overview(path_18, OV_COMPARE)
a25 = open_overview(path_25, OV_COMPARE)

w18 = (a18 == 1); w25 = (a25 == 1)
change = np.zeros((*a18.shape, 4), dtype=np.uint8)
change[w18 &  w25] = [65,  155, 223, 220]  # kept water  – blue
change[w18 & ~w25] = [230, 57,  70,  220]  # lost water  – red
change[~w18 & w25] = [45,  198, 83,  220]  # gained water – green
change_b64 = to_b64(Image.fromarray(change, 'RGBA'))

# ── Chart data arrays ──
YRS   = [y for _,_,y in PERIODS]
WATER = [stats[y]["water"]    for y in YRS]
VOL   = [stats[y]["vol"]      for y in YRS]
UTIL  = [stats[y]["util"]     for y in YRS]
SNOW  = [stats[y]["snow"]     for y in YRS]
SNOWR = [stats[y]["reg_snow"] for y in YRS]
CROPS = [stats[y]["crops"]    for y in YRS]
BUILT = [stats[y]["built"]    for y in YRS]
TREES = [stats[y]["trees"]    for y in YRS]
BARE  = [stats[y]["bare"]     for y in YRS]
DA    = [round(WATER[i]-WATER[i-1],1) if i>0 else 0 for i in range(len(YRS))]

latest  = stats[YRS[-1]]
earliest= stats[YRS[0]]
total_dA = round(latest["water"] - earliest["water"], 1)
total_dV = round(latest["vol"]   - earliest["vol"],   2)

# ── Bounds for Leaflet ──
S, W = BOUNDS[0]
N, E = BOUNDS[1]
cLat = round((S+N)/2, 4)
cLon = round((W+E)/2, 4)

# ════════════════════════════════════════════════════════════════════
#  HTML
# ════════════════════════════════════════════════════════════════════
print("Writing HTML…")

# JS data
jWater   = json.dumps(water_b64)
jFull    = json.dumps(full_b64)
jThumb   = json.dumps(thumb_b64)
jStats   = json.dumps(stats)
jYrs     = json.dumps(YRS)
jWaterA  = json.dumps(WATER)
jVol     = json.dumps(VOL)
jUtil    = json.dumps(UTIL)
jSnow    = json.dumps(SNOW)
jSnowR   = json.dumps(SNOWR)
jCrops   = json.dumps(CROPS)
jBuilt   = json.dumps(BUILT)
jTrees   = json.dumps(TREES)
jBare    = json.dumps(BARE)
jDA      = json.dumps(DA)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>托克托古尔水库 · 水文监测地图仪表盘</title>

<!-- Leaflet -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<!-- Chart.js -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

<style>
/* ── Reset & base ── */
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#08131e;color:#d6eaf8;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}

/* ── Topbar ── */
#topbar{{
  position:fixed;top:0;left:0;right:0;z-index:1000;
  background:rgba(8,19,30,0.92);backdrop-filter:blur(8px);
  border-bottom:1px solid #1e3a5f;
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 20px;height:56px;
}}
#topbar h1{{font-size:17px;font-weight:700;color:#fff;white-space:nowrap}}
#topbar h1 span{{color:#00c8f0}}
.top-kpis{{display:flex;gap:20px;align-items:center}}
.top-kpi{{text-align:center}}
.top-kpi .v{{font-size:18px;font-weight:800;color:#00c8f0;line-height:1}}
.top-kpi .l{{font-size:10px;color:#7fb3d3;margin-top:1px}}

/* ── Map wrapper ── */
#map-section{{margin-top:56px;position:relative}}
#map{{width:100%;height:calc(100vh - 56px);min-height:420px}}

/* ── Year strip (over map) ── */
#year-strip{{
  position:absolute;bottom:0;left:0;right:0;z-index:800;
  background:rgba(8,19,30,0.85);backdrop-filter:blur(6px);
  border-top:1px solid #1e3a5f;
  display:flex;align-items:center;padding:8px 16px;gap:8px;
}}
.yr-btn{{
  padding:5px 14px;border-radius:20px;border:1px solid #1e4a7a;
  background:transparent;color:#7fb3d3;cursor:pointer;font-size:13px;
  font-weight:600;transition:all .2s;
}}
.yr-btn:hover{{background:#1e3a5f;color:#fff}}
.yr-btn.active{{background:#0077b6;border-color:#00b4d8;color:#fff}}
#play-btn{{
  padding:5px 16px;border-radius:20px;border:1px solid #00c8f0;
  background:rgba(0,200,240,0.15);color:#00c8f0;cursor:pointer;
  font-size:13px;font-weight:700;margin-left:auto;
}}
#play-btn:hover{{background:rgba(0,200,240,0.3)}}

/* ── Floating stats card ── */
#stats-card{{
  position:absolute;top:70px;right:16px;z-index:900;
  background:rgba(8,19,30,0.88);backdrop-filter:blur(8px);
  border:1px solid #1e4a7a;border-radius:12px;padding:14px 18px;
  min-width:180px;
}}
#stats-card .sc-yr{{font-size:18px;font-weight:800;color:#00c8f0;margin-bottom:8px}}
.sc-row{{display:flex;justify-content:space-between;gap:16px;
  padding:5px 0;border-bottom:1px solid rgba(30,58,95,0.5);font-size:13px}}
.sc-row:last-child{{border-bottom:none}}
.sc-lbl{{color:#7fb3d3}}
.sc-val{{font-weight:700;color:#fff}}
.util-pill{{
  display:inline-block;padding:2px 8px;border-radius:10px;
  font-size:12px;font-weight:700;
}}

/* ── Sections ── */
.section{{padding:28px 24px;max-width:1400px;margin:0 auto}}
.sec-title{{
  font-size:16px;font-weight:700;color:#00c8f0;
  border-left:3px solid #00c8f0;padding-left:10px;margin-bottom:16px;
}}

/* ── Before/After slider ── */
.ba-wrap{{
  position:relative;width:100%;overflow:hidden;
  border-radius:10px;border:1px solid #1e3a5f;
  cursor:col-resize;user-select:none;background:#000;
  aspect-ratio: 1.9/1;
}}
.ba-wrap img{{
  position:absolute;top:0;left:0;width:100%;height:100%;
  object-fit:contain;object-position:center;
}}
#ba-before{{z-index:1}}
#ba-after{{z-index:2;clip-path:inset(0 50% 0 0)}}
.ba-handle{{
  position:absolute;top:0;bottom:0;z-index:3;
  width:3px;background:#fff;left:50%;
  display:flex;align-items:center;justify-content:center;
  cursor:col-resize;
}}
.ba-handle::after{{
  content:'◀ ▶';font-size:11px;color:#fff;
  background:rgba(0,0,0,0.7);padding:4px 8px;border-radius:20px;
  white-space:nowrap;pointer-events:none;
}}
.ba-label{{
  position:absolute;top:12px;z-index:4;
  background:rgba(0,0,0,0.6);color:#fff;
  font-size:13px;font-weight:700;padding:4px 12px;border-radius:20px;
}}
#lbl-before{{left:12px}}
#lbl-after{{right:12px}}

/* ── Change map ── */
.change-wrap{{
  border-radius:10px;border:1px solid #1e3a5f;overflow:hidden;
  background:#0a1628;text-align:center;
}}
.change-wrap img{{width:100%;max-height:360px;object-fit:contain}}
.change-legend{{
  display:flex;gap:20px;justify-content:center;
  padding:10px;background:#0a1628;font-size:13px;
}}
.cl-dot{{
  width:14px;height:14px;border-radius:3px;display:inline-block;
  margin-right:5px;vertical-align:middle;
}}

/* ── Filmstrip ── */
#filmstrip{{
  display:flex;gap:8px;overflow-x:auto;padding:12px 0;
  scrollbar-width:thin;scrollbar-color:#1e3a5f #08131e;
}}
.film-item{{
  flex:0 0 auto;cursor:pointer;
  border:2px solid transparent;border-radius:8px;overflow:hidden;
  transition:all .2s;background:#0a1628;
}}
.film-item:hover{{border-color:#1a8cff;transform:translateY(-2px)}}
.film-item.active{{border-color:#00c8f0;box-shadow:0 0 12px rgba(0,200,240,0.4)}}
.film-item img{{width:120px;height:auto;display:block}}
.film-lbl{{
  text-align:center;font-size:12px;font-weight:700;
  padding:4px;color:#7fb3d3;background:#08131e;
}}
.film-item.active .film-lbl{{color:#00c8f0}}

/* ── Charts grid ── */
.chart-grid{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px}}
@media(max-width:900px){{.chart-grid{{grid-template-columns:1fr}}}}
.chart-card{{
  background:#0f1f30;border:1px solid #1e3a5f;border-radius:10px;
  padding:16px 18px;
}}
.chart-card h3{{font-size:13px;color:#7fb3d3;font-weight:600;margin-bottom:12px}}

/* ── 2-col compare layout ── */
.col2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:900px){{.col2{{grid-template-columns:1fr}}}}

/* ── Data table ── */
.tbl{{width:100%;border-collapse:collapse;font-size:12.5px}}
.tbl th{{
  background:#08131e;color:#00c8f0;font-weight:600;
  padding:9px 12px;text-align:right;border-bottom:2px solid #1e3a5f;
  white-space:nowrap;
}}
.tbl th:first-child{{text-align:center}}
.tbl td{{padding:8px 12px;text-align:right;border-bottom:1px solid #1e3a5f}}
.tbl td:first-child{{text-align:center;font-weight:700;color:#00c8f0}}
.tbl tr:hover td{{background:rgba(0,200,240,.05)}}
.tbl tr:last-child td{{border-bottom:none}}
.tag{{display:inline-block;padding:2px 7px;border-radius:12px;font-size:11px;font-weight:700}}
.t-hi{{background:rgba(45,198,83,.15);color:#2dc653}}
.t-md{{background:rgba(244,162,97,.15);color:#f4a261}}
.t-lo{{background:rgba(230,57,70,.15);color:#e63946}}

/* ── Leaflet overrides ── */
.leaflet-control-attribution{{background:rgba(8,19,30,0.8)!important;color:#7fb3d3!important}}
</style>
</head>
<body>

<!-- ══ TOPBAR ══ -->
<div id="topbar">
  <h1>💧 托克托古尔水库 &nbsp;<span>水文监测地图</span></h1>
  <div class="top-kpis">
    <div class="top-kpi"><div class="v">{latest['water']} km²</div><div class="l">2025 水面面积</div></div>
    <div class="top-kpi"><div class="v">{latest['vol']} km³</div><div class="l">估算蓄水量</div></div>
    <div class="top-kpi"><div class="v" style="color:#f4a261">{latest['util']}%</div><div class="l">库容利用率</div></div>
    <div class="top-kpi"><div class="v" style="color:#e63946">{total_dA} km²</div><div class="l">2018→2025 减少</div></div>
    <div class="top-kpi"><div class="v" style="color:#90e0ef">{stats[YRS[-1]]['reg_snow']:,.0f} km²</div><div class="l">区域积雪（2025）</div></div>
  </div>
</div>

<!-- ══ MAP ══ -->
<div id="map-section">
  <div id="map"></div>

  <!-- Floating stats card -->
  <div id="stats-card">
    <div class="sc-yr" id="sc-year">2025</div>
    <div class="sc-row"><span class="sc-lbl">水面面积</span><span class="sc-val" id="sc-area">— km²</span></div>
    <div class="sc-row"><span class="sc-lbl">估算蓄水量</span><span class="sc-val" id="sc-vol">— km³</span></div>
    <div class="sc-row"><span class="sc-lbl">库容利用率</span><span class="sc-val" id="sc-util">—%</span></div>
    <div class="sc-row"><span class="sc-lbl">区域积雪</span><span class="sc-val" id="sc-snow">— km²</span></div>
    <div class="sc-row"><span class="sc-lbl">农田</span><span class="sc-val" id="sc-crops">— km²</span></div>
  </div>

  <!-- Year strip -->
  <div id="year-strip">
    {"".join(f'<button class="yr-btn{" active" if yr==YRS[-1] else ""}" onclick="setYear(\'{yr}\')">{yr}</button>' for _,_,yr in PERIODS)}
    <button id="play-btn" onclick="togglePlay()">▶ 播放</button>
  </div>
</div>

<!-- ══ BEFORE / AFTER ══ -->
<div class="section">
  <div class="sec-title">🔄 水面变化对比：拖拽滑块查看 2018 → 2025</div>
  <div class="ba-wrap" id="baWrap">
    <span class="ba-label" id="lbl-before">2018（{earliest['water']} km²）</span>
    <span class="ba-label" id="lbl-after">2025（{latest['water']} km²）</span>
    <img id="ba-before" src="{full_b64[YRS[0]]}" alt="2018">
    <img id="ba-after"  src="{full_b64[YRS[-1]]}" alt="2025">
    <div class="ba-handle" id="baHandle"></div>
  </div>
</div>

<!-- ══ CHANGE DETECTION ══ -->
<div class="section" style="padding-top:0">
  <div class="col2">
    <div>
      <div class="sec-title">🗺️ 水面变化检测图（2018 → 2025）</div>
      <div class="change-wrap">
        <img src="{change_b64}" alt="变化检测">
        <div class="change-legend">
          <span><span class="cl-dot" style="background:#4196DE"></span>持续水面（两年均为水体）</span>
          <span><span class="cl-dot" style="background:#e63946"></span>水面消退（2018有→2025无）</span>
          <span><span class="cl-dot" style="background:#2dc653"></span>新增水面（2018无→2025有）</span>
        </div>
      </div>
    </div>

    <div>
      <div class="sec-title">🎞️ 时序胶片（点击切换地图）</div>
      <div id="filmstrip">
        {"".join(f'''
        <div class="film-item{" active" if yr==YRS[-1] else ""}" onclick="setYear(\'{yr}\')" id="film-{yr}">
          <img src="{thumb_b64[yr]}" alt="{yr}">
          <div class="film-lbl">{yr}<br>{stats[yr]["water"]} km²</div>
        </div>''' for _,_,yr in PERIODS)}
      </div>
      <div style="margin-top:12px;font-size:12px;color:#7fb3d3;line-height:1.8">
        <strong style="color:#00c8f0">调色板说明：</strong>
        <span style="color:#4196DE">■</span>水体 &nbsp;
        <span style="color:#e49633">■</span>农田 &nbsp;
        <span style="color:#3d7d49">■</span>植被 &nbsp;
        <span style="color:#c4281b">■</span>建设用地 &nbsp;
        <span style="color:#a8ebff">■</span>积雪 &nbsp;
        <span style="color:#e3e2c3">■</span>裸地
      </div>
    </div>
  </div>
</div>

<!-- ══ CHARTS ══ -->
<div class="section" style="padding-top:0">
  <div class="sec-title">📈 关键水文指标时序图</div>
  <div class="chart-grid">

    <div class="chart-card">
      <h3>水面面积 &amp; 估算蓄水量（2018–2025）</h3>
      <canvas id="mainChart" height="140"></canvas>
    </div>

    <div class="chart-card">
      <h3>区域积雪 / 冰川面积（UTM-43T 全带）</h3>
      <canvas id="snowChart" height="140"></canvas>
    </div>

    <div class="chart-card">
      <h3>有效库容利用率（%）</h3>
      <canvas id="utilChart" height="140"></canvas>
    </div>

  </div>
</div>

<!-- ══ DATA TABLE ══ -->
<div class="section" style="padding-top:0">
  <div class="sec-title">📋 年度水文数据汇总</div>
  <div style="overflow:auto;background:#0f1f30;border:1px solid #1e3a5f;border-radius:10px">
    <table class="tbl">
      <thead><tr>
        <th>年份</th><th>水面面积(km²)</th><th>蓄水量(km³)</th>
        <th>库容利用率</th><th>面积变化</th><th>本地积雪(km²)</th>
        <th>区域积雪(km²)</th><th>农田(km²)</th><th>植被(km²)</th><th>状态</th>
      </tr></thead>
      <tbody>
        {"".join(f"""
        <tr>
          <td>{yr}</td>
          <td>{stats[yr]['water']}</td>
          <td>{stats[yr]['vol']}</td>
          <td><span class="tag {'t-hi' if stats[yr]['util']>=80 else ('t-md' if stats[yr]['util']>=60 else 't-lo')}">{stats[yr]['util']}%</span></td>
          <td style="color:{'#e63946' if DA[i]<0 else '#2dc653'}">{'+' if DA[i]>0 else ''}{DA[i]}</td>
          <td>{stats[yr]['snow']}</td>
          <td>{stats[yr]['reg_snow']:,.0f}</td>
          <td>{stats[yr]['crops']}</td>
          <td>{stats[yr]['trees']}</td>
          <td><span class="tag {'t-hi' if stats[yr]['util']>=80 else ('t-md' if stats[yr]['util']>=60 else 't-lo')}">{'充盈' if stats[yr]['util']>=80 else ('正常' if stats[yr]['util']>=60 else '偏枯')}</span></td>
        </tr>""" for i,(s,e,yr) in enumerate(PERIODS))}
      </tbody>
    </table>
  </div>
  <div style="margin-top:10px;font-size:11.5px;color:#7fb3d3;line-height:1.8">
    蓄水量由水面积–库容曲线推算（V = V_死 + V_有效 × [(A–A_死)/(A_满–A_死)]^1.5），不确定性 ±15%。
    积雪面积为 Dynamic World Class-9 年度合成值，反映持久性积雪范围。
    数据来源：Google Dynamic World / Sentinel-2，CRS：EPSG:32643，分辨率 10 m。
  </div>
</div>

<footer style="text-align:center;padding:20px;font-size:12px;color:#4a6a8a;border-top:1px solid #1e3a5f">
  Sentinel-2 · Dynamic World · GDAL · Leaflet · Chart.js &nbsp;|&nbsp; 托克托古尔水库 2018–2025 &nbsp;|&nbsp; 仅供科研参考
</footer>

<!-- ══════════════════════════════════════════════════════════
     SCRIPTS
══════════════════════════════════════════════════════════ -->
<script>
// ── Data ──────────────────────────────────────────────────
const YRS        = {jYrs};
const waterB64   = {jWater};
const fullB64    = {jFull};
const statsData  = {jStats};
const WATER_ARR  = {jWaterA};
const VOL_ARR    = {jVol};
const UTIL_ARR   = {jUtil};
const SNOW_ARR   = {jSnow};
const SNOWR_ARR  = {jSnowR};
const DA_ARR     = {jDA};

// ── Leaflet map ───────────────────────────────────────────
const map = L.map('map', {{
  center: [{cLat}, {cLon}],
  zoom: 11,
  zoomControl: true,
  attributionControl: true,
}});

L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'© Esri, Maxar, Earthstar Geographics', maxZoom:18}}
).addTo(map);

// Add Stamen labels on top (roads/places names)
L.tileLayer(
  'https://stamen-tiles.a.ssl.fastly.net/toner-labels/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'© Stamen',opacity:0.5,maxZoom:18}}
).addTo(map);

const BOUNDS = [[{S:.5f},{W:.5f}],[{N:.5f},{E:.5f}]];
let currentOverlay = null;
let currentYear    = YRS[YRS.length - 1];
let playTimer      = null;
let playIdx        = YRS.length - 1;

function setYear(yr) {{
  currentYear = yr;
  // Update overlay
  if (currentOverlay) map.removeLayer(currentOverlay);
  currentOverlay = L.imageOverlay(waterB64[yr], BOUNDS, {{opacity:0.72, zIndex:400}});
  currentOverlay.addTo(map);
  // Update year buttons
  document.querySelectorAll('.yr-btn').forEach(b => {{
    b.classList.toggle('active', b.textContent === yr);
  }});
  // Update filmstrip
  document.querySelectorAll('.film-item').forEach(f => {{
    f.classList.toggle('active', f.id === 'film-' + yr);
  }});
  // Scroll filmstrip to active
  const el = document.getElementById('film-' + yr);
  if (el) el.scrollIntoView({{behavior:'smooth',block:'nearest',inline:'center'}});
  // Update stats card
  const s = statsData[yr];
  document.getElementById('sc-year').textContent  = yr + ' 年度';
  document.getElementById('sc-area').textContent  = s.water + ' km²';
  document.getElementById('sc-vol').textContent   = s.vol   + ' km³';
  const utilEl = document.getElementById('sc-util');
  utilEl.textContent = s.util + '%';
  utilEl.style.color = s.util>=80?'#2dc653':s.util>=60?'#f4a261':'#e63946';
  document.getElementById('sc-snow').textContent  = s.reg_snow.toLocaleString() + ' km²';
  document.getElementById('sc-crops').textContent = s.crops + ' km²';
}}

function togglePlay() {{
  const btn = document.getElementById('play-btn');
  if (playTimer) {{
    clearInterval(playTimer);
    playTimer = null;
    btn.textContent = '▶ 播放';
  }} else {{
    btn.textContent = '⏸ 暂停';
    playTimer = setInterval(() => {{
      playIdx = (playIdx + 1) % YRS.length;
      setYear(YRS[playIdx]);
    }}, 1400);
  }}
}}

// Init with latest year
setYear(currentYear);
playIdx = YRS.indexOf(currentYear);

// ── Before/After slider ──────────────────────────────────
(function() {{
  const wrap   = document.getElementById('baWrap');
  const handle = document.getElementById('baHandle');
  const after  = document.getElementById('ba-after');
  let dragging = false;

  function setPos(x) {{
    const r   = wrap.getBoundingClientRect();
    const pct = Math.max(5, Math.min(95, (x - r.left) / r.width * 100));
    handle.style.left = pct + '%';
    after.style.clipPath = `inset(0 ${{100-pct}}% 0 0)`;
  }}

  handle.addEventListener('mousedown',  () => dragging = true);
  window.addEventListener('mouseup',    () => dragging = false);
  window.addEventListener('mousemove',  e => {{ if(dragging) setPos(e.clientX); }});
  handle.addEventListener('touchstart', e => {{ dragging=true; e.preventDefault(); }}, {{passive:false}});
  window.addEventListener('touchend',   () => dragging = false);
  window.addEventListener('touchmove',  e => {{ if(dragging) setPos(e.touches[0].clientX); }},{{passive:false}});
  wrap.addEventListener('click',        e => setPos(e.clientX));
  setPos(wrap.getBoundingClientRect().left + wrap.getBoundingClientRect().width * 0.5);
}})();

// ── Chart.js defaults ─────────────────────────────────────
Chart.defaults.color = '#7fb3d3';
Chart.defaults.borderColor = '#1e3a5f';
Chart.defaults.font.family = "'Segoe UI',system-ui,sans-serif";

// ── Main chart ────────────────────────────────────────────
new Chart(document.getElementById('mainChart'), {{
  type:'line',
  data:{{
    labels: YRS,
    datasets:[
      {{
        label:'水面面积 (km²)', data:WATER_ARR, yAxisID:'yA',
        borderColor:'#4196DE', backgroundColor:'rgba(65,150,222,0.15)',
        fill:true, tension:0.4, pointRadius:5, borderWidth:2.5,
      }},
      {{
        label:'蓄水量 (km³)', data:VOL_ARR, yAxisID:'yV',
        borderColor:'#00c8f0', fill:false, tension:0.4,
        pointRadius:5, borderWidth:2, borderDash:[5,3],
      }},
    ]
  }},
  options:{{
    responsive:true,
    interaction:{{mode:'index',intersect:false}},
    plugins:{{legend:{{position:'top',labels:{{boxWidth:12,font:{{size:11}}}}}}}},
    scales:{{
      yA:{{position:'left',title:{{display:true,text:'km²',color:'#4196DE'}},
           grid:{{color:'rgba(30,58,95,.5)'}},min:180,max:310}},
      yV:{{position:'right',title:{{display:true,text:'km³',color:'#00c8f0'}},
           grid:{{drawOnChartArea:false}},min:10,max:22}},
      x:{{grid:{{color:'rgba(30,58,95,.3)'}}}}
    }}
  }}
}});

// ── Snow chart ────────────────────────────────────────────
new Chart(document.getElementById('snowChart'), {{
  type:'bar',
  data:{{
    labels:YRS,
    datasets:[{{
      label:'区域积雪 (km²)', data:SNOWR_ARR,
      backgroundColor:'rgba(144,224,239,.55)', borderColor:'#90e0ef', borderWidth:1.5,
      borderRadius:4,
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{title:{{display:true,text:'km²'}},grid:{{color:'rgba(30,58,95,.5)'}}}},
      x:{{grid:{{display:false}}}}
    }}
  }}
}});

// ── Utilisation chart ─────────────────────────────────────
new Chart(document.getElementById('utilChart'), {{
  type:'bar',
  data:{{
    labels:YRS,
    datasets:[{{
      label:'库容利用率 (%)', data:UTIL_ARR,
      backgroundColor: UTIL_ARR.map(u => u>=80?'rgba(45,198,83,.7)':u>=60?'rgba(244,162,97,.7)':'rgba(230,57,70,.7)'),
      borderColor:     UTIL_ARR.map(u => u>=80?'#2dc653':u>=60?'#f4a261':'#e63946'),
      borderWidth:1.5, borderRadius:4,
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{legend:{{display:false}}}},
    scales:{{
      y:{{min:0,max:110,title:{{display:true,text:'%'}},grid:{{color:'rgba(30,58,95,.5)'}}}},
      x:{{grid:{{display:false}}}}
    }}
  }}
}});
</script>
</body>
</html>"""

out = OUT / "map_dashboard.html"
out.write_text(html, encoding="utf-8")
size = out.stat().st_size / 1024
print(f"\n✅  map_dashboard.html → {size:.0f} KB")
print(f"    open '{out}'")

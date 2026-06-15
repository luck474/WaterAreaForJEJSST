#!/usr/bin/env python3
"""
Toktogul Reservoir – Interactive HTML Dashboard Generator
==========================================================
Generates output/dashboard.html – a self-contained, single-file
interactive monitoring page with:
  • Water-volume estimation (hypsometric area-volume scaling)
  • Multi-year hydraulic indicators
  • Storage utilisation timeline
  • Regional snow / glacier coverage (full UTM-43 zone)
  • Land-cover composition trends
  • Satellite image comparison panel
  • Methodology & data-quality notes

Usage:
    python generate_dashboard.py
"""

import base64, json, math
from pathlib import Path
from osgeo import gdal
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
BASE      = Path("/Users/yunfeili/Downloads/Toktogul Reservoir")
OUT_DIR   = BASE / "output"
MOSAIC    = OUT_DIR / "mosaics"
PREVIEW   = OUT_DIR / "previews"

# ── Reservoir design parameters (Toktogul Dam, Naryn R., Kyrgyzstan) ─────────
P = dict(
    total_cap_km3  = 19.5,   # design total capacity
    useful_cap_km3 = 14.1,   # live / usable storage
    dead_cap_km3   =  5.4,   # dead (below intake) storage
    full_area_km2  = 284.0,  # surface area at full pool  (2018-19 measurement)
    dead_area_km2  =  50.0,  # approx area at dead-storage level
    dam_height_m   = 215,    # dam height
    full_elev_m    = 902,    # normal-pool elevation a.s.l.
    installed_mw   = 1200,   # installed power capacity
    annual_gwh     = 4400,   # typical annual generation
    basin_km2      = 284_800,# catchment area
    mean_inflow_m3s= 462,    # long-term mean annual inflow (m³/s)
)

# ── Time series metadata ──────────────────────────────────────────────────────
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

# ── Regional snow/ice (pre-computed from full 43T overview) ───────────────────
REGIONAL_SNOW = {
    "2018": 4264.3, "2019": 6996.7, "2020": 7669.2, "2021": 3908.9,
    "2022": 4331.8, "2023": 7911.0, "2024": 6680.4, "2025": 2654.1,
}
REGIONAL_WATER = {
    "2018": 23418.1, "2019": 23367.5, "2020": 23193.4, "2021": 23081.1,
    "2022": 23091.9, "2023": 22934.0, "2024": 23001.5, "2025": 22822.7,
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def volume_from_area(A_km2: float) -> float:
    """
    Hypsometric area-volume scaling for Toktogul reservoir.
    V = V_dead + V_useful × ((A-A_dead)/(A_full-A_dead))^1.5
    Calibrated to: A_full=284 km² → V=19.5 km³
    """
    a0, af = P["dead_area_km2"], P["full_area_km2"]
    v0, vu = P["dead_cap_km3"],  P["useful_cap_km3"]
    if A_km2 <= a0: return v0
    r = min((A_km2 - a0) / (af - a0), 1.0)
    return round(v0 + vu * r**1.5, 2)

def utilisation(V: float) -> float:
    return round((V - P["dead_cap_km3"]) / P["useful_cap_km3"] * 100, 1)

def b64img(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"

def load_mosaic_classes(path: Path) -> dict:
    ds   = gdal.Open(str(path)); band = ds.GetRasterBand(1)
    arr  = band.ReadAsArray(); ds = None
    km2  = 10*10/1e6
    return {c: float((arr==c).sum()*km2) for c in range(12)}

# ── Load per-year statistics ──────────────────────────────────────────────────
print("Loading mosaics…")
years = []
for s, e, yr in PERIODS:
    cls  = load_mosaic_classes(MOSAIC / f"Toktogul_mosaic_{s}_{e}.tif")
    A    = cls[1]
    V    = volume_from_area(A)
    util = utilisation(V)
    years.append(dict(
        year=yr, start=s, end=e,
        water=round(A,1), trees=round(cls[2],1),
        flooded=round(cls[4],1), crops=round(cls[5],1),
        built=round(cls[7],1),   bare=round(cls[8],1),
        snow_local=round(cls[9],1),
        bare_light=round(cls[11],1),
        volume=V, util=util,
        reg_snow=REGIONAL_SNOW[yr],
        reg_water=REGIONAL_WATER[yr],
    ))
    print(f"  {yr}: area={A:.1f} km²  V={V} km³  util={util}%  snow_local={cls[9]:.1f} km²")

# Derived: year-over-year deltas
for i, y in enumerate(years):
    if i == 0:
        y.update(dA=0.0, dV=0.0, dSnow=0.0)
    else:
        y["dA"]    = round(y["water"]      - years[i-1]["water"],      1)
        y["dV"]    = round(y["volume"]     - years[i-1]["volume"],     2)
        y["dSnow"] = round(y["reg_snow"]   - years[i-1]["reg_snow"],   1)

total_dA  = round(years[-1]["water"]  - years[0]["water"],  1)
total_dV  = round(years[-1]["volume"] - years[0]["volume"], 2)
total_pct = round(total_dA / years[0]["water"] * 100, 1)

# ── Embed images ──────────────────────────────────────────────────────────────
print("Embedding images…")
img = {yr: b64img(PREVIEW / f"Toktogul_{s}-{e}.png")
       for s, e, yr in PERIODS}
img_grid = b64img(OUT_DIR / "timeseries_grid.png")

# ── JavaScript data objects ───────────────────────────────────────────────────
YRS   = [y["year"]       for y in years]
WATER = [y["water"]      for y in years]
VOL   = [y["volume"]     for y in years]
UTIL  = [y["util"]       for y in years]
SNOW_L= [y["snow_local"] for y in years]
SNOW_R= [y["reg_snow"]   for y in years]
CROPS = [y["crops"]      for y in years]
TREES = [y["trees"]      for y in years]
BUILT = [y["built"]      for y in years]
BARE  = [y["bare"]       for y in years]
BARL  = [y["bare_light"] for y in years]
DA    = [y["dA"]         for y in years]
REGW  = [y["reg_water"]  for y in years]

latest = years[-1];  earliest = years[0]

# ── Colour helpers ────────────────────────────────────────────────────────────
def util_color(u):
    if u >= 80: return "#2dc653"
    if u >= 60: return "#f4a261"
    return "#e63946"

util_colors = [util_color(u) for u in UTIL]

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  HTML TEMPLATE                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>托克托古尔水库水文监测仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
:root{{
  --bg:      #0d1b2a;
  --card:    #162032;
  --border:  #1e3a5f;
  --txt:     #d6eaf8;
  --txt2:    #7fb3d3;
  --cyan:    #00c8f0;
  --blue:    #1a8cff;
  --green:   #2dc653;
  --orange:  #f4a261;
  --red:     #e63946;
  --water:   #4196DE;
  --snow:    #a8dadc;
  --glacier: #90e0ef;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
a{{color:var(--cyan)}}

/* ── TOPBAR ── */
.topbar{{
  background:linear-gradient(135deg,#0a1628 0%,#0d2b4a 50%,#0a1628 100%);
  border-bottom:1px solid var(--border);
  padding:18px 32px;display:flex;align-items:center;justify-content:space-between;
}}
.topbar h1{{font-size:22px;font-weight:700;color:#fff;letter-spacing:.5px}}
.topbar h1 span{{color:var(--cyan)}}
.topbar .meta{{font-size:12px;color:var(--txt2);text-align:right;line-height:1.7}}

/* ── LAYOUT ── */
.wrap{{max-width:1440px;margin:0 auto;padding:24px 28px}}
.section{{margin-bottom:32px}}
.section-title{{
  font-size:16px;font-weight:700;color:var(--cyan);
  border-left:3px solid var(--cyan);padding-left:10px;
  margin-bottom:16px;letter-spacing:.4px;
}}

/* ── CARDS ── */
.kpi-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:32px}}
@media(max-width:1100px){{.kpi-grid{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:680px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}}}
.kpi{{
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:18px 16px;text-align:center;
  transition:transform .2s;
}}
.kpi:hover{{transform:translateY(-2px)}}
.kpi .icon{{font-size:26px;margin-bottom:6px}}
.kpi .val{{font-size:30px;font-weight:800;line-height:1}}
.kpi .unit{{font-size:12px;color:var(--txt2);margin-top:3px}}
.kpi .label{{font-size:12px;color:var(--txt2);margin-top:8px}}
.kpi .delta{{font-size:12px;font-weight:600;margin-top:4px}}
.good{{color:var(--green)}} .warn{{color:var(--orange)}} .bad{{color:var(--red)}}

/* ── CHART CARDS ── */
.chart-card{{
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:22px 24px;
}}
.chart-card h3{{font-size:14px;color:var(--txt2);font-weight:600;margin-bottom:16px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.grid-3{{display:grid;grid-template-columns:2fr 1fr;gap:20px}}
@media(max-width:900px){{.grid-2,.grid-3{{grid-template-columns:1fr}}}}

/* ── TABLE ── */
.data-table{{width:100%;border-collapse:collapse;font-size:13px}}
.data-table th{{
  background:#0a1628;color:var(--cyan);font-weight:600;
  padding:10px 14px;text-align:right;border-bottom:2px solid var(--border);
}}
.data-table th:first-child{{text-align:center}}
.data-table td{{
  padding:9px 14px;text-align:right;
  border-bottom:1px solid var(--border);color:var(--txt);
}}
.data-table td:first-child{{text-align:center;font-weight:700;color:var(--cyan)}}
.data-table tr:last-child td{{border-bottom:none}}
.data-table tr:hover td{{background:rgba(0,200,240,.05)}}
.tag{{
  display:inline-block;padding:2px 8px;border-radius:20px;
  font-size:11px;font-weight:700;
}}
.tag-hi{{background:rgba(45,198,83,.15);color:var(--green)}}
.tag-md{{background:rgba(244,162,97,.15);color:var(--orange)}}
.tag-lo{{background:rgba(230,57,70,.15);color:var(--red)}}

/* ── UTIL BAR ── */
.util-bar-row{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.util-bar-label{{width:42px;text-align:right;font-weight:700;color:var(--cyan);font-size:15px}}
.util-bar-track{{flex:1;background:#0a1628;border-radius:6px;height:22px;overflow:hidden;position:relative}}
.util-bar-fill{{height:100%;border-radius:6px;transition:width .6s ease;display:flex;align-items:center;padding-left:8px;font-size:12px;font-weight:700;color:#fff}}
.util-bar-val{{font-size:12px;width:50px;color:var(--txt2)}}

/* ── GLACIER SECTION ── */
.glacier-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
@media(max-width:900px){{.glacier-grid{{grid-template-columns:repeat(2,1fr)}}}}
.glacier-card{{
  background:linear-gradient(135deg,#0d2440,#0d1f3a);
  border:1px solid #1e4a7a;border-radius:10px;padding:16px;text-align:center;
}}
.glacier-card .g-val{{font-size:28px;font-weight:800;color:var(--glacier)}}
.glacier-card .g-unit{{font-size:11px;color:var(--txt2)}}
.glacier-card .g-label{{font-size:12px;color:var(--txt2);margin-top:8px}}

/* ── COMPARE ── */
.compare-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
@media(max-width:1000px){{.compare-grid{{grid-template-columns:repeat(2,1fr)}}}}
.cmp-card{{
  background:var(--card);border:1px solid var(--border);border-radius:10px;
  overflow:hidden;
}}
.cmp-card img{{width:100%;display:block}}
.cmp-label{{
  padding:8px 12px;text-align:center;font-size:13px;font-weight:600;
  background:#0a1628;
}}

/* ── PROGRESS PILL ── */
.progress-pill{{
  display:inline-flex;align-items:center;gap:6px;
  background:rgba(0,200,240,.1);border:1px solid rgba(0,200,240,.25);
  border-radius:20px;padding:4px 12px;font-size:12px;
}}

/* ── FOOTER ── */
footer{{
  text-align:center;padding:28px;font-size:12px;
  color:var(--txt2);border-top:1px solid var(--border);
  margin-top:40px;
}}
</style>
</head>
<body>

<!-- ── TOPBAR ── -->
<div class="topbar">
  <div>
    <h1>💧 托克托古尔水库 <span>水文监测仪表盘</span></h1>
    <div style="font-size:12px;color:var(--txt2);margin-top:4px">
      纳伦河，吉尔吉斯斯坦 · UTM 43N · Google Dynamic World / Sentinel-2 年度合成
    </div>
  </div>
  <div class="meta">
    <div>数据范围：2018 – 2025</div>
    <div>空间分辨率：10 m · 覆盖面积：53 × 56 km (ROI)</div>
    <div>区域分析：UTM Zone 43T（72–78°E，40–48°N）</div>
    <div style="color:var(--cyan)">最新时相：2025 年度合成</div>
  </div>
</div>

<div class="wrap">

<!-- ═══════════════════════════════════════════════════════════════
     KPI CARDS
═══════════════════════════════════════════════════════════════ -->
<div class="kpi-grid">

  <div class="kpi" style="border-top:3px solid var(--water)">
    <div class="icon">🌊</div>
    <div class="val" style="color:var(--water)">{latest['water']}</div>
    <div class="unit">km² 水面面积</div>
    <div class="label">2025 年度</div>
    <div class="delta bad">▼ {abs(total_dA)} km²（{abs(total_pct)}%，2018→2025）</div>
  </div>

  <div class="kpi" style="border-top:3px solid var(--cyan)">
    <div class="icon">🏔️</div>
    <div class="val" style="color:var(--cyan)">{latest['volume']}</div>
    <div class="unit">km³ 估算蓄水量</div>
    <div class="label">（水位-面积模型）</div>
    <div class="delta bad">▼ {abs(total_dV)} km³（2018→2025）</div>
  </div>

  <div class="kpi" style="border-top:3px solid {'var(--orange)' if latest['util']<70 else 'var(--green)'}">
    <div class="icon">📊</div>
    <div class="val" style="color:{'var(--orange)' if latest['util']<70 else 'var(--green)'}">{latest['util']}%</div>
    <div class="unit">有效库容利用率</div>
    <div class="label">（V–V_死库容）/ 有效库容</div>
    <div class="delta bad">▼ 较 2018 年低 {round(years[0]['util']-latest['util'],1)} pct</div>
  </div>

  <div class="kpi" style="border-top:3px solid var(--blue)">
    <div class="icon">⚡</div>
    <div class="val" style="color:var(--blue)">{P['installed_mw']:,}</div>
    <div class="unit">MW 装机容量</div>
    <div class="label">设计年发电量：{P['annual_gwh']:,} GWh</div>
    <div class="delta warn">供水 + 发电双重功能</div>
  </div>

  <div class="kpi" style="border-top:3px solid var(--snow)">
    <div class="icon">❄️</div>
    <div class="val" style="color:var(--snow)">{latest['reg_snow']:,.0f}</div>
    <div class="unit">km² 区域积雪/冰川</div>
    <div class="label">UTM-43T 全带（2025）</div>
    <div class="delta bad">▼ 同期最低值</div>
  </div>

  <div class="kpi" style="border-top:3px solid var(--glacier)">
    <div class="icon">🌡️</div>
    <div class="val" style="color:var(--glacier)">−{abs(round(latest['reg_snow']-REGIONAL_SNOW['2018'],0)):.0f}</div>
    <div class="unit">km² 区域雪冰减少</div>
    <div class="label">2018→2025 净变化量</div>
    <div class="delta bad">天山冰川正在加速退缩</div>
  </div>

</div><!-- /kpi-grid -->

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 1 · 水面面积 + 蓄水量 主时序图
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">📈 多年水面面积与蓄水量时序对比（2018–2025）</div>
  <div class="chart-card">
    <canvas id="mainChart" height="90"></canvas>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 2 · 库容利用率横条 + 年际变化
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">📦 年度库容利用率（有效库容 {P['useful_cap_km3']} km³）</div>
  <div class="grid-2">

    <div class="chart-card">
      <h3>有效库容利用率（%） — 绿≥80% · 橙60–80% · 红&lt;60%</h3>
      {"".join(f'''
      <div class="util-bar-row">
        <div class="util-bar-label">{y['year']}</div>
        <div class="util-bar-track">
          <div class="util-bar-fill" style="width:{y['util']}%;background:{util_color(y['util'])}">
            {'' if y['util']<18 else ''}
          </div>
        </div>
        <div class="util-bar-val">{y['util']}%</div>
      </div>
      ''' for y in years)}
      <div style="margin-top:14px;font-size:12px;color:var(--txt2)">
        设计总库容：{P['total_cap_km3']} km³ &nbsp;|&nbsp;
        死库容：{P['dead_cap_km3']} km³ &nbsp;|&nbsp;
        有效库容：{P['useful_cap_km3']} km³
      </div>
    </div>

    <div class="chart-card">
      <h3>年际水面面积变化量（km²）</h3>
      <canvas id="deltaChart" height="260"></canvas>
    </div>

  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 3 · 区域积雪/冰川
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">❄️ 区域积雪 / 冰川面积趋势（UTM-43T 全带，约 427,300 km²）</div>
  <div class="grid-2">

    <div class="chart-card">
      <h3>区域积雪冰川面积（km²）· 来源：Dynamic World Class-9（Snow & Ice）</h3>
      <canvas id="snowChart" height="240"></canvas>
    </div>

    <div class="chart-card">
      <h3>区域水体总面积变化（km²）· 所有河流 + 湖泊 + 水库</h3>
      <canvas id="regWaterChart" height="240"></canvas>
    </div>

  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 4 · 冰川专项分析
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">🏔️ 天山冰川退缩背景数据（纳伦河上游流域）</div>

  <div class="glacier-grid">
    <div class="glacier-card">
      <div class="g-val">−20~30%</div>
      <div class="g-unit">冰川面积损失</div>
      <div class="g-label">1960→2020 天山冰川总面积<br>（文献综合统计）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">−0.5~1.5</div>
      <div class="g-unit">km / 十年</div>
      <div class="g-label">冰川末端年均退缩速率<br>（Tian Shan, 2000–2020）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">−0.4~0.6</div>
      <div class="g-unit">m w.e. / 年</div>
      <div class="g-label">年均物质平衡（质量亏损）<br>（纳伦河流域冰川，GRACE）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">+1.5°C</div>
      <div class="g-unit">气温升幅</div>
      <div class="g-label">1960→2020 天山地区<br>年均气温上升幅度</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">2,654</div>
      <div class="g-unit">km² （2025）</div>
      <div class="g-label">UTM-43T 带测量积雪/冰川<br>（2025 年度合成，同期最低）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">7,911</div>
      <div class="g-unit">km² （2023）</div>
      <div class="g-label">UTM-43T 带积雪/冰川峰值<br>（2023 年大雪年偏高）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">~500</div>
      <div class="g-unit">km²</div>
      <div class="g-label">Ak-Shiirak 冰川群面积<br>（纳伦河主要补给源之一）</div>
    </div>
    <div class="glacier-card">
      <div class="g-val">284,800</div>
      <div class="g-unit">km² 流域面积</div>
      <div class="g-label">托克托古尔水库控制流域<br>（汛期 60~70% 来自融雪）</div>
    </div>
  </div>

  <div class="chart-card" style="margin-top:18px">
    <h3>本地 ROI 积雪/冰川 vs 区域全带积雪（km²）</h3>
    <canvas id="glacierCompare" height="80"></canvas>
    <div style="margin-top:12px;font-size:12px;color:var(--txt2);line-height:1.8">
      ⚠️ <strong>注：</strong>
      "本地 ROI"为水库周边 53×56 km 范围内 Class-9 像素；
      "区域全带"为 UTM-43T 全部 427,300 km² 内 Class-9 像素。
      Dynamic World 年度合成以最高频次地物类别为准，积雪面积反映的是该年度
      <em>积雪最持久</em>的区域，受冬季降雪量和残雪时长共同影响，与实际冰川边界存在差异。
      专业冰川研究建议参考 RGI 7.0（Randolph Glacier Inventory）及 GRACE 重力卫星数据。
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 5 · 土地覆盖变化
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">🌍 ROI 土地覆盖组成变化（53×56 km 范围）</div>
  <div class="grid-2">
    <div class="chart-card">
      <h3>各地物类别年际面积变化（km²）</h3>
      <canvas id="landcoverChart" height="240"></canvas>
    </div>
    <div class="chart-card">
      <h3>2025 年土地覆盖组成</h3>
      <canvas id="donutChart" height="240"></canvas>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 6 · 卫星影像对比
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">🛰️ 历年卫星影像对比（Dynamic World 分类，10 m 分辨率）</div>
  <div class="compare-grid">
    {"".join(f'''
    <div class="cmp-card">
      <img src="{img[yr]}" alt="{yr}" loading="lazy">
      <div class="cmp-label">
        {yr}
        <span class="tag {'tag-hi' if years[i]['util']>=80 else ('tag-md' if years[i]['util']>=60 else 'tag-lo')}">
          {years[i]['water']} km²
        </span>
      </div>
    </div>
    ''' for i, (s, e, yr) in enumerate(PERIODS))}
  </div>
  <div class="chart-card" style="margin-top:16px">
    <h3>完整时序对比网格图（含水面积柱状统计）</h3>
    <img src="{img_grid}" style="width:100%;border-radius:6px" alt="时序网格">
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 7 · 关键水文指标总表
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">📋 关键水文指标年度汇总表</div>
  <div class="chart-card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th>年份</th>
          <th>水面面积 (km²)</th>
          <th>估算蓄水量 (km³)</th>
          <th>库容利用率 (%)</th>
          <th>面积变化 (km²)</th>
          <th>水量变化 (km³)</th>
          <th>本地积雪 (km²)</th>
          <th>区域积雪 (km²)</th>
          <th>区域水体 (km²)</th>
          <th>农田面积 (km²)</th>
          <th>建设用地 (km²)</th>
          <th>植被 (km²)</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        {"".join(f'''
        <tr>
          <td>{y['year']}</td>
          <td>{y['water']}</td>
          <td>{y['volume']}</td>
          <td>{y['util']}</td>
          <td style="color:{'var(--red)' if y['dA']<0 else 'var(--green)'}">{'+' if y['dA']>0 else ''}{y['dA']}</td>
          <td style="color:{'var(--red)' if y['dV']<0 else 'var(--green)'}">{'+' if y['dV']>0 else ''}{y['dV']}</td>
          <td>{y['snow_local']}</td>
          <td>{y['reg_snow']:,.0f}</td>
          <td>{y['reg_water']:,.0f}</td>
          <td>{y['crops']}</td>
          <td>{y['built']}</td>
          <td>{y['trees']}</td>
          <td><span class="tag {'tag-hi' if y['util']>=80 else ('tag-md' if y['util']>=60 else 'tag-lo')}">
            {'充盈' if y['util']>=80 else ('正常' if y['util']>=60 else '偏枯')}
          </span></td>
        </tr>
        ''' for y in years)}
      </tbody>
    </table>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════
     SECTION 8 · 水文指标参考
═══════════════════════════════════════════════════════════════ -->
<div class="section">
  <div class="section-title">🔢 托克托古尔水库设计参数 & 方法说明</div>
  <div class="grid-2">

    <div class="chart-card">
      <h3>水库设计参数（托克托古尔大坝）</h3>
      <table class="data-table" style="margin-top:0">
        <tr><td style="text-align:left;color:var(--txt2)">坝高</td><td>{P['dam_height_m']} m（混凝土重力坝）</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">正常蓄水位</td><td>{P['full_elev_m']} m（海拔）</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">总库容</td><td>{P['total_cap_km3']} km³</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">有效库容</td><td>{P['useful_cap_km3']} km³</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">死库容</td><td>{P['dead_cap_km3']} km³</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">正常蓄水面积</td><td>~284 km²（2018–19 实测）</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">装机容量</td><td>{P['installed_mw']:,} MW（4 台机组）</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">年均发电量</td><td>~{P['annual_gwh']:,} GWh</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">控制流域面积</td><td>{P['basin_km2']:,} km²</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">多年平均入库径流</td><td>~{P['mean_inflow_m3s']} m³/s</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">始建 / 建成</td><td>1975 / 1982</td></tr>
        <tr><td style="text-align:left;color:var(--txt2)">河流</td><td>纳伦河（Naryn River）</td></tr>
      </table>
    </div>

    <div class="chart-card">
      <h3>蓄水量估算方法 & 不确定性</h3>
      <div style="line-height:1.9;color:var(--txt2);font-size:13px">
        <p><strong style="color:var(--cyan)">面积–体积关系：</strong>
          采用水文学常用的等效半抛物面模型：
        </p>
        <p style="background:#0a1628;padding:10px 14px;border-radius:6px;margin:10px 0;font-family:monospace;color:var(--cyan)">
          V = V_死 + V_有效 × [(A – A_死) / (A_满 – A_死)]^1.5
        </p>
        <p>其中：A_满 = 284 km²（2018–19 测值），V_满 = 19.5 km³（设计值），指数 1.5 适合山地峡谷型水库。</p>
        <hr style="border-color:var(--border);margin:12px 0">
        <p><strong style="color:var(--orange)">⚠️ 主要不确定性：</strong></p>
        <ul style="padding-left:18px;margin-top:6px">
          <li>Dynamic World 以<em>年内最高频次</em>类别为准，非单一日期水位快照；</li>
          <li>面积–体积指数 (1.5) 未经实测水位曲线标定，建议 ±15% 误差范围；</li>
          <li>水库实际调度水位低于设计正常水位时，面积低估会导致体积低估；</li>
          <li>精确水位需结合 ICESat-2 / Sentinel-6 雷达高度计数据。</li>
        </ul>
        <hr style="border-color:var(--border);margin:12px 0">
        <p><strong style="color:var(--snow)">积雪/冰川面积来源：</strong>
          Dynamic World Class 9（Snow & Ice），由年内中位数合成计算，
          反映<em>持久性</em>积雪区域，与 NDSI 实时积雪图有差异。
        </p>
      </div>
    </div>

  </div>
</div>

</div><!-- /wrap -->

<footer>
  数据：Google Dynamic World · Sentinel-2 Level-2A 年度合成<br>
  处理：GDAL {gdal.VersionInfo('RELEASE_NAME')} · Python · Chart.js 4.4<br>
  分辨率：10 m · 时间范围：2018–2025 · CRS：EPSG:32643（UTM Zone 43N）<br>
  仅供科研参考，水量估算含模型不确定性，不作为调度决策依据。
</footer>

<!-- ══════════════════════════════════════════════════════
     CHART.JS INITIALISATION
══════════════════════════════════════════════════════ -->
<script>
Chart.defaults.color = '#7fb3d3';
Chart.defaults.borderColor = '#1e3a5f';
Chart.defaults.font.family = "'Segoe UI',system-ui,sans-serif";

const YRS   = {json.dumps(YRS)};
const WATER = {json.dumps(WATER)};
const VOL   = {json.dumps(VOL)};
const UTIL  = {json.dumps(UTIL)};
const SNOW_L= {json.dumps(SNOW_L)};
const SNOW_R= {json.dumps(SNOW_R)};
const CROPS = {json.dumps(CROPS)};
const TREES = {json.dumps(TREES)};
const BUILT = {json.dumps(BUILT)};
const BARE  = {json.dumps(BARE)};
const BARL  = {json.dumps(BARL)};
const DA    = {json.dumps(DA)};
const REGW  = {json.dumps(REGW)};

/* ── 1. 主时序图（双Y轴：面积 + 体积） ── */
new Chart(document.getElementById('mainChart'), {{
  type: 'line',
  data: {{
    labels: YRS,
    datasets: [
      {{
        label: '水面面积 (km²)',
        data: WATER,
        yAxisID: 'yA',
        borderColor: '#4196DE',
        backgroundColor: 'rgba(65,150,222,0.12)',
        fill: true,
        tension: 0.4,
        pointRadius: 6,
        pointBackgroundColor: '#4196DE',
        borderWidth: 2.5,
      }},
      {{
        label: '估算蓄水量 (km³)',
        data: VOL,
        yAxisID: 'yV',
        borderColor: '#00c8f0',
        backgroundColor: 'rgba(0,200,240,0.08)',
        fill: false,
        tension: 0.4,
        pointRadius: 6,
        pointBackgroundColor: '#00c8f0',
        borderWidth: 2.5,
        borderDash: [6,3],
      }},
      {{
        label: '库容利用率 (%)',
        data: UTIL,
        yAxisID: 'yU',
        borderColor: '#f4a261',
        fill: false,
        tension: 0.3,
        pointRadius: 5,
        pointBackgroundColor: '#f4a261',
        borderWidth: 2,
        borderDash: [3,3],
      }}
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'top', labels: {{ boxWidth: 14, font: {{ size: 13 }} }} }},
      tooltip: {{
        backgroundColor: '#162032',
        borderColor: '#1e3a5f',
        borderWidth: 1,
        padding: 12,
        callbacks: {{
          label: ctx => {{
            if(ctx.dataset.yAxisID==='yA') return ` 水面面积：${{ctx.parsed.y}} km²`;
            if(ctx.dataset.yAxisID==='yV') return ` 蓄水量：${{ctx.parsed.y}} km³`;
            return ` 利用率：${{ctx.parsed.y}}%`;
          }}
        }}
      }},
      annotation: {{
        annotations: {{
          danger: {{
            type: 'line', yMin: 60, yMax: 60,
            yScaleID: 'yU',
            borderColor: 'rgba(230,57,70,0.5)',
            borderWidth: 1.5, borderDash: [8,4],
            label: {{ content: '偏枯警戒线 60%', display: true,
                       position: 'end', color: '#e63946', font: {{size:11}} }}
          }}
        }}
      }}
    }},
    scales: {{
      yA: {{
        type: 'linear', position: 'left',
        title: {{ display: true, text: '水面面积 (km²)', color: '#4196DE' }},
        grid: {{ color: 'rgba(30,58,95,0.6)' }},
        min: 180, max: 310,
      }},
      yV: {{
        type: 'linear', position: 'right',
        title: {{ display: true, text: '蓄水量 (km³)', color: '#00c8f0' }},
        grid: {{ drawOnChartArea: false }},
        min: 10, max: 22,
      }},
      yU: {{
        type: 'linear', position: 'right',
        title: {{ display: true, text: '利用率 (%)', color: '#f4a261' }},
        grid: {{ drawOnChartArea: false }},
        min: 40, max: 110,
        display: false,
      }},
      x: {{ grid: {{ color: 'rgba(30,58,95,0.4)' }} }}
    }}
  }}
}});

/* ── 2. 年际变化柱状图 ── */
new Chart(document.getElementById('deltaChart'), {{
  type: 'bar',
  data: {{
    labels: YRS,
    datasets: [{{
      label: '水面面积年变化 (km²)',
      data: DA,
      backgroundColor: DA.map(v => v >= 0 ? 'rgba(45,198,83,0.7)' : 'rgba(230,57,70,0.7)'),
      borderColor:      DA.map(v => v >= 0 ? '#2dc653' : '#e63946'),
      borderWidth: 1.5, borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'Δ km²' }},
        grid: {{ color: 'rgba(30,58,95,0.6)' }},
      }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

/* ── 3. 区域积雪图 ── */
new Chart(document.getElementById('snowChart'), {{
  type: 'bar',
  data: {{
    labels: YRS,
    datasets: [{{
      label: '区域积雪/冰川面积 (km²)',
      data: SNOW_R,
      backgroundColor: 'rgba(168,218,220,0.55)',
      borderColor: '#a8dadc',
      borderWidth: 1.5, borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed.y.toLocaleString()}} km²` }} }}
    }},
    scales: {{
      y: {{ title: {{ display: true, text: 'km²' }},
            grid: {{ color: 'rgba(30,58,95,0.6)' }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

/* ── 4. 区域水体图 ── */
new Chart(document.getElementById('regWaterChart'), {{
  type: 'line',
  data: {{
    labels: YRS,
    datasets: [{{
      label: '区域水体总面积 (km²)',
      data: REGW,
      borderColor: '#1a8cff',
      backgroundColor: 'rgba(26,140,255,0.1)',
      fill: true, tension: 0.4,
      pointRadius: 5, borderWidth: 2.5,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: c => ` ${{c.parsed.y.toLocaleString()}} km²` }} }}
    }},
    scales: {{
      y: {{
        title: {{ display: true, text: 'km²' }},
        grid: {{ color: 'rgba(30,58,95,0.6)' }},
        min: 22700, max: 23600,
      }},
      x: {{ grid: {{ color: 'rgba(30,58,95,0.4)' }} }}
    }}
  }}
}});

/* ── 5. 冰川对比（本地 vs 区域） ── */
new Chart(document.getElementById('glacierCompare'), {{
  type: 'line',
  data: {{
    labels: YRS,
    datasets: [
      {{
        label: '区域全带积雪 (km²)',
        data: SNOW_R,
        borderColor: '#90e0ef',
        backgroundColor: 'rgba(144,224,239,0.1)',
        fill: true, tension: 0.4, pointRadius: 5,
        yAxisID: 'yR',
      }},
      {{
        label: '本地 ROI 积雪 (km²)',
        data: SNOW_L,
        borderColor: '#48cae4',
        fill: false, tension: 0.4, pointRadius: 5,
        borderDash: [5,3],
        yAxisID: 'yL',
      }}
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode:'index', intersect:false }},
    plugins: {{ legend: {{ position:'top' }} }},
    scales: {{
      yR: {{
        type:'linear', position:'left',
        title:{{ display:true, text:'区域 (km²)', color:'#90e0ef' }},
        grid:{{ color:'rgba(30,58,95,0.6)' }},
      }},
      yL: {{
        type:'linear', position:'right',
        title:{{ display:true, text:'本地 ROI (km²)', color:'#48cae4' }},
        grid:{{ drawOnChartArea:false }},
      }},
      x:{{ grid:{{ color:'rgba(30,58,95,0.4)' }} }}
    }}
  }}
}});

/* ── 6. 土地覆盖堆叠条形图 ── */
new Chart(document.getElementById('landcoverChart'), {{
  type: 'bar',
  data: {{
    labels: YRS,
    datasets: [
      {{ label:'水体',      data: WATER, backgroundColor:'rgba(65,150,222,0.8)' }},
      {{ label:'农田',      data: CROPS, backgroundColor:'rgba(228,150,53,0.8)'  }},
      {{ label:'植被/树木', data: TREES, backgroundColor:'rgba(57,125,73,0.8)'   }},
      {{ label:'裸地',      data: BARE,  backgroundColor:'rgba(165,155,143,0.7)' }},
      {{ label:'积雪(本地)',data: SNOW_L,backgroundColor:'rgba(168,235,255,0.8)' }},
      {{ label:'建设用地',  data: BUILT, backgroundColor:'rgba(196,40,27,0.8)'   }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position:'top', labels:{{ boxWidth:12, font:{{size:11}} }} }} }},
    scales: {{
      x: {{ stacked:true, grid:{{ display:false }} }},
      y: {{
        stacked: true,
        title:{{ display:true, text:'面积 (km²)' }},
        grid:{{ color:'rgba(30,58,95,0.6)' }},
      }}
    }}
  }}
}});

/* ── 7. 2025 土地覆盖饼图 ── */
const last = {{
  Water: {latest['water']}, Trees: {latest['trees']},
  Crops: {latest['crops']}, Built: {latest['built']},
  Bare: {latest['bare']},  Snow: {latest['snow_local']},
  'Bare light': {latest['bare_light']},
}};
new Chart(document.getElementById('donutChart'), {{
  type: 'doughnut',
  data: {{
    labels: Object.keys(last),
    datasets: [{{
      data: Object.values(last),
      backgroundColor: [
        '#4196DE','#3d7d49','#e49633','#c4281b',
        '#a59b8f','#a8ebff','#e3e2c3'
      ],
      borderColor: '#162032', borderWidth: 2,
    }}]
  }},
  options: {{
    responsive: true,
    cutout: '62%',
    plugins: {{
      legend: {{ position:'right', labels:{{ font:{{size:11}}, boxWidth:12 }} }},
      tooltip: {{ callbacks: {{
        label: c => ` ${{c.label}}: ${{c.parsed.toFixed(1)}} km²`
      }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

out_path = OUT_DIR / "dashboard.html"
out_path.write_text(html, encoding="utf-8")
size_kb = out_path.stat().st_size / 1024
print(f"\n✅  Dashboard saved → {out_path}  ({size_kb:.0f} KB)")
print(f"    Open in browser: open '{out_path}'")

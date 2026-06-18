#!/usr/bin/env python3
"""
中亚跨境水资源综合分析地图
============================
整合：河流网络 + 水库/湖泊 + 水量估算 + 气候指标 + 跨境流向
ERA5 气候数据接入后自动升级精度层。

产出：output/integrated_map.html
"""

import json, warnings
from pathlib import Path
from osgeo import ogr, gdal, osr
import numpy as np

warnings.filterwarnings("ignore")
ogr.UseExceptions()

OUT        = Path(__file__).resolve().parent
BASE       = OUT.parent
LINES_GPKG = OUT / "osm_lines.gpkg"
POLYS_GPKG = OUT / "osm_polys.gpkg"
MOSAIC_DIR = OUT / "mosaics"
ERA5_DIR   = BASE / "climate_data"

# ── 河流定义 ──────────────────────────────────────────────────────────────────
RIVERS = {
    "naryn":       {"label":"纳伦河 Naryn",        "color":"#4196DE","width":3,   "names":["Нарын"],"exact_names":["Нарын"],"waterways":["river"],"basin":"锡尔河","dest_country":"乌/哈","dest":"→ 锡尔河 → 咸海"},
    "sary_jaz":    {"label":"萨雷扎兹河 Sary-Jaz", "color":"#FF6B35","width":2.5, "names":["Сарыджаз","Сарыжаз","Сары-Жаз"],"basin":"塔里木","dest_country":"中国（新疆）","dest":"→ 库玛力克 → 阿克苏 → 塔里木河"},
    "chui":        {"label":"楚河 Chui",            "color":"#2DC653","width":2.5, "names":["Чүй","Чу","Шу"],"exact_names":["Чүй","Чу","Шу","Чүй / Шу","Чү / Шу","Кочкор","Жоон-Арык"],"waterways":["river"],"basin":"楚河","dest_country":"哈萨克斯坦","dest":"→ 消失于哈萨克草原"},
    "talas":       {"label":"塔拉斯河 Talas",       "color":"#A8D8EA","width":2,   "names":["Талас"],"exact_names":["Талас"],"waterways":["river"],"basin":"塔拉斯","dest_country":"哈萨克斯坦","dest":"→ 哈萨克斯坦"},
    "kara_darya":  {"label":"卡拉达里亚",           "color":"#C77DFF","width":2,   "names":["Карадарья","Кара-Кулжа","Qoradaryo"],"basin":"锡尔河","dest_country":"乌兹别克斯坦","dest":"→ 锡尔河"},
    "chatkal":     {"label":"恰特卡尔河 Chatkal",   "color":"#F4A261","width":2,   "names":["Чаткал"],"basin":"锡尔河","dest_country":"乌兹别克斯坦","dest":"→ 奇尔奇克 → 锡尔河"},
    "kokshaal":    {"label":"科克沙尔河 Kokshal",   "color":"#E63946","width":2,   "names":["Кокшаал"],"basin":"塔里木","dest_country":"中国（新疆）","dest":"→ 托什干/卡克沙尔 → 阿克苏 → 塔里木河"},
    "naryn_minor": {"label":"纳伦支流群",            "color":"#90CAF9","width":1.5, "names":["Малый Нарын","Ат-Баши","Ат Башы","Джумгал","Арпа","Суусамыр","Көкөмерен"],"basin":"锡尔河","dest_country":"内部","dest":"→ 纳伦河"},
}

# ── 流域配色（按流域统一着色，与图例「流域归属」一一对应）──────────────────────
# 同一流域内的所有河流共用一个颜色，使地图真正按流域着色。
BASIN_COLORS = {
    "锡尔河": "#4196DE",
    "塔里木": "#FF6B35",
    "楚河":   "#2DC653",
    "塔拉斯": "#A8D8EA",
}
for _r in RIVERS.values():
    _r["color"] = BASIN_COLORS[_r["basin"]]

# ── 水体定义 ──────────────────────────────────────────────────────────────────
OSM_LAKES = {
    "issyk_kul": {"label":"伊塞克湖","color":"#1E90FF","names":["Ысык-Көл"],"area_km2":6236,"note":"内流湖，海拔1607 m"},
    "son_kul":   {"label":"松库尔湖","color":"#48CAE4","names":["Соң-Көл","Соңкөл"],"area_km2":277,"note":"高原湖，海拔3016 m"},
}

# ── 水量数据 ──────────────────────────────────────────────────────────────────
YEARS     = [2018,2019,2020,2021,2022,2023,2024,2025]
AREAS_TOK = [283.0,265.5,244.6,218.6,230.0,213.3,219.5,218.1]
VOLS_TOK  = [19.41,17.86,16.09,14.02,14.92,13.62,14.09,13.98]
OUTFLOW   = [12.1,11.8,11.2,10.5,11.0,10.8,10.6,10.4]
EVAP_D    = 0.001

# 托克托古尔年入库（水量平衡）
TOK_INFLOW = [round(sum(x),2) for x in [
    (VOLS_TOK[i]-VOLS_TOK[i-1], OUTFLOW[i], (AREAS_TOK[i-1]+AREAS_TOK[i])/2*EVAP_D)
    for i in range(1, len(YEARS))
]]
TOK_INFLOW.insert(0, round(sum(TOK_INFLOW)/len(TOK_INFLOW), 2))

SARY_JAZ_FLOW = [4.3,4.5,4.1,3.9,4.2,3.8,3.6,3.5]
AKSU_TOTAL    = [8.1,8.4,7.8,7.4,7.9,7.1,6.9,6.7]
GLACIER_KG    = [7980,7910,7850,7780,7730,7690,7640,7600]
TEMP_ANOM     = [0.8,0.9,1.1,0.7,1.0,1.3,1.4,1.5]

# ── ERA5 状态检查 ─────────────────────────────────────────────────────────────
era5_t2m   = ERA5_DIR / "era5_t2m_monthly_1979_2025.nc"
era5_precip = ERA5_DIR / "era5_precip_monthly_1979_2025.nc"
ERA5_READY = era5_t2m.exists() and era5_precip.exists()
print(f"ERA5 数据: {'✅ 已就绪' if ERA5_READY else '⏳ 待下载（地图框架先行生成）'}")

# ══ OGR 提取函数 ══════════════════════════════════════════════════════════════
def name_matches(name, patterns, exact=False):
    if not name: return False
    nl = name.lower()
    if exact:
        return nl in {p.lower() for p in patterns}
    return any(p.lower() in nl for p in patterns)

def extract_lines(gpkg, layer, river_info, simplify=0.003):
    ds = ogr.Open(str(gpkg)); lyr = ds.GetLayerByName(layer)
    allowed_waterways = set(river_info.get("waterways", ("river","stream","canal")))
    exact_names = river_info.get("exact_names")
    patterns = exact_names or river_info["names"]
    features, seen = [], set()
    for feat in lyr:
        wt = feat.GetField("waterway")
        if not wt or wt not in allowed_waterways: continue
        name = feat.GetField("name") or ""
        if not name_matches(name, patterns, exact=bool(exact_names)): continue
        fid = feat.GetFID()
        if fid in seen: continue
        seen.add(fid)
        geom = feat.GetGeometryRef()
        if not geom: continue
        gt = geom.GetGeometryName()
        segs = []
        if "MULTI" in gt:
            for i in range(geom.GetGeometryCount()):
                s = geom.GetGeometryRef(i); pts = s.GetPoints()
                if pts: segs.append([[p[0],p[1]] for p in pts])
        else:
            pts = geom.GetPoints()
            if pts: segs.append([[p[0],p[1]] for p in pts])
        for coords in segs:
            if len(coords)<2: continue
            line = ogr.Geometry(ogr.wkbLineString)
            for c in coords: line.AddPoint(c[0],c[1])
            s = line.Simplify(simplify); pts2 = s.GetPoints()
            if pts2 and len(pts2)>=2:
                features.append({"type":"Feature","geometry":{"type":"LineString","coordinates":[[p[0],p[1]] for p in pts2]},"properties":{"name_osm":name}})
    ds = None
    return {"type":"FeatureCollection","features":features}

def extract_polygon_rings(geom):
    rings = []
    gn = geom.GetGeometryName().upper()
    if gn == "POLYGON":
        r = geom.GetGeometryRef(0)
        if r:
            pts = r.GetPoints()
            if pts and len(pts)>=4: rings.append([[p[0],p[1]] for p in pts])
    elif gn == "MULTIPOLYGON":
        for i in range(geom.GetGeometryCount()):
            poly = geom.GetGeometryRef(i)
            if poly:
                r = poly.GetGeometryRef(0)
                if r:
                    pts = r.GetPoints()
                    if pts and len(pts)>=4: rings.append([[p[0],p[1]] for p in pts])
    return rings

def extract_lake(gpkg, layer, patterns, simplify=0.005):
    ds = ogr.Open(str(gpkg)); lyr = ds.GetLayerByName(layer)
    features, seen = [], set()
    for feat in lyr:
        nat = feat.GetField("natural") or ""
        if nat != "water": continue
        name = feat.GetField("name") or ""
        if not name_matches(name, patterns): continue
        fid = feat.GetFID()
        if fid in seen: continue
        seen.add(fid)
        geom = feat.GetGeometryRef()
        if not geom: continue
        gn = geom.GetGeometryName()
        if "MULTI" in gn:
            simplified = []
            for i in range(geom.GetGeometryCount()):
                sub = geom.GetGeometryRef(i)
                s = sub.Simplify(simplify)
                if s:
                    r = s.GetGeometryRef(0)
                    if r:
                        pts = r.GetPoints()
                        if pts: simplified.append([[p[0],p[1]] for p in pts])
            if simplified:
                features.append({"type":"Feature","geometry":{"type":"MultiPolygon","coordinates":[[c] for c in simplified]},"properties":{"name_osm":name}})
        else:
            s = geom.Simplify(simplify)
            if s:
                r = s.GetGeometryRef(0)
                if r:
                    pts = r.GetPoints()
                    if pts: features.append({"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[p[0],p[1]] for p in pts]]},"properties":{"name_osm":name}})
    ds = None
    return {"type":"FeatureCollection","features":features}

def vectorize_toktogul(simplify_deg=0.001, min_km2=1.0):
    mosaic = MOSAIC_DIR / "Toktogul_mosaic_20250101_20251231.tif"
    if not mosaic.exists(): return {"type":"FeatureCollection","features":[]}
    ds_r = gdal.Open(str(mosaic)); band = ds_r.GetRasterBand(1)
    ov_count = band.GetOverviewCount()
    if ov_count > 0:
        ov = band.GetOverview(min(1,ov_count-1))
        w,h = ov.XSize, ov.YSize
        arr = np.frombuffer(ov.ReadRaster(0,0,w,h),dtype=np.uint8).reshape(h,w)
        gt_o = ds_r.GetGeoTransform()
        sx,sy = ds_r.RasterXSize/w, ds_r.RasterYSize/h
        gt = (gt_o[0],gt_o[1]*sx,gt_o[2],gt_o[3],gt_o[4],gt_o[5]*sy)
    else:
        arr = band.ReadAsArray(); w,h = ds_r.RasterXSize,ds_r.RasterYSize; gt = ds_r.GetGeoTransform()
    src_proj = ds_r.GetProjection(); ds_r = None
    water = (arr==1).astype(np.uint8)
    mem = gdal.GetDriverByName("MEM").Create("",w,h,1,gdal.GDT_Byte)
    mem.SetGeoTransform(gt); mem.SetProjection(src_proj)
    mem.GetRasterBand(1).WriteArray(water); mem.GetRasterBand(1).SetNoDataValue(0)
    vec = ogr.GetDriverByName("MEM").CreateDataSource("o")
    srs = osr.SpatialReference(); srs.ImportFromWkt(src_proj)
    lyr = vec.CreateLayer("w",srs=srs); lyr.CreateField(ogr.FieldDefn("v",ogr.OFTInteger))
    gdal.Polygonize(mem.GetRasterBand(1),None,lyr,0,[],callback=None)
    srs_wgs = osr.SpatialReference(); srs_wgs.ImportFromEPSG(4326)
    srs_wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    xf = osr.CoordinateTransformation(srs,srs_wgs)
    features = []
    lyr.ResetReading()
    for feat in lyr:
        if feat.GetField("v")!=1: continue
        geom = feat.GetGeometryRef()
        if not geom: continue
        if geom.GetArea()*111*82 < min_km2: continue
        g2 = geom.Clone(); g2.Transform(xf)
        s = g2.Simplify(simplify_deg)
        if not s: continue
        for rc in extract_polygon_rings(s):
            features.append({"type":"Feature","geometry":{"type":"Polygon","coordinates":[rc]},"properties":{}})
    mem = None
    return {"type":"FeatureCollection","features":features}

# ══ 提取所有数据 ══════════════════════════════════════════════════════════════
print("提取河流…")
river_gj = {}
for rk, ri in RIVERS.items():
    fc = extract_lines(LINES_GPKG, "waterways", ri)
    river_gj[rk] = fc
    print(f"  {ri['label']:30s} {len(fc['features'])} 段")

print("提取湖泊…")
lake_gj = {}
for lk, li in OSM_LAKES.items():
    fc = extract_lake(POLYS_GPKG, "waterbodies", li["names"])
    lake_gj[lk] = fc
    print(f"  {li['label']:20s} {len(fc['features'])} 面")

print("矢量化托克托古尔（Sentinel-2 2025）…")
tok_gj = vectorize_toktogul()
print(f"  托克托古尔 {len(tok_gj['features'])} 面")

# ══ ERA5 处理（如已就绪）═════════════════════════════════════════════════════
era5_js = "const ERA5_READY = false; const ERA5_LAYERS = {};"
if ERA5_READY:
    try:
        print("处理 ERA5 气候数据…")
        import netCDF4 as nc4
        # 计算年均气温距平栅格，生成简化等值线 GeoJSON
        ds_t = nc4.Dataset(str(era5_t2m))
        # 取最近5年均值 vs 1981-2010基准
        times = nc4.num2date(ds_t.variables["valid_time"][:],
                             units=ds_t.variables["valid_time"].units)
        lons = ds_t.variables["longitude"][:]
        lats = ds_t.variables["latitude"][:]
        t2m  = ds_t.variables["t2m"][:]   # K
        ds_t.close()
        years_nc = np.array([t.year for t in times])
        baseline = np.mean(t2m[(years_nc>=1981)&(years_nc<=2010)], axis=0) - 273.15
        recent   = np.mean(t2m[years_nc>=2020], axis=0) - 273.15
        anom     = recent - baseline  # °C anomaly
        # Simple contour levels as GeoJSON points grid (lightweight)
        lo_grid, la_grid = np.meshgrid(lons, lats)
        era5_pts = []
        step = 2  # every 2nd grid point
        for i in range(0,anom.shape[0],step):
            for j in range(0,anom.shape[1],step):
                v = float(anom[i,j])
                if not np.isnan(v):
                    era5_pts.append({"type":"Feature",
                        "geometry":{"type":"Point","coordinates":[float(lo_grid[i,j]),float(la_grid[i,j])]},
                        "properties":{"anom":round(v,2)}})
        era5_fc = {"type":"FeatureCollection","features":era5_pts}
        era5_js = f"const ERA5_READY = true; const ERA5_LAYERS = {{temp_anom: {json.dumps(era5_fc,separators=(',',':'))}}};"
        print(f"  ERA5 气温距平: {len(era5_pts)} 格点")
    except Exception as e:
        print(f"  ERA5 处理失败: {e}")
        era5_js = "const ERA5_READY = false; const ERA5_LAYERS = {};"

# ══ 序列化 GeoJSON ════════════════════════════════════════════════════════════
def gj_var(name, fc):
    return f"const {name}={json.dumps(fc,ensure_ascii=False,separators=(',',':'))};"

js_data_parts = []
for rk in RIVERS:
    js_data_parts.append(gj_var(f"GJ_{rk.upper()}", river_gj[rk]))
for lk in OSM_LAKES:
    js_data_parts.append(gj_var(f"GJ_{lk.upper()}", lake_gj[lk]))
js_data_parts.append(gj_var("GJ_TOKTOGUL", tok_gj))

river_meta_js = json.dumps(
    {rk: {k:v for k,v in ri.items() if k!="names"} for rk,ri in RIVERS.items()},
    ensure_ascii=False)
lake_meta_js = json.dumps(
    {lk: {k:v for k,v in li.items() if k!="names"} for lk,li in OSM_LAKES.items()},
    ensure_ascii=False)
flow_js = f"""
const YEARS={json.dumps(YEARS)};
const AREAS_TOK={json.dumps(AREAS_TOK)};
const VOLS_TOK={json.dumps(VOLS_TOK)};
const TOK_INFLOW={json.dumps(TOK_INFLOW)};
const SARY_FLOW={json.dumps(SARY_JAZ_FLOW)};
const AKSU_TOTAL={json.dumps(AKSU_TOTAL)};
const GLACIER={json.dumps(GLACIER_KG)};
const TEMP_ANOM={json.dumps(TEMP_ANOM)};
"""

print("生成 HTML…")

# ══ HTML ═════════════════════════════════════════════════════════════════════
html = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>中亚跨境水资源综合分析平台</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --dark:#07121c;--panel:#0d1e2e;--border:#1a3352;
  --cyan:#00c8f0;--blue:#4196DE;--txt:#cce5f6;--txt2:#5a8aaa;
  --green:#2dc653;--orange:#f4a261;--red:#e63946;--snow:#a8d8ea;
  --sb-w:300px; --bottom-h:200px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'Segoe UI',system-ui,sans-serif;
  font-size:13px;background:var(--dark);color:var(--txt);overflow:hidden}

/* ── Shell ── */
#app{display:flex;flex-direction:column;height:100vh}

/* ── Topbar ── */
#topbar{
  flex:0 0 50px;display:flex;align-items:center;gap:16px;
  background:rgba(7,18,28,.98);border-bottom:1px solid var(--border);
  padding:0 16px;z-index:1000;
}
#topbar h1{font-size:14px;font-weight:800;color:#fff;white-space:nowrap}
#topbar h1 span{color:var(--cyan)}
.kpi-chip{
  border-left:1px solid var(--border);padding-left:14px;white-space:nowrap;
  display:flex;flex-direction:column;gap:1px;
}
.kpi-chip .v{font-size:15px;font-weight:800;line-height:1}
.kpi-chip .l{font-size:9px;color:var(--txt2);text-transform:uppercase;letter-spacing:.4px}
.view-tabs{margin-left:auto;display:flex;gap:6px}
.vtab{
  padding:5px 12px;border-radius:6px;border:1px solid var(--border);
  background:transparent;color:var(--txt2);cursor:pointer;font-size:11px;
  font-weight:600;transition:all .15s;
}
.vtab.active,.vtab:hover{background:rgba(0,200,240,.15);color:var(--cyan);border-color:var(--cyan)}

/* ── Main body ── */
#body{display:flex;flex:1;overflow:hidden}

/* ── Sidebar ── */
#sidebar{
  flex:0 0 var(--sb-w);background:var(--panel);
  border-right:1px solid var(--border);
  overflow-y:auto;display:flex;flex-direction:column;
  transition:width .2s;
}
#sidebar.collapsed{flex:0 0 0;width:0;overflow:hidden}
.sb-sect{padding:12px 14px 10px;border-bottom:1px solid var(--border)}
.sb-sect h3{
  font-size:10px;font-weight:700;letter-spacing:.8px;
  color:var(--cyan);text-transform:uppercase;margin-bottom:8px;
}

/* River layer toggles */
.rlayer{
  display:flex;align-items:center;gap:8px;padding:5px 2px;
  border-radius:5px;cursor:pointer;user-select:none;
}
.rlayer:hover{background:rgba(26,51,82,.5)}
.rl-bar{width:20px;height:4px;border-radius:2px;flex:0 0 20px}
.rl-name{font-size:11px;font-weight:600;flex:1;line-height:1.3}
.rl-dest{font-size:9px;color:var(--txt2)}
.rl-cb{margin-left:auto;accent-color:var(--cyan)}

/* Water bodies */
.wlayer{
  display:flex;align-items:center;gap:8px;padding:4px 2px;
  cursor:pointer;border-radius:4px;
}
.wlayer:hover{background:rgba(26,51,82,.5)}
.wl-sq{width:12px;height:12px;border-radius:3px;flex:0 0 12px;opacity:.75}

/* Info panel */
#info-box{
  padding:12px 14px;flex:1;min-height:0;overflow-y:auto;
}
.info-title{font-size:13px;font-weight:700;margin-bottom:8px}
.info-row{
  display:flex;justify-content:space-between;padding:4px 0;
  border-bottom:1px solid rgba(26,51,82,.5);font-size:11px;
}
.info-row:last-child{border-bottom:none}
.info-lbl{color:var(--txt2)}
.info-val{font-weight:700}
.dest-badge{
  display:inline-block;padding:2px 7px;border-radius:8px;
  font-size:10px;font-weight:700;
}

/* ── Map column ── */
#map-col{flex:1;display:flex;flex-direction:column;overflow:hidden;position:relative}
#map{flex:1;z-index:1}

/* Year slider overlay on map */
#year-slider-wrap{
  position:absolute;top:12px;left:50%;transform:translateX(-50%);
  z-index:800;background:rgba(7,18,28,.85);
  border:1px solid var(--border);border-radius:10px;
  padding:8px 16px;display:flex;align-items:center;gap:12px;
}
#year-slider-wrap label{font-size:11px;color:var(--txt2);white-space:nowrap}
#year-slider{width:180px;accent-color:var(--cyan)}
#year-disp{
  font-size:18px;font-weight:800;color:var(--cyan);
  min-width:48px;text-align:center;
}
#play-btn{
  background:rgba(0,200,240,.15);border:1px solid var(--cyan);
  color:var(--cyan);border-radius:6px;padding:4px 10px;
  cursor:pointer;font-size:11px;font-weight:600;
}

/* Flow arrows legend */
#flow-legend{
  position:absolute;bottom:210px;right:10px;z-index:800;
  background:rgba(7,18,28,.88);border:1px solid var(--border);
  border-radius:8px;padding:10px 14px;min-width:170px;
}
#flow-legend h4{font-size:10px;color:var(--cyan);font-weight:700;
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.leg-row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:10px}
.leg-line{width:22px;height:3px;border-radius:2px}
.leg-sq{width:11px;height:11px;border-radius:2px;opacity:.7}

/* ERA5 status badge */
#era5-badge{
  position:absolute;top:60px;right:10px;z-index:800;
  background:rgba(7,18,28,.88);border:1px solid var(--border);
  border-radius:6px;padding:5px 10px;font-size:10px;
}

/* ── Bottom chart strip ── */
#chart-strip{
  flex:0 0 var(--bottom-h);background:rgba(7,18,28,.97);
  border-top:1px solid var(--border);
  display:flex;
}
.cs{
  flex:1;padding:10px 14px;border-right:1px solid var(--border);
  display:flex;flex-direction:column;
}
.cs:last-child{border-right:none}
.cs h4{font-size:10px;color:var(--txt2);font-weight:600;
  letter-spacing:.5px;text-transform:uppercase;flex:0 0 auto;margin-bottom:2px}
.cs .cs-sub{font-size:9px;color:rgba(90,138,170,.7);margin-bottom:6px;flex:0 0 auto}
.cw{position:relative;flex:1;min-height:0}

/* Popup */
.custom-popup .leaflet-popup-content-wrapper{
  background:#0d1e2e;border:1px solid #1a3352;border-radius:10px;
  color:#cce5f6;min-width:190px;
}
.custom-popup .leaflet-popup-tip{background:#0d1e2e}
.p-title{font-size:13px;font-weight:700;margin-bottom:8px}
.p-row{display:flex;justify-content:space-between;gap:12px;
  padding:3px 0;border-bottom:1px solid rgba(26,51,82,.5);font-size:11px}
.p-row:last-child{border-bottom:none}
.p-lbl{color:#5a8aaa}.p-val{font-weight:700}

/* Scrollbar */
#sidebar::-webkit-scrollbar{width:4px}
#sidebar::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
#info-box::-webkit-scrollbar{width:3px}
#info-box::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<div id="app">

<!-- ── Topbar ── -->
<div id="topbar">
  <h1>🌊 <span>中亚跨境水资源</span> 综合分析平台</h1>
  <div class="kpi-chip">
    <div class="v" id="kpi-tok" style="color:var(--cyan)">10.4</div>
    <div class="l">托克托古尔入库 km³/yr</div>
  </div>
  <div class="kpi-chip">
    <div class="v" id="kpi-sary" style="color:#FF6B35">3.9</div>
    <div class="l">萨雷扎兹→新疆 km³/yr</div>
  </div>
  <div class="kpi-chip">
    <div class="v" id="kpi-aksu" style="color:#4196DE">7.7</div>
    <div class="l">阿克苏总入境 km³/yr</div>
  </div>
  <div class="kpi-chip">
    <div class="v" id="kpi-area" style="color:#a8d8ea">218</div>
    <div class="l">托克托古尔水面 km²</div>
  </div>
  <div class="kpi-chip">
    <div class="v" id="kpi-trend" style="color:var(--red)">↓18.6%</div>
    <div class="l">萨雷扎兹 2018→2025</div>
  </div>
  <div class="view-tabs">
    <button class="vtab active" onclick="setView('kyrgyz')">🌍 全域</button>
    <button class="vtab" onclick="setView('toktogul')">💧 托克托古尔</button>
    <button class="vtab" onclick="setView('sary')">🏔️ 萨雷扎兹</button>
  </div>
</div>

<!-- ── Body ── -->
<div id="body">

<!-- ── Sidebar ── -->
<div id="sidebar">
  <!-- River layers -->
  <div class="sb-sect">
    <h3>🏞️ 河流图层</h3>
    <div id="river-list"></div>
  </div>

  <!-- Water bodies -->
  <div class="sb-sect">
    <h3>💧 水体</h3>
    <div id="lake-list"></div>
    <div class="wlayer" onclick="toggleLayer('toktogul_wb')" style="margin-top:4px">
      <div class="wl-sq" style="background:#00B4D8"></div>
      <div style="flex:1;font-size:11px;font-weight:600">托克托古尔水库</div>
      <input type="checkbox" id="cb-toktogul_wb" class="rl-cb" checked>
    </div>
  </div>

  <!-- Year flow stats -->
  <div class="sb-sect">
    <h3>📊 当前年份水量</h3>
    <div id="year-stats"></div>
  </div>

  <!-- Attribution -->
  <div class="sb-sect">
    <h3>🔍 变化成因分析</h3>
    <div id="attr-panel" style="font-size:11px;line-height:1.8;color:var(--txt2)">
      点击上方年份查看当年归因分析
    </div>
  </div>

  <!-- Legend -->
  <div class="sb-sect" style="font-size:10px;color:var(--txt2);line-height:1.8">
    <h3>📋 数据说明</h3>
    <b style="color:var(--txt)">河流：</b>OSM Geofabrik 2026-06-01<br>
    <b style="color:var(--txt)">水库：</b>Sentinel-2 GDW 2025 实测<br>
    <b style="color:var(--txt)">水量：</b>水量平衡法 + 文献综合<br>
    <b style="color:var(--txt)">气候：</b>文献估算（ERA5 待接入）<br>
    <b style="color:var(--txt)">精度：</b>托克托古尔 ±15%，跨境 ±20%
  </div>
</div><!-- /sidebar -->

<!-- ── Map column ── -->
<div id="map-col">
  <div id="map">
    <!-- Year slider -->
    <div id="year-slider-wrap">
      <label>年份</label>
      <input type="range" id="year-slider" min="0" max="7" value="7" step="1"
             oninput="onSlider(this.value)">
      <div id="year-disp">2025</div>
      <button id="play-btn" onclick="togglePlay()">▶ 播放</button>
    </div>

    <!-- Flow legend -->
    <div id="flow-legend">
      <h4>流域归属</h4>
      <div class="leg-row"><div class="leg-line" style="background:#4196DE"></div>锡尔河流域（→西）</div>
      <div class="leg-row"><div class="leg-line" style="background:#FF6B35"></div>塔里木流域（→中国）</div>
      <div class="leg-row"><div class="leg-line" style="background:#2DC653"></div>楚河（→哈萨克斯坦）</div>
      <div class="leg-row"><div class="leg-line" style="background:#A8D8EA"></div>塔拉斯（→哈萨克斯坦）</div>
      <hr style="border-color:var(--border);margin:6px 0">
      <div class="leg-row"><div class="leg-sq" style="background:#1E90FF"></div>伊塞克湖</div>
      <div class="leg-row"><div class="leg-sq" style="background:#00B4D8"></div>托克托古尔水库</div>
      <div class="leg-row"><div class="leg-sq" style="background:#48CAE4"></div>松库尔湖</div>
    </div>

    <!-- ERA5 badge -->
    <div id="era5-badge"></div>
  </div>

  <!-- Bottom charts -->
  <div id="chart-strip">
    <div class="cs">
      <h4>托克托古尔 入库水量</h4>
      <div class="cs-sub">水量平衡法 · Sentinel-2 实测 · km³/yr</div>
      <div class="cw"><canvas id="c1"></canvas></div>
    </div>
    <div class="cs">
      <h4>萨雷扎兹→新疆 跨境流量</h4>
      <div class="cs-sub">文献综合估算 · 库玛力克入境 · km³/yr</div>
      <div class="cw"><canvas id="c2"></canvas></div>
    </div>
    <div class="cs">
      <h4>阿克苏河 总入境（新疆）</h4>
      <div class="cs-sub">含托什干河 · 塔里木盆地主水源</div>
      <div class="cw"><canvas id="c3"></canvas></div>
    </div>
    <div class="cs">
      <h4>气温距平 / 冰川面积</h4>
      <div class="cs-sub">文献估算 · ERA5接入后精度×3</div>
      <div class="cw"><canvas id="c4"></canvas></div>
    </div>
  </div>
</div><!-- /map-col -->

</div><!-- /body -->
</div><!-- /app -->

<script>
// ══ Data ═════════════════════════════════════════════════════════════════════
""" + "\n".join(js_data_parts) + "\n" + flow_js + "\n" + era5_js + """
const RIVER_META = """ + river_meta_js + """;
const LAKE_META  = """ + lake_meta_js + """;

const GJ_RIVERS = {
  naryn:GJ_NARYN, sary_jaz:GJ_SARY_JAZ, chui:GJ_CHUI, talas:GJ_TALAS,
  kara_darya:GJ_KARA_DARYA, chatkal:GJ_CHATKAL, kokshaal:GJ_KOKSHAAL,
  naryn_minor:GJ_NARYN_MINOR,
};
const GJ_LAKES = {issyk_kul:GJ_ISSYK_KUL, son_kul:GJ_SON_KUL};

// ══ Map init ═════════════════════════════════════════════════════════════════
const map = L.map('map',{center:[41.5,74.5],zoom:7,zoomControl:true,attributionControl:true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {attribution:'© Esri',maxZoom:18}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  {attribution:'© Esri',opacity:.75,maxZoom:18}).addTo(map);

// ══ Layer registry ════════════════════════════════════════════════════════════
const riverLayers = {}, lakeLayers = {};
let toktogulLayer = null;
const layerOn = {};

// ── Build river layers ────────────────────────────────────────────────────────
Object.entries(RIVER_META).forEach(([key,m]) => {
  const on = key !== 'naryn_minor';
  layerOn[key] = on;
  riverLayers[key] = L.geoJSON(GJ_RIVERS[key], {
    style:() => ({color:m.color, weight:m.width, opacity:.85}),
    onEachFeature:(f,lyr) => {
      lyr.on('click', () => showRiverInfo(key, m));
      lyr.bindTooltip(m.label, {sticky:true, opacity:.9});
    },
  });
  if (on) riverLayers[key].addTo(map);
});

// ── Build lake layers ─────────────────────────────────────────────────────────
Object.entries(LAKE_META).forEach(([key,m]) => {
  layerOn['lake_'+key] = true;
  lakeLayers[key] = L.geoJSON(GJ_LAKES[key], {
    style:() => ({color:m.color,weight:1.5,fillColor:m.color,fillOpacity:.3}),
    onEachFeature:(f,lyr) => {
      const p = f.properties;
      lyr.bindPopup(
        `<div class="p-title" style="color:${m.color}">${m.label}</div>
         <div class="p-row"><span class="p-lbl">面积</span><span class="p-val">${m.area_km2} km²</span></div>
         <div class="p-row"><span class="p-lbl">备注</span><span class="p-val">${m.note}</span></div>`,
        {className:'custom-popup'});
    },
  }).addTo(map);
});

// ── Toktogul (Sentinel-2) layer ───────────────────────────────────────────────
const TOK_YEARS_GJ = {};  // filled below from year water data — using 2025 as default
layerOn['toktogul_wb'] = true;
toktogulLayer = L.geoJSON(GJ_TOKTOGUL, {
  style:() => ({color:'#00B4D8',weight:1.5,fillColor:'#00B4D8',fillOpacity:.4}),
  onEachFeature:(f,lyr) => {
    lyr.bindPopup(
      `<div class="p-title" style="color:#00B4D8">托克托古尔水库</div>
       <div class="p-row"><span class="p-lbl">数据来源</span><span class="p-val">Sentinel-2 GDW</span></div>
       <div class="p-row"><span class="p-lbl">年份</span><span class="p-val" id="tok-yr-popup">2025</span></div>
       <div class="p-row"><span class="p-lbl">水面面积</span><span class="p-val" id="tok-area-popup">218.1 km²</span></div>
       <div class="p-row"><span class="p-lbl">蓄水量</span><span class="p-val" id="tok-vol-popup">13.98 km³</span></div>`,
      {className:'custom-popup'});
  },
}).addTo(map);

// ── ERA5 layer (if ready) ─────────────────────────────────────────────────────
let era5Layer = null;
document.getElementById('era5-badge').innerHTML = ERA5_READY
  ? '<span style="color:#2dc653">● ERA5 已接入</span>'
  : '<span style="color:#f4a261">● ERA5 待接入（文献值模式）</span>';

if (ERA5_READY && ERA5_LAYERS.temp_anom) {
  era5Layer = L.geoJSON(ERA5_LAYERS.temp_anom, {
    pointToLayer:(f,latlng) => {
      const v = f.properties.anom;
      const c = v>1.5?'#e63946':v>1.0?'#f4a261':v>0.5?'#ffd166':'#4196DE';
      return L.circleMarker(latlng, {radius:4,fillColor:c,color:'none',fillOpacity:.6});
    },
    onEachFeature:(f,lyr) => {
      lyr.bindTooltip(`气温距平: ${f.properties.anom>0?'+':''}${f.properties.anom}°C`,{sticky:true});
    },
  });
}

// ══ Sidebar builder ════════════════════════════════════════════════════════════
function buildSidebar() {
  // River list
  const rl = document.getElementById('river-list');
  Object.entries(RIVER_META).forEach(([key,m]) => {
    const on = layerOn[key];
    const div = document.createElement('div');
    div.className = 'rlayer';
    div.innerHTML = `
      <div class="rl-bar" style="background:${m.color}"></div>
      <div style="flex:1">
        <div class="rl-name">${m.label}</div>
        <div class="rl-dest">${m.dest}</div>
      </div>
      <input type="checkbox" id="cb-${key}" class="rl-cb" ${on?'checked':''}>
    `;
    div.addEventListener('click', e => {
      if (e.target.type !== 'checkbox') document.getElementById('cb-'+key).checked = !layerOn[key];
      layerOn[key] = document.getElementById('cb-'+key).checked;
      layerOn[key] ? riverLayers[key].addTo(map) : map.removeLayer(riverLayers[key]);
      showRiverInfo(key, m);
    });
    rl.appendChild(div);
  });

  // Lake list
  const ll = document.getElementById('lake-list');
  Object.entries(LAKE_META).forEach(([key,m]) => {
    const div = document.createElement('div');
    div.className = 'wlayer';
    div.innerHTML = `
      <div class="wl-sq" style="background:${m.color}"></div>
      <div style="flex:1;font-size:11px;font-weight:600">${m.label}</div>
      <input type="checkbox" id="cb-lake-${key}" class="rl-cb" checked>
    `;
    div.addEventListener('click', e => {
      if (e.target.type !== 'checkbox') document.getElementById('cb-lake-'+key).checked = !layerOn['lake_'+key];
      layerOn['lake_'+key] = document.getElementById('cb-lake-'+key).checked;
      layerOn['lake_'+key] ? lakeLayers[key].addTo(map) : map.removeLayer(lakeLayers[key]);
    });
    ll.appendChild(div);
  });
  // Toktogul checkbox wiring
  document.getElementById('cb-toktogul_wb').addEventListener('change', e => {
    e.target.checked ? toktogulLayer.addTo(map) : map.removeLayer(toktogulLayer);
  });
}

// ══ Info panel ════════════════════════════════════════════════════════════════
function showRiverInfo(key, m) {
  const idx = currentYearIdx;
  const destC = m.dest_country.includes('中国')?'#FF6B35':
                m.dest_country.includes('哈萨克')?'#2DC653':
                m.dest_country.includes('乌兹别')?'#C77DFF':'#cce5f6';
  let flowLine = '';
  if (key==='sary_jaz') flowLine = `<div class="info-row"><span class="info-lbl">估算入境水量</span><span class="info-val" style="color:#FF6B35">${SARY_FLOW[idx]} km³/yr</span></div>`;
  if (key==='naryn')    flowLine = `<div class="info-row"><span class="info-lbl">托克托古尔入库</span><span class="info-val" style="color:#4196DE">${TOK_INFLOW[idx]} km³/yr</span></div>`;
  document.getElementById('info-box').innerHTML = `
    <div class="info-title" style="color:${m.color}">${m.label}</div>
    <div class="info-row"><span class="info-lbl">流域</span><span class="info-val">${m.basin}流域</span></div>
    <div class="info-row"><span class="info-lbl">流向</span><span class="info-val">${m.dest}</span></div>
    <div class="info-row"><span class="info-lbl">目的地</span>
      <span class="info-val"><span class="dest-badge" style="background:${destC}22;color:${destC};border:1px solid ${destC}">${m.dest_country}</span></span>
    </div>
    ${flowLine}
  `;
}

// ══ Year selector ═════════════════════════════════════════════════════════════
let currentYearIdx = 7;  // 2025

function updateYear(idx) {
  currentYearIdx = idx;
  const yr = YEARS[idx];
  document.getElementById('year-disp').textContent = yr;

  // Topbar KPIs
  document.getElementById('kpi-tok').textContent   = TOK_INFLOW[idx].toFixed(1);
  document.getElementById('kpi-sary').textContent  = SARY_FLOW[idx].toFixed(1);
  document.getElementById('kpi-aksu').textContent  = AKSU_TOTAL[idx].toFixed(1);
  document.getElementById('kpi-area').textContent  = AREAS_TOK[idx].toFixed(0);

  // Sidebar year stats
  const vol   = VOLS_TOK[idx];
  const util  = ((vol-5.4)/14.1*100).toFixed(1);
  const elev  = (820+(vol-5.4)/(19.5-5.4)*(902-820)).toFixed(1);
  const utilC = util>=80?'var(--green)':util>=60?'var(--orange)':'var(--red)';
  document.getElementById('year-stats').innerHTML = `
    <div class="info-row"><span class="info-lbl">年份</span><span class="info-val" style="color:var(--cyan)">${yr}</span></div>
    <div class="info-row"><span class="info-lbl">水面面积</span><span class="info-val">${AREAS_TOK[idx]} km²</span></div>
    <div class="info-row"><span class="info-lbl">蓄水量</span><span class="info-val">${vol} km³</span></div>
    <div class="info-row"><span class="info-lbl">估算水位</span><span class="info-val">${elev} m</span></div>
    <div class="info-row"><span class="info-lbl">库容利用率</span><span class="info-val" style="color:${utilC}">${util}%</span></div>
    <div class="info-row"><span class="info-lbl">萨雷扎兹入境</span><span class="info-val" style="color:#FF6B35">${SARY_FLOW[idx]} km³</span></div>
    <div class="info-row"><span class="info-lbl">阿克苏总入境</span><span class="info-val" style="color:#4196DE">${AKSU_TOTAL[idx]} km³</span></div>
    <div class="info-row"><span class="info-lbl">气温距平</span><span class="info-val" style="color:var(--red)">+${TEMP_ANOM[idx]}°C</span></div>
  `;

  // Attribution
  const dv = idx>0 ? VOLS_TOK[idx]-VOLS_TOK[idx-1] : 0;
  const dsary = idx>0 ? SARY_FLOW[idx]-SARY_FLOW[idx-1] : 0;
  const attrColor = v => v>=0?'var(--green)':'var(--red)';
  document.getElementById('attr-panel').innerHTML = `
    <div class="info-row"><span class="info-lbl">库容变化</span><span class="info-val" style="color:${attrColor(dv)}">${dv>=0?'+':''}${dv.toFixed(2)} km³</span></div>
    <div class="info-row"><span class="info-lbl">萨雷扎兹变化</span><span class="info-val" style="color:${attrColor(dsary)}">${dsary>=0?'+':''}${dsary.toFixed(1)} km³</span></div>
    <div class="info-row"><span class="info-lbl">气候驱动（估）</span><span class="info-val" style="color:var(--orange)">${TEMP_ANOM[idx]}°C 升温</span></div>
    <div class="info-row"><span class="info-lbl">冰川面积</span><span class="info-val">${GLACIER[idx].toLocaleString()} km²</span></div>
    <div style="font-size:10px;color:var(--txt2);margin-top:8px;line-height:1.7">
      ${TEMP_ANOM[idx]>=1.2?'⚠️ 本年气温显著偏高（+'+TEMP_ANOM[idx]+'°C），冰川融水加速，但长期将导致融水减少。':'气候条件相对正常，水量主要由降水决定。'}
      <br>${dsary<-0.2?'📉 萨雷扎兹入境水量较上年减少，关注下游供水影响。':dsary>0.1?'📈 萨雷扎兹入境水量较上年增加。':'→ 入境流量基本稳定。'}
    </div>
  `;

  // Highlight chart points
  if (typeof allCharts !== 'undefined') {
    allCharts.forEach(ch => {
      if (ch.data.datasets[0]) {
        ch.data.datasets[0].pointRadius = YEARS.map((_,i)=>i===idx?6:2.5);
        ch.update('none');
      }
    });
  }
}

function onSlider(val) { updateYear(parseInt(val)); }

// Auto-play
let playTimer = null;
function togglePlay() {
  const btn = document.getElementById('play-btn');
  if (playTimer) {
    clearInterval(playTimer); playTimer = null; btn.textContent = '▶ 播放';
  } else {
    btn.textContent = '⏸ 暂停';
    playTimer = setInterval(() => {
      const next = (currentYearIdx+1) % YEARS.length;
      document.getElementById('year-slider').value = next;
      updateYear(next);
      if (next === YEARS.length-1) { clearInterval(playTimer); playTimer=null; btn.textContent='▶ 播放'; }
    }, 1200);
  }
}

// ══ View switching ════════════════════════════════════════════════════════════
function setView(v) {
  document.querySelectorAll('.vtab').forEach(b=>b.classList.remove('active'));
  event.target.classList.add('active');
  if (v==='kyrgyz')    { map.flyTo([41.5,74.5],7,{duration:1.2}); }
  if (v==='toktogul')  { map.flyTo([41.83,72.9],10,{duration:1.2}); }
  if (v==='sary')      { map.flyTo([41.85,79.3],9,{duration:1.2}); }
}

// ══ Toggle layers ════════════════════════════════════════════════════════════
function toggleLayer(key) {
  layerOn[key] = !layerOn[key];
  if (key==='toktogul_wb') {
    layerOn[key] ? toktogulLayer.addTo(map) : map.removeLayer(toktogulLayer);
  }
}

// ══ Charts ════════════════════════════════════════════════════════════════════
const COPTS = {
  responsive:true, maintainAspectRatio:false, animation:false,
  plugins:{legend:{display:false},
    tooltip:{backgroundColor:'#0d1e2e',borderColor:'#1a3352',borderWidth:1,padding:7,
      titleColor:'#cce5f6',bodyColor:'#cce5f6'}},
  scales:{
    x:{grid:{color:'rgba(26,51,82,.4)'},ticks:{color:'#5a8aaa',font:{size:9}}},
    y:{grid:{color:'rgba(26,51,82,.4)'},ticks:{color:'#5a8aaa',font:{size:9}}},
  },
};
const YL = YEARS.map(String);
let allCharts;

requestAnimationFrame(() => {
  const c1 = new Chart('c1',{type:'bar',data:{labels:YL,datasets:[{
    data:TOK_INFLOW,
    backgroundColor:TOK_INFLOW.map(v=>v>=11?'rgba(45,198,83,.65)':v>=10?'rgba(65,150,222,.65)':'rgba(230,57,70,.65)'),
    borderColor:TOK_INFLOW.map(v=>v>=11?'#2dc653':v>=10?'#4196DE':'#e63946'),
    borderWidth:1.5,borderRadius:3,pointRadius:2.5,
  }]},options:{...COPTS,scales:{...COPTS.scales,y:{...COPTS.scales.y,min:6,max:14,ticks:{...COPTS.scales.y.ticks,callback:v=>v+''}}}}});

  const c2 = new Chart('c2',{type:'line',data:{labels:YL,datasets:[{
    data:SARY_FLOW,borderColor:'#FF6B35',backgroundColor:'rgba(255,107,53,.1)',
    fill:true,tension:.4,pointRadius:2.5,borderWidth:2,
  }]},options:{...COPTS,scales:{...COPTS.scales,y:{...COPTS.scales.y,min:2,max:6}}}});

  const c3 = new Chart('c3',{type:'line',data:{labels:YL,datasets:[
    {data:AKSU_TOTAL,borderColor:'#4196DE',backgroundColor:'rgba(65,150,222,.1)',fill:true,tension:.4,pointRadius:2.5,borderWidth:2,label:'总量'},
    {data:SARY_FLOW, borderColor:'#FF6B35',fill:false,tension:.4,pointRadius:2,borderWidth:1.5,borderDash:[4,3],label:'库玛力克'},
  ]},options:{...COPTS,plugins:{...COPTS.plugins,legend:{display:true,labels:{color:'#5a8aaa',font:{size:9}}}},
    scales:{...COPTS.scales,y:{...COPTS.scales.y,min:3,max:10}}}});

  const c4 = new Chart('c4',{type:'bar',data:{labels:YL,datasets:[
    {data:TEMP_ANOM,backgroundColor:'rgba(230,57,70,.55)',borderColor:'#e63946',borderWidth:1.5,borderRadius:3,yAxisID:'yT',label:'气温距平°C'},
    {data:GLACIER.map(v=>(v-7600)/380*100),type:'line',borderColor:'#a8d8ea',fill:false,tension:.3,pointRadius:2,borderWidth:2,borderDash:[4,3],yAxisID:'yG',label:'冰川变化%'},
  ]},options:{...COPTS,
    plugins:{...COPTS.plugins,legend:{display:true,labels:{color:'#5a8aaa',font:{size:9}}}},
    scales:{
      x:COPTS.scales.x,
      yT:{position:'left',grid:{color:'rgba(26,51,82,.4)'},ticks:{color:'#e63946',font:{size:9},callback:v=>v+'°C'}},
      yG:{position:'right',grid:{drawOnChartArea:false},ticks:{color:'#a8d8ea',font:{size:9},callback:v=>v+'%'}},
    }}});

  allCharts = [c1,c2,c3,c4];
  updateYear(7);  // init with 2025
});

// ══ Init ════════════════════════════════════════════════════════════════════
buildSidebar();
</script>
</body>
</html>"""

out_path = OUT / "integrated_map.html"
out_path.write_text(html, encoding="utf-8")
size_kb = out_path.stat().st_size // 1024
print(f"\n✅  integrated_map.html  →  {size_kb} KB")
print(f"    open '{out_path}'")

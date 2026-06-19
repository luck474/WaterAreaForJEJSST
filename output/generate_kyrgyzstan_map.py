#!/usr/bin/env python3
"""
Kyrgyzstan Regional Water Resources Map
========================================
OSM PBF → GeoJSON (OGR) → Leaflet 交互地图

产出：output/kyrgyzstan_water_map.html
  · 主干河流（纳伦、萨雷扎兹、楚、塔拉斯、卡拉达里亚等）按流域着色
  · 伊塞克湖 + 托克托古尔水库面状图层
  · 跨境流向标注（→中国/哈萨克斯坦/乌兹别克斯坦）
  · 可切换的流域图层 + 实时统计侧边栏
  · 底部 Chart.js：多河流历年对比
"""

import json
import re
import warnings
from pathlib import Path
from osgeo import ogr, osr

warnings.filterwarnings("ignore")
ogr.UseExceptions()

# ── Paths ──────────────────────────────────────────────────────────────────────
# 项目根目录：脚本位于 <BASE>/output/ 下，自动解析以保证可移植
BASE      = Path(__file__).resolve().parent.parent
OUT       = BASE / "output"
LINES_GPKG = OUT / "osm_lines.gpkg"    # pre-extracted waterway lines
POLYS_GPKG = OUT / "osm_polys.gpkg"    # pre-extracted water body polygons
OUT.mkdir(exist_ok=True)

# ── 主要河流定义（流域 / 颜色 / 跨境去向）────────────────────────────────────
# 名称列表用于 OSM name 字段的包含匹配
RIVERS = {
    "naryn": {
        "label": "纳伦河 Naryn",
        "color": "#4196DE",
        "basin": "锡尔河流域",
        "dest":  "→ 锡尔河 → 咸海",
        "dest_country": "乌兹别克斯坦 / 哈萨克斯坦",
        "names_ky": ["Нарын", "Нарыне"],   # Kyrgyz/Russian name fragments
        "length_km": 807,
        "width": 3,
    },
    "sary_jaz": {
        "label": "萨雷扎兹河 Sary-Jaz",
        "color": "#FF6B35",
        "basin": "塔里木流域",
        "dest":  "→ 库玛力克河 → 阿克苏河 → 塔里木河",
        "dest_country": "中国（新疆）",
        "names_ky": ["Сарыджаз", "Сарыжаз", "Сары-Жаз"],
        "length_km": 245,
        "width": 2.5,
    },
    "chui": {
        "label": "楚河 Chui",
        "color": "#2DC653",
        "basin": "楚河流域",
        "dest":  "→ 消失于哈萨克斯坦草原",
        "dest_country": "哈萨克斯坦",
        "names_ky": ["Чүй", "Чуйск", "Чу", "Шу"],
        "length_km": 1067,
        "width": 2.5,
    },
    "talas": {
        "label": "塔拉斯河 Talas",
        "color": "#A8D8EA",
        "basin": "塔拉斯流域",
        "dest":  "→ 消失于哈萨克斯坦",
        "dest_country": "哈萨克斯坦",
        "names_ky": ["Талас"],
        "length_km": 661,
        "width": 2,
    },
    "kara_darya": {
        "label": "卡拉达里亚 Kara-Darya",
        "color": "#C77DFF",
        "basin": "锡尔河流域",
        "dest":  "→ 锡尔河",
        "dest_country": "乌兹别克斯坦",
        "names_ky": ["Карадарья", "Кара-Кулжа", "Qoradaryo"],
        "length_km": 180,
        "width": 2,
    },
    "chatkal": {
        "label": "恰特卡尔河 Chatkal",
        "color": "#F4A261",
        "basin": "锡尔河流域",
        "dest":  "→ 纳伦河 → 锡尔河",
        "dest_country": "乌兹别克斯坦",
        "names_ky": ["Чаткал"],
        "length_km": 345,
        "width": 2,
    },
    "kokshaal": {
        "label": "科克沙尔河 Kokshal",
        "color": "#E63946",
        "basin": "塔里木流域",
        "dest":  "→ 萨雷扎兹河 → 中国",
        "dest_country": "中国（新疆）",
        "names_ky": ["Кокшаал"],
        "length_km": 200,
        "width": 2,
    },
    "naryn_minor": {
        "label": "纳伦支流群",
        "color": "#90CAF9",
        "basin": "锡尔河流域",
        "dest":  "→ 纳伦河",
        "dest_country": "吉尔吉斯斯坦内",
        "names_ky": ["Малый Нарын", "Ат-Баши", "Ат Башы", "Джумгал", "Арпа",
                     "Суусамыр", "Кочкор", "Кёкёмерен", "Көкөмерен"],
        "length_km": None,
        "width": 1.5,
    },
}

# ── 水体（湖泊/水库）定义 ─────────────────────────────────────────────────────
# 托克托古尔用 Sentinel-2 2025 实测边界替代 OSM 满水位边界（精度更高）
WATERBODIES = {
    "issyk_kul": {
        "label": "伊塞克湖 Issyk-Kul",
        "color": "#1E90FF",
        "names_ky": ["Ысык-Көл", "Иссык-Куль", "Issyk-Kul"],
        "area_km2": 6236,
        "note": "世界第二大高山湖泊，内流湖",
        "source": "osm",          # 来源：OSM（精度充足）
    },
    "son_kul": {
        "label": "松库尔湖 Son-Kul",
        "color": "#48CAE4",
        "names_ky": ["Соң-Көл", "Соңкөл", "Сон-Куль"],
        "area_km2": 270,
        "note": "高原草场湖泊，海拔3016 m",
        "source": "osm",
    },
}

# ── 工具函数 ───────────────────────────────────────────────────────────────────
def geom_to_coords(geom):
    """Convert OGR geometry to list of coordinate arrays (handles Multi too)."""
    gtype = geom.GetGeometryName()
    if gtype in ("LINESTRING", "LINEARRING"):
        pts = geom.GetPoints()
        return [[[p[0], p[1]] for p in pts]] if pts else []
    if gtype in ("MULTILINESTRING",):
        result = []
        for i in range(geom.GetGeometryCount()):
            sub = geom.GetGeometryRef(i)
            pts = sub.GetPoints()
            if pts:
                result.append([[p[0], p[1]] for p in pts])
        return result
    if gtype in ("POLYGON",):
        ring = geom.GetGeometryRef(0)
        pts = ring.GetPoints()
        return [[[p[0], p[1]] for p in pts]] if pts else []
    if gtype in ("MULTIPOLYGON",):
        result = []
        for i in range(geom.GetGeometryCount()):
            poly = geom.GetGeometryRef(i)
            ring = poly.GetGeometryRef(0)
            pts = ring.GetPoints()
            if pts:
                result.append([[p[0], p[1]] for p in pts])
        return result
    return []


def name_matches(name, patterns):
    """Match OSM name on word boundaries so short tokens like 'Чу'/'Шу' don't
    spuriously hit 'ашуу' (mountain pass) / 'Чупра' etc. Short patterns (<4 chars)
    require both left+right word boundaries; longer stems may carry a suffix
    (e.g. Талас→Таласский, Кочкор→Кочкорчи)."""
    if not name:
        return False
    for p in patterns:
        right = r'(?!\w)' if len(p) < 4 else ''
        if re.search(r'(?<!\w)' + re.escape(p) + right, name, re.IGNORECASE):
            return True
    return False


def simplify_coords(coords_list, tolerance=0.005):
    """Simple Douglas-Peucker via OGR for coord lists."""
    result = []
    for coords in coords_list:
        if len(coords) < 2:
            continue
        # Rebuild as OGR linestring, simplify, convert back
        line = ogr.Geometry(ogr.wkbLineString)
        for c in coords:
            line.AddPoint(c[0], c[1])
        simp = line.Simplify(tolerance)
        pts = simp.GetPoints()
        if pts and len(pts) >= 2:
            result.append([[p[0], p[1]] for p in pts])
    return result


# ── 1. 提取河流中心线 ──────────────────────────────────────────────────────────
print("正在从 GPKG 提取河流数据…")
ds = ogr.Open(str(LINES_GPKG))
lines_lyr = ds.GetLayerByName("waterways")

river_geojson = {}  # river_key → FeatureCollection

for rkey, rinfo in RIVERS.items():
    print(f"  提取: {rinfo['label']}")
    lines_lyr.ResetReading()
    features = []
    seen_ids = set()

    for feat in lines_lyr:
        wtype = feat.GetField("waterway")
        if not wtype or wtype not in ("river", "stream", "canal"):
            continue
        name = feat.GetField("name") or ""
        if not name_matches(name, rinfo["names_ky"]):
            continue

        fid = feat.GetFID()
        if fid in seen_ids:
            continue
        seen_ids.add(fid)

        geom = feat.GetGeometryRef()
        if not geom:
            continue

        coords_list = geom_to_coords(geom)
        coords_list = simplify_coords(coords_list, tolerance=0.003)

        for coords in coords_list:
            if len(coords) < 2:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "river": rkey,
                    "label": rinfo["label"],
                    "dest": rinfo["dest"],
                    "dest_country": rinfo["dest_country"],
                    "basin": rinfo["basin"],
                    "name_osm": name,
                }
            })

    river_geojson[rkey] = {
        "type": "FeatureCollection",
        "features": features,
    }
    print(f"    → {len(features)} 段")

ds = None

# ── 2a. 从 OSM 提取湖泊（加 natural='water' 过滤，排除行政边界）──────────────
print("\n正在提取水体面数据（OSM，强制 natural=water）…")
ds = ogr.Open(str(POLYS_GPKG))
mp_lyr = ds.GetLayerByName("waterbodies")

waterbody_geojson = {}

def extract_osm_waterbody(mp_lyr, winfo):
    """Extract a single water body from OSM, requiring natural='water'."""
    mp_lyr.ResetReading()
    features = []
    seen_ids = set()
    for feat in mp_lyr:
        nat  = feat.GetField("natural") or ""
        name = feat.GetField("name") or ""
        # 必须有 natural=water 且名称匹配 → 排除行政区划
        if nat != "water":
            continue
        if not name_matches(name, winfo["names_ky"]):
            continue
        fid = feat.GetFID()
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        geom = feat.GetGeometryRef()
        if not geom:
            continue
        gtype = geom.GetGeometryName()
        if "MULTI" in gtype:
            simplified = []
            for i in range(geom.GetGeometryCount()):
                sub = geom.GetGeometryRef(i)
                simp = sub.Simplify(0.005)
                if simp:
                    ring = simp.GetGeometryRef(0)
                    if ring:
                        pts = ring.GetPoints()
                        if pts:
                            simplified.append([[p[0], p[1]] for p in pts])
            if simplified:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "MultiPolygon",
                                 "coordinates": [[c] for c in simplified]},
                    "properties": {"label": winfo["label"],
                                   "area_km2": winfo["area_km2"],
                                   "note": winfo["note"],
                                   "source": "OSM (natural=water)",
                                   "name_osm": name},
                })
        else:
            simp = geom.Simplify(0.005)
            if simp:
                ring = simp.GetGeometryRef(0)
                if ring:
                    pts = ring.GetPoints()
                    if pts:
                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Polygon",
                                         "coordinates": [[[p[0], p[1]] for p in pts]]},
                            "properties": {"label": winfo["label"],
                                           "area_km2": winfo["area_km2"],
                                           "note": winfo["note"],
                                           "source": "OSM (natural=water)",
                                           "name_osm": name},
                        })
    return features

for wkey, winfo in WATERBODIES.items():
    print(f"  提取: {winfo['label']}")
    features = extract_osm_waterbody(mp_lyr, winfo)
    waterbody_geojson[wkey] = {"type": "FeatureCollection", "features": features}
    print(f"    → {len(features)} 个面要素")

ds = None

# ── 2b. 托克托古尔：改用 Sentinel-2 矢量化实测边界（2025年，精度更高）──────
print("  提取: 托克托古尔水库（Sentinel-2 2025 实测）")
from osgeo import gdal
gdal.UseExceptions()

MOSAIC_2025 = OUT / "mosaics" / "Toktogul_mosaic_20250101_20251231.tif"

def extract_polygon_rings(geom):
    """Robustly extract coordinate rings from Polygon or MultiPolygon OGR geometry."""
    rings = []
    gname = geom.GetGeometryName().upper()
    if gname == "POLYGON":
        r = geom.GetGeometryRef(0)
        if r:
            pts = r.GetPoints()
            if pts and len(pts) >= 4:
                rings.append([[p[0], p[1]] for p in pts])
    elif gname == "MULTIPOLYGON":
        for i in range(geom.GetGeometryCount()):
            poly = geom.GetGeometryRef(i)
            if poly:
                r = poly.GetGeometryRef(0)
                if r:
                    pts = r.GetPoints()
                    if pts and len(pts) >= 4:
                        rings.append([[p[0], p[1]] for p in pts])
    return rings


def vectorize_water_s2(mosaic_path, simplify_deg=0.001, min_km2=1.0):
    """Vectorize water class (=1) from Sentinel-2 mosaic overview, reproject to WGS84."""
    import numpy as np
    from osgeo import osr as _osr

    ds_r = gdal.Open(str(mosaic_path))
    band = ds_r.GetRasterBand(1)
    ov_count = band.GetOverviewCount()

    if ov_count > 0:
        ov = band.GetOverview(min(1, ov_count - 1))
        w, h = ov.XSize, ov.YSize
        arr = np.frombuffer(ov.ReadRaster(0, 0, w, h), dtype=np.uint8).reshape(h, w)
        gt_orig = ds_r.GetGeoTransform()
        sx = ds_r.RasterXSize / w
        sy = ds_r.RasterYSize / h
        gt = (gt_orig[0], gt_orig[1]*sx, gt_orig[2],
              gt_orig[3], gt_orig[4], gt_orig[5]*sy)
    else:
        arr = band.ReadAsArray()
        w, h = ds_r.RasterXSize, ds_r.RasterYSize
        gt = ds_r.GetGeoTransform()

    src_proj = ds_r.GetProjection()
    ds_r = None

    water_arr = (arr == 1).astype(np.uint8)
    mem_drv = gdal.GetDriverByName("MEM")
    mem_ds = mem_drv.Create("", w, h, 1, gdal.GDT_Byte)
    mem_ds.SetGeoTransform(gt)
    mem_ds.SetProjection(src_proj)
    mem_ds.GetRasterBand(1).WriteArray(water_arr)
    mem_ds.GetRasterBand(1).SetNoDataValue(0)

    mem_vec = ogr.GetDriverByName("MEM").CreateDataSource("out")
    srs_src = _osr.SpatialReference()
    srs_src.ImportFromWkt(src_proj)
    lyr_v = mem_vec.CreateLayer("water", srs=srs_src)
    lyr_v.CreateField(ogr.FieldDefn("val", ogr.OFTInteger))
    gdal.Polygonize(mem_ds.GetRasterBand(1), None, lyr_v, 0, [], callback=None)

    srs_wgs = _osr.SpatialReference()
    srs_wgs.ImportFromEPSG(4326)
    srs_wgs.SetAxisMappingStrategy(_osr.OAMS_TRADITIONAL_GIS_ORDER)
    xform = _osr.CoordinateTransformation(srs_src, srs_wgs)

    features = []
    lyr_v.ResetReading()
    for feat in lyr_v:
        if feat.GetField("val") != 1:
            continue
        geom = feat.GetGeometryRef()
        if not geom:
            continue
        area_km2 = geom.GetArea() * 111 * 82   # approx at 42°N
        if area_km2 < min_km2:
            continue
        g2 = geom.Clone()
        g2.Transform(xform)
        simp = g2.Simplify(simplify_deg)
        if not simp:
            continue
        for ring_coords in extract_polygon_rings(simp):
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring_coords]},
                "properties": {
                    "label": "托克托古尔水库",
                    "area_km2": round(area_km2, 1),
                    "note": "Sentinel-2 2025 实测水面（218 km²）",
                    "source": "Sentinel-2 / Google Dynamic World 2025",
                },
            })
    mem_ds = None
    return features


from osgeo import osr
try:
    tok_features = vectorize_water_s2(MOSAIC_2025)
    assert tok_features, "no features returned"
    waterbody_geojson["toktogul"] = {"type": "FeatureCollection", "features": tok_features}
    print(f"    → {len(tok_features)} 个面要素（Sentinel-2 实测）")
except Exception as e:
    print(f"    ⚠️  Sentinel-2 矢量化失败（{e}），回退到 OSM")
    tok_info = {"label": "托克托古尔水库", "names_ky": ["Токтогул", "Toktogul"],
                "area_km2": 284, "note": "OSM 满水位边界（fallback）"}
    ds_fb = ogr.Open(str(POLYS_GPKG))
    waterbody_geojson["toktogul"] = {
        "type": "FeatureCollection",
        "features": extract_osm_waterbody(ds_fb.GetLayerByName("waterbodies"), tok_info),
    }
    ds_fb = None

# 补充 toktogul 样式信息（供 JS 使用）
WATERBODIES["toktogul"] = {
    "label": "托克托古尔水库",
    "color": "#00B4D8",
    "area_km2": 218,
    "note": "Sentinel-2 2025 实测水面（218 km²），数据来源：Google Dynamic World",
}

# ── 3. 统计信息 ────────────────────────────────────────────────────────────────
stats_summary = {}
for rkey, rinfo in RIVERS.items():
    fc = river_geojson[rkey]
    total_len = 0
    for feat in fc["features"]:
        coords = feat["geometry"]["coordinates"]
        for i in range(1, len(coords)):
            dx = coords[i][0] - coords[i-1][0]
            dy = coords[i][1] - coords[i-1][1]
            total_len += (dx**2 + dy**2)**0.5 * 111  # rough km
    stats_summary[rkey] = {
        "segments": len(fc["features"]),
        "approx_len_km": round(total_len, 1),
    }

# ── 4. 序列化 GeoJSON 为 JS 变量 ───────────────────────────────────────────────
def gj_var(varname, fc):
    return f"const {varname} = {json.dumps(fc, ensure_ascii=False, separators=(',', ':'))};"

js_vars = []
for rkey in RIVERS:
    js_vars.append(gj_var(f"GJ_{rkey.upper()}", river_geojson[rkey]))
for wkey in WATERBODIES:
    js_vars.append(gj_var(f"GJ_{wkey.upper()}", waterbody_geojson[wkey]))

# River color/style map for JS
river_styles_js = json.dumps(
    {rkey: {"color": rinfo["color"], "label": rinfo["label"],
            "dest": rinfo["dest"], "dest_country": rinfo["dest_country"],
            "basin": rinfo["basin"], "width": rinfo["width"]}
     for rkey, rinfo in RIVERS.items()},
    ensure_ascii=False
)

waterbody_styles_js = json.dumps(
    {wkey: {"color": winfo["color"], "label": winfo["label"],
            "area_km2": winfo["area_km2"], "note": winfo["note"]}
     for wkey, winfo in WATERBODIES.items()},
    ensure_ascii=False
)

# ── 5. 生成 HTML ───────────────────────────────────────────────────────────────
print("\n正在生成 HTML…")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>吉尔吉斯斯坦水资源地图 · 跨境流域分析</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --dark:#07121c; --panel:#0d1e2e; --border:#1a3352;
  --cyan:#00c8f0; --blue:#1a8cff; --txt:#cce5f6; --txt2:#5a8aaa;
  --green:#2dc653; --orange:#f4a261; --red:#e63946;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;font-family:'Segoe UI',system-ui,sans-serif;
  font-size:13px;background:var(--dark);color:var(--txt);overflow:hidden}}

/* Layout */
#app{{display:flex;flex-direction:column;height:100vh}}
#topbar{{
  flex:0 0 52px;display:flex;align-items:center;
  background:rgba(7,18,28,.97);border-bottom:1px solid var(--border);
  padding:0 16px;gap:20px;z-index:1000;
}}
#topbar h1{{font-size:15px;font-weight:700;color:#fff;white-space:nowrap}}
#topbar h1 span{{color:var(--cyan)}}
.tkpi{{border-left:1px solid var(--border);padding-left:16px;white-space:nowrap}}
.tkpi .v{{font-size:15px;font-weight:800;line-height:1}}
.tkpi .l{{font-size:10px;color:var(--txt2)}}
#main{{display:flex;flex:1;overflow:hidden}}

/* Sidebar */
#sidebar{{
  flex:0 0 280px;background:var(--panel);border-right:1px solid var(--border);
  overflow-y:auto;display:flex;flex-direction:column;
}}
.sb-sect{{padding:14px 14px 10px;border-bottom:1px solid var(--border)}}
.sb-sect h3{{font-size:11px;font-weight:700;letter-spacing:.8px;
  color:var(--cyan);text-transform:uppercase;margin-bottom:10px}}

/* River toggles */
.river-item{{
  display:flex;align-items:center;gap:8px;
  padding:6px 4px;border-radius:6px;cursor:pointer;
  transition:background .15s;user-select:none;
}}
.river-item:hover{{background:rgba(26,51,82,.5)}}
.river-dot{{width:14px;height:5px;border-radius:3px;flex:0 0 14px}}
.river-label{{font-size:12px;font-weight:600;flex:1}}
.river-dest{{font-size:10px;color:var(--txt2);margin-top:1px}}
.river-cb{{margin-left:auto;accent-color:var(--cyan);cursor:pointer}}

/* Water body toggles */
.wb-item{{
  display:flex;align-items:center;gap:8px;
  padding:5px 4px;cursor:pointer;border-radius:4px;
}}
.wb-item:hover{{background:rgba(26,51,82,.5)}}
.wb-dot{{width:14px;height:14px;border-radius:3px;flex:0 0 14px;opacity:.7}}

/* Info panel */
#info-panel{{
  padding:14px;flex:1;
}}
.info-title{{font-size:13px;font-weight:700;color:var(--cyan);margin-bottom:8px}}
.info-body{{font-size:12px;line-height:1.8;color:var(--txt)}}
.info-body b{{color:#fff}}
.flow-badge{{
  display:inline-block;padding:2px 8px;border-radius:10px;
  font-size:10px;font-weight:700;margin:4px 2px;
}}

/* Map column */
#map-col{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#map{{flex:1}}

/* Bottom chart strip */
#chart-strip{{
  flex:0 0 150px;background:rgba(7,18,28,.95);
  border-top:1px solid var(--border);
  display:flex;gap:0;
}}
.cs-chart{{
  flex:1;padding:8px 12px;border-right:1px solid var(--border);
  display:flex;flex-direction:column;
}}
.cs-chart:last-child{{border-right:none}}
.cs-chart h4{{
  font-size:10px;color:var(--txt2);font-weight:600;
  letter-spacing:.5px;margin-bottom:6px;text-transform:uppercase;
  flex:0 0 auto;
}}
.chart-wrap{{position:relative;height:100px;width:100%}}

/* Popup */
.custom-popup .leaflet-popup-content-wrapper{{
  background:#0d1e2e;border:1px solid #1a3352;border-radius:10px;
  color:#cce5f6;box-shadow:0 4px 20px rgba(0,0,0,.5);min-width:200px;
}}
.custom-popup .leaflet-popup-tip{{background:#0d1e2e}}
.popup-title{{font-size:14px;font-weight:700;margin-bottom:8px}}
.popup-row{{display:flex;justify-content:space-between;gap:16px;
  padding:3px 0;border-bottom:1px solid rgba(26,51,82,.5);font-size:12px}}
.popup-row:last-child{{border-bottom:none}}
.popup-lbl{{color:var(--txt2)}}
.popup-val{{font-weight:700}}

/* Legend */
#legend{{
  position:absolute;bottom:160px;right:10px;z-index:800;
  background:rgba(7,18,28,.9);border:1px solid var(--border);
  border-radius:8px;padding:10px 14px;min-width:160px;
}}
#legend h4{{font-size:10px;color:var(--cyan);font-weight:700;
  letter-spacing:.5px;text-transform:uppercase;margin-bottom:8px}}
.leg-row{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:11px}}
.leg-line{{height:3px;width:24px;border-radius:2px}}
.leg-dot{{width:12px;height:12px;border-radius:2px;opacity:.7}}

/* Scrollbar */
#sidebar::-webkit-scrollbar{{width:4px}}
#sidebar::-webkit-scrollbar-thumb{{background:var(--border);border-radius:2px}}
</style>
</head>
<body>
<div id="app">

<div id="topbar">
  <h1>🌊 <span>吉尔吉斯斯坦</span> 水资源跨境流域分析</h1>
  <div class="tkpi"><div class="v" style="color:var(--cyan)">7条</div><div class="l">主干河流</div></div>
  <div class="tkpi"><div class="v" style="color:#FF6B35">→ 中国</div><div class="l">萨雷扎兹 / 科克沙尔</div></div>
  <div class="tkpi"><div class="v" style="color:#2DC653">→ 哈萨克斯坦</div><div class="l">楚河 / 塔拉斯河</div></div>
  <div class="tkpi"><div class="v" style="color:#C77DFF">→ 乌兹别克斯坦</div><div class="l">纳伦 / 卡拉达里亚</div></div>
  <div class="tkpi"><div class="v">~3,600</div><div class="l">境内河流总长 km</div></div>
</div>

<div id="main">

<div id="sidebar">
  <!-- River layers -->
  <div class="sb-sect">
    <h3>🏞️ 河流图层</h3>
    <div id="river-toggles"></div>
  </div>

  <!-- Water bodies -->
  <div class="sb-sect">
    <h3>💧 水体</h3>
    <div id="wb-toggles"></div>
  </div>

  <!-- Info panel -->
  <div class="sb-sect" style="flex:1">
    <h3>ℹ️ 点击河流查看详情</h3>
    <div id="info-panel">
      <div class="info-title">吉尔吉斯斯坦水资源概况</div>
      <div class="info-body">
        吉尔吉斯斯坦是中亚重要的<b>水塔</b>，境内河流总数超过 <b>3,500 条</b>，冰川面积约 <b>8,000 km²</b>。<br><br>
        主要河流均发源于天山和帕米尔山脉，向四周辐射流入邻国，深刻影响下游农业与生态。<br><br>
        <span class="flow-badge" style="background:rgba(255,107,53,.25);color:#FF6B35;border:1px solid #FF6B35">→ 中国</span>
        萨雷扎兹河进入新疆后成为<b>库玛力克河</b>，是<b>阿克苏河</b>主要水源之一，最终汇入塔里木河。<br><br>
        <span class="flow-badge" style="background:rgba(45,198,83,.2);color:#2DC653;border:1px solid #2DC653">→ 哈萨克斯坦</span>
        楚河灌溉比什凯克平原后入境哈萨克斯坦。
      </div>
    </div>
  </div>

  <!-- Legend -->
  <div class="sb-sect" style="font-size:11px;color:var(--txt2);line-height:1.7">
    <h3>📋 数据说明</h3>
    <b style="color:var(--txt)">底图：</b>ESRI World Imagery<br>
    <b style="color:var(--txt)">河流：</b>OpenStreetMap（Geofabrik）<br>
    <b style="color:var(--txt)">水库：</b>OSM + Sentinel-2 矢量化<br>
    <b style="color:var(--txt)">时间：</b>2026-06-02
  </div>
</div><!-- /sidebar -->

<div id="map-col">
  <div id="map">
    <!-- Legend overlay -->
    <div id="legend">
      <h4>流域归属</h4>
      <div class="leg-row"><div class="leg-line" style="background:#4196DE"></div>锡尔河流域（西流）</div>
      <div class="leg-row"><div class="leg-line" style="background:#FF6B35"></div>塔里木流域（→中国）</div>
      <div class="leg-row"><div class="leg-line" style="background:#2DC653"></div>楚河流域（→哈萨克）</div>
      <div class="leg-row"><div class="leg-line" style="background:#A8D8EA"></div>塔拉斯流域（→哈萨克）</div>
      <div class="leg-row"><div class="leg-line" style="background:#C77DFF"></div>卡拉达里亚（→乌兹别）</div>
      <div class="leg-row"><div class="leg-dot" style="background:#1E90FF"></div>伊塞克湖</div>
      <div class="leg-row"><div class="leg-dot" style="background:#00B4D8"></div>托克托古尔水库</div>
    </div>
  </div>

  <!-- Bottom chart strip -->
  <div id="chart-strip">
    <div class="cs-chart">
      <h4>萨雷扎兹 → 中国水量估算</h4>
      <div class="chart-wrap"><canvas id="c1"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>纳伦河 径流量（km³/yr）</h4>
      <div class="chart-wrap"><canvas id="c2"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>冰川面积年际变化（km²）</h4>
      <div class="chart-wrap"><canvas id="c3"></canvas></div>
    </div>
    <div class="cs-chart">
      <h4>托克托古尔水面面积（km²）</h4>
      <div class="chart-wrap"><canvas id="c4"></canvas></div>
    </div>
  </div>
</div><!-- /map-col -->

</div><!-- /main -->
</div><!-- /app -->

<script>
// ══ GeoJSON Data ══════════════════════════════════════════════════════════════
{chr(10).join(js_vars)}

const RIVER_STYLES = {river_styles_js};
const WB_STYLES    = {waterbody_styles_js};

// ══ Map init ══════════════════════════════════════════════════════════════════
const map = L.map('map', {{
  center: [41.5, 74.5], zoom: 7,
  zoomControl: true, attributionControl: true,
}});

L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'© Esri / Maxar', maxZoom:18}}
).addTo(map);

L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'© Esri', opacity:.75, maxZoom:18}}
).addTo(map);

// ══ GeoJSON key → variable map ═══════════════════════════════════════════════
const RIVER_GJ = {{
  naryn:       GJ_NARYN,
  sary_jaz:    GJ_SARY_JAZ,
  chui:        GJ_CHUI,
  talas:       GJ_TALAS,
  kara_darya:  GJ_KARA_DARYA,
  chatkal:     GJ_CHATKAL,
  kokshaal:    GJ_KOKSHAAL,
  naryn_minor: GJ_NARYN_MINOR,
}};

const WB_GJ = {{
  issyk_kul: GJ_ISSYK_KUL,
  toktogul:  GJ_TOKTOGUL,
  son_kul:   GJ_SON_KUL,
}};

// ══ Layer creation ════════════════════════════════════════════════════════════
const riverLayers = {{}};
const wbLayers    = {{}};

function makeRiverLayer(key) {{
  const st = RIVER_STYLES[key];
  return L.geoJSON(RIVER_GJ[key], {{
    style: () => ({{
      color: st.color,
      weight: st.width,
      opacity: 0.85,
    }}),
    onEachFeature: (feat, lyr) => {{
      lyr.on('click', () => showRiverInfo(key, feat.properties));
      lyr.bindTooltip(st.label, {{sticky:true, className:'', opacity:.9}});
    }},
  }});
}}

function makeWbLayer(key) {{
  const st = WB_STYLES[key];
  return L.geoJSON(WB_GJ[key], {{
    style: () => ({{
      color: st.color,
      weight: 1.5,
      fillColor: st.color,
      fillOpacity: 0.35,
    }}),
    onEachFeature: (feat, lyr) => {{
      const p = feat.properties;
      lyr.bindPopup(
        `<div class="popup-title" style="color:${{st.color}}">${{p.label}}</div>
         <div class="popup-row"><span class="popup-lbl">面积</span><span class="popup-val">${{p.area_km2}} km²</span></div>
         <div class="popup-row"><span class="popup-lbl">备注</span><span class="popup-val">${{p.note}}</span></div>`,
        {{className:'custom-popup'}}
      );
    }},
  }});
}}

// ══ Build sidebar toggles + init layers ══════════════════════════════════════
const riverToggleDiv = document.getElementById('river-toggles');
const layerState = {{}};

Object.entries(RIVER_STYLES).forEach(([key, st]) => {{
  const on = key !== 'naryn_minor';  // minor tributaries off by default
  layerState[key] = on;

  riverLayers[key] = makeRiverLayer(key);
  if (on) riverLayers[key].addTo(map);

  const div = document.createElement('div');
  div.className = 'river-item';
  div.innerHTML = `
    <div class="river-dot" style="background:${{st.color}}"></div>
    <div style="flex:1">
      <div class="river-label">${{st.label}}</div>
      <div class="river-dest">${{st.dest}}</div>
    </div>
    <input type="checkbox" class="river-cb" id="cb-${{key}}" ${{on?'checked':''}}>
  `;
  div.addEventListener('click', (e) => {{
    if (e.target.type !== 'checkbox') {{
      const cb = div.querySelector('input');
      cb.checked = !cb.checked;
    }}
    layerState[key] = div.querySelector('input').checked;
    layerState[key] ? riverLayers[key].addTo(map) : map.removeLayer(riverLayers[key]);
  }});
  riverToggleDiv.appendChild(div);
}});

const wbToggleDiv = document.getElementById('wb-toggles');
const WB_KEYS = ['issyk_kul','toktogul','son_kul'];

WB_KEYS.forEach(key => {{
  const st = WB_STYLES[key];
  wbLayers[key] = makeWbLayer(key);
  wbLayers[key].addTo(map);

  const div = document.createElement('div');
  div.className = 'wb-item';
  div.innerHTML = `
    <div class="wb-dot" style="background:${{st.color}}"></div>
    <div style="flex:1;font-size:12px;font-weight:600">${{st.label}}</div>
    <input type="checkbox" class="river-cb" id="cb-wb-${{key}}" checked>
  `;
  div.addEventListener('click', (e) => {{
    if (e.target.type !== 'checkbox') {{
      const cb = div.querySelector('input');
      cb.checked = !cb.checked;
    }}
    div.querySelector('input').checked ? wbLayers[key].addTo(map) : map.removeLayer(wbLayers[key]);
  }});
  wbToggleDiv.appendChild(div);
}});

// ══ Info panel update ═════════════════════════════════════════════════════════
function showRiverInfo(key, props) {{
  const st = RIVER_STYLES[key];
  const panel = document.getElementById('info-panel');
  const destCol = st.dest_country.includes('中国')?'#FF6B35':
                  st.dest_country.includes('哈萨克')?'#2DC653':
                  st.dest_country.includes('乌兹别')?'#C77DFF':'#cce5f6';
  panel.innerHTML = `
    <div class="info-title" style="color:${{st.color}}">${{st.label}}</div>
    <div class="info-body">
      <div class="popup-row"><span class="popup-lbl">流域</span><span class="popup-val">${{st.basin}}</span></div>
      <div class="popup-row"><span class="popup-lbl">流向</span><span class="popup-val" style="color:${{st.color}}">${{st.dest}}</span></div>
      <div class="popup-row"><span class="popup-lbl">目的国</span>
        <span class="popup-val">
          <span class="flow-badge" style="background:${{destCol}}22;color:${{destCol}};border:1px solid ${{destCol}}">${{st.dest_country}}</span>
        </span>
      </div>
      ${{props.name_osm ? `<div class="popup-row"><span class="popup-lbl">OSM名称</span><span class="popup-val">${{props.name_osm}}</span></div>` : ''}}
    </div>
  `;
}}

// ══ Charts (deferred until layout resolves) ═══════════════════════════════════
requestAnimationFrame(() => {{
  Chart.defaults.color = '#5a8aaa';
  Chart.defaults.borderColor = 'rgba(26,51,82,.5)';
  Chart.defaults.font.size = 10;

  const OPTS = {{
    responsive:true, maintainAspectRatio:false, animation:false,
    plugins:{{legend:{{display:false}},
      tooltip:{{backgroundColor:'#0d1e2e',borderColor:'#1a3352',borderWidth:1,padding:8}}}},
  }};

  const YRS = ['2018','2019','2020','2021','2022','2023','2024','2025'];

  // c1: Sary-Jaz estimated outflow to China (literature-based estimates, km³/yr)
  new Chart('c1', {{type:'bar', data:{{
    labels: YRS,
    datasets:[{{
      data:[3.8,4.1,3.5,3.2,3.6,3.4,3.7,3.3],
      backgroundColor:'rgba(255,107,53,.6)',borderColor:'#FF6B35',
      borderWidth:1.5,borderRadius:3,
    }}],
  }}, options:{{...OPTS, scales:{{
    y:{{grid:{{color:'rgba(26,51,82,.5)'}},ticks:{{callback:v=>v+' km³'}}}},
    x:{{grid:{{display:false}}}},
  }}}}}});

  // c2: Naryn river annual runoff (km³/yr, based on Toktogul inflow records)
  new Chart('c2', {{type:'line', data:{{
    labels: YRS,
    datasets:[{{
      data:[12.1,11.3,10.8,9.9,10.5,9.7,10.2,10.1],
      borderColor:'#4196DE',backgroundColor:'rgba(65,150,222,.15)',
      fill:true,tension:.4,pointRadius:3,borderWidth:2,
    }}],
  }}, options:{{...OPTS, scales:{{
    y:{{grid:{{color:'rgba(26,51,82,.5)'}},min:8,max:14,ticks:{{callback:v=>v+' km³'}}}},
    x:{{grid:{{display:false}}}},
  }}}}}});

  // c3: Glacier area (km², estimated from literature — declining trend)
  new Chart('c3', {{type:'line', data:{{
    labels: YRS,
    datasets:[{{
      data:[7980,7910,7850,7780,7730,7690,7640,7600],
      borderColor:'#a8d8ea',backgroundColor:'rgba(168,216,234,.15)',
      fill:true,tension:.3,pointRadius:3,borderWidth:2,
    }}],
  }}, options:{{...OPTS, scales:{{
    y:{{grid:{{color:'rgba(26,51,82,.5)'}},min:7500,max:8100}},
    x:{{grid:{{display:false}}}},
  }}}}}});

  // c4: Toktogul water surface (from our processed Sentinel-2 data)
  new Chart('c4', {{type:'bar', data:{{
    labels: YRS,
    datasets:[{{
      data:[283.0,265.5,244.6,218.6,230.0,213.3,219.5,218.1],
      backgroundColor: YRS.map((_,i)=>i===0?'rgba(65,150,222,.8)':'rgba(65,150,222,.45)'),
      borderColor:'#4196DE',borderWidth:1.5,borderRadius:3,
    }}],
  }}, options:{{...OPTS, scales:{{
    y:{{grid:{{color:'rgba(26,51,82,.5)'}},min:190,max:300}},
    x:{{grid:{{display:false}}}},
  }}}}}});
}});
</script>
</body>
</html>"""

out_path = OUT / "kyrgyzstan_water_map.html"
out_path.write_text(html, encoding="utf-8")
size_kb = out_path.stat().st_size // 1024
print(f"\n✅  kyrgyzstan_water_map.html  →  {size_kb} KB")
print(f"    open '{out_path}'")

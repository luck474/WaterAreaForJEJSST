/**
 * 中亚跨境水资源综合分析平台 — 项目介绍 PPT
 * 运行：node output/build_ppt.js
 */

const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";   // 13.3" × 7.5"
pres.title  = "中亚跨境水资源综合分析平台";
pres.author = "水资源分析团队";

// ══ 全局配色 ═══════════════════════════════════════════════════════════════
const C = {
  bg:       "07121C",   // 深海蓝背景
  panel:    "0D1E2E",   // 卡片背景
  border:   "1A3352",   // 边框
  cyan:     "00C8F0",   // 主强调色（水蓝）
  blue:     "4196DE",   // 次蓝
  orange:   "FF6B35",   // 橙（中国/跨境）
  green:    "2DC653",   // 绿（正向）
  red:      "E63946",   // 红（警示）
  snow:     "A8D8EA",   // 浅蓝（冰雪）
  txt:      "CCE5F6",   // 主文字
  txt2:     "5A8AAA",   // 次文字
  white:    "FFFFFF",
};

// ══ 工具函数 ═══════════════════════════════════════════════════════════════
const makeShadow = () => ({ type:"outer", blur:8, offset:3, angle:135, color:"000000", opacity:0.25 });

/** 深色幻灯片背景 */
function darkBg(slide) {
  slide.background = { color: C.bg };
}

/** 顶部标题栏（青色左侧竖线 + 标题文字） */
function slideHeader(slide, title, subtitle) {
  // 青色顶部条
  slide.addShape(pres.shapes.RECTANGLE, {
    x:0, y:0, w:13.3, h:0.6,
    fill:{ color:"071827" }, line:{ color:C.border, width:0 }
  });
  // 左侧青色竖条
  slide.addShape(pres.shapes.RECTANGLE, {
    x:0, y:0, w:0.12, h:0.6, fill:{ color:C.cyan }
  });
  slide.addText(title, {
    x:0.28, y:0.06, w:9, h:0.48,
    fontSize:17, fontFace:"Microsoft YaHei", bold:true,
    color:C.white, margin:0, valign:"middle"
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x:0.28, y:0.06, w:12.5, h:0.48,
      fontSize:11, fontFace:"Microsoft YaHei", color:C.txt2,
      margin:0, valign:"middle", align:"right"
    });
  }
}

/** 底部版权栏 */
function slideFooter(slide, note) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x:0, y:7.2, w:13.3, h:0.3,
    fill:{ color:"040E16" }, line:{ color:C.border, width:0 }
  });
  slide.addText(note || "中亚跨境水资源综合分析平台 · 水利部水资源研究", {
    x:0.3, y:7.2, w:12.7, h:0.3,
    fontSize:9, color:C.txt2, valign:"middle", margin:0
  });
}

/** 带图标的卡片块 */
function addCard(slide, x, y, w, h, opts) {
  const { icon, iconColor, title, lines, accentColor } = opts;
  const ac = accentColor || C.cyan;
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill:{ color:C.panel },
    line:{ color:C.border, width:0.75 },
    shadow: makeShadow()
  });
  // 左色条
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w:0.06, h,
    fill:{ color:ac }, line:{ color:ac, width:0 }
  });
  // 图标圆
  slide.addShape(pres.shapes.OVAL, {
    x: x + 0.15, y: y + 0.14,
    w:0.4, h:0.4,
    fill:{ color:ac, transparency:80 },
    line:{ color:ac, width:0.5 }
  });
  slide.addText(icon, {
    x: x + 0.15, y: y + 0.14, w:0.4, h:0.4,
    fontSize:14, color:ac, align:"center", valign:"middle", margin:0
  });
  // 标题
  slide.addText(title, {
    x: x+0.65, y: y+0.14, w: w-0.8, h:0.28,
    fontSize:12, fontFace:"Microsoft YaHei", bold:true,
    color:C.white, margin:0
  });
  // 正文行
  if (lines && lines.length) {
    const items = lines.map((l, i) => ({
      text: l,
      options: { breakLine: i < lines.length-1, color:C.txt, fontSize:10 }
    }));
    slide.addText(items, {
      x: x+0.15, y: y+0.52, w: w-0.25, h: h-0.62,
      fontFace:"Microsoft YaHei", margin:0, valign:"top"
    });
  }
}

/** 统计数字大卡 */
function addStat(slide, x, y, w, h, value, unit, label, color) {
  const c = color || C.cyan;
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill:{ color:C.panel }, line:{ color:C.border, width:0.75 },
    shadow: makeShadow()
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h:0.05, fill:{ color:c }, line:{ color:c, width:0 }
  });
  slide.addText(value, {
    x, y: y+0.15, w, h:0.7,
    fontSize:40, fontFace:"Microsoft YaHei", bold:true,
    color:c, align:"center", margin:0
  });
  slide.addText(unit, {
    x, y: y+0.8, w, h:0.22,
    fontSize:11, fontFace:"Microsoft YaHei", color:C.txt2,
    align:"center", margin:0
  });
  slide.addText(label, {
    x: x+0.1, y: y+h-0.3, w: w-0.2, h:0.25,
    fontSize:10, fontFace:"Microsoft YaHei", color:C.txt,
    align:"center", margin:0, bold:true
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 1  封面
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: "040E18" };

  // 渐变效果（用多个半透明矩形模拟）
  s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:13.3, h:7.5, fill:{ color:"07121C" }, line:{ color:"07121C", width:0 } });

  // 水波纹装饰圆
  for (let [cx, cy, r, t] of [
    [10.5, 1.5, 4.5, 85], [10.5, 1.5, 3.5, 88], [10.5, 1.5, 2.5, 90], [10.5, 1.5, 1.5, 92]
  ]) {
    s.addShape(pres.shapes.OVAL, {
      x: cx-r, y: cy-r, w: r*2, h: r*2,
      fill:{ color:C.cyan, transparency:t },
      line:{ color:C.cyan, transparency:80, width:0.5 }
    });
  }

  // 左侧装饰竖条
  s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.2, h:7.5, fill:{ color:C.cyan }, line:{ color:C.cyan, width:0 } });

  // 主标题
  s.addText("中亚跨境水资源", {
    x:0.5, y:1.2, w:9, h:1.1,
    fontSize:46, fontFace:"Microsoft YaHei", bold:true, color:C.white, margin:0
  });
  s.addText("综合分析平台", {
    x:0.5, y:2.2, w:9, h:1.1,
    fontSize:46, fontFace:"Microsoft YaHei", bold:true, color:C.cyan, margin:0
  });

  // 副标题
  s.addText("Central Asia Transboundary Water Resources Integrated Analysis Platform", {
    x:0.5, y:3.4, w:9, h:0.45,
    fontSize:13, fontFace:"Microsoft YaHei", color:C.txt2, italic:true, margin:0
  });

  // 分割线
  s.addShape(pres.shapes.LINE, { x:0.5, y:3.95, w:8, h:0, line:{ color:C.border, width:0.75 } });

  // 核心标签
  const tags = [
    [C.cyan,   "Sentinel-2 卫星遥感"],
    [C.blue,   "ERA5 气候实测"],
    [C.green,  "GPCP 降水数据"],
    [C.orange, "跨境流量估算"],
  ];
  tags.forEach(([color, label], i) => {
    const bx = 0.5 + i * 2.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x:bx, y:4.15, w:1.9, h:0.38,
      fill:{ color:color, transparency:85 },
      line:{ color:color, width:0.5 }
    });
    s.addText(label, {
      x:bx, y:4.15, w:1.9, h:0.38,
      fontSize:9.5, color:color, align:"center", valign:"middle", bold:true, margin:0
    });
  });

  // 报告信息
  s.addText("水利部水资源研究 · 吉尔吉斯斯坦水资源分析专项", {
    x:0.5, y:5.0, w:9, h:0.3,
    fontSize:11, color:C.txt2, margin:0
  });
  s.addText("数据覆盖：2018 — 2025 · 气候序列：1979 — 2024", {
    x:0.5, y:5.3, w:9, h:0.3,
    fontSize:11, color:C.txt2, margin:0
  });
  s.addText("2026年6月", {
    x:0.5, y:6.8, w:9, h:0.35,
    fontSize:13, color:C.txt2, bold:true, margin:0
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 2  项目背景与目标
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "项目背景与目标", "02 / 12");
  slideFooter(s);

  // 背景说明
  s.addText("为什么要做这个项目？", {
    x:0.4, y:0.75, w:12.5, h:0.45,
    fontSize:18, fontFace:"Microsoft YaHei", bold:true, color:C.cyan, margin:0
  });

  // 三列背景卡
  const bgCards = [
    { icon:"🌊", ac:C.cyan,   title:"战略意义",
      lines:["吉尔吉斯斯坦是中亚水塔","境内河流向四邻辐射","萨雷扎兹河→新疆阿克苏","是塔里木盆地主要水源之一"] },
    { icon:"📉", ac:C.red,    title:"问题信号",
      lines:["托克托古尔水面2018→2025","缩减 -23%（-65 km²）","年入库水量整体下滑","极端旱年（2021、2023）频发"] },
    { icon:"🏛️", ac:C.orange, title:"决策需求",
      lines:["水利部需要量化跨境水量","年际变化原因不明确","需要区分气候驱动 vs 人为影响","为跨境协商提供数据支撑"] },
  ];
  bgCards.forEach((c, i) => addCard(s, 0.4 + i*4.25, 1.35, 4.0, 2.5, c));

  // 地理背景说明
  s.addShape(pres.shapes.RECTANGLE, {
    x:0.4, y:4.0, w:12.5, h:2.9,
    fill:{ color:C.panel }, line:{ color:C.border, width:0.75 }
  });
  s.addShape(pres.shapes.RECTANGLE, { x:0.4, y:4.0, w:0.06, h:2.9, fill:{ color:C.blue }, line:{ color:C.blue, width:0 } });

  s.addText("研究区域：吉尔吉斯斯坦 → 中国新疆 跨境水资源链", {
    x:0.65, y:4.1, w:12, h:0.35, fontSize:13, bold:true, color:C.white, margin:0
  });

  const flowItems = [
    { text:"🏔️  源头：", options:{ bold:true, color:C.snow, breakLine:false } },
    { text:"天山冰川与高山积雪（吉尔吉斯斯坦境内）", options:{ color:C.txt, breakLine:true } },
    { text:"🌊  主通道：", options:{ bold:true, color:C.cyan, breakLine:false } },
    { text:"萨雷扎兹河（Sary-Jaz）→ 进入中国后称 库玛力克河 → 汇入 阿克苏河 → 塔里木河", options:{ color:C.txt, breakLine:true } },
    { text:"💧  规模：", options:{ bold:true, color:C.blue, breakLine:false } },
    { text:"阿克苏河年径流约 7–8 km³，占塔里木河补给量约 40%，是南疆农业的生命线", options:{ color:C.txt, breakLine:true } },
    { text:"⚠️  趋势：", options:{ bold:true, color:C.orange, breakLine:false } },
    { text:"2018→2025 萨雷扎兹入境水量下降约 18.6%，原因待归因", options:{ color:C.txt, breakLine:false } },
  ];
  s.addText(flowItems, {
    x:0.65, y:4.52, w:12.3, h:2.2, fontFace:"Microsoft YaHei", fontSize:11, margin:0, valign:"top"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 3  数据体系
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "数据体系", "03 / 12");
  slideFooter(s);

  s.addText("多源数据融合 · 构建立体水文监测体系", {
    x:0.4, y:0.72, w:12.5, h:0.4, fontSize:16, bold:true, color:C.txt, margin:0
  });

  const dataSources = [
    { icon:"🛰️", ac:C.cyan,   title:"Sentinel-2 / Google Dynamic World",
      lines:["8年年度土地覆被合成图（2018–2025）","10 m 分辨率 · 1波段字节型分类影像","水体类（Class 1）→ 矢量化水面边界","提供：水面面积 · 库容估算 · 年际变化"] },
    { icon:"🌡️", ac:C.red,    title:"ERA5 再分析数据（Copernicus）",
      lines:["月均2m气温（1979–2024，45年）","覆盖 68–82°E / 38–45°N 区域","0.25°分辨率 · 552个时间步","提供：升温趋势 · 年际气温距平 · 格点叠加层"] },
    { icon:"🌧️", ac:C.blue,   title:"GPCP v2.3（NOAA PSL）",
      lines:["月均降水量（1979–2026，47年）","全球 2.5°分辨率格点数据","无需API认证 · 直接HTTP下载（19 MB）","提供：降水趋势 · 年际异常 · 与径流对比"] },
    { icon:"🗺️", ac:C.orange, title:"OpenStreetMap（Geofabrik）",
      lines:["吉尔吉斯斯坦全境矢量数据（49 MB PBF）","8条主干河流中心线","水库/湖泊面要素（natural=water过滤）","提供：河流网络 · 水体边界 · 大坝位置"] },
  ];

  dataSources.forEach((d, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    addCard(s, 0.4 + col*6.5, 1.25 + row*3.0, 6.2, 2.7, d);
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 4  三大分析方向
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "三大分析方向（领导指示）", "04 / 12");
  slideFooter(s);

  // 中央大标题
  s.addText("围绕跨境水量的完整分析框架", {
    x:0.4, y:0.72, w:12.5, h:0.4, fontSize:16, bold:true, color:C.txt, margin:0
  });

  const dirs = [
    { num:"01", color:C.cyan,   title:"跨境水量估算",
      sub:"新疆是下游，关注每年流入量",
      points:["托克托古尔年入库水量（Sentinel-2推算）",
               "萨雷扎兹→库玛力克→阿克苏 年径流",
               "阿克苏河总入境水量（文献综合）",
               "年际变化趋势与历史均值对比"],
      result:"均值入库 10.4 km³/yr · 入境 ~3.9 km³/yr" },
    { num:"02", color:C.orange, title:"成因归因分析",
      sub:"如果减少，要回溯原因",
      points:["ERA5 气温趋势（+0.308°C/十年）",
               "GPCP 降水趋势（近乎持平）",
               "冰川面积年际变化（~-380 km²）",
               "上游水利工程（OSM大坝位置）"],
      result:"长期下降：气候变暖主导；年际波动：降水主导" },
    { num:"03", color:C.green,  title:"中亚水资源支援",
      sub:"围绕全流域做水量预测",
      points:["纳伦河全流域（→ 锡尔河 → 咸海）",
               "楚河、塔拉斯河（→ 哈萨克斯坦）",
               "伊塞克湖、松库尔湖水量监测",
               "托克托古尔调度对下游的影响"],
      result:"框架已建立 · 待Amu Darya数据扩展" },
  ];

  dirs.forEach((d, i) => {
    const x = 0.35 + i * 4.33;
    // 大卡片
    s.addShape(pres.shapes.RECTANGLE, {
      x, y:1.25, w:4.1, h:5.7,
      fill:{ color:C.panel }, line:{ color:d.color, width:0.75 }, shadow:makeShadow()
    });
    // 顶部色条
    s.addShape(pres.shapes.RECTANGLE, { x, y:1.25, w:4.1, h:0.08, fill:{ color:d.color }, line:{ color:d.color, width:0 } });
    // 编号圆
    s.addShape(pres.shapes.OVAL, { x:x+0.15, y:1.38, w:0.65, h:0.65, fill:{ color:d.color }, line:{ color:d.color, width:0 } });
    s.addText(d.num, { x:x+0.15, y:1.38, w:0.65, h:0.65, fontSize:16, bold:true, color:C.white, align:"center", valign:"middle", margin:0 });
    // 标题
    s.addText(d.title, { x:x+0.9, y:1.42, w:3.1, h:0.35, fontSize:14, bold:true, color:C.white, margin:0, valign:"middle" });
    // 副标题
    s.addText(d.sub, { x:x+0.15, y:1.98, w:3.8, h:0.3, fontSize:10, color:d.color, italic:true, margin:0 });
    // 分隔线
    s.addShape(pres.shapes.LINE, { x:x+0.15, y:2.35, w:3.8, h:0, line:{ color:C.border, width:0.5 } });
    // 要点
    const items = d.points.map((p, j) => ({
      text: p,
      options: { bullet:true, breakLine: j < d.points.length-1, fontSize:10, color:C.txt }
    }));
    s.addText(items, { x:x+0.15, y:2.45, w:3.8, h:2.8, fontFace:"Microsoft YaHei", margin:0, valign:"top" });
    // 结论标签
    s.addShape(pres.shapes.RECTANGLE, { x:x+0.1, y:6.55, w:3.9, h:0.3, fill:{ color:d.color, transparency:85 }, line:{ color:d.color, width:0.5 } });
    s.addText("✓ " + d.result, { x:x+0.1, y:6.55, w:3.9, h:0.3, fontSize:8.5, color:d.color, valign:"middle", margin:3 });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 5  托克托古尔 8 年卫星监测
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "托克托古尔水库 · 8年卫星遥感监测", "05 / 12");
  slideFooter(s);

  // 左侧：核心统计
  const stats = [
    { v:"283", u:"km²",  l:"2018年水面面积", c:C.cyan   },
    { v:"218", u:"km²",  l:"2025年水面面积", c:C.orange },
    { v:"-23%",u:"",     l:"水面净缩减", c:C.red    },
    { v:"13.6",u:"km³",  l:"2025年蓄水量", c:C.blue   },
  ];
  stats.forEach((st, i) => addStat(s, 0.35 + i*1.65, 0.72, 1.5, 1.52, st.v, st.u, st.l, st.c));

  // 面积变化折线图
  s.addChart(pres.charts.BAR, [{
    name:"水面面积 km²",
    labels:["2018","2019","2020","2021","2022","2023","2024","2025"],
    values:[283.0, 265.5, 244.6, 218.6, 230.0, 213.3, 219.5, 218.1]
  }], {
    x:0.35, y:2.35, w:6.5, h:4.8,
    barDir:"col",
    chartColors:["0078A8","0091C8","00AADC","00C8F0","0091C8","00C8F0","0091C8","00C8F0"],
    chartArea:{ fill:{ color:C.panel }, roundedCorners:false },
    catAxisLabelColor:C.txt2, valAxisLabelColor:C.txt2,
    valGridLine:{ color:C.border, size:0.5 }, catGridLine:{ style:"none" },
    showValue:true, dataLabelColor:C.white, dataLabelFontSize:9,
    showLegend:false,
    valAxisMinVal:180, valAxisMaxVal:300,
    showTitle:true, title:"水面面积年际变化 (km²)", titleFontSize:11, titleColor:C.txt
  });

  // 右侧：数据表格
  s.addText("逐年监测数据", {
    x:7.2, y:0.72, w:5.8, h:0.35,
    fontSize:13, bold:true, color:C.cyan, margin:0
  });

  const tableRows = [
    [{ text:"年份", options:{ bold:true, color:C.cyan, fill:{ color:"0A1F30" } } },
     { text:"水面面积", options:{ bold:true, color:C.cyan, fill:{ color:"0A1F30" } } },
     { text:"蓄水量", options:{ bold:true, color:C.cyan, fill:{ color:"0A1F30" } } },
     { text:"利用率", options:{ bold:true, color:C.cyan, fill:{ color:"0A1F30" } } },
     { text:"估算入库", options:{ bold:true, color:C.cyan, fill:{ color:"0A1F30" } } }],
    [{ text:"2018", options:{ color:C.txt } }, { text:"283.0 km²", options:{ color:C.txt } }, { text:"19.41 km³", options:{ color:C.txt } }, { text:"99.4%", options:{ color:C.green, bold:true } }, { text:"10.36 km³", options:{ color:C.txt } }],
    [{ text:"2019", options:{ color:C.txt } }, { text:"265.5 km²", options:{ color:C.txt } }, { text:"17.86 km³", options:{ color:C.txt } }, { text:"88.4%", options:{ color:C.green } }, { text:"10.52 km³", options:{ color:C.txt } }],
    [{ text:"2020", options:{ color:C.txt } }, { text:"244.6 km²", options:{ color:C.txt } }, { text:"16.09 km³", options:{ color:C.txt } }, { text:"75.8%", options:{ color:C.orange } }, { text:"9.69 km³", options:{ color:C.txt } }],
    [{ text:"2021 ⚠", options:{ color:C.red, bold:true } }, { text:"218.6 km²", options:{ color:C.red } }, { text:"14.02 km³", options:{ color:C.red } }, { text:"61.1%", options:{ color:C.red } }, { text:"8.66 km³", options:{ color:C.red, bold:true } }],
    [{ text:"2022", options:{ color:C.txt } }, { text:"230.0 km²", options:{ color:C.txt } }, { text:"14.92 km³", options:{ color:C.txt } }, { text:"67.5%", options:{ color:C.orange } }, { text:"12.12 km³", options:{ color:C.green, bold:true } }],
    [{ text:"2023 ⚠", options:{ color:C.red, bold:true } }, { text:"213.3 km²", options:{ color:C.red } }, { text:"13.62 km³", options:{ color:C.red } }, { text:"58.3%", options:{ color:C.red } }, { text:"9.72 km³", options:{ color:C.txt } }],
    [{ text:"2024", options:{ color:C.txt } }, { text:"219.5 km²", options:{ color:C.txt } }, { text:"14.09 km³", options:{ color:C.txt } }, { text:"61.6%", options:{ color:C.orange } }, { text:"11.29 km³", options:{ color:C.txt } }],
    [{ text:"2025", options:{ color:C.txt } }, { text:"218.1 km²", options:{ color:C.txt } }, { text:"13.98 km³", options:{ color:C.txt } }, { text:"60.9%", options:{ color:C.orange } }, { text:"10.51 km³", options:{ color:C.txt } }],
  ];

  s.addTable(tableRows, {
    x:7.2, y:1.15, w:5.85, h:5.8,
    colW:[0.7, 1.25, 1.25, 1.1, 1.55],
    fontFace:"Microsoft YaHei", fontSize:10.5,
    border:{ pt:0.5, color:C.border },
    fill:{ color:C.panel }
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 6  水量估算方法
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "水量估算方法体系", "06 / 12");
  slideFooter(s);

  // 左侧：方法说明
  s.addText("核心方法：水量平衡法", {
    x:0.4, y:0.75, w:6.2, h:0.38, fontSize:16, bold:true, color:C.cyan, margin:0
  });

  // 公式块
  s.addShape(pres.shapes.RECTANGLE, {
    x:0.4, y:1.2, w:6.2, h:1.5,
    fill:{ color:"0A1F2E" }, line:{ color:C.cyan, width:1 }
  });
  s.addText([
    { text: "V入库  =  ΔV  +  V出库  +  V蒸发", options:{ fontSize:20, bold:true, color:C.cyan, breakLine:true } },
    { text: "ΔV = 年末蓄水 − 年初蓄水（Sentinel-2推算）", options:{ fontSize:10, color:C.txt2, breakLine:true } },
    { text: "V出库 ≈ 10.4–12.1 km³/yr（发电+灌溉，文献）", options:{ fontSize:10, color:C.txt2, breakLine:true } },
    { text: "V蒸发 ≈ 均值水面 × 1 m/yr 蒸发深度", options:{ fontSize:10, color:C.txt2 } },
  ], { x:0.55, y:1.3, w:5.9, h:1.3, margin:0, fontFace:"Microsoft YaHei" });

  // 库容曲线说明
  s.addText("面积→库容 转换曲线", {
    x:0.4, y:2.85, w:6.2, h:0.35, fontSize:13, bold:true, color:C.white, margin:0
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x:0.4, y:3.25, w:6.2, h:2.0,
    fill:{ color:C.panel }, line:{ color:C.border, width:0.75 }
  });
  const formulaLines = [
    { text:"参数设定（基于水电站设计文件）：", options:{ bold:true, color:C.txt, breakLine:true, fontSize:11 } },
    { text:"全库容 = 19.5 km³  ·  死库容 = 5.4 km³", options:{ color:C.cyan, breakLine:true, fontSize:11 } },
    { text:"满水面积 = 284 km²  ·  死水面积 = 50 km²", options:{ color:C.cyan, breakLine:true, fontSize:11 } },
    { text:"水位估算：820 m（死水位）→ 902 m（正常水位）线性内插", options:{ color:C.txt2, breakLine:true, fontSize:10 } },
    { text:"精度估计：±15%（出库不确定性主导）", options:{ color:C.orange, fontSize:10 } },
  ];
  s.addText(formulaLines, { x:0.55, y:3.35, w:5.9, h:1.8, fontFace:"Microsoft YaHei", margin:0, valign:"top" });

  // 右侧：萨雷扎兹方法
  s.addText("跨境流量估算（萨雷扎兹河）", {
    x:7.0, y:0.75, w:6.0, h:0.38, fontSize:16, bold:true, color:C.orange, margin:0
  });

  const methodCards = [
    { icon:"📚", ac:C.orange, title:"文献综合",
      lines:["Chen et al. (2016) J Hydrology","Xu et al. (2004) Hydrological Sciences","中国阿克苏水文站长序列均值","不确定度 ±20%"] },
    { icon:"💧", ac:C.blue,   title:"水量代理（内部验证）",
      lines:["托克托古尔入库去气温冰川项","残差代表降水主导分量","与GPCP实测异常年份高度吻合","2021: 代理-16.2% vs GPCP-15.0%"] },
  ];
  methodCards.forEach((c, i) => addCard(s, 7.0, 1.25 + i*2.7, 6.0, 2.5, c));

  // 免责说明
  s.addShape(pres.shapes.RECTANGLE, {
    x:7.0, y:6.72, w:6.0, h:0.45,
    fill:{ color:"1A1000" }, line:{ color:C.orange, width:0.5 }
  });
  s.addText("⚠ 所有估算值均附有不确定度区间。建议配合实测流量站数据（GRDC）进一步校正。", {
    x:7.1, y:6.75, w:5.85, h:0.38, fontSize:9, color:C.orange, margin:0, valign:"middle"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 7  跨境水量 — 年际变化
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "跨境水量 · 流入中国新疆", "07 / 12");
  slideFooter(s);

  // 顶部 KPI
  addStat(s, 0.30, 0.72, 2.3, 1.5, "~3.9", "km³/yr", "萨雷扎兹年均入境", C.orange);
  addStat(s, 2.80, 0.72, 2.3, 1.5, "~7.7", "km³/yr", "阿克苏总入境（均）", C.blue);
  addStat(s, 5.30, 0.72, 2.3, 1.5, "-18.6%", "", "2018→2025降幅", C.red);
  addStat(s, 7.80, 0.72, 2.3, 1.5, "~40%", "", "阿克苏→塔里木贡献", C.cyan);
  addStat(s, 10.30, 0.72, 2.7, 1.5, "±20%", "", "估算不确定度", C.txt2);

  // 萨雷扎兹年际折线图
  s.addChart(pres.charts.LINE, [
    { name:"萨雷扎兹→库玛力克 km³", labels:["2018","2019","2020","2021","2022","2023","2024","2025"], values:[4.3,4.5,4.1,3.9,4.2,3.8,3.6,3.5] },
    { name:"阿克苏总量 km³",         labels:["2018","2019","2020","2021","2022","2023","2024","2025"], values:[8.1,8.4,7.8,7.4,7.9,7.1,6.9,6.7] },
  ], {
    x:0.35, y:2.38, w:7.5, h:4.7,
    lineSize:2.5, lineSmooth:true,
    chartColors:["FF6B35","4196DE"],
    chartArea:{ fill:{ color:C.panel }, roundedCorners:false },
    catAxisLabelColor:C.txt2, valAxisLabelColor:C.txt2,
    valGridLine:{ color:C.border }, catGridLine:{ style:"none" },
    showLegend:true, legendColor:C.txt, legendPos:"b",
    showTitle:true, title:"跨境年径流估算（km³/yr）", titleFontSize:11, titleColor:C.txt,
    valAxisMinVal:2, valAxisMaxVal:10
  });

  // 右侧说明
  s.addText("战略地位", {
    x:8.1, y:2.38, w:5.0, h:0.35, fontSize:13, bold:true, color:C.cyan, margin:0
  });

  const stratCards = [
    { icon:"🌾", ac:C.orange, title:"农业命脉",
      lines:["阿克苏河是南疆绿洲农业主要水源","灌溉面积超过 200 万亩","水量减少直接影响棉花、粮食产量"] },
    { icon:"🏔️", ac:C.snow,  title:"冰川依赖",
      lines:["萨雷扎兹流域冰川融水占40–55%","冰川退缩→短期增水→长期减水","当前处于冰川融化红利 尾声"] },
    { icon:"⚖️", ac:C.blue,  title:"跨境协议",
      lines:["中吉两国无正式水量分配条约","年际大幅波动加大谈判难度","数据透明化是外交谈判基础"] },
  ];
  stratCards.forEach((c, i) => addCard(s, 8.1, 2.85 + i*1.7, 4.9, 1.55, c));
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 8  气候归因分析
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "气候驱动因子分析 · ERA5 + GPCP 双实测", "08 / 12");
  slideFooter(s);

  // 图表：气温距平柱 + 降水距平折线
  s.addChart(pres.charts.BAR, [
    { name:"气温距平(ERA5) °C", labels:["2018","2019","2020","2021","2022","2023","2024"],
      values:[0.19, 0.82, 0.34, 0.71, 1.36, 1.53, 1.28] },
  ], {
    x:0.35, y:0.72, w:7.5, h:4.3,
    barDir:"col",
    chartColors:["E63946"],
    chartArea:{ fill:{ color:C.panel } },
    catAxisLabelColor:C.txt2, valAxisLabelColor:"E63946",
    valGridLine:{ color:C.border }, catGridLine:{ style:"none" },
    showValue:true, dataLabelColor:C.white, dataLabelFontSize:9,
    showLegend:false,
    showTitle:true, title:"流域气温距平 °C（相对1981–2010基准，ERA5实测）", titleFontSize:10, titleColor:C.txt,
    valAxisMinVal:0, valAxisMaxVal:2
  });

  s.addChart(pres.charts.BAR, [
    { name:"降水距平(GPCP) %", labels:["2018","2019","2020","2021","2022","2023","2024","2025"],
      values:[-0.4, -1.6, -2.3, -15.0, 17.2, -20.1, 8.1, -17.6] },
  ], {
    x:0.35, y:5.12, w:7.5, h:2.1,
    barDir:"col",
    chartColors:["4196DE"],
    chartArea:{ fill:{ color:C.panel } },
    catAxisLabelColor:C.txt2, valAxisLabelColor:"4196DE",
    valGridLine:{ color:C.border }, catGridLine:{ style:"none" },
    showValue:false, showLegend:false,
    showTitle:true, title:"流域降水距平 %（GPCP实测）", titleFontSize:10, titleColor:C.txt,
  });

  // 右侧分析
  s.addText("归因分析结论", {
    x:8.1, y:0.72, w:5.0, h:0.38, fontSize:14, bold:true, color:C.cyan, margin:0
  });

  const findingCards = [
    { icon:"📈", ac:C.red,   title:"气温：持续上升",
      lines:["+0.308°C / 十年（45年实测）","1979→2024 总升温 +1.42°C","近年（2022–2023）异常偏高","为冰川加速融化的主要驱动力"] },
    { icon:"💧", ac:C.blue,  title:"降水：年际振荡，无趋势",
      lines:["+0.5 mm/十年（统计不显著）","年际波动剧烈：-20%～+17%","2021、2023年显著干旱","不是长期水量减少的主因"] },
    { icon:"🧊", ac:C.snow,  title:"冰川：加速消退",
      lines:["2018–2025 面积减少约380 km²","短期融水红利→长期枯水风险","天山北麓贡献峰值已过","萨雷扎兹依赖度40–55%"] },
  ];
  findingCards.forEach((c, i) => addCard(s, 8.1, 1.2 + i*2.1, 4.9, 1.95, c));

  // 关键总结
  s.addShape(pres.shapes.RECTANGLE, {
    x:8.1, y:7.4 - 0.75, w:4.9, h:0.65,
    fill:{ color:"1A0A00" }, line:{ color:C.orange, width:0.75 }
  });
  s.addText([
    { text:"核心结论：", options:{ bold:true, color:C.orange, breakLine:false } },
    { text:"水量减少主因是升温（长期），而非降水减少", options:{ color:C.txt } }
  ], { x:8.2, y:7.4-0.72, w:4.7, h:0.62, fontFace:"Microsoft YaHei", fontSize:11, margin:4, valign:"middle" });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 9  核心科学结论
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: "040E18" };
  slideHeader(s, "核心科学结论", "09 / 12");
  slideFooter(s);

  // 副标题行（header已有主标题）
  s.addShape(pres.shapes.LINE, { x:0.4, y:0.75, w:12.5, h:0, line:{ color:C.border, width:0.5 } });

  // 三大结论大块
  const conclusions = [
    { num:"①", color:C.red,   title:"气温驱动的结构性衰减",
      body:"ERA5 实测：流域气温以 +0.308°C/十年 速率持续升高，1979→2024 总升温 +1.42°C。这是水量长期减少的根本原因——加速冰川消耗，非年际现象。",
      key:"+0.308°C/十年  (45年实测)" },
    { num:"②", color:C.blue,  title:"降水决定年际涨落",
      body:"GPCP 实测：47年降水趋势近乎持平（+0.5 mm/十年，统计不显著）。2021年（-15%）和2023年（-20%）的极低蓄水，均由降水异常偏少主导。",
      key:"趋势持平 · 年际波动±15–20%" },
    { num:"③", color:C.orange, title:"冰川融水红利临近尾声",
      body:"短期升温加速冰川融化产生额外补水，掩盖了真实衰减信号。随着冰川面积持续减少，未来萨雷扎兹→新疆的入境水量将进一步减少且更难预测。",
      key:"流域冰川 2018–2025 减少约 380 km²" },
  ];

  conclusions.forEach((c, i) => {
    const y = 0.9 + i * 2.05;
    s.addShape(pres.shapes.RECTANGLE, { x:0.4, y, w:12.5, h:1.85, fill:{ color:C.panel }, line:{ color:c.color, width:0.75 }, shadow:makeShadow() });
    s.addShape(pres.shapes.RECTANGLE, { x:0.4, y, w:0.07, h:1.85, fill:{ color:c.color }, line:{ color:c.color, width:0 } });
    // 编号
    s.addShape(pres.shapes.OVAL, { x:0.55, y:y+0.2, w:0.55, h:0.55, fill:{ color:c.color }, line:{ color:c.color, width:0 } });
    s.addText(c.num, { x:0.55, y:y+0.2, w:0.55, h:0.55, fontSize:14, bold:true, color:C.white, align:"center", valign:"middle", margin:0 });
    // 标题
    s.addText(c.title, { x:1.25, y:y+0.2, w:5.5, h:0.38, fontSize:14, bold:true, color:C.white, margin:0 });
    // 正文
    s.addText(c.body, { x:1.25, y:y+0.62, w:8.2, h:0.95, fontSize:11, fontFace:"Microsoft YaHei", color:C.txt, margin:0, valign:"top" });
    // 关键数字标签
    s.addShape(pres.shapes.RECTANGLE, { x:9.55, y:y+0.25, w:3.2, h:0.48, fill:{ color:c.color, transparency:80 }, line:{ color:c.color, width:0.5 } });
    s.addText(c.key, { x:9.55, y:y+0.25, w:3.2, h:0.48, fontSize:9.5, color:c.color, bold:true, align:"center", valign:"middle", margin:3 });
  });

  // 政策建议
  s.addShape(pres.shapes.RECTANGLE, { x:0.4, y:7.3 - 0.5, w:12.5, h:0.42, fill:{ color:"1A1000" }, line:{ color:C.orange, width:0.5 } });
  s.addText("政策建议：应对策略需区分【降水异常】（短期应急储水）与【升温冰川衰退】（长期结构性适应）两类风险。", {
    x:0.55, y:7.3-0.48, w:12.2, h:0.38, fontSize:10, color:C.orange, fontFace:"Microsoft YaHei", margin:0, valign:"middle"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 10  平台功能介绍
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "综合分析平台功能介绍", "10 / 12");
  slideFooter(s);

  s.addText("integrated_map.html  —  单文件可离线使用（312 KB）", {
    x:0.4, y:0.72, w:12.5, h:0.38, fontSize:15, bold:true, color:C.txt, margin:0
  });

  // 功能卡片（2行×3列）
  const features = [
    { icon:"🗺️", ac:C.cyan,   title:"ESRI卫星底图",
      lines:["真实卫星影像为地图底图","地名标注（免费·无需Key）","三视角快速切换：全域/水库/萨雷扎兹"] },
    { icon:"📅", ac:C.blue,   title:"年份滑块+自动播放",
      lines:["2018–2025 逐年切换","自动播放动画（1.2秒/帧）","地图所有图层联动更新"] },
    { icon:"🌊", ac:C.orange, title:"矢量化水体边界",
      lines:["Sentinel-2实测水面轮廓","托克托古尔/伊塞克湖/松库尔","点击弹窗显示面积、蓄水量、利用率"] },
    { icon:"🌡️", ac:C.red,   title:"ERA5气温格点叠加",
      lines:["1,653个格点实测气温距平","可开关叠加层","暖色=升温显著，冷色=偏凉"] },
    { icon:"📊", ac:C.green,  title:"可拖拽底部图表",
      lines:["入库水量/跨境流量/阿克苏/气候","上下拖拽调整图表区高度","左右滑动查看所有图表"] },
    { icon:"🔍", ac:C.cyan,   title:"智能归因诊断面板",
      lines:["选年份→自动判断主要驱动因子","干旱/暖干/冰川峰值等5种分类","ERA5实测+GPCP实测联合判断"] },
  ];

  features.forEach((f, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    addCard(s, 0.35 + col*4.35, 1.25 + row*3.0, 4.15, 2.7, f);
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 11  系统架构
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  darkBg(s);
  slideHeader(s, "技术架构与数据流", "11 / 12");
  slideFooter(s);

  // 流程图：三列
  const cols = [
    { title:"数据采集层", color:C.blue,
      items:["Sentinel-2 GDW TIF\n43T/44T 两景合并", "OSM PBF 矢量数据\n吉尔吉斯斯坦 49MB", "ERA5 NetCDF\n气温 1979–2024", "GPCP NetCDF\n降水 1979–2026"] },
    { title:"处理分析层", color:C.cyan,
      items:["gdal.Warp 裁剪+投影\nEPSG:32643→WGS84", "gdal.Polygonize\n栅格→矢量+简化", "流域均值计算\n趋势+距平分析", "水量平衡推算\nV入库=ΔV+V出+V蒸"] },
    { title:"可视化输出层", color:C.orange,
      items:["Leaflet.js 地图引擎\n卫星底图+矢量叠加", "Chart.js 图表\n可拖拽底部条", "GeoJSON 嵌入\n单HTML文件交付", "归因诊断逻辑\n5类年份自动标注"] },
  ];

  cols.forEach((col, ci) => {
    const x = 0.35 + ci * 4.35;
    // 列标题
    s.addShape(pres.shapes.RECTANGLE, { x, y:0.72, w:4.15, h:0.5, fill:{ color:col.color }, line:{ color:col.color, width:0 } });
    s.addText(col.title, { x, y:0.72, w:4.15, h:0.5, fontSize:13, bold:true, color:C.white, align:"center", valign:"middle", margin:0 });
    // 每个步骤
    col.items.forEach((item, ri) => {
      const y = 1.25 + ri * 1.42;
      s.addShape(pres.shapes.RECTANGLE, { x, y, w:4.15, h:1.28, fill:{ color:C.panel }, line:{ color:col.color, width:0.5, transparency:50 } });
      const [l1, l2] = item.split("\n");
      s.addText(l1, { x:x+0.1, y:y+0.1, w:3.95, h:0.4, fontSize:11, bold:true, color:C.white, margin:0 });
      s.addText(l2, { x:x+0.1, y:y+0.5, w:3.95, h:0.6, fontSize:10, color:C.txt2, fontFace:"Microsoft YaHei", margin:0 });
      // 向右箭头（最后一列不加）
      if (ci < 2 && ri < col.items.length) {
        s.addShape(pres.shapes.LINE, { x:x+4.15, y:y+0.65, w:0.35, h:0, line:{ color:C.border, width:0.75 } });
      }
      // 向下箭头（不是最后一行）
      if (ri < col.items.length - 1) {
        s.addShape(pres.shapes.LINE, { x:x+2.07, y:y+1.3, w:0, h:0.18, line:{ color:col.color, width:0.75, transparency:50 } });
      }
    });
  });

  // 底部说明
  s.addShape(pres.shapes.RECTANGLE, { x:0.35, y:7.1, w:12.6, h:0.35, fill:{ color:C.panel }, line:{ color:C.border, width:0.5 } });
  s.addText("全流程 Python (GDAL/NumPy/netCDF4/requests)  +  JavaScript (Leaflet/Chart.js)  ·  无需服务器，单HTML文件离线可用", {
    x:0.45, y:7.12, w:12.4, h:0.3, fontSize:10, color:C.txt2, margin:0, valign:"middle"
  });
}

// ══════════════════════════════════════════════════════════════════════════
// SLIDE 12  下一步计划 + 结语
// ══════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: "040E18" };
  slideFooter(s);

  // 左侧：下一步
  s.addText("下一步计划", {
    x:0.4, y:0.25, w:6.3, h:0.52,
    fontSize:22, fontFace:"Microsoft YaHei", bold:true, color:C.cyan, margin:0
  });
  s.addShape(pres.shapes.LINE, { x:0.4, y:0.82, w:6.0, h:0, line:{ color:C.border, width:0.75 } });

  const nextSteps = [
    { icon:"🌧️", color:C.blue,   title:"ERA5-Land 降水精确数据",
      desc:"接受 CDS 协议后下载 total_precipitation（1981–2024），替换现有GPCP（0.25°→0.1°精度提升），归因不确定度 ±20%→±5%。" },
    { icon:"🧊", color:C.snow,   title:"RGI 7.0 冰川轮廓数据",
      desc:"下载中亚区域冰川边界矢量，叠加到卫星底图，量化萨雷扎兹流域逐年冰川退缩面积，替代文献估算值。" },
    { icon:"💧", color:C.green,  title:"GRDC 实测流量站数据",
      desc:"注册GRDC，获取纳伦河/锡尔河长序列实测径流数据，作为跨境流量估算的校验基准。" },
    { icon:"🌍", color:C.orange, title:"扩展至阿姆河流域（方向3）",
      desc:"下载塔吉克/乌兹别克OSM数据，建立阿姆河+咸海流域水量监测，支援中亚国家水利规划。" },
  ];

  nextSteps.forEach((ns, i) => {
    const y = 1.0 + i * 1.58;
    s.addShape(pres.shapes.RECTANGLE, { x:0.4, y, w:6.3, h:1.45, fill:{ color:C.panel }, line:{ color:ns.color, width:0.5 }, shadow:makeShadow() });
    s.addShape(pres.shapes.OVAL, { x:0.55, y:y+0.12, w:0.45, h:0.45, fill:{ color:ns.color, transparency:75 }, line:{ color:ns.color, width:0.5 } });
    s.addText(ns.icon, { x:0.55, y:y+0.12, w:0.45, h:0.45, fontSize:14, align:"center", valign:"middle", margin:0 });
    s.addText(ns.title, { x:1.1, y:y+0.12, w:5.5, h:0.35, fontSize:11.5, bold:true, color:ns.color, margin:0 });
    s.addText(ns.desc, { x:0.55, y:y+0.52, w:6.0, h:0.8, fontSize:9.5, fontFace:"Microsoft YaHei", color:C.txt2, margin:0, valign:"top" });
  });

  // 右侧：结语
  s.addText("结语", {
    x:7.3, y:0.25, w:5.7, h:0.52, fontSize:22, bold:true, color:C.white, margin:0
  });
  s.addShape(pres.shapes.LINE, { x:7.3, y:0.82, w:5.5, h:0, line:{ color:C.border, width:0.75 } });

  // 圆形装饰
  for (let [r, t] of [[3.2,90],[2.5,88],[1.8,85],[1.1,75]]) {
    s.addShape(pres.shapes.OVAL, {
      x: 9.3+2.5-r, y: 3.5-r, w:r*2, h:r*2,
      fill:{ color:C.cyan, transparency:t },
      line:{ color:C.cyan, transparency:85, width:0.5 }
    });
  }

  s.addText([
    { text:"本项目建立了\n", options:{ fontSize:14, color:C.txt2, breakLine:false } },
    { text:"中亚跨境水资源\n综合分析平台", options:{ fontSize:20, bold:true, color:C.white, breakLine:true } },
  ], { x:7.3, y:1.1, w:5.7, h:1.4, fontFace:"Microsoft YaHei", margin:0, align:"center" });

  const achievements = [
    [C.cyan,   "8年", "卫星遥感监测序列"],
    [C.red,    "45年", "ERA5气候实测"],
    [C.blue,   "47年", "GPCP降水数据"],
    [C.orange, "7条", "主干河流矢量化"],
  ];

  achievements.forEach(([color, num, label], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 7.3 + col * 2.9, y = 2.75 + row * 1.15;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w:2.7, h:0.95, fill:{ color:C.panel }, line:{ color:color, width:0.5 } });
    s.addText(num, { x, y:y+0.05, w:2.7, h:0.5, fontSize:22, bold:true, color:color, align:"center", margin:0 });
    s.addText(label, { x, y:y+0.55, w:2.7, h:0.3, fontSize:9, color:C.txt2, align:"center", margin:0 });
  });

  // 联系方式
  s.addShape(pres.shapes.RECTANGLE, {
    x:7.3, y:5.05, w:5.7, h:2.35,
    fill:{ color:"0A1F2E" }, line:{ color:C.border, width:0.75 }
  });
  const summaryLines = [
    { text:"数据驱动  ·  可追溯  ·  持续更新\n", options:{ bold:true, fontSize:13, color:C.cyan, breakLine:false } },
    { text:"平台以单一 HTML 文件交付，离线可用，\n", options:{ fontSize:11, color:C.txt, breakLine:false } },
    { text:"数据层随新气候数据自动升级精度，\n", options:{ fontSize:11, color:C.txt, breakLine:false } },
    { text:"可作为对外合作的技术展示与谈判依据。", options:{ fontSize:11, color:C.txt } },
  ];
  s.addText(summaryLines, { x:7.45, y:5.2, w:5.4, h:2.0, fontFace:"Microsoft YaHei", margin:0, valign:"top" });
}

// ══════════════════════════════════════════════════════════════════════════
// 输出
// ══════════════════════════════════════════════════════════════════════════
const OUT = path.join(__dirname, "..", "output", "中亚跨境水资源综合分析平台.pptx");
pres.writeFile({ fileName: OUT }).then(() => {
  console.log(`✅ PPT 生成完成: ${OUT}`);
}).catch(err => {
  console.error("❌ 生成失败:", err);
});

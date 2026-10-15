// 登入頁背景圖（v1.46.2 起，v1.46.3 改版）
//
// 畫面元素：
//   - 中藥：以人參為中心，502 種中藥以葉序螺旋排列圍繞（TCMSP 收錄的藥材數），外圈標出幾味常用藥
//   - DNA 暗黑基因檢測：雙股螺旋，掃描框掃過時 OncoKB 癌症基因（平台稱「暗黑基因」）依序亮起
//   - AI 整合分析：中央核心，七個國際資料庫環繞
//   - 標語：七大國際資料庫整合 → 找出疾病靶點 → 篩選中藥成分 → 抑制靶點蛋白
//     並以動畫呈現：成分分子從中藥群飛向靶點蛋白，蛋白被抑制
//   - 底部：分析鏈路與科研用途聲明
//
// 為什麼用程式畫 SVG 而不是放一張圖片：
//   1. 依瀏覽器實際尺寸重新排版（寬螢幕：圖在左、登入卡在右；直式／手機：圖在上、卡在下）
//   2. 文字是真的文字，跟著登入頁語系（英／繁／簡／韓）轉換
//   3. 沒有外部檔案，不會因為圖檔沒部署而破圖
// 所有圖形都是自繪幾何線條，沒有使用任何外部素材。
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const C = {
    jade: "#7fd1a8", gold: "#e2b866", cyan: "#6cc6e0", coral: "#ef8a7a",
    text: "#e9f3ee", muted: "rgba(233,243,238,.62)", faint: "rgba(233,243,238,.45)",
  };
  // 七個資料庫：名稱、在平台裡的角色、顏色（金＝中藥，青＝分子與蛋白，綠＝通路，珊瑚＝腫瘤）
  const DBS = [
    ["TCMSP", "中藥系統藥理", C.gold],
    ["PubChem", "化合物結構", C.cyan],
    ["UniProt", "蛋白靶點標準化", C.cyan],
    ["KEGG", "訊號通路", C.jade],
    ["Reactome", "生物反應路徑", C.jade],
    ["OncoKB", "癌症基因知識庫", C.coral],
    ["DepMap", "腫瘤細胞株依賴", C.coral],
  ];
  const HERB_COUNT = 502;                       // TCMSP 收錄、平台上架的藥材數
  const HERB_NAMES = ["黃芪", "當歸", "甘草", "丹參", "黃連", "枸杞子", "川芎", "茯苓"];
  // 暗黑基因（OncoKB 癌症基因）中常見、平台實際比對得到的幾個
  const DARK_GENES = ["TP53", "EGFR", "BCL2", "KRAS", "PIK3CA", "PTEN"];
  const TAGLINE = ["七大國際資料庫整合", "找出疾病靶點", "篩選中藥成分", "抑制靶點蛋白"];
  const CHAIN = ["中藥", "成分", "靶點", "疾病", "腫瘤細胞"];
  const SCAN_SECONDS = 9;                       // 暗黑基因掃描一輪的秒數
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const t = (s) => (window.loginT ? window.loginT(s) : s);
  const el = (name, attrs, parent) => {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  };
  const text = (parent, x, y, s, attrs) => {
    const n = el("text", Object.assign({ x, y }, attrs || {}), parent);
    n.textContent = t(s);
    return n;
  };
  // 粗估文字寬度（中日韓字約 1 em，其餘約 0.56 em），用來決定標語要不要拆兩行
  const textWidth = (s, fs) => [...s].reduce((a, ch) => a + (/[　-鿿가-힯]/.test(ch) ? fs : fs * 0.56), 0);

  // ---------------- 版面：依視窗尺寸決定 ----------------
  function layout(w, h) {
    // 橫拿的手機（例如 844×390）也左右並排；但寬度要夠放登入卡（340px）再加一個看得清楚的圖
    const wide = (w >= 900 || (w >= 760 && h < 520)) && w / h >= 1.15;
    if (wide) {
      // 登入卡固定 340px 寬，右側保留區至少要放得下它
      const pad = Math.max(32, w * 0.04);
      const cardZone = Math.max(340 + pad + 24, Math.min(460, w * 0.36) + pad);
      const artW = w - cardZone;
      const short = h < 560;
      const helixX = Math.max(30, artW * 0.055);
      const top = short ? 54 : Math.max(70, h * 0.11);           // 標語下緣
      const bottom = h - 46;                                       // 鏈路上緣
      const R = Math.max(70, Math.min(artW * 0.2, (bottom - top) * 0.34));
      const cx = artW - R - 64;                                     // 環圈靠右，左邊留給中藥群
      const cy = top + (bottom - top) * 0.5;
      // 矮螢幕（橫拿手機）寬度不夠：暗黑基因標籤直接疊在螺旋上，不另佔一欄
      const gx0 = helixX + (short ? 50 : 120);
      // 中藥群右緣＋藥名標籤（約 50px）不能碰到環圈左側的資料庫標籤；空間不夠就不放藥名
      const names = !short && (cx - R - 120 - gx0) / 2 >= 55;
      const Rg = Math.max(short ? 42 : 50, Math.min((cx - R - (names ? 120 : 70) - gx0) / 2, (bottom - top) * 0.36));
      return { mode: "wide", w, h, artW, cx, cy, R, short,
        helix: { x: helixX, vertical: true, inline: short },
        galaxy: { x: gx0 + Rg + (names ? 46 : 0), y: cy + (bottom - top) * 0.04, R: Rg, names,
          caption: names ? "以人參為中心・502 種中藥" : "502 種中藥", capAbove: false },
        protein: { x: cx + R * 0.98, y: Math.min(bottom - 30, cy + R * 1.08) },
        tagline: { x: (helixX + 40 + artW) / 2, y: short ? 26 : Math.max(34, h * 0.055), maxW: artW - helixX - 80 },
        chain: { x: cx, y: h - 18 } };
    }
    // 直式或窄螢幕：圖放在上方一條帶狀區，登入卡從帶狀區下緣開始
    const band = Math.max(330, Math.min(h * 0.52, w * 1.1, 480));
    const tagH = 40;                                              // 帶狀區最下面兩行標語
    const R = Math.max(70, Math.min(w * 0.27, (band - tagH - 70) * 0.34));
    const cx = w * 0.6, cy = 58 + (band - tagH - 58) * 0.47;
    return { mode: "portrait", w, h, cx, cy, R, band,
      helix: { y: 16, vertical: false },
      // 左側一欄（資料庫環圈左邊的空位）
      galaxy: { x: Math.max(40, w * 0.12), y: cy - R * 0.1, R: Math.max(30, Math.min(44, w * 0.11)), names: false,
        caption: "502 種中藥", capAbove: false },
      protein: null,
      tagline: { x: w / 2, y: band - tagH + 4, maxW: w - 24 },
      chain: { x: w / 2, y: h - 18 } };
  }

  // ---------------- 各元素 ----------------
  function defs(svg) {
    const d = el("defs", {}, svg);
    const bg = el("linearGradient", { id: "lbgBg", x1: "0", y1: "0", x2: "1", y2: "1" }, d);
    el("stop", { offset: "0", "stop-color": "#0d261c" }, bg);
    el("stop", { offset: ".55", "stop-color": "#16402d" }, bg);
    el("stop", { offset: "1", "stop-color": "#1f4f37" }, bg);
    [["lbgGlow", C.cyan, ".30"], ["lbgHerbGlow", C.gold, ".22"], ["lbgHot", C.coral, ".55"]].forEach(([id, c, o]) => {
      const g = el("radialGradient", { id }, d);
      el("stop", { offset: "0", "stop-color": c, "stop-opacity": o }, g);
      el("stop", { offset: "1", "stop-color": c, "stop-opacity": "0" }, g);
    });
    const dots = el("pattern", { id: "lbgDots", width: "26", height: "26", patternUnits: "userSpaceOnUse" }, d);
    el("circle", { cx: "2", cy: "2", r: "1", fill: "rgba(233,243,238,.07)" }, dots);
  }

  // DNA 雙股螺旋＋暗黑基因檢測
  function helix(g, L) {
    const { w, h } = L;
    const grp = el("g", { class: "lbg-helix" }, g);
    const vertical = L.helix.vertical;
    const amp = vertical ? Math.min(28, w * 0.02) : 10;
    const period = vertical ? 150 : 90;
    const len = vertical ? h : w;
    const pt = (s, phase) => {
      const off = Math.sin((s / period) * 2 * Math.PI + phase) * amp;
      return vertical ? [L.helix.x + off, s] : [s, L.helix.y + off];
    };
    const path = (phase) => {
      let d = "";
      for (let s = -10; s <= len + 10; s += 6) {
        const [x, y] = pt(s, phase);
        d += (d ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }
      return d;
    };
    const baseColors = [C.coral, C.gold, C.cyan, C.jade];
    let k = 0;
    for (let s = 0; s <= len; s += period / 6) {
      const [x1, y1] = pt(s, 0), [x2, y2] = pt(s, Math.PI);
      el("line", { x1, y1, x2, y2, stroke: baseColors[k++ % 4], "stroke-width": "2", "stroke-opacity": ".5", "stroke-linecap": "round" }, grp);
    }
    el("path", { d: path(0), fill: "none", stroke: C.coral, "stroke-width": "2.4", "stroke-opacity": ".85" }, grp);
    el("path", { d: path(Math.PI), fill: "none", stroke: C.cyan, "stroke-width": "2.4", "stroke-opacity": ".85" }, grp);

    // 標籤：「暗黑基因檢測」＋「DNA 定序掃描中」
    const lab = el("g", {}, grp);
    const lx = vertical ? L.helix.x + amp + 14 : 12;
    const ly = vertical ? (L.short ? 70 : Math.max(96, h * 0.15)) : L.helix.y + amp + 18;
    text(lab, lx, ly, "暗黑基因檢測", { fill: C.coral, "font-size": vertical ? 15 : 12, "font-weight": 800 });
    if (vertical) text(lab, lx, ly + 17, "DNA 定序掃描中…", { "font-size": 11, fill: C.muted, class: "lbg-blink" });

    // 掃描框：一輪 SCAN_SECONDS 秒，從頭掃到尾；掃到基因位置時那個基因亮起
    const box = vertical
      ? { x: L.helix.x - amp - 8, y: -60, width: (amp + 8) * 2, height: 60 }
      : { x: -50, y: L.helix.y - amp - 6, width: 50, height: (amp + 6) * 2 };
    el("rect", Object.assign({ class: "lbg-scan " + (vertical ? "lbg-scan-v" : "lbg-scan-h"), rx: 6,
      fill: "rgba(239,138,122,.10)", stroke: C.coral, "stroke-opacity": ".8", "stroke-dasharray": "4 4",
      style: `--scan-dist:${len + 60}px;animation-duration:${SCAN_SECONDS}s` }, box), grp);

    // 暗黑基因：沿螺旋分布，各自在掃描框經過時亮起
    // 從標籤下方開始排，免得第一個基因壓到「暗黑基因檢測」字樣
    const n = DARK_GENES.length;
    const s0 = vertical ? Math.max(len * 0.22, ly + 42) : len * 0.3, s1 = len * 0.92;
    DARK_GENES.forEach((gene, i) => {
      const s = s0 + (s1 - s0) * (i / (n - 1));
      const [x, y] = pt(s, 0), [x2, y2] = pt(s, Math.PI);
      const mx = (x + x2) / 2, my = (y + y2) / 2;
      const delay = -SCAN_SECONDS + ((s + 30) / (len + 60)) * SCAN_SECONDS;   // 與掃描框同步
      const hit = el("g", { class: "lbg-gene", style: `animation-duration:${SCAN_SECONDS}s;animation-delay:${delay.toFixed(2)}s` }, grp);
      el("circle", { cx: mx, cy: my, r: vertical && !L.helix.inline ? 26 : 16, fill: "url(#lbgHot)" }, hit);
      el("line", { x1: x, y1: y, x2, y2, stroke: "#fff", "stroke-width": 3, "stroke-linecap": "round" }, hit);
      if (vertical && !L.helix.inline) {
        const tx = L.helix.x + amp + 14;
        el("line", { x1: Math.max(x, x2) + 2, y1: my, x2: tx - 4, y2: my, stroke: C.coral, "stroke-width": 1, "stroke-dasharray": "2 3" }, hit);
        const chipW = textWidth(gene, 12) + 16;
        el("rect", { x: tx, y: my - 10, width: chipW, height: 20, rx: 10, fill: "rgba(239,138,122,.18)", stroke: C.coral }, hit);
        const tt = el("text", { x: tx + chipW / 2, y: my + 4, "text-anchor": "middle", "font-size": 12, "font-weight": 700, fill: "#fff",
          "font-family": "ui-monospace, Menlo, Consolas, monospace" }, hit);
        tt.textContent = gene;
      } else {
        const tt = el("text", { x: mx, y: my + 4, "text-anchor": "middle", "font-size": 10.5, "font-weight": 800, fill: "#fff",
          "font-family": "ui-monospace, Menlo, Consolas, monospace", stroke: "#0d261c", "stroke-width": 3, "paint-order": "stroke" }, hit);
        tt.textContent = gene;
      }
    });
  }

  // 人參全株（局部座標：地面在 y=-78，葉頂約 y=-230，根鬚到 y=+12）
  function ginseng(parent, x, y, s) {
    const grp = el("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(3)})`, class: "lbg-herb" }, parent);
    const stroke = { fill: "none", stroke: C.jade, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" };
    el("path", Object.assign({ d: "M-46 -78 L46 -78", "stroke-dasharray": "3 6", "stroke-opacity": ".45" }, stroke), grp);
    el("path", { d: "M-6 -78 C-14 -60 -16 -42 -10 -24 C-6 -12 -14 -4 -22 4 M-10 -24 C-2 -14 6 -8 14 2 M-12 -50 C-26 -46 -36 -40 -44 -30 M-8 -40 C6 -40 16 -36 26 -28",
      fill: "none", stroke: C.gold, "stroke-width": 2.6, "stroke-linecap": "round" }, grp);
    el("path", { d: "M-6 -78 C-1 -60 1 -42 -4 -26 C-8 -38 -12 -56 -6 -78 Z", fill: C.gold, "fill-opacity": ".4" }, grp);
    el("path", { d: "M-22 4 l-6 8 M-22 4 l2 10 M14 2 l6 8 M14 2 l-2 10 M-44 -30 l-8 4 M26 -28 l8 3",
      fill: "none", stroke: C.gold, "stroke-width": 1.2, "stroke-opacity": ".7", "stroke-linecap": "round" }, grp);
    el("path", Object.assign({ d: "M-6 -78 C-4 -120 2 -160 0 -205", "stroke-width": 2.4 }, stroke), grp);
    const leafSet = (rot) => {
      const lg = el("g", { transform: `translate(0 -205) rotate(${rot})` }, grp);
      el("path", Object.assign({ d: "M0 0 L0 -26" }, stroke), lg);
      [-62, -30, 0, 30, 62].forEach((a, i) => {
        const len = i === 2 ? 46 : (i === 1 || i === 3 ? 40 : 30);
        el("path", { d: `M0 -26 C-9 ${-26 - len * 0.4} -6 ${-26 - len * 0.85} 0 ${-26 - len} C6 ${-26 - len * 0.85} 9 ${-26 - len * 0.4} 0 -26 Z`,
          transform: `rotate(${a} 0 -26)`, fill: C.jade, "fill-opacity": ".28", stroke: C.jade, "stroke-width": 1.5 }, lg);
      });
    };
    leafSet(-48); leafSet(48); leafSet(0);
    [[0, -214], [-6, -220], [6, -220], [0, -227], [-4, -211], [5, -210]].forEach(([bx, by]) =>
      el("circle", { cx: bx, cy: by - 2, r: 4.4, fill: C.coral, "fill-opacity": ".95" }, grp));
    return grp;
  }

  // 502 種中藥：以人參為中心的葉序螺旋（黃金角 137.5°，看起來像自然生長，不會排成直線）
  function herbGalaxy(g, L) {
    const { x: gx, y: gy, R: Rg } = L.galaxy;
    const grp = el("g", { class: "lbg-galaxy" }, g);
    el("circle", { cx: gx, cy: gy, r: Rg * 1.15, fill: "url(#lbgHerbGlow)" }, grp);
    const r0 = Rg * 0.48;
    const cols = [C.gold, C.jade, "#d8e6a0", C.gold, C.jade];
    const dots = el("g", { class: "lbg-herb-dots" }, grp);
    for (let i = 0; i < HERB_COUNT; i++) {
      const f = i / (HERB_COUNT - 1);
      const r = r0 + (Rg - r0) * Math.sqrt(f);
      const a = i * 2.399963;
      const big = i % 23 === 0;
      const tw = i % 11 === 0;
      el("circle", { cx: (gx + r * Math.cos(a)).toFixed(1), cy: (gy + r * Math.sin(a)).toFixed(1),
        r: big ? 2.6 : (Rg > 90 ? 1.7 : 1.3), fill: cols[i % 5], "fill-opacity": big ? ".95" : ".55",
        class: tw ? "lbg-twinkle" : null, style: tw ? `animation-delay:${(-(i % 7) * 0.6).toFixed(1)}s` : null }, dots);
    }
    // 中心的人參：整株高度約等於內圈直徑，植株中心對準螺旋中心
    const s = (r0 * 2.1) / 242;
    ginseng(grp, gx, gy + 109 * s, s);
    // 外圈幾味常用藥（寬螢幕才放，避免手機上擠成一團）
    if (L.galaxy.names) {
      HERB_NAMES.forEach((name, i) => {
        const a = (-112 + i * (360 / HERB_NAMES.length)) * Math.PI / 180;
        const x = gx + (Rg + 12) * Math.cos(a), y = gy + (Rg + 12) * Math.sin(a);
        el("circle", { cx: gx + Rg * Math.cos(a), cy: gy + Rg * Math.sin(a), r: 3, fill: C.gold }, grp);
        text(grp, x, y + 4, name, { fill: C.text, "fill-opacity": ".8", "font-size": 11.5, "text-anchor": Math.cos(a) >= 0 ? "start" : "end" });
      });
    }
    const capY = L.galaxy.capAbove ? gy - Rg - 10 : gy + Rg + (L.galaxy.names ? 40 : 16);
    text(grp, gx, capY, L.galaxy.caption, { fill: C.gold, "font-size": L.mode === "wide" ? 13 : 10.5, "font-weight": 700, "text-anchor": "middle" });
  }

  function aiHub(g, L) {
    const { cx, cy, R } = L;
    const hr = R * 0.34;
    el("circle", { cx, cy, r: hr * 2.1, fill: "url(#lbgGlow)" }, g);
    el("circle", { cx, cy, r: hr, fill: "rgba(13,38,28,.88)", stroke: C.cyan, "stroke-width": 1.6 }, g);
    el("circle", { class: "lbg-pulse", cx, cy, r: hr, fill: "none", stroke: C.cyan, "stroke-width": 1.2 }, g);
    // 小圓（手機）時「AI」字與說明放在圓外下方，圓內只畫神經網路，避免文字壓在節點上
    const compact = hr < 48;
    const layers = [3, 4, 3], nodes = [];
    const span = hr * 0.95;
    const netCy = compact ? cy : cy - hr * 0.2;
    const step = compact ? hr * 0.36 : hr * 0.26;
    layers.forEach((n, li) => {
      const x = cx - span * 0.55 + li * span * 0.55;
      nodes.push([...Array(n)].map((_, j) => [x, netCy + (j - (n - 1) / 2) * step]));
    });
    const net = el("g", { class: "lbg-net" }, g);
    for (let li = 0; li < 2; li++) nodes[li].forEach(([x1, y1]) => nodes[li + 1].forEach(([x2, y2]) =>
      el("line", { x1, y1, x2, y2, stroke: C.cyan, "stroke-opacity": ".35", "stroke-width": 1 }, net)));
    nodes.flat().forEach(([x, y], i) => el("circle", { cx: x, cy: y, r: Math.max(2.6, hr * 0.045),
      fill: i % 3 === 0 ? C.gold : C.cyan, class: "lbg-node" }, net));
    if (compact) {
      text(g, cx, cy + hr + 14, "AI 整合分析", { fill: C.text, "font-size": 10.5, "font-weight": 700, "text-anchor": "middle" });
    } else {
      text(g, cx, cy + hr * 0.62, "AI", { fill: C.text, "font-size": hr * 0.3, "font-weight": 800, "text-anchor": "middle", "letter-spacing": "2" });
      text(g, cx, cy + hr * 0.62 + Math.max(14, hr * 0.2), "AI 整合分析", { fill: C.muted, "font-size": Math.max(10, hr * 0.12), "text-anchor": "middle" });
    }
  }

  function databases(g, L) {
    const { cx, cy, R } = L;
    el("circle", { cx, cy, r: R, fill: "none", stroke: "rgba(233,243,238,.18)", "stroke-dasharray": "2 7" }, g);
    const pts = DBS.map((_, i) => {
      const a = (-90 + i * 360 / DBS.length) * Math.PI / 180;
      return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    });
    el("polygon", { points: pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: "none", stroke: "rgba(233,243,238,.10)" }, g);
    const fs = Math.max(10.5, Math.min(15, R * 0.075));
    pts.forEach(([x, y], i) => {
      const [name, role, color] = DBS[i];
      el("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: color, "stroke-opacity": ".55", "stroke-width": 1.4,
        "stroke-dasharray": "3 9", class: "lbg-flow", style: `animation-delay:${(-i * 0.35).toFixed(2)}s` }, g);
      const pw = name.length * fs * 0.62 + 20, ph = fs + 11;
      el("rect", { class: "lbg-db", x: x - pw / 2, y: y - ph / 2, width: pw, height: ph, rx: ph / 2, fill: "rgba(13,38,28,.92)", stroke: color, "stroke-width": 1.6 }, g);
      text(g, x, y + fs * 0.36, name, { fill: C.text, "font-size": fs, "font-weight": 700, "text-anchor": "middle" });
      const below = y >= cy - R * 0.2;
      text(g, x, below ? y + ph / 2 + fs * 0.95 : y - ph / 2 - fs * 0.45, role,
        { fill: C.muted, "font-size": Math.max(9.5, fs * 0.74), "text-anchor": "middle" });
    });
  }

  // 標語：四步流程，放不下一行就拆兩行
  function tagline(g, L) {
    const { x, y, maxW } = L.tagline;
    const fs = L.mode === "wide" ? (L.short ? 13 : 15) : 11;
    const words = TAGLINE.map(t);
    const colors = [C.jade, C.coral, C.gold, C.cyan];
    const lines = textWidth(words.join(" → "), fs) + 40 <= maxW ? [[0, 1, 2, 3]] : [[0, 1], [2, 3]];
    lines.forEach((idxs, li) => {
      const tl = el("text", { x, y: y + li * (fs + 7), "text-anchor": "middle", "font-size": fs, "font-weight": 700 }, g);
      idxs.forEach((idx, i) => {
        if (idx > 0) { const a = el("tspan", { fill: C.faint, dx: i ? "6" : "0" }, tl); a.textContent = "→"; }
        const s = el("tspan", { dx: idx > 0 ? "6" : "0", fill: colors[idx] }, tl);
        s.textContent = words[idx];
      });
    });
  }

  // 成分分子從中藥群飛向靶點蛋白，蛋白被抑制（寬螢幕才有，手機上空間不夠）
  function inhibition(g, L) {
    if (!L.protein) return;
    const { x: px, y: py } = L.protein;
    const { x: gx, y: gy, R: Rg } = L.galaxy;
    const grp = el("g", { class: "lbg-inhibit" }, g);
    const sx = gx + Rg * 0.7, sy = gy + Rg * 0.35;
    const d = `M${sx.toFixed(1)} ${sy.toFixed(1)} Q${((sx + px) / 2).toFixed(1)} ${(Math.max(sy, py) + L.R * 0.55).toFixed(1)} ${(px - 26).toFixed(1)} ${py.toFixed(1)}`;
    el("path", { id: "lbgDrugPath", d, fill: "none", stroke: C.gold, "stroke-opacity": ".22", "stroke-dasharray": "2 6" }, grp);
    if (!reduceMotion) {
      [0, 1.3, 2.6].forEach((b) => {
        const m = el("g", {}, grp);
        // 小分子：六角環
        el("polygon", { points: [...Array(6)].map((_, k) => `${(5 * Math.cos(k * Math.PI / 3)).toFixed(1)},${(5 * Math.sin(k * Math.PI / 3)).toFixed(1)}`).join(" "),
          fill: "rgba(226,184,102,.35)", stroke: C.gold, "stroke-width": 1.4 }, m);
        const am = el("animateMotion", { dur: "3.9s", begin: `${b}s`, repeatCount: "indefinite", rotate: "auto" }, m);
        el("mpath", { href: "#lbgDrugPath" }, am);
      });
    }
    // 靶點蛋白：幾顆球組成的團塊；被抑制時變暗並出現 ✕
    const prot = el("g", { class: "lbg-protein" }, grp);
    [[0, 0, 15], [-13, -8, 10], [12, -10, 11], [-9, 11, 9], [12, 10, 9]].forEach(([dx, dy, r]) =>
      el("circle", { cx: px + dx, cy: py + dy, r, fill: "rgba(239,138,122,.35)", stroke: C.coral, "stroke-width": 1.4 }, prot));
    const x = el("g", { class: "lbg-block" }, grp);
    el("circle", { cx: px, cy: py, r: 24, fill: "none", stroke: "#fff", "stroke-width": 2 }, x);
    el("path", { d: `M${px - 11} ${py - 11} L${px + 11} ${py + 11} M${px + 11} ${py - 11} L${px - 11} ${py + 11}`, stroke: "#fff", "stroke-width": 2.6, "stroke-linecap": "round" }, x);
    text(grp, px, py + 40, "抑制靶點蛋白", { fill: C.coral, "font-size": 12, "font-weight": 700, "text-anchor": "middle" });
  }

  function chain(g, L) {
    if (L.mode === "portrait") {
      // 登入卡下方還有空間才畫（卡片位置由 CSS 決定，這裡量實際位置）
      const card = document.querySelector(".login-card");
      const bottom = card ? card.getBoundingClientRect().bottom + window.scrollY : L.h;
      if (L.h - bottom < 46) return;
    }
    const fs = L.mode === "wide" ? 12.5 : 11;
    const grp = el("g", {}, g);
    const t1 = el("text", { x: L.chain.x, y: L.chain.y - 18, "text-anchor": "middle", "font-size": fs, fill: C.muted }, grp);
    CHAIN.forEach((w, i) => {
      if (i) { const a = el("tspan", { fill: C.jade, dx: "4" }, t1); a.textContent = "→"; }
      const s = el("tspan", { fill: C.text, dx: i ? "4" : "0" }, t1);
      s.textContent = t(w);
    });
    text(grp, L.chain.x, L.chain.y, "科研輔助工具，不作為醫療診斷或治療建議", { fill: C.faint, "font-size": L.mode === "wide" ? 11 : 10, "text-anchor": "middle" });
  }

  // ---------------- 組裝 ----------------
  let last = "";
  function render() {
    const host = document.getElementById("loginBg");
    if (!host) return;
    // 不要對尺寸設下限：設了 viewBox 就會跟視窗比例不符，圖會被裁掉
    const w = Math.max(1, window.innerWidth), h = Math.max(1, window.innerHeight);
    const key = w + "x" + h;
    if (key === last) return;
    last = key;
    const L = layout(w, h);
    document.body.classList.toggle("login-wide", L.mode === "wide");
    document.body.classList.toggle("login-portrait", L.mode === "portrait");
    document.documentElement.style.setProperty("--login-art-band", (L.band || 0) + "px");

    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, width: "100%", height: "100%", preserveAspectRatio: "xMidYMid slice",
      "aria-hidden": "true", focusable: "false", role: "presentation",
      "font-family": "'Noto Sans TC','PingFang TC','Microsoft JhengHei',system-ui,sans-serif" });
    defs(svg);
    el("rect", { width: w, height: h, fill: "url(#lbgBg)" }, svg);
    el("rect", { width: w, height: h, fill: "url(#lbgDots)" }, svg);
    const g = el("g", { class: "lbg-art" }, svg);
    herbGalaxy(g, L);
    inhibition(g, L);
    databases(g, L);
    aiHub(g, L);
    helix(g, L);
    tagline(g, L);
    chain(g, L);
    host.replaceChildren(svg);
  }

  let timer = null;
  const schedule = () => { clearTimeout(timer); timer = setTimeout(render, 120); };
  window.addEventListener("resize", schedule);
  window.addEventListener("orientationchange", schedule);
  window.renderLoginBackground = () => { last = ""; render(); };
  render();
})();

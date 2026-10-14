// 登入頁背景圖（v1.46.2）
//
// 畫面元素：中藥（人參全株＋葉枝）、AI 整合分析（中心的神經網路）、DNA 基因檢測（雙股螺旋）、
// 七個整合的國際資料庫（環繞 AI 的七個節點），以及底部的分析鏈路與科研用途聲明。
//
// 為什麼用程式畫 SVG 而不是放一張圖片：
//   1. 依瀏覽器實際尺寸重新排版（寬螢幕：圖在左、登入卡在右；直式／手機：圖在上、卡在下），
//      一張固定比例的圖片只能裁切或變形
//   2. 文字是真的文字，會跟著登入頁語系（英／繁／簡／韓）轉換
//   3. 沒有外部檔案，不會因為圖檔沒部署到 Cloudflare 而破圖
//
// 所有圖形都是自繪的幾何線條，沒有使用任何外部素材。
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const C = {
    jade: "#7fd1a8", gold: "#e2b866", cyan: "#6cc6e0", coral: "#ef8a7a",
    text: "#e9f3ee", muted: "rgba(233,243,238,.62)",
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
  const CHAIN = ["中藥", "成分", "靶點", "疾病", "腫瘤細胞"];

  const t = (s) => (window.loginT ? window.loginT(s) : s);
  const el = (name, attrs, parent) => {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  };
  const text = (parent, x, y, s, attrs) => {
    const n = el("text", Object.assign({ x, y }, attrs || {}), parent);
    n.textContent = t(s);
    return n;
  };

  // 直式版面左下角人參的位置：OncoKB 與 Reactome 之間的空隙中點
  function cxPortraitLeft(w, band) {
    const R = Math.max(76, Math.min(w * 0.34, band * 0.34, (band * 0.42 - 30) / 0.9));
    return Math.min(w / 2 - R * 0.43 - 62, w * 0.12);
  }

  // ---------------- 版面：依視窗尺寸決定 ----------------
  function layout(w, h) {
    // 橫拿的手機（例如 844×390）高度不夠放上下兩段，也用左右並排；
    // 但寬度要夠放登入卡（340px）再加一個看得清楚的圖，再窄（例如 667×375）就上下排、頁面往下捲
    const wide = (w >= 900 || (w >= 760 && h < 520)) && w / h >= 1.15;
    if (wide) {
      // 登入卡固定 340px 寬，右側保留區至少要放得下它，否則七個資料庫會被卡片蓋住
      const pad = Math.max(32, w * 0.04);
      const cardZone = Math.max(340 + pad + 24, Math.min(460, w * 0.36) + pad);
      const artW = w - cardZone;
      const R = Math.max(h < 520 ? 80 : 110, Math.min(artW * 0.3, h * 0.31));
      return { mode: "wide", w, h, cx: artW * 0.54, cy: h * 0.47, R,
        helix: { x: Math.max(34, artW * 0.07), vertical: true },
        // 人參放在螺旋右邊，留出根鬚的寬度，不要壓到螺旋；
        // 矮螢幕（橫拿手機）環圈幾乎佔滿高度，人參改放右下角、標籤朝左
        herb: h < 560
          ? { x: artW * 0.93, y: h - 26, s: Math.min(1.25, h / 760), label: "left" }
          : { x: Math.max(Math.max(34, artW * 0.07) + 110, artW * 0.17), y: h - 26, s: Math.min(1.25, h / 760), label: "right" },
        sprig: { x: artW * 0.9, y: h * 0.13, s: Math.min(1.1, h / 820) },
        chainY: h - 26, chainX: artW * 0.54, band: 0 };
    }
    // 直式或窄螢幕：圖放在上方一條帶狀區，登入卡從帶狀區下緣開始
    // 直式版面空間小：螺旋貼頂、標題省略（七個節點本身就說明了），人參縮小放右下角，
    // 分析鏈路與聲明改放在視窗最底部（被登入卡蓋住時就不畫）
    const band = Math.max(250, Math.min(h * 0.42, w * 0.95, 420));
    // 下半圈節點的說明文字要落在帶狀區內（登入卡從帶狀區下緣開始）
    const R = Math.max(76, Math.min(w * 0.34, band * 0.34, (band * 0.42 - 30) / 0.9));
    return { mode: "portrait", w, h, cx: w / 2, cy: band * 0.58, R,
      helix: { y: 18, vertical: false },
      // 左下角：OncoKB 說明文字下方、Reactome 左邊的空位
      herb: { x: Math.max(24, cxPortraitLeft(w, band)), y: band - 8, s: Math.min(0.3, band / 1100), label: "low" },
      sprig: { x: w - Math.max(30, w * 0.08), y: band * 0.13, s: Math.min(0.5, band / 700) },
      chainY: h - 30, chainX: w / 2, band };
  }

  // ---------------- 各元素 ----------------
  function defs(svg) {
    const d = el("defs", {}, svg);
    const bg = el("linearGradient", { id: "lbgBg", x1: "0", y1: "0", x2: "1", y2: "1" }, d);
    el("stop", { offset: "0", "stop-color": "#0d261c" }, bg);
    el("stop", { offset: ".55", "stop-color": "#16402d" }, bg);
    el("stop", { offset: "1", "stop-color": "#1f4f37" }, bg);
    const glow = el("radialGradient", { id: "lbgGlow" }, d);
    el("stop", { offset: "0", "stop-color": C.cyan, "stop-opacity": ".32" }, glow);
    el("stop", { offset: "1", "stop-color": C.cyan, "stop-opacity": "0" }, glow);
    const dots = el("pattern", { id: "lbgDots", width: "26", height: "26", patternUnits: "userSpaceOnUse" }, d);
    el("circle", { cx: "2", cy: "2", r: "1", fill: "rgba(233,243,238,.07)" }, dots);
  }

  function helix(g, L) {
    const { w, h } = L;
    const grp = el("g", { class: "lbg-helix" }, g);
    const amp = L.mode === "wide" ? Math.min(30, w * 0.022) : 13;
    const period = L.mode === "wide" ? 150 : 96;
    const len = L.mode === "wide" ? h : w;
    const pt = (s, phase) => {
      const off = Math.sin((s / period) * 2 * Math.PI + phase) * amp;
      return L.helix.vertical ? [L.helix.x + off, s] : [s, L.helix.y + off];
    };
    const path = (phase) => {
      let d = "";
      for (let s = -10; s <= len + 10; s += 6) {
        const [x, y] = pt(s, phase);
        d += (d ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }
      return d;
    };
    // 鹼基對橫桿：四種鹼基四種顏色
    const baseColors = [C.coral, C.gold, C.cyan, C.jade];
    let k = 0;
    for (let s = 0; s <= len; s += period / 6) {
      const [x1, y1] = pt(s, 0), [x2, y2] = pt(s, Math.PI);
      el("line", { x1, y1, x2, y2, stroke: baseColors[k++ % 4], "stroke-width": "2", "stroke-opacity": ".55", "stroke-linecap": "round" }, grp);
    }
    el("path", { d: path(0), fill: "none", stroke: C.coral, "stroke-width": "2.4", "stroke-opacity": ".85" }, grp);
    el("path", { d: path(Math.PI), fill: "none", stroke: C.cyan, "stroke-width": "2.4", "stroke-opacity": ".85" }, grp);
    // 標籤
    const lx = L.helix.vertical ? L.helix.x + amp + 12 : 14;
    const ly = L.helix.vertical ? Math.max(48, h * 0.08) : L.helix.y + amp + 16;
    const lab = el("g", {}, grp);
    text(lab, lx, ly, "DNA 基因檢測", { fill: C.coral, "font-size": L.mode === "wide" ? 14 : 12, "font-weight": 700,
      "text-anchor": "start" });
    if (L.mode === "wide") {
      // 掃描框：像是正在判讀序列的一段
      const sy = h * 0.32;
      el("rect", { class: "lbg-scan", x: L.helix.x - amp - 10, y: sy, width: (amp + 10) * 2, height: 70, rx: 6,
        fill: "rgba(239,138,122,.08)", stroke: C.coral, "stroke-opacity": ".7", "stroke-dasharray": "4 4" }, grp);
      text(lab, lx, ly + 18, "ATCG…GCTA", { fill: C.muted, "font-size": 11, "font-family": "ui-monospace, Menlo, Consolas, monospace" });
    }
  }

  function ginseng(g, x, y, s, side) {
    const grp = el("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(3)})`, class: "lbg-herb" }, g);
    const stroke = { fill: "none", stroke: C.jade, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" };
    // 地面
    el("path", Object.assign({ d: "M-70 -78 L95 -78", "stroke-dasharray": "3 6", "stroke-opacity": ".45" }, stroke), grp);
    // 根：主根＋分支＋鬚根
    el("path", { d: "M-6 -78 C-14 -60 -16 -42 -10 -24 C-6 -12 -14 -4 -22 4 M-10 -24 C-2 -14 6 -8 14 2 M-12 -50 C-26 -46 -36 -40 -44 -30 M-8 -40 C6 -40 16 -36 26 -28",
      fill: "none", stroke: C.gold, "stroke-width": 2.4, "stroke-linecap": "round" }, grp);
    el("path", { d: "M-6 -78 C-1 -60 1 -42 -4 -26 C-8 -38 -12 -56 -6 -78 Z", fill: C.gold, "fill-opacity": ".35" }, grp);
    el("path", { d: "M-22 4 l-6 8 M-22 4 l2 10 M14 2 l6 8 M14 2 l-2 10 M-44 -30 l-8 4 M26 -28 l8 3",
      fill: "none", stroke: C.gold, "stroke-width": 1.2, "stroke-opacity": ".7", "stroke-linecap": "round" }, grp);
    // 莖
    el("path", Object.assign({ d: "M-6 -78 C-4 -120 2 -160 0 -205" }, stroke), grp);
    // 五片掌狀複葉 × 3 組
    const leafSet = (ax, ay, rot) => {
      const lg = el("g", { transform: `translate(${ax} ${ay}) rotate(${rot})` }, grp);
      el("path", Object.assign({ d: "M0 0 L0 -26" }, stroke), lg);
      [-62, -30, 0, 30, 62].forEach((a, i) => {
        const len = i === 2 ? 46 : (i === 1 || i === 3 ? 40 : 30);
        el("path", { d: `M0 -26 C${-9} ${-26 - len * 0.4} ${-6} ${-26 - len * 0.85} 0 ${-26 - len} C${6} ${-26 - len * 0.85} ${9} ${-26 - len * 0.4} 0 -26 Z`,
          transform: `rotate(${a} 0 -26)`, fill: C.jade, "fill-opacity": ".22", stroke: C.jade, "stroke-width": 1.4 }, lg);
      });
    };
    leafSet(0, -205, -48); leafSet(0, -205, 48); leafSet(0, -205, 0);
    // 紅色漿果
    [[0, -214], [-6, -220], [6, -220], [0, -227], [-4, -211], [5, -210]].forEach(([bx, by]) =>
      el("circle", { cx: bx, cy: by - 2, r: 4.2, fill: C.coral, "fill-opacity": ".9" }, grp));
    // 文字在縮放的群組裡，字級除以縮放比例，畫面上才維持固定大小
    const k = 1 / Math.max(0.35, s);
    if (side === "low") {
      text(grp, 30, -84, "人參", { fill: C.gold, "font-size": 12 * k, "font-weight": 700 });
    } else if (side === "left") {
      text(grp, -34, -40, "人參", { fill: C.gold, "font-size": 13 * k, "font-weight": 700, "text-anchor": "end" });
    } else {
      text(grp, 40, -132, "人參", { fill: C.gold, "font-size": 15 * k, "font-weight": 700 });
      text(grp, 40, -132 + 17 * k, "Panax ginseng", { fill: C.muted, "font-size": 11 * k, "font-style": "italic" });
    }
  }

  function sprig(g, x, y, s) {
    const grp = el("g", { transform: `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${s.toFixed(3)}) rotate(-28)`, class: "lbg-herb" }, g);
    el("path", { d: "M0 0 C-10 40 -8 90 6 140", fill: "none", stroke: C.gold, "stroke-width": 1.8, "stroke-opacity": ".75" }, grp);
    for (let i = 0; i < 6; i++) {
      const yy = 18 + i * 20, side = i % 2 ? 1 : -1;
      el("path", { d: `M${-2 + i * 0.6} ${yy} c${side * 14} -10 ${side * 34} -6 ${side * 40} 6 c${side * -10} 10 ${side * -28} 8 ${side * -40} -6 Z`,
        fill: C.gold, "fill-opacity": ".16", stroke: C.gold, "stroke-width": 1.2, "stroke-opacity": ".7" }, grp);
    }
  }

  function aiHub(g, L) {
    const { cx, cy, R } = L;
    const hr = R * 0.34;
    el("circle", { cx, cy, r: hr * 2.1, fill: "url(#lbgGlow)" }, g);
    el("circle", { cx, cy, r: hr, fill: "rgba(13,38,28,.86)", stroke: C.cyan, "stroke-width": 1.6 }, g);
    el("circle", { class: "lbg-pulse", cx, cy, r: hr, fill: "none", stroke: C.cyan, "stroke-width": 1.2 }, g);
    // 神經網路：3-4-3
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
      text(g, cx, cy + hr + 15, "AI 整合分析", { fill: C.text, "font-size": 11, "font-weight": 700, "text-anchor": "middle" });
    } else {
      text(g, cx, cy + hr * 0.62, "AI", { fill: C.text, "font-size": hr * 0.3, "font-weight": 800,
        "text-anchor": "middle", "letter-spacing": "2" });
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
    // 相鄰資料庫之間的串接（七邊形）
    el("polygon", { points: pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "),
      fill: "none", stroke: "rgba(233,243,238,.10)" }, g);
    const fs = Math.max(11, Math.min(16, R * 0.072));
    pts.forEach(([x, y], i) => {
      const [name, role, color] = DBS[i];
      // AI → 資料庫的資料流
      el("line", { x1: cx, y1: cy, x2: x, y2: y, stroke: color, "stroke-opacity": ".55", "stroke-width": 1.4,
        "stroke-dasharray": "3 9", class: "lbg-flow", style: `animation-delay:${(-i * 0.35).toFixed(2)}s` }, g);
      const pw = name.length * fs * 0.62 + 22, ph = fs + 12;
      el("rect", { x: x - pw / 2, y: y - ph / 2, width: pw, height: ph, rx: ph / 2,
        fill: "rgba(13,38,28,.92)", stroke: color, "stroke-width": 1.6 }, g);
      text(g, x, y + fs * 0.36, name, { fill: C.text, "font-size": fs, "font-weight": 700, "text-anchor": "middle" });
      // 角色說明放在節點外側，上半圈在上、下半圈在下
      const below = y >= cy - R * 0.2;
      text(g, x, below ? y + ph / 2 + fs * 0.95 : y - ph / 2 - fs * 0.45, role,
        { fill: C.muted, "font-size": Math.max(10, fs * 0.74), "text-anchor": "middle" });
    });
    if (L.mode === "wide") text(g, cx, cy - R - Math.max(30, R * 0.2), "七大國際資料庫整合",
      { fill: C.jade, "font-size": Math.max(12, fs * 0.95), "font-weight": 700, "text-anchor": "middle", "letter-spacing": "1" });
  }

  function chain(g, L) {
    const fs = L.mode === "wide" ? 12.5 : 11;
    if (L.mode === "portrait") {
      // 登入卡下方還有空間才畫（卡片位置由 CSS 決定，這裡量實際位置）
      const card = document.querySelector(".login-card");
      const bottom = card ? card.getBoundingClientRect().bottom + window.scrollY : L.h;
      if (L.h - bottom < 46) return;
    }
    const grp = el("g", {}, g);
    const t1 = el("text", { x: L.chainX, y: L.chainY - 20, "text-anchor": "middle", "font-size": fs, fill: C.muted }, grp);
    CHAIN.forEach((w, i) => {
      if (i) { const a = el("tspan", { fill: C.jade, dx: "4" }, t1); a.textContent = "→"; }
      const s = el("tspan", { fill: C.text, dx: i ? "4" : "0" }, t1);
      s.textContent = t(w);
    });
    text(grp, L.chainX, L.chainY, "科研輔助工具，不作為醫療診斷或治療建議", { fill: "rgba(233,243,238,.45)", "font-size": L.mode === "wide" ? 11 : 10, "text-anchor": "middle" });
  }

  // ---------------- 組裝 ----------------
  let last = "";
  function render() {
    const host = document.getElementById("loginBg");
    if (!host) return;
    // 不要對尺寸設下限：設了 viewBox 就會跟視窗比例不符，圖會被裁掉（v1.46.2 在 844×390 實測過）
    const w = Math.max(1, window.innerWidth), h = Math.max(1, window.innerHeight);
    const key = w + "x" + h;
    if (key === last) return;
    last = key;
    const L = layout(w, h);
    document.body.classList.toggle("login-wide", L.mode === "wide");
    document.body.classList.toggle("login-portrait", L.mode === "portrait");
    document.documentElement.style.setProperty("--login-art-band", L.band + "px");

    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, width: "100%", height: "100%", preserveAspectRatio: "xMidYMid slice",
      "aria-hidden": "true", focusable: "false", role: "presentation",
      "font-family": "'Noto Sans TC','PingFang TC','Microsoft JhengHei',system-ui,sans-serif" });
    defs(svg);
    el("rect", { width: w, height: h, fill: "url(#lbgBg)" }, svg);
    el("rect", { width: w, height: h, fill: "url(#lbgDots)" }, svg);
    const g = el("g", { class: "lbg-art" + (L.mode === "portrait" ? " lbg-portrait" : "") }, svg);
    helix(g, L);
    sprig(g, L.sprig.x, L.sprig.y, L.sprig.s);
    ginseng(g, L.herb.x, L.herb.y, L.herb.s, L.herb.label);
    databases(g, L);
    aiHub(g, L);
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

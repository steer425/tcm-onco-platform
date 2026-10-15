// 登入頁 3D 研究流程動畫：載入器（v1.46.4；v1.46.5 加入點選互動與登入框延後開啟）
//
// 什麼時候用 3D、什麼時候用平面版（js/login-bg.js）：
//   - 3D：寬螢幕（寬 ≥ 900、高 ≥ 560、橫向），瀏覽器支援 WebGL，且使用者沒有開「減少動態效果」
//   - 其他（手機、窄視窗、橫拿手機、不支援 WebGL、低記憶體裝置）：平面版
// 視窗縮放時隨時切換；切到平面版或分頁隱藏時 3D 停止繪製，不耗電。
//
// 載入順序：登入框與平面背景先出現 → 頁面載完後才去抓 Three.js（約 150 KB）→ 場景建好再淡入、淡出平面版。
// 任何一步失敗（CDN 抓不到、WebGL 建立失敗）都停在平面版，不影響登入。
(function () {
  const CDN = "https://cdn.jsdelivr.net/npm/three@0.128.0/";
  const LIBS = [
    "build/three.min.js",
    "examples/js/shaders/CopyShader.js",
    "examples/js/shaders/LuminosityHighPassShader.js",
    "examples/js/postprocessing/EffectComposer.js",
    "examples/js/postprocessing/RenderPass.js",
    "examples/js/postprocessing/ShaderPass.js",
    "examples/js/postprocessing/UnrealBloomPass.js",
  ].map((f) => CDN + f).concat(["js/login-3d-scene.js"]);

  const t = (s) => (window.loginT ? window.loginT(s) : s);
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lowMemory = navigator.deviceMemory && navigator.deviceMemory <= 2;
  const webgl = (() => {
    try { const c = document.createElement("canvas"); return !!(c.getContext("webgl") || c.getContext("experimental-webgl")); }
    catch (e) { return false; }
  })();
  const capable = !reduceMotion && !lowMemory && webgl;
  const fits = () => window.innerWidth >= 900 && window.innerHeight >= 560 && window.innerWidth / window.innerHeight >= 1.15;

  let canvas = null, hud = null, scene = null, loading = false, failed = false, loginOpen = false;

  // 介紹視窗內容（v1.46.5）：七本秘笈＝七個資料庫，藥田＝502 種中藥。數字與平台實際資料一致
  const DB_INFO = [
    { name: "TCMSP", manual: "本草藥理真經", sub: "Traditional Chinese Medicine Systems Pharmacology Database・西北農林科技大學",
      body: ["收錄中藥材、化學成分、ADME 藥動參數（口服生物利用度 OB、類藥性 DL 等）、作用靶點與相關疾病。",
             "平台用途：分析鏈路的骨幹，藥材 → 成分 → 靶點 → 疾病都從這裡開始；活性成分以 OB ≥ 30%、DL ≥ 0.18 篩選。"],
      url: "https://tcmsp-e.com/" },
    { name: "PubChem", manual: "萬化分子譜", sub: "美國國家生物技術資訊中心（NCBI／NIH）",
      body: ["全球最大的公開化合物資料庫，提供分子結構、SMILES、InChIKey、CAS 號與分子量。",
             "平台用途：把中藥成分的名稱轉成真正的分子結構，並用分子量和 TCMSP 互相驗算。"],
      url: "https://pubchem.ncbi.nlm.nih.gov/" },
    { name: "UniProt", manual: "蛋白靶點錄", sub: "UniProt 聯盟（EMBL-EBI、SIB、PIR）",
      body: ["權威的蛋白質序列與功能資料庫，提供每個蛋白對應的標準基因符號。",
             "平台用途：把 TCMSP 的蛋白全名標準化成基因符號，癌症基因比對率從 2.6% 提升到 18%。"],
      url: "https://www.uniprot.org/" },
    { name: "KEGG", manual: "經脈通路圖", sub: "京都基因與基因體百科全書（京都大學）",
      body: ["以通路圖描繪細胞內的訊號傳導與代謝網路，包含多條癌症相關通路。",
             "平台用途：通路富集分析，看靶點集中落在哪些生物路徑上（人類通路 372 條）。"],
      url: "https://www.kegg.jp/" },
    { name: "Reactome", manual: "生化反應訣", sub: "開放原始碼的生物路徑資料庫（OICR、EMBL-EBI 等）",
      body: ["以逐步反應的層級描述生物過程，分類比 KEGG 更細。",
             "平台用途：與 KEGG 並行的通路富集分析（人類通路 2,867 條）。"],
      url: "https://reactome.org/" },
    { name: "OncoKB", manual: "腫瘤基因秘錄", sub: "Memorial Sloan Kettering 癌症中心",
      body: ["精準腫瘤學知識庫，整理癌症相關基因與其臨床證據等級。",
             "平台用途：平台「暗黑基因」清單的來源，比對中藥靶點中哪些是癌症基因。"],
      url: "https://www.oncokb.org/" },
    { name: "DepMap", manual: "細胞依存心法", sub: "Broad Institute 癌症依賴圖譜計畫",
      body: ["以 CRISPR 實驗量測上千株腫瘤細胞對每個基因的依賴程度。",
             "平台用途：檢查中藥靶點是否為特定腫瘤細胞株的選擇性依賴基因（24Q2 版，1,208 株細胞）。"],
      url: "https://depmap.org/" },
  ];
  const HERB_INFO = { name: "502 種中藥", manual: "", sub: "TCMSP 收錄、平台上架的藥材",
    body: ["平台收錄 TCMSP 的 502 種中藥材，每味藥材都連到它的化學成分、作用靶點與相關疾病。",
           "平台以人參作為示範案例：190 種成分中有 22 種通過活性篩選，連到 118 個靶點。",
           "登入後可在「TCMSP 藥材關聯查詢站」查詢任何一味藥材。"],
    url: null };

  function buildDom() {
    canvas = document.createElement("canvas");
    canvas.id = "login3d";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);

    const root = document.createElement("div");
    root.id = "login3dHud";
    root.setAttribute("aria-hidden", "true");
    const top = document.createElement("div"); top.className = "l3d-top";
    const tag = document.createElement("div"); tag.className = "l3d-tagline";
    ["七大國際資料庫整合", "找出疾病靶點", "篩選中藥成分", "抑制靶點蛋白"].forEach((s, i) => {
      if (i) { const a = document.createElement("i"); a.textContent = "→"; tag.appendChild(a); }
      const sp = document.createElement("span"); sp.textContent = t(s); tag.appendChild(sp);
    });
    const row = document.createElement("div"); row.className = "l3d-steps";
    const STEP_TEXT = ["取出 DNA 報告・篩檢致病基因", "在螺旋上標定靶點", "熔煉中藥・整合七大資料庫", "提煉候選分子", "瞄準・逐一發射候選分子", "靶點蛋白受抑制"];
    const STEP_COLOR = ["#5fd4ff", "#ff6b5e", "#e0a24a", "#e0a24a", "#5fd4ff", "#6fe0b0"];
    const steps = STEP_TEXT.map((s, i) => {
      const d = document.createElement("div"); d.className = "l3d-step"; d.style.setProperty("--c", STEP_COLOR[i]);
      const b = document.createElement("b"); b.textContent = String(i + 1);
      const sp = document.createElement("span"); sp.textContent = t(s);
      d.append(b, sp); row.appendChild(d); return d;
    });
    const gene = document.createElement("div"); gene.className = "l3d-gene"; row.appendChild(gene);
    top.append(tag, row);
    const cap = document.createElement("div"); cap.className = "l3d-caption";
    const hint = document.createElement("div"); hint.className = "l3d-hint"; hint.textContent = t("點選熔爐開啟登入・點選秘笈或藥田查看介紹");
    cap.appendChild(hint);
    const strong = document.createElement("strong"); strong.textContent = t("研究流程示意動畫");
    const rest = document.createElement("span"); rest.textContent = t("非療效宣稱・科研輔助工具，不作為醫療診斷或治療建議");
    cap.append(strong, document.createTextNode("・"), rest);
    root.append(top, cap);
    document.body.appendChild(root);

    // 鍵盤與讀屏使用者的入口：不靠點 3D 熔爐也能開登入框
    const openBtn = document.createElement("button");
    openBtn.type = "button"; openBtn.id = "l3dOpenLogin"; openBtn.textContent = t("開啟登入");
    openBtn.addEventListener("click", openLogin);
    document.body.appendChild(openBtn);

    // 介紹視窗
    const dlg = document.createElement("div");
    dlg.id = "l3dInfo"; dlg.hidden = true;
    dlg.innerHTML = '<div class="l3d-info-card" role="dialog" aria-modal="true" aria-labelledby="l3dInfoTitle">' +
      '<button type="button" class="l3d-info-close"></button><p class="l3d-info-manual"></p><h3 id="l3dInfoTitle"></h3>' +
      '<p class="l3d-info-sub"></p><div class="l3d-info-body"></div><p class="l3d-info-foot"></p></div>';
    document.body.appendChild(dlg);
    dlg.querySelector(".l3d-info-close").textContent = "✕ " + t("關閉");
    dlg.querySelector(".l3d-info-foot").textContent = t("科研輔助工具，不作為醫療診斷或治療建議");
    dlg.addEventListener("click", (e) => { if (e.target === dlg) closeInfo(); });
    dlg.querySelector(".l3d-info-close").addEventListener("click", closeInfo);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !dlg.hidden) closeInfo(); });

    hud = { root, steps, gene, onPick };
  }

  let lastFocus = null;
  function showInfo(info, kind) {
    const dlg = document.getElementById("l3dInfo");
    dlg.dataset.kind = kind;
    dlg.querySelector(".l3d-info-manual").textContent = info.manual ? "《" + t(info.manual) + "》" : "";
    dlg.querySelector("h3").textContent = t(info.name);
    dlg.querySelector(".l3d-info-sub").textContent = t(info.sub);
    const body = dlg.querySelector(".l3d-info-body"); body.replaceChildren();
    info.body.forEach((p) => { const el = document.createElement("p"); el.textContent = t(p); body.appendChild(el); });
    if (info.url) {
      const a = document.createElement("a"); a.href = info.url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = t("前往官方網站") + " ↗"; body.appendChild(a);
    }
    lastFocus = document.activeElement;
    dlg.hidden = false;
    dlg.querySelector(".l3d-info-close").focus();
  }
  function closeInfo() {
    const dlg = document.getElementById("l3dInfo");
    dlg.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function onPick(p) {
    if (p.type === "furnace") openLogin();
    else if (p.type === "db") showInfo(DB_INFO[p.i], "db");
    else if (p.type === "herbs") showInfo(HERB_INFO, "herbs");
  }
  // 登入框：3D 模式下先藏起來，點熔爐（或「開啟登入」鈕）才出現
  function openLogin() {
    if (loginOpen) return;
    loginOpen = true;
    document.body.classList.add("login-open");
    if (scene) scene.setLoginOpen(true);
    setTimeout(() => { const a = document.getElementById("account"); if (a) a.focus(); }, 450);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.async = false;
      s.onload = resolve; s.onerror = () => reject(new Error("load failed: " + src));
      document.head.appendChild(s);
    });
  }

  async function load() {
    loading = true;
    try {
      for (const src of LIBS) await loadScript(src);
      if (!window.THREE || !window.startLogin3D) throw new Error("three.js not available");
      buildDom();
      scene = window.startLogin3D(canvas, hud);
      scene.setLoginOpen(loginOpen);
      window.__login3d = scene;          // 測試用
      apply();
    } catch (e) {
      failed = true;                     // 停在平面版
      if (canvas) canvas.remove();
      if (hud) hud.root.remove();
    } finally {
      loading = false;
    }
  }

  function apply() {
    const on = capable && fits();
    // 第三方登入失敗轉回來時帶著錯誤訊息，登入框要直接打開，訊息才看得到
    if (/[?&]google_error=/.test(location.search)) loginOpen = true;
    document.body.classList.toggle("login-open", loginOpen);
    if (on && !scene && !loading && !failed) { load(); return; }
    document.body.classList.toggle("login-3d", !!(on && scene));
    if (scene) scene.setActive(on);
  }

  if (!capable) return;
  let timer = null;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(apply, 150); });
  // 等登入框與平面背景先畫好，再開始抓 3D
  const start = () => setTimeout(apply, 300);
  if (document.readyState === "complete") start(); else window.addEventListener("load", start);
})();

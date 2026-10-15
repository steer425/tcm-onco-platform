// 登入頁 3D 研究流程動畫：載入器（v1.46.4）
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

  let canvas = null, hud = null, scene = null, loading = false, failed = false;

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
    const strong = document.createElement("strong"); strong.textContent = t("研究流程示意動畫");
    const rest = document.createElement("span"); rest.textContent = t("非療效宣稱・科研輔助工具，不作為醫療診斷或治療建議");
    cap.append(strong, document.createTextNode("・"), rest);
    root.append(top, cap);
    document.body.appendChild(root);
    hud = { root, steps, gene };
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

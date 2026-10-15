// 登入頁 3D 研究流程動畫：載入器（v1.46.4；v1.46.5 點選互動與登入框延後開啟；v1.46.6 介紹視窗改成與登入框同位置同大小）
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
  ].map((f) => CDN + f).concat(["js/login-3d-info.js", "js/login-3d-scene.js"]);

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

  // 介紹內容（七本秘笈、花園、巫師）在 js/login-3d-info.js（三種語言各一份，v1.46.6）
  let infoKey = null;                                    // 目前開著的介紹："db:0"…"db:6"、"herbs"、"wizard"

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
    const hint = document.createElement("div"); hint.className = "l3d-hint"; hint.textContent = t("點選熔爐開啟／收起登入・點選秘笈、花園或巫師查看介紹");
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

    // 介紹視窗：和登入框同位置、同大小、同樣式（v1.46.6），放在 .login-wrap 裡，以登入框的位置為準
    const dlg = document.createElement("div");
    dlg.id = "l3dInfo"; dlg.className = "l3d-panel"; dlg.setAttribute("role", "dialog"); dlg.setAttribute("aria-labelledby", "l3dInfoTitle");
    dlg.setAttribute("aria-hidden", "true");
    dlg.innerHTML = '<button type="button" class="l3d-info-close"></button>' +
      '<div class="l3d-info-head"><p class="l3d-info-manual"></p><h3 id="l3dInfoTitle"></h3><p class="l3d-info-sub"></p></div>' +
      '<nav class="l3d-info-nav" aria-label="sections"></nav><div class="l3d-info-body" tabindex="0"></div><p class="l3d-info-foot"></p>';
    (document.querySelector(".login-wrap") || document.body).appendChild(dlg);
    dlg.querySelector(".l3d-info-close").textContent = "✕ " + t("關閉");
    dlg.querySelector(".l3d-info-foot").textContent = t("科研輔助工具，不作為醫療診斷或治療建議");
    dlg.querySelector(".l3d-info-close").addEventListener("click", closeInfo);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && infoKey) closeInfo(); });
    window.addEventListener("resize", syncPanelBox);

    hud = { root, steps, gene, onPick };
  }

  let lastFocus = null;
  // 介紹視窗的位置與大小跟登入框一致（登入框藏起來時仍佔版位，offset* 不受 transform 影響）
  function syncPanelBox() {
    const dlg = document.getElementById("l3dInfo"), card = document.querySelector(".login-card");
    if (!dlg || !card) return;
    dlg.style.left = card.offsetLeft + "px"; dlg.style.top = card.offsetTop + "px";
    dlg.style.width = card.offsetWidth + "px"; dlg.style.height = Math.max(card.offsetHeight, 460) + "px";
  }
  function entryFor(key) {
    const I = window.LOGIN3D_INFO;
    if (key === "herbs") return I.pick(I.herbs);
    if (key === "wizard") return I.pick(I.wizard);
    return I.pick(I.db[+key.split(":")[1]]);
  }
  function showInfo(key) {
    if (!window.LOGIN3D_INFO) return;
    if (infoKey === key) { closeInfo(); return; }          // 再點同一個 → 收起
    if (loginOpen) setLogin(false);
    const info = entryFor(key), dlg = document.getElementById("l3dInfo");
    dlg.dataset.kind = key.split(":")[0];
    dlg.querySelector(".l3d-info-manual").textContent = [info.manual ? "《" + info.manual + "》" : "", info.star ? "★ " + info.star : ""].filter(Boolean).join("・");
    dlg.querySelector("h3").textContent = info.name;
    dlg.querySelector(".l3d-info-sub").textContent = info.sub;
    const nav = dlg.querySelector(".l3d-info-nav"), body = dlg.querySelector(".l3d-info-body");
    nav.replaceChildren(); body.replaceChildren(); body.scrollTop = 0;
    const lab = document.createElement("span"); lab.className = "l3d-nav-label"; lab.textContent = t("快速跳到"); nav.appendChild(lab);
    info.sections.forEach(([tag, text], k) => {
      const sec = document.createElement("section"); sec.id = "l3dSec" + k;
      const tg = document.createElement("span"); tg.className = "l3d-tag"; tg.textContent = tag;
      const p = document.createElement("p"); p.textContent = text;
      sec.append(tg, p);
      if (info.email && k === 2) {                           // 巫師：聯絡方式那段附上郵件連結
        const a = document.createElement("a"); a.className = "l3d-mail"; a.href = "mailto:" + info.email; a.textContent = "✉ " + info.email; sec.appendChild(a);
      }
      body.appendChild(sec);
      const chip = document.createElement("button"); chip.type = "button"; chip.className = "l3d-chip"; chip.textContent = tag;
      chip.addEventListener("click", () => { body.scrollTo({ top: sec.offsetTop - body.offsetTop - 4, behavior: "smooth" }); });
      nav.appendChild(chip);
    });
    if (info.url) {
      const a = document.createElement("a"); a.className = "l3d-site"; a.href = info.url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = t("前往官方網站") + " ↗"; body.appendChild(a);
    }
    if (!infoKey) lastFocus = document.activeElement;
    infoKey = key;
    syncPanelBox();
    dlg.classList.add("open"); dlg.setAttribute("aria-hidden", "false");
    document.body.classList.add("l3d-info-open");
    if (scene) scene.setLoginOpen(true);
    dlg.querySelector(".l3d-info-close").focus({ preventScroll: true });
  }
  function closeInfo() {
    if (!infoKey) return;
    infoKey = null;
    const dlg = document.getElementById("l3dInfo");
    dlg.classList.remove("open"); dlg.setAttribute("aria-hidden", "true");
    document.body.classList.remove("l3d-info-open");
    if (scene) scene.setLoginOpen(loginOpen);
    if (lastFocus && lastFocus.focus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
  }
  function onPick(p) {
    if (p.type === "furnace") { if (loginOpen) closeLogin(); else openLogin(); }
    else if (p.type === "db") showInfo("db:" + p.i);
    else if (p.type === "herbs") showInfo("herbs");
    else if (p.type === "wizard") showInfo("wizard");
  }
  // 登入框：3D 模式下先藏起來，點熔爐（或「開啟登入」鈕）才出現；打開後再點熔爐收起來。和介紹視窗同一時間只開一個
  function setLogin(on) {
    loginOpen = on;
    document.body.classList.toggle("login-open", on);
    if (scene) scene.setLoginOpen(on || !!infoKey);
  }
  function closeLogin() {
    if (!loginOpen) return;
    const card = document.querySelector(".login-card");
    if (card && card.contains(document.activeElement)) document.activeElement.blur();
    setLogin(false);
  }
  function openLogin() {
    if (loginOpen) return;
    if (infoKey) closeInfo();
    setLogin(true);
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
    document.body.classList.toggle("login-open", loginOpen);
    if (on && !scene && !loading && !failed) { load(); return; }
    document.body.classList.toggle("login-3d", !!(on && scene));
    if (scene) scene.setActive(on);
  }

  if (!capable) return;
  // 第三方登入失敗轉回來時帶著錯誤訊息，登入框要直接打開，訊息才看得到（只在進頁時判斷一次，之後可以點熔爐收起）
  if (/[?&]google_error=/.test(location.search)) loginOpen = true;
  let timer = null;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(apply, 150); });
  // 等登入框與平面背景先畫好，再開始抓 3D
  const start = () => setTimeout(apply, 300);
  if (document.readyState === "complete") start(); else window.addEventListener("load", start);
})();

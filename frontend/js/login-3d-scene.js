// 登入頁 3D 研究流程動畫的場景（v1.46.4；v1.46.5 七本秘笈；v1.46.6 版面重排與花園；v1.46.7 北斗固定於熔爐上方、移除巫師；v1.46.8 文字改 HTML 疊層）。由 js/login-3d.js 在條件符合時延後載入並呼叫 startLogin3D()。
//
// 一輪 12 秒：從人體取出 DNA 報告 → 沿螺旋篩檢致病基因、在螺旋上標定靶點 → 502 種中藥進熔爐、七大資料庫依序點亮
// → 提煉候選分子 → 瞄準光線、逐一發射 → 靶點蛋白逐步虛弱 → 人體發出聖光。
// 畫面上的字一律是研究流程用語（「靶點蛋白受抑制」「候選分子命中靶點・研究流程示意」），不寫療效。
// 所有模型都由程式以幾何形狀生成，沒有外部素材。
window.startLogin3D = function (canvas, hud) {
  "use strict";
  const T = THREE;
  const tr = (s) => (window.loginT ? window.loginT(s) : s);
  const lin = (hex) => new THREE.Color(hex).convertSRGBToLinear();
  const COL = { jade: 0x6fe0b0, gold: 0xe2b866, bronze: 0xb07a3a, plasma: 0x5fd4ff, lesion: 0xff6b5e, white: 0xffffff, ember: 0xff8a3a };
  const DBS = [
    ["TCMSP", "中藥系統藥理", "#e2b866"], ["PubChem", "化合物結構", "#5fd4ff"], ["UniProt", "蛋白靶點標準化", "#5fd4ff"],
    ["KEGG", "訊號通路", "#6fe0b0"], ["Reactome", "生物反應路徑", "#6fe0b0"], ["OncoKB", "癌症基因知識庫", "#ff6b5e"],
    ["DepMap", "腫瘤細胞株依賴", "#ff6b5e"],
  ];
  const GENES = ["TP53", "EGFR", "BCL2", "KRAS", "PIK3CA", "PTEN"];
  const HERB_COUNT = 502;
  const LOOP = 12;                          // 一輪秒數
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------- 基本場景 ----------------
  const renderer = new T.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputEncoding = T.sRGBEncoding;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const scene = new T.Scene();
  scene.background = lin(0x050b10);
  scene.fog = new T.FogExp2(lin(0x050b10), 0.016);
  const BASE_FOV = 44;
  const camera = new T.PerspectiveCamera(BASE_FOV, 1, 0.1, 200);
  const CAM_TARGET = new T.Vector3(-3.8, 5.0, 0);
  let orbitOn = true;

  scene.add(new T.HemisphereLight(0x9fd8ff, 0x10201a, 0.55));
  const key = new T.DirectionalLight(0xfff1dd, 0.9); key.position.set(8, 14, 10); scene.add(key);
  const rim = new T.DirectionalLight(0x5fd4ff, 0.5); rim.position.set(-12, 6, -8); scene.add(rim);

  // 文字貼圖（中文用系統字型繪到 canvas）
  function labelTexture(lines, opt) {
    opt = opt || {};
    lines = lines.map(tr);
    const pad = 18, fs = opt.size || 44;
    const c = document.createElement("canvas"), x = c.getContext("2d");
    const font = (w, s) => `${w} ${s}px "Noto Sans TC","Noto Sans CJK TC","PingFang TC","Microsoft JhengHei",sans-serif`;
    x.font = font(800, fs);
    const w0 = Math.max(...lines.map((l, i) => { x.font = font(i ? 500 : 800, i ? fs * 0.62 : fs); return x.measureText(l).width; }));
    c.width = Math.ceil(w0 + pad * 2); c.height = Math.ceil(fs * (1 + (lines.length - 1) * 0.8) + pad * 2);
    if (opt.bg) {
      x.fillStyle = opt.bg; x.strokeStyle = opt.color || "#fff"; x.lineWidth = 4;
      const r = 18; x.beginPath(); x.roundRect ? x.roundRect(2, 2, c.width - 4, c.height - 4, r) : x.rect(2, 2, c.width - 4, c.height - 4);
      x.fill(); x.stroke();
    }
    lines.forEach((l, i) => {
      x.font = font(i ? 500 : 800, i ? fs * 0.62 : fs);
      x.fillStyle = i ? "rgba(232,243,239,.78)" : (opt.color || "#fff");
      x.textAlign = "center"; x.textBaseline = "top";
      x.fillText(l, c.width / 2, pad + (i ? fs * 1.08 + (i - 1) * fs * 0.8 : 0));
    });
    const tex = new T.CanvasTexture(c); tex.encoding = T.sRGBEncoding; tex.anisotropy = 4;
    return { tex, aspect: c.width / c.height };
  }
  // 場景文字一律用 HTML 疊在畫面上（v1.46.8）：貼圖文字縮小顯示會糊、又會被光暈後製暈開。
  // 每格把 3D 位置投影到螢幕座標，再依距離換算字級；介面與舊的 sprite 相同（.position、.material.opacity），呼叫端不必改。
  const labelLayer = document.createElement("div"); labelLayer.id = "login3dLabels"; labelLayer.setAttribute("aria-hidden", "true");
  canvas.after(labelLayer);
  const LABELS = [];
  // lines：第一行主文字、其餘為小字；unit：主文字在 3D 中的字高（世界單位）；opt：color、bg、cls、vertical、minPx
  function htmlLabel(lines, unit, opt) {
    opt = opt || {};
    const o = new T.Object3D(), el = document.createElement("div");
    el.className = "l3d-lab" + (opt.cls ? " " + opt.cls : "") + (opt.vertical ? " l3d-lab-v" : "");
    if (opt.color) el.style.color = opt.color;
    if (opt.bg) { el.style.background = opt.bg; el.style.borderColor = opt.color || "#fff"; el.classList.add("l3d-lab-box"); }
    lines.forEach((l, i) => {
      const sp = document.createElement("span"); sp.className = i ? "l3d-lab-sub" : "l3d-lab-main";
      sp.textContent = opt.vertical ? [...tr(l)].join("\n") : tr(l);      // 直書：逐字換行（比 writing-mode 在各瀏覽器穩定）
      el.appendChild(sp);
    });
    labelLayer.appendChild(el);
    o.material = { opacity: 1, depthTest: true, map: { dispose() {} }, dispose() { el.remove(); const k = LABELS.indexOf(o); if (k >= 0) LABELS.splice(k, 1); } };
    o.userData.label = { el, unit, minPx: opt.minPx || 13, maxPx: opt.maxPx || 32, hideBelow: opt.hideBelow || 0 };
    LABELS.push(o);
    return o;
  }
  function sprite(lines, height, opt) { return htmlLabel(lines, height * 0.55, opt); }
  const _lp = new T.Vector3(), _lq = new T.Vector3(), _camUp = new T.Vector3();
  function attachedAndVisible(o) {
    for (let p = o; p; p = p.parent) { if (!p.visible) return false; if (p === scene) return true; }
    return false;
  }
  function updateLabels() {
    const W = viewW, H = viewH;
    _camUp.set(0, 1, 0).applyQuaternion(camera.quaternion);
    for (const o of LABELS) {
      const L = o.userData.label, el = L.el;
      const op = o.material.opacity;
      if (op <= 0.01 || !attachedAndVisible(o)) { if (el.style.display !== "none") el.style.display = "none"; continue; }
      o.getWorldPosition(_lp); _lq.copy(_lp).addScaledVector(_camUp, L.unit);
      _lp.project(camera); _lq.project(camera);
      if (_lp.z > 1 || _lp.z < -1) { el.style.display = "none"; continue; }
      const px = Math.abs(_lq.y - _lp.y) / 2 * H;                 // 主文字在螢幕上的高度（px）
      if (L.hideBelow && px < L.hideBelow) { el.style.display = "none"; continue; }
      const fs = Math.max(L.minPx, Math.min(L.maxPx, px));
      el.style.display = "";
      el.style.fontSize = fs.toFixed(1) + "px";
      el.style.opacity = Math.min(1, op).toFixed(3);
      el.style.transform = `translate(${((_lp.x + 1) / 2 * W).toFixed(1)}px, ${((1 - _lp.y) / 2 * H).toFixed(1)}px) translate(-50%, -50%)`;
    }
  }
  // 柔光貼圖（光暈、粒子共用）
  const glowTex = (() => {
    const c = document.createElement("canvas"); c.width = c.height = 128;
    const x = c.getContext("2d"), g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.25, "rgba(255,255,255,.55)"); g.addColorStop(1, "rgba(255,255,255,0)");
    x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    return new T.CanvasTexture(c);
  })();
  function glow(color, size, opacity) {
    const s = new T.Sprite(new T.SpriteMaterial({ map: glowTex, color, transparent: true, opacity: opacity == null ? 1 : opacity,
      blending: T.AdditiveBlending, depthWrite: false, toneMapped: false }));
    s.scale.set(size, size, 1); return s;
  }

  // ---------------- 地面：星點網格 ----------------
  const floor = new T.Mesh(new T.CircleGeometry(40, 64), new T.MeshBasicMaterial({ color: lin(0x061117) }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.62; scene.add(floor);
  const grid = new T.PolarGridHelper(18, 24, 10, 64, lin(0x16463c), lin(0x0e2a26));
  grid.position.y = -0.6; scene.add(grid);

  // ---------------- 底層：502 種中藥，人參在中心 ----------------
  const FURN_X = 0.2;                         // 熔爐：右側 80% 舞台的中心（v1.46.6）
  const HERB_R = 8.6;                          // 藥田半徑（v1.46.5 放大）
  const herbs = new T.Group(); herbs.position.set(FURN_X, -0.4, 0); scene.add(herbs);
  // 502 種中藥＝502 朵花（v1.46.6 由葉片改成花花草草）：花莖、五瓣花、花心，外加草叢
  const tmpM = new T.Matrix4(), tmpQ = new T.Quaternion(), tmpE = new T.Euler(), tmpC = new T.Color(), tmpS = new T.Vector3();
  const petalGeo = (() => {                                  // 五瓣花：圓盤外緣依角度起伏成花瓣，平放朝上
    const g = new T.CircleGeometry(1, 60), pos = g.attributes.position;
    for (let k = 1; k < pos.count; k++) {
      const x = pos.getX(k), y = pos.getY(k), a = Math.atan2(y, x), r = 0.45 + 0.55 * Math.pow(Math.abs(Math.cos(a * 2.5)), 0.7);
      pos.setXY(k, Math.cos(a) * r, Math.sin(a) * r); pos.setZ(k, 0.12 * r * r);   // 花瓣微微上翹
    }
    g.rotateX(-Math.PI / 2); g.computeVertexNormals(); return g;
  })();
  const flowerMat = new T.MeshStandardMaterial({ roughness: 0.55, metalness: 0.0, side: T.DoubleSide, emissive: lin(0x221018), emissiveIntensity: 0.35 });
  const herbMesh = new T.InstancedMesh(petalGeo, flowerMat, HERB_COUNT);
  const coreMesh = new T.InstancedMesh(new T.SphereGeometry(1, 10, 8), new T.MeshStandardMaterial({ color: lin(0xffd25e), roughness: 0.4, emissive: lin(0x5a3a00), emissiveIntensity: 0.6 }), HERB_COUNT);
  const stemMesh = new T.InstancedMesh(new T.CylinderGeometry(0.018, 0.026, 1, 5).translate(0, 0.5, 0), new T.MeshStandardMaterial({ color: lin(0x4fae6a), roughness: 0.7 }), HERB_COUNT);
  const flowerPal = [0xff8fb8, 0xc39bff, 0xffd75e, 0xfff4e6, 0xffa45c, 0xff7a7a, 0x8fd0ff, 0xe8a6ff];
  const herbPos = [];
  for (let i = 0; i < HERB_COUNT; i++) {
    const f = i / (HERB_COUNT - 1), r = 1.6 + (HERB_R - 1.6) * Math.sqrt(f), a = i * 2.399963;
    const h = 0.32 + 0.3 * ((i * 53) % 13) / 13;            // 花莖高度
    const p = new T.Vector3(r * Math.cos(a), 0, r * Math.sin(a));
    herbPos.push(p);
    tmpQ.identity(); tmpM.compose(p, tmpQ, tmpS.set(1, h, 1)); stemMesh.setMatrixAt(i, tmpM);
    const sc = 0.15 + 0.1 * ((i * 37) % 11) / 11;
    tmpE.set(0.25 * Math.sin(i * 1.3), i * 0.7, 0.25 * Math.cos(i * 0.9)); tmpQ.setFromEuler(tmpE);
    const top = p.clone(); top.y = h;
    tmpM.compose(top, tmpQ, tmpS.set(sc, sc, sc)); herbMesh.setMatrixAt(i, tmpM);
    herbMesh.setColorAt(i, tmpC.setHex(flowerPal[i % flowerPal.length]).convertSRGBToLinear());
    top.y += 0.02; tmpM.compose(top, tmpQ, tmpS.set(sc * 0.32, sc * 0.22, sc * 0.32)); coreMesh.setMatrixAt(i, tmpM);
  }
  // 草叢：細長的錐形草葉，散布在花之間
  const GRASS = 900;
  const grassMesh = new T.InstancedMesh(new T.ConeGeometry(0.035, 1, 4).translate(0, 0.5, 0), new T.MeshStandardMaterial({ roughness: 0.8, emissive: lin(0x0b2a14), emissiveIntensity: 0.5 }), GRASS);
  const grassPal = [0x3f9a5a, 0x5cbf73, 0x2f7d48, 0x7fcf86];
  for (let i = 0; i < GRASS; i++) {
    const r = 1.4 + (HERB_R + 0.1 - 1.4) * Math.sqrt(((i * 0.6180339) % 1)), a = i * 2.39996 + 0.9;
    const p = new T.Vector3(r * Math.cos(a), 0, r * Math.sin(a));
    tmpE.set(0.35 * Math.sin(i * 2.1), 0, 0.35 * Math.cos(i * 1.7)); tmpQ.setFromEuler(tmpE);
    tmpM.compose(p, tmpQ, tmpS.set(1, 0.22 + 0.3 * ((i * 29) % 7) / 7, 1)); grassMesh.setMatrixAt(i, tmpM);
    grassMesh.setColorAt(i, tmpC.setHex(grassPal[i % grassPal.length]).convertSRGBToLinear());
  }
  herbs.add(stemMesh); herbs.add(coreMesh); herbs.add(grassMesh);
  herbs.add(herbMesh);
  const herbRing = new T.Mesh(new T.RingGeometry(HERB_R + 0.25, HERB_R + 0.37, 128), new T.MeshBasicMaterial({ color: 0xe2b866, transparent: true, opacity: 0.35, side: T.DoubleSide }));
  herbRing.rotation.x = -Math.PI / 2; herbs.add(herbRing);
  // 看不見的圓盤：讓整片藥田都點得到（只點葉片太難點中）
  const herbHit = new T.Mesh(new T.CircleGeometry(HERB_R + 0.4, 64), new T.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
  herbHit.rotation.x = -Math.PI / 2; herbHit.position.y = 0.05; herbHit.userData.pick = { type: "herbs" }; herbs.add(herbHit);
  const herbLabel = sprite(["502 種中藥"], 0.7, { color: "#e2b866" }); herbLabel.position.set(FURN_X, -0.3, HERB_R + 2.0); scene.add(herbLabel);

  // 人參：莖、三組五片掌狀複葉、紅色漿果、主根與鬚根
  function buildGinseng() {
    const g = new T.Group();
    const green = new T.MeshStandardMaterial({ color: 0x6fe0b0, roughness: 0.5, emissive: 0x0b3a28, emissiveIntensity: 0.6 });
    const root = new T.MeshStandardMaterial({ color: 0xe2b866, roughness: 0.45, emissive: 0x3a2508, emissiveIntensity: 0.5 });
    const stem = new T.Mesh(new T.CylinderGeometry(0.035, 0.05, 1.5, 8), green); stem.position.y = 0.75; g.add(stem);
    for (let k = 0; k < 3; k++) {
      const set = new T.Group(); set.position.y = 1.5; set.rotation.y = k * 2.1; set.rotation.z = 0.55;
      const pet = new T.Mesh(new T.CylinderGeometry(0.02, 0.02, 0.45, 6), green); pet.position.y = 0.22; set.add(pet);
      for (let j = 0; j < 5; j++) {
        const leaf = new T.Mesh(new T.SphereGeometry(1, 10, 8), green);
        const len = j === 2 ? 0.42 : (j === 1 || j === 3 ? 0.36 : 0.26);
        leaf.scale.set(0.09, len, 0.025);
        const a = (j - 2) * 0.55; leaf.position.set(Math.sin(a) * len, 0.45 + Math.cos(a) * len, 0); leaf.rotation.z = -a;
        set.add(leaf);
      }
      g.add(set);
    }
    const berryMat = new T.MeshStandardMaterial({ color: 0xff5a4a, emissive: 0xff2a1a, emissiveIntensity: 0.7, roughness: 0.3 });
    [[0, 0], [0.07, 0.04], [-0.07, 0.04], [0, 0.09], [0.04, -0.06], [-0.05, -0.05]].forEach(([dx, dz]) => {
      const b = new T.Mesh(new T.SphereGeometry(0.055, 10, 8), berryMat); b.position.set(dx, 1.62 + Math.abs(dz), dz); g.add(b);
    });
    const main = new T.Mesh(new T.CylinderGeometry(0.11, 0.03, 0.9, 10), root); main.position.y = -0.45; g.add(main);
    [[0.6, 0.5], [-0.7, 0.45], [0.2, 0.55]].forEach(([rz, l], i) => {
      const leg = new T.Mesh(new T.CylinderGeometry(0.04, 0.012, l, 6), root);
      leg.position.set(Math.sin(rz) * 0.18, -0.75, (i - 1) * 0.08); leg.rotation.z = rz; g.add(leg);
    });
    return g;
  }
  const ginseng = buildGinseng(); ginseng.position.set(0, 0.55, 0); ginseng.scale.setScalar(1.1); herbs.add(ginseng);
  const ginsengGlow = glow(0xe2b866, 3.4, 0.45); ginsengGlow.position.set(0, 1.4, 0); herbs.add(ginsengGlow);

  // 上升的藥氣：中藥粒子沿螺旋被吸進丹爐
  const STREAM = 260;
  const streamGeo = new T.BufferGeometry();
  const streamPos = new Float32Array(STREAM * 3), streamSeed = new Float32Array(STREAM);
  for (let i = 0; i < STREAM; i++) streamSeed[i] = Math.random();
  streamGeo.setAttribute("position", new T.BufferAttribute(streamPos, 3));
  const streamMat = new T.PointsMaterial({ map: glowTex, color: 0xe2b866, size: 0.28, transparent: true, opacity: 0.9,
    blending: T.AdditiveBlending, depthWrite: false, toneMapped: false });
  const stream = new T.Points(streamGeo, streamMat); scene.add(stream);

  // ---------------- 中層：丹爐（三足鼎）＋七大資料庫 ----------------
  const FURN_Y = 3.2;
  const furnace = new T.Group(); furnace.position.set(FURN_X, FURN_Y, 0); scene.add(furnace);
  const bronze = new T.MeshStandardMaterial({ color: 0xb07a3a, metalness: 0.85, roughness: 0.32, emissive: 0x2a1404, emissiveIntensity: 0.4 });
  const profile = [[0.0, -1.05], [0.9, -1.05], [1.35, -0.75], [1.55, -0.2], [1.5, 0.45], [1.25, 0.9], [1.32, 1.0], [1.1, 1.05]]
    .map(([r, y]) => new T.Vector2(r, y));
  const body = new T.Mesh(new T.LatheGeometry(profile, 48), bronze); furnace.add(body);
  body.userData.pick = { type: "furnace" };
  for (let k = 0; k < 3; k++) {
    const a = k * Math.PI * 2 / 3 + Math.PI / 6;
    const leg = new T.Mesh(new T.CylinderGeometry(0.12, 0.2, 1.7, 10), bronze);
    leg.position.set(Math.cos(a) * 0.95, -1.75, Math.sin(a) * 0.95); leg.rotation.z = Math.cos(a) * 0.12; leg.rotation.x = -Math.sin(a) * 0.12;
    leg.userData.pick = { type: "furnace" };
    furnace.add(leg);
  }
  [-1, 1].forEach((s) => {
    const h = new T.Mesh(new T.TorusGeometry(0.32, 0.07, 10, 24, Math.PI), bronze);
    h.position.set(s * 1.0, 1.2, 0); h.rotation.y = s > 0 ? 0 : Math.PI; furnace.add(h);
  });
  const band = new T.Mesh(new T.TorusGeometry(1.53, 0.045, 8, 64), new T.MeshStandardMaterial({ color: 0xe2b866, metalness: 1, roughness: 0.25 }));
  band.rotation.x = Math.PI / 2; band.position.y = 0.15; furnace.add(band);
  // 爐火：爐口的發光與火苗粒子
  const fireLight = new T.PointLight(0xff8a3a, 2.2, 14, 2); fireLight.position.set(0, 1.4, 0); furnace.add(fireLight);
  const mouthGlow = glow(0xff8a3a, 4.2, 0.85); mouthGlow.position.set(0, 1.25, 0); furnace.add(mouthGlow);
  const FIRE = 120;
  const fireGeo = new T.BufferGeometry(); const firePos = new Float32Array(FIRE * 3), fireSeed = new Float32Array(FIRE);
  for (let i = 0; i < FIRE; i++) fireSeed[i] = Math.random();
  fireGeo.setAttribute("position", new T.BufferAttribute(firePos, 3));
  const fire = new T.Points(fireGeo, new T.PointsMaterial({ map: glowTex, color: 0xff9a4a, size: 0.35, transparent: true, opacity: 0.85,
    blending: T.AdditiveBlending, depthWrite: false, toneMapped: false }));
  fire.position.copy(furnace.position); scene.add(fire);
  const furnLabel = sprite(["熔爐・整合七大資料庫"], 0.5, { color: "#e0a24a", bg: "rgba(20,12,4,.8)" }); furnLabel.position.set(FURN_X, 1.05, 2.6); scene.add(furnLabel);
  // 「點擊熔爐開啟登入」提示：登入框開啟後消失
  const loginHint = sprite(["點擊熔爐・開啟登入"], 0.62, { color: "#fff1c0", bg: "rgba(60,30,6,.85)" });
  loginHint.position.set(FURN_X, 0.15, 3.2); scene.add(loginHint);
  // 星斗轉到爐前時會經過這兩個標籤，讓標籤永遠畫在最上層才看得清楚
  [furnLabel, loginHint].forEach((o) => { o.material.depthTest = false; o.renderOrder = 10; });
  const furnHalo = new T.Mesh(new T.TorusGeometry(1.95, 0.04, 8, 80), new T.MeshBasicMaterial({ color: 0xffd27a, transparent: true, opacity: 0, toneMapped: false }));
  furnHalo.rotation.x = Math.PI / 2; furnHalo.position.set(FURN_X, FURN_Y + 0.15, 0); scene.add(furnHalo);

  // 七本武林秘笈（線裝書，青花藍白、半透明），固定在熔爐上方排成北斗七星（v1.46.7）。
  // 北斗七星：天樞、天璇、天璣、天權（斗身），玉衡、開陽、瑤光（斗柄），座標為星圖上的真實相對位置。
  // 位置以數值搜尋決定：書（含左側星名、上方星點）不碰熔爐、發射平台與砲管、候選分子與其標籤、瞄準光線、DNA 標籤與上方標語列，
  // 七本彼此也不重疊；斗身在熔爐左上方，斗柄從候選分子上方越過。滑鼠越靠近，書越亮。
  const DIPPER = [[0, 0], [0.06, -0.62], [0.86, -0.8], [0.9, -0.27], [1.5, -0.12], [2.08, 0.05], [2.72, -0.3]];
  const DIPPER_LINKS = [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6]];
  const MANUALS = ["本草藥理真經", "萬化分子譜", "蛋白靶點錄", "經脈通路圖", "生化反應訣", "腫瘤基因秘錄", "細胞依存心法"];
  const STAR_NAMES = ["天樞", "天璇", "天璣", "天權", "玉衡", "開陽", "瑤光"];
  const BOOK_W = 1.5, BOOK_H = 1.95;
  function coverTexture(i) {
    // 封面只畫圖案（青花紋、雙框、縫線、題簽）；資料庫名稱、書名、星名都用 HTML 疊上，才不會糊（v1.46.8）
    const W = 512, H = 666, c = document.createElement("canvas"); c.width = W; c.height = H;
    const x = c.getContext("2d");
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, "rgba(46,104,206,.4)"); g.addColorStop(1, "rgba(22,62,140,.48)");
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    x.strokeStyle = "rgba(255,255,255,.16)"; x.lineWidth = 4;
    for (let k = 0; k < 6; k++) {
      const cy = 150 + k * 70, cx = 110 + (k % 2) * 70;
      x.beginPath(); x.arc(cx, cy, 30, Math.PI, 0); x.arc(cx + 46, cy, 16, Math.PI, 0); x.stroke();
    }
    x.strokeStyle = "rgba(255,255,255,.95)"; x.lineWidth = 6; x.strokeRect(16, 16, W - 32, H - 32);
    x.lineWidth = 2; x.strokeRect(30, 30, W - 60, H - 60);
    x.strokeStyle = "#fff"; x.lineWidth = 4;
    for (let k = 0; k < 5; k++) { const y = 56 + k * ((H - 112) / 4); x.beginPath(); x.moveTo(0, y); x.lineTo(40, y); x.stroke(); x.beginPath(); x.arc(40, y, 5, 0, Math.PI * 2); x.fillStyle = "#fff"; x.fill(); }
    // 白色題簽（書名用 HTML 疊上，見 bookLabels）
    x.fillStyle = "rgba(247,250,255,.5)"; x.fillRect(W - 150, 132, 76, 360); x.strokeStyle = "rgba(255,255,255,.8)"; x.lineWidth = 3; x.strokeRect(W - 144, 140, 64, 344);
    const tex = new T.CanvasTexture(c); tex.encoding = T.sRGBEncoding; tex.anisotropy = 8;
    return tex;
  }
  const DIP = { S: 4.9, rot: -0.04, x0: FURN_X - 7.2, y0: 11.8 };   // 天樞的位置、星圖縮放與旋轉（見上方說明）
  const starPos = DIPPER.map(([dx, dy]) => {
    const c = Math.cos(DIP.rot), s = Math.sin(DIP.rot);
    return new T.Vector3(DIP.x0 + (dx * c - dy * s) * DIP.S, DIP.y0 + (dx * s + dy * c) * DIP.S, 0);
  });
  // 星名直書在書的左側（放在書下方會擠到下一顆星，見上方說明）
  function starLabel(name) {
    const cjk = /[\u4e00-\u9fff\uac00-\ud7af]/.test(tr(name));
    return htmlLabel([name], 0.3, { color: "#ffe9b0", bg: "rgba(10,22,48,.85)", vertical: cjk, cls: "l3d-lab-star", minPx: 13, maxPx: 22 });
  }
  const plaques = DBS.map(([name, role, color], i) => {
    const grp = new T.Group(); grp.position.copy(starPos[i]); scene.add(grp);   // 每本一組：書、光暈、星點、星名，整組面向鏡頭
    const pageMat = new T.MeshStandardMaterial({ color: 0xf2f6ff, roughness: 0.8, transparent: true, opacity: 0.35, depthWrite: false });
    const backMat = new T.MeshStandardMaterial({ color: 0x1d4c9c, roughness: 0.6, transparent: true, opacity: 0.3, depthWrite: false });
    const cover = new T.MeshBasicMaterial({ map: coverTexture(i), transparent: true, opacity: 0.94, toneMapped: false, depthWrite: false });
    const book = new T.Mesh(new T.BoxGeometry(BOOK_W, BOOK_H, 0.22), [pageMat, backMat, pageMat, pageMat, cover, backMat]);
    book.userData.pick = { type: "db", i }; grp.add(book);
    const g = glow(0x9cc6ff, 3.2, 0.12); g.position.z = -0.3; grp.add(g);
    const star = glow(0xffffff, 0.8, 0.9); star.position.y = BOOK_H / 2 + 0.28; grp.add(star);
    const nameLab = starLabel(STAR_NAMES[i]); nameLab.position.set(-BOOK_W / 2 - 0.42, 0, 0); grp.add(nameLab);
    // 封面上的字：資料庫名稱（下方、粗白字）與書名（右側題簽、直書；畫面太小時不顯示，以免變成看不清的小點）
    const dbLab = htmlLabel([name], 0.3, { cls: "l3d-lab-db", minPx: 13, maxPx: 26 }); dbLab.position.set(-0.05, -BOOK_H * 0.33, 0.15); book.add(dbLab);
    if (/[\u4e00-\u9fff\uac00-\ud7af]/.test(tr(MANUALS[i]))) {      // 英文書名太長放不進題簽，只在介紹視窗顯示
      const ttl = htmlLabel([MANUALS[i]], 0.17, { cls: "l3d-lab-title", vertical: true, hideBelow: 9.5, minPx: 9.5, maxPx: 16 });
      ttl.position.set(BOOK_W * 0.3, BOOK_H * 0.05, 0.15); book.add(ttl);
    }
    return { m: book, grp, g, star, cover, pageMat, backMat, nameLab, near: 0 };
  });
  // 斗形連線：連在書頂的星點上（固定）
  const dipperLines = new T.LineSegments(new T.BufferGeometry().setFromPoints(DIPPER_LINKS.flatMap(([a, b]) =>
    [starPos[a].clone().setY(starPos[a].y + BOOK_H / 2 + 0.28), starPos[b].clone().setY(starPos[b].y + BOOK_H / 2 + 0.28)])),
    new T.LineBasicMaterial({ color: 0xdbe9ff, transparent: true, opacity: 0.6, toneMapped: false }));
  scene.add(dipperLines);
  const dipperLabel = sprite(["北斗七星・七大國際資料庫"], 0.55, { color: "#cfe2ff" });
  dipperLabel.position.set(starPos[6].x, starPos[6].y - BOOK_H / 2 - 0.55, 0); scene.add(dipperLabel);
  const _v = new T.Vector3();
  let mouseX = -1e4, mouseY = -1e4;                        // 滑鼠的畫面座標（靠近發光用）

  // ---------------- 上層：候選分子（球棍模型）＋發射平台 ----------------
  const PLAT_Y = FURN_Y + 2.6;
  const platform = new T.Group(); platform.position.set(FURN_X, PLAT_Y, 0); scene.add(platform);
  const platMat = new T.MeshStandardMaterial({ color: 0x1b3b40, metalness: 0.9, roughness: 0.3, emissive: 0x0a2a30, emissiveIntensity: 0.6 });
  const disk = new T.Mesh(new T.CylinderGeometry(1.5, 1.7, 0.22, 48), platMat); platform.add(disk);
  const ringGlowMat = new T.MeshBasicMaterial({ color: 0x5fd4ff, transparent: true, opacity: 0.9, toneMapped: false });
  const ring1 = new T.Mesh(new T.TorusGeometry(1.62, 0.03, 8, 80), ringGlowMat); ring1.rotation.x = Math.PI / 2; ring1.position.y = 0.12; platform.add(ring1);
  // 發射砲管：指向左方的標靶
  const barrelPivot = new T.Group(); barrelPivot.position.set(0, 0.35, 0); platform.add(barrelPivot);
  const barrel = new T.Mesh(new T.CylinderGeometry(0.22, 0.32, 2.1, 20), platMat); barrel.rotation.z = Math.PI / 2; barrel.position.x = -1.05; barrelPivot.add(barrel);
  [0.25, 0.75, 1.25].forEach((d) => { const r = new T.Mesh(new T.TorusGeometry(0.27, 0.035, 8, 24), ringGlowMat); r.rotation.y = Math.PI / 2; r.position.x = -d - 0.4; barrelPivot.add(r); });
  const muzzle = new T.Object3D(); muzzle.position.set(-2.15, 0, 0); barrelPivot.add(muzzle);
  const muzzleFlash = glow(0x9fe8ff, 2.4, 0); muzzle.add(muzzleFlash);
  const beamUp = new T.Mesh(new T.CylinderGeometry(0.5, 0.9, PLAT_Y - FURN_Y - 1.2, 24, 1, true),
    new T.MeshBasicMaterial({ color: 0xe0a24a, transparent: true, opacity: 0.12, blending: T.AdditiveBlending, side: T.DoubleSide, depthWrite: false, toneMapped: false }));
  beamUp.position.set(FURN_X, (PLAT_Y + FURN_Y + 1.2) / 2, 0); scene.add(beamUp);

  function buildMolecule() {
    const g = new T.Group();
    const C = new T.MeshStandardMaterial({ color: 0xd9e3e0, metalness: 0.2, roughness: 0.3, emissive: 0x334448, emissiveIntensity: 0.5 });
    const O = new T.MeshStandardMaterial({ color: 0xff6b5e, roughness: 0.3, emissive: 0x5a1410, emissiveIntensity: 0.6 });
    const N = new T.MeshStandardMaterial({ color: 0x5fd4ff, roughness: 0.3, emissive: 0x0d3a50, emissiveIntensity: 0.6 });
    const bond = new T.MeshStandardMaterial({ color: 0xe2b866, metalness: 0.6, roughness: 0.3, emissive: 0x3a2508, emissiveIntensity: 0.6 });
    const atoms = [];
    const add = (p, mat, r) => { const a = new T.Mesh(new T.SphereGeometry(r, 18, 14), mat); a.position.copy(p); g.add(a); atoms.push(a); return p; };
    const link = (a, b) => {
      const d = new T.Vector3().subVectors(b, a), len = d.length();
      const c = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, len, 8), bond);
      c.position.copy(a).addScaledVector(d, 0.5); c.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), d.normalize()); g.add(c);
    };
    const ring = [], ring2 = [];
    for (let k = 0; k < 6; k++) { const a = k * Math.PI / 3; ring.push(add(new T.Vector3(Math.cos(a) * 0.7, Math.sin(a) * 0.7, 0), C, 0.2)); }
    for (let k = 0; k < 6; k++) link(ring[k], ring[(k + 1) % 6]);
    for (let k = 0; k < 6; k++) { const a = k * Math.PI / 3; ring2.push(new T.Vector3(1.21 + Math.cos(a + Math.PI / 6) * 0.0, 0, 0)); }
    const o1 = add(new T.Vector3(-1.35, 0.35, 0.15), O, 0.22); link(ring[3], o1);
    const n1 = add(new T.Vector3(1.4, -0.3, -0.1), N, 0.22); link(ring[0], n1);
    const c2 = add(new T.Vector3(2.0, 0.25, 0.2), C, 0.2); link(n1, c2);
    const o2 = add(new T.Vector3(0.4, 1.35, -0.2), O, 0.22); link(ring[1], o2);
    const c3 = add(new T.Vector3(-0.5, -1.35, 0.25), C, 0.2); link(ring[4], c3);
    return g;
  }
  const molecule = buildMolecule(); molecule.position.set(FURN_X, PLAT_Y + 1.7, 0); molecule.scale.setScalar(0.001); scene.add(molecule);
  const molGlow = glow(0xe2b866, 4.5, 0); molGlow.position.copy(molecule.position); scene.add(molGlow);
  const molLabel = sprite(["候選分子"], 0.48, { color: "#e2b866" }); molLabel.position.set(FURN_X + 2.4, PLAT_Y + 2.4, 0); scene.add(molLabel);

  // ---------------- 最左側：人體（最後會發出聖光） ----------------
  const BODY_X = -20.2;                        // 人在最左、DNA 在其右，兩者間距 v1.46.7 拉寬；合計約佔畫面左側 20%
  const bodyG = new T.Group(); bodyG.position.set(BODY_X, -0.5, 0); scene.add(bodyG);
  const holo = new T.MeshBasicMaterial({ color: 0x5fd4ff, wireframe: true, transparent: true, opacity: 0.32, toneMapped: false });
  const holoFill = new T.MeshBasicMaterial({ color: 0x0d3a50, transparent: true, opacity: 0.25, depthWrite: false, toneMapped: false });
  const part = (geo, x, y, z, rz) => {
    const a = new T.Mesh(geo, holoFill), b = new T.Mesh(geo, holo);
    [a, b].forEach((m) => { m.position.set(x, y, z || 0); if (rz) m.rotation.z = rz; bodyG.add(m); });
  };
  part(new T.SphereGeometry(0.55, 16, 12), 0, 7.0);
  part(new T.CylinderGeometry(0.18, 0.2, 0.4, 10), 0, 6.3);
  part(new T.CylinderGeometry(1.05, 0.8, 2.6, 14, 4), 0, 4.8);
  part(new T.CylinderGeometry(0.8, 0.85, 1.0, 14, 2), 0, 3.0);
  [-1, 1].forEach((s) => {
    part(new T.CylinderGeometry(0.22, 0.18, 2.2, 10, 3), s * 1.38, 4.85, 0, s * 0.18);
    part(new T.CylinderGeometry(0.17, 0.14, 2.0, 10, 3), s * 1.62, 2.75, 0, s * 0.06);
    part(new T.CylinderGeometry(0.34, 0.26, 2.6, 10, 3), s * 0.45, 1.25, 0);
    part(new T.CylinderGeometry(0.25, 0.18, 2.4, 10, 3), s * 0.5, -1.0, 0);
  });
  const chestGlow = glow(0x5fd4ff, 2.8, 0); chestGlow.position.set(0, 4.8, 0.9); bodyG.add(chestGlow);
  const bodyLabel = sprite(["受檢者"], 0.45, { color: "#5fd4ff" }); bodyLabel.position.set(BODY_X, -1.45, 0.5); scene.add(bodyLabel);
  const HOLO_CYAN = lin(0x5fd4ff), HOLO_GOLD = lin(0xffe7a8);

  // ---------------- DNA 報告：從人體取出，向右推展成雙股螺旋 ----------------
  const DNA_X = -15.4, DNA_Y = -0.3, RUNGS = 34, STEP = 0.24;
  const GENE_K = 22;                                   // 致病基因所在的鹼基位置
  const GENE_Y = DNA_Y + GENE_K * STEP;
  const dna = new T.Group(); scene.add(dna);
  const dnaA = new T.MeshStandardMaterial({ color: 0xff6b5e, emissive: 0x5a1410, emissiveIntensity: 0.8, roughness: 0.4 });
  const dnaB = new T.MeshStandardMaterial({ color: 0x5fd4ff, emissive: 0x0d3a50, emissiveIntensity: 0.8, roughness: 0.4 });
  const rungCols = [0xff6b5e, 0xe2b866, 0x5fd4ff, 0x6fe0b0];
  const dnaRungs = [];
  for (let k = 0; k < RUNGS; k++) {
    const y = k * STEP, a = k * 0.42, r = 0.62;
    const p1 = new T.Vector3(Math.cos(a) * r, y, Math.sin(a) * r), p2 = new T.Vector3(-Math.cos(a) * r, y, -Math.sin(a) * r);
    const s1 = new T.Mesh(new T.SphereGeometry(0.1, 10, 8), dnaA); s1.position.copy(p1); dna.add(s1);
    const s2 = new T.Mesh(new T.SphereGeometry(0.1, 10, 8), dnaB); s2.position.copy(p2); dna.add(s2);
    const d = new T.Vector3().subVectors(p2, p1);
    const rungMat = new T.MeshBasicMaterial({ color: lin(rungCols[k % 4]), transparent: true, opacity: 0.55, toneMapped: false });
    const rg = new T.Mesh(new T.CylinderGeometry(0.03, 0.03, d.length(), 6), rungMat);
    rg.position.copy(p1).addScaledVector(d, 0.5); rg.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), d.clone().normalize());
    rg.userData.base = lin(rungCols[k % 4]);
    dna.add(rg); dnaRungs.push(rg);
  }
  const dnaLabel = sprite(["DNA 報告"], 0.6, { color: "#5fd4ff" }); dnaLabel.position.set(DNA_X, DNA_Y + RUNGS * STEP + 0.9, 0); scene.add(dnaLabel);
  // 掃描環：沿螺旋由上往下
  const scanRing = new T.Mesh(new T.TorusGeometry(1.05, 0.03, 8, 64), new T.MeshBasicMaterial({ color: 0x5fd4ff, transparent: true, opacity: 0, toneMapped: false }));
  scanRing.rotation.x = Math.PI / 2; scene.add(scanRing);
  const scanDisc = new T.Mesh(new T.CircleGeometry(1.05, 40), new T.MeshBasicMaterial({ color: 0x5fd4ff, transparent: true, opacity: 0, side: T.DoubleSide, depthWrite: false, toneMapped: false }));
  scanDisc.rotation.x = -Math.PI / 2; scene.add(scanDisc);
  // 致病基因在螺旋上的位置
  const geneGlow = glow(0xff6b5e, 2.6, 0); geneGlow.position.set(DNA_X, GENE_Y, 0); scene.add(geneGlow);
  let geneSprite = null;
  function setGene(name) {
    if (geneSprite) { scene.remove(geneSprite); geneSprite.material.map.dispose(); geneSprite.material.dispose(); }
    geneSprite = sprite([name, "致病基因"], 0.85, { color: "#ff6b5e", bg: "rgba(40,8,6,.85)" });
    geneSprite.position.set(DNA_X + 2.5, GENE_Y + 1.5, 0.6); geneSprite.material.opacity = 0; scene.add(geneSprite);
    hud.gene.textContent = name;
  }

  // ---------------- 靶點：標在 DNA 螺旋的致病基因上 ----------------
  const TARGET = new T.Vector3(DNA_X, GENE_Y, 1.0);
  const target = new T.Group(); target.position.copy(TARGET); scene.add(target);
  const retMat = new T.MeshBasicMaterial({ color: 0xff6b5e, transparent: true, opacity: 0, toneMapped: false, side: T.DoubleSide });
  const ret1 = new T.Mesh(new T.RingGeometry(1.35, 1.41, 64), retMat); target.add(ret1);
  const ret2 = new T.Mesh(new T.RingGeometry(0.92, 0.97, 64, 1, 0, Math.PI * 1.6), retMat); target.add(ret2);
  [0, 1, 2, 3].forEach((k) => {
    const t = new T.Mesh(new T.PlaneGeometry(0.06, 0.45), retMat); const a = k * Math.PI / 2;
    t.position.set(Math.cos(a) * 1.62, Math.sin(a) * 1.62, 0); t.rotation.z = a + Math.PI / 2; target.add(t);
  });
  const targetLabel = sprite(["靶點蛋白"], 0.45, { color: "#ff6b5e" }); targetLabel.position.set(DNA_X, GENE_Y - 2.0, 1.0); scene.add(targetLabel);
  // 蛋白：凹凸的球團，會隨每一發命中逐步虛弱（縮小、褪色、鬆散）
  const proteinMat = new T.MeshStandardMaterial({ color: 0xff6b5e, roughness: 0.45, metalness: 0.1, emissive: 0x5a1410, emissiveIntensity: 0.8, transparent: true });
  const P_HOT = new T.Color(0xff6b5e), P_WEAK = new T.Color(0x6f7d7b);
  const protein = new T.Group(); protein.position.copy(TARGET); scene.add(protein);
  const blobs = [];
  for (let k = 0; k < 22; k++) {
    const u = Math.acos(2 * ((k * 0.618) % 1) - 1), v = k * 2.4;
    const r = 0.38 + 0.12 * ((k * 7) % 5) / 5;
    const b = new T.Mesh(new T.SphereGeometry(0.24 + 0.09 * ((k * 3) % 4) / 4, 12, 10), proteinMat);
    b.position.set(r * Math.sin(u) * Math.cos(v), r * Math.cos(u), r * Math.sin(u) * Math.sin(v));
    b.userData.home = b.position.clone();
    protein.add(b); blobs.push(b);
  }
  const proteinGlow = glow(0xff6b5e, 2.8, 0.5); protein.add(proteinGlow);

  // ---------------- 瞄準光線＋逐一發射的候選分子 ----------------
  const SHOTS = 5, SHOT_GAP = 0.55, SHOT_FLIGHT = 0.55, AIM_AT = 5.9, FIRE_AT = 6.5;
  const LAST_HIT = FIRE_AT + (SHOTS - 1) * SHOT_GAP + SHOT_FLIGHT;
  const aimMat = new T.MeshBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0, blending: T.AdditiveBlending, depthWrite: false, toneMapped: false });
  const aimBeam = new T.Mesh(new T.CylinderGeometry(0.035, 0.035, 1, 8, 1, true), aimMat); scene.add(aimBeam);
  const aimCore = new T.Mesh(new T.CylinderGeometry(0.11, 0.11, 1, 8, 1, true), aimMat.clone()); scene.add(aimCore);
  const aimDot = glow(0x9fe8ff, 1.4, 0); aimDot.position.copy(TARGET); scene.add(aimDot);
  const shotGeo = new T.IcosahedronGeometry(0.2, 1);
  const shotMat = new T.MeshBasicMaterial({ color: 0xffe2a0, toneMapped: false });
  const shots = [...Array(SHOTS)].map(() => {
    const m = new T.Mesh(shotGeo, shotMat); const g = glow(0xe2b866, 1.6, 0.9); m.add(g); m.visible = false; scene.add(m);
    const trailN = 18, tg = new T.BufferGeometry(), tp = new Float32Array(trailN * 3);
    tg.setAttribute("position", new T.BufferAttribute(tp, 3));
    const trail = new T.Points(tg, new T.PointsMaterial({ map: glowTex, color: 0xe2b866, size: 0.35, transparent: true, opacity: 0.8,
      blending: T.AdditiveBlending, depthWrite: false, toneMapped: false }));
    trail.visible = false; scene.add(trail);
    return { m, trail, tp, trailN };
  });
  const hitFlash = glow(0xffffff, 4, 0); hitFlash.position.copy(TARGET); scene.add(hitFlash);
  const shock = new T.Mesh(new T.RingGeometry(0.9, 1.0, 64), new T.MeshBasicMaterial({ color: 0xffe2a0, transparent: true, opacity: 0, side: T.DoubleSide, toneMapped: false }));
  shock.position.copy(TARGET); scene.add(shock);
  const weakLabel = sprite(["靶點蛋白受抑制"], 0.6, { color: "#c9d6d3", bg: "rgba(10,20,22,.8)" });
  weakLabel.position.set(DNA_X + 2.2, GENE_Y - 1.2, 1.2); weakLabel.material.opacity = 0; scene.add(weakLabel);

  // ---------------- 聖光：整個人體發光，光束從天而降 ----------------
  const victory = new T.Group(); victory.position.set(BODY_X, -2.6, 0); scene.add(victory);
  const rays = [];
  for (let k = 0; k < 9; k++) {
    const g = new T.ConeGeometry(1.4 + (k % 3) * 0.45, 20, 28, 1, true); g.translate(0, 10, 0);   // 頂端窄、往下變寬
    const r = new T.Mesh(g, new T.MeshBasicMaterial({ color: 0xfff1c0, transparent: true, opacity: 0, blending: T.AdditiveBlending,
      side: T.DoubleSide, depthWrite: false, toneMapped: false }));
    r.rotation.z = (k - 4) * 0.035; r.rotation.x = ((k * 5) % 3 - 1) * 0.03; victory.add(r); rays.push(r);
  }
  const halo = new T.Mesh(new T.TorusGeometry(0.85, 0.05, 8, 64), new T.MeshBasicMaterial({ color: 0xfff1c0, transparent: true, opacity: 0, toneMapped: false }));
  halo.position.set(0, 10.6, 0); halo.rotation.x = Math.PI / 2.4; victory.add(halo);
  const bodyAura = glow(0xffe7a8, 12, 0); bodyAura.position.set(0, 6.6, -0.5); victory.add(bodyAura);
  const SPARK = 160, sparkGeo = new T.BufferGeometry(), sparkPos = new Float32Array(SPARK * 3), sparkSeed = new Float32Array(SPARK);
  for (let i = 0; i < SPARK; i++) sparkSeed[i] = Math.random();
  sparkGeo.setAttribute("position", new T.BufferAttribute(sparkPos, 3));
  const sparks = new T.Points(sparkGeo, new T.PointsMaterial({ map: glowTex, color: 0xfff1c0, size: 0.22, transparent: true, opacity: 0,
    blending: T.AdditiveBlending, depthWrite: false, toneMapped: false }));
  victory.add(sparks);
  const winLabel = sprite(["候選分子命中靶點", "研究流程示意"], 0.85, { color: "#fff1c0", bg: "rgba(30,24,6,.75)" });
  winLabel.position.set(0, 12.2, 0.4); winLabel.material.opacity = 0; victory.add(winLabel);

  // ---------------- 後製光暈（bloom），載入失敗就直接渲染 ----------------
  let composer = null, bloom = null;
  try {
    if (T.EffectComposer && T.UnrealBloomPass) {
      composer = new T.EffectComposer(renderer);
      composer.addPass(new T.RenderPass(scene, camera));
      bloom = new T.UnrealBloomPass(new T.Vector2(1, 1), 0.75, 0.5, 0.7);
      composer.addPass(bloom);
    }
  } catch (e) { composer = null; }

  // ---------------- 尺寸：登入框在右側，場景往左偏 ----------------
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const pad = Math.max(32, w * 0.04);
    cardZone = Math.max(340 + pad + 24, Math.min(460, w * 0.36) + pad);
    viewW = w; viewH = h;
    camera.userData.dist = 29;
    camera.updateProjectionMatrix();
    if (composer) { composer.setSize(w, h); bloom.setSize(w, h); }
    hud.root.style.setProperty("--art-w", (loginOpen ? w - cardZone : w) + "px");
  }
  // 面板開啟前場景置中；開啟後整個場景縮小移到左側（每幀平滑移動）
  let cardZone = 0, viewW = 1, viewH = 1, panelK = 0, loginOpen = false, hover = null;
  window.addEventListener("resize", resize); resize();

  // ---------------- 點選：熔爐開登入框、秘笈與藥田開介紹 ----------------
  const pickables = [];
  scene.traverse((o) => { if (o.userData && o.userData.pick) pickables.push(o); });
  const ray = new T.Raycaster(), ndc = new T.Vector2();
  function pickAt(ev) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(pickables, false)[0];
    return hit ? hit.object.userData.pick : null;
  }
  canvas.addEventListener("pointermove", (ev) => {
    if (!active) return;
    hover = pickAt(ev); mouseX = ev.clientX; mouseY = ev.clientY;
    canvas.style.cursor = hover ? "pointer" : "default";
  });
  canvas.addEventListener("pointerleave", () => { hover = null; mouseX = mouseY = -1e4; canvas.style.cursor = "default"; });
  canvas.addEventListener("click", (ev) => {
    if (!active) return;
    const p = pickAt(ev);
    if (p && hud.onPick) hud.onPick(p);
  });

  // ---------------- 時間軸（一輪 12 秒） ----------------
  // 0.0–1.6 從人體取出 DNA 報告並向右推展 → 1.6–3.2 沿螺旋掃描、致病基因亮起 → 3.2–4.2 在螺旋上標定靶點
  // 1.0–5.4 熔爐整合七大資料庫 → 4.6–5.8 提煉候選分子 → 5.9 瞄準光線 → 6.5–9.25 逐一發射、蛋白逐步虛弱
  // 9.3–11.2 人體發出聖光 → 11.2–12 收回、換下一個基因
  const steps = hud.steps;
  const STEP_AT = [0, 3.2, 1.0, 4.6, AIM_AT, LAST_HIT];
  const STEP_END = [3.2, 4.2, 5.4, 5.9, LAST_HIT, 11.2];
  let cycle = -1, clockT = 0, paused = false, last = performance.now(), active = true;
  const ease = (x) => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x);
  const seg = (t, a, b) => ease((t - a) / (b - a));
  const lerpV = (a, b, k) => new T.Vector3().lerpVectors(a, b, k);
  const muzzleWorld = () => muzzle.getWorldPosition(new T.Vector3());
  function shotPos(k) {
    // 沿瞄準光線前進，略帶弧度
    const a = muzzleWorld(), b = TARGET.clone(), p = lerpV(a, b, k);
    p.y += Math.sin(k * Math.PI) * 0.6;
    return p;
  }
  const UP = new T.Vector3(0, 1, 0);
  function placeBeam(mesh, a, b) {
    const d = new T.Vector3().subVectors(b, a), len = d.length();
    mesh.position.copy(a).addScaledVector(d, 0.5); mesh.scale.set(1, len, 1);
    mesh.quaternion.setFromUnitVectors(UP, d.normalize());
  }
  const bodyHome = new T.Vector3(BODY_X, 4.0, 0.9), dnaHome = new T.Vector3(DNA_X, DNA_Y, 0);
  const tmpCol = new T.Color();

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!active) { requestAnimationFrame(frame); return; }
    if (!paused && !document.hidden) clockT += dt;
    const total = reduceMotion ? 10.2 : clockT;               // 減少動態效果：停在聖光畫面
    const c = Math.floor(total / LOOP), t = total - c * LOOP;
    if (c !== cycle) { cycle = c; setGene(GENES[c % GENES.length]); }

    // 鏡頭：緩慢環繞（可關閉）
    const dist = camera.userData.dist || 31;
    const ang = orbitOn && !reduceMotion ? Math.sin(total * 0.12) * 0.06 : 0;   // 擺幅小一點，左側的人與 DNA 不會被切到
    camera.position.set(CAM_TARGET.x + Math.sin(ang) * dist, CAM_TARGET.y + 3.2 + Math.sin(total * 0.09) * 0.6, Math.cos(ang) * dist);
    camera.lookAt(CAM_TARGET);
    // 右側面板（登入框或介紹視窗）打開時：整個場景等比縮小、移到面板左邊，不被面板擋住
    panelK += ((loginOpen ? 1 : 0) - panelK) * Math.min(1, dt * 4);
    const zf = 1 - panelK * cardZone / viewW;
    camera.fov = 2 * Math.atan(Math.tan(BASE_FOV * Math.PI / 360) / zf) * 180 / Math.PI;
    camera.setViewOffset(viewW, viewH, panelK * cardZone / 2, 0, viewW, viewH);

    // 中藥盤自轉、藥氣上升（熔煉階段更旺）
    herbs.rotation.y = total * 0.08;
    const smelt = Math.max(0.35, seg(t, 0.5, 1.4) * (1 - seg(t, 5.6, 6.6)));
    for (let i = 0; i < STREAM; i++) {
      const s = streamSeed[i], k = (total * 0.32 + s) % 1;
      const r = (1 - k) * (1.3 + 4.2 * ((s * 7.3) % 1)) + k * 0.7, a = s * 40 + k * 7 + total * 0.5;
      streamPos[i * 3] = FURN_X + Math.cos(a) * r; streamPos[i * 3 + 1] = -0.2 + k * (FURN_Y + 1.4); streamPos[i * 3 + 2] = Math.sin(a) * r;
    }
    streamGeo.attributes.position.needsUpdate = true; streamMat.opacity = 0.25 + 0.7 * smelt;
    for (let i = 0; i < FIRE; i++) {
      const s = fireSeed[i], k = (total * (0.6 + s * 0.6) + s) % 1, a = s * 30;
      firePos[i * 3] = Math.cos(a) * (0.9 - k * 0.6) * (0.4 + s); firePos[i * 3 + 1] = 1.1 + k * 1.6; firePos[i * 3 + 2] = Math.sin(a) * (0.9 - k * 0.6) * (0.4 + s);
    }
    fireGeo.attributes.position.needsUpdate = true;
    fireLight.intensity = 1.6 + smelt * 2.2 + Math.sin(total * 13) * 0.25;
    mouthGlow.material.opacity = 0.45 + 0.5 * smelt;

    // 七本秘笈：固定在熔爐上方，熔煉時依序點亮（1.0–5.2 秒）；滑鼠越靠近越亮，指到時放大
    const rect = canvas.getBoundingClientRect();
    plaques.forEach((p, i) => {
      p.grp.quaternion.copy(camera.quaternion);
      p.grp.position.y = starPos[i].y + 0.06 * Math.sin(total * 1.3 + i);        // 輕輕浮動
      _v.copy(p.grp.position).project(camera);
      const px = rect.left + (_v.x + 1) / 2 * rect.width, py = rect.top + (1 - _v.y) / 2 * rect.height;
      const near = Math.max(0, 1 - Math.hypot(px - mouseX, py - mouseY) / 170);
      p.near += (near - p.near) * Math.min(1, dt * 8);
      const on = seg(t, 1.0 + i * 0.6, 1.3 + i * 0.6) * (1 - seg(t, 10.5, 11.5));
      const hov = hover && hover.type === "db" && hover.i === i ? 1 : 0;
      const lit = Math.max(on * 0.6, p.near, hov);
      p.cover.opacity = 0.9 + 0.1 * lit;
      p.g.material.opacity = 0.1 + 0.85 * lit; p.g.scale.setScalar(3.2 + 1.6 * lit);
      p.star.material.opacity = 0.6 + 0.4 * Math.max(lit, Math.sin(total * 3 + i));
      const sc = 1 + 0.08 * p.near + 0.12 * hov; p.m.scale.lerp(new T.Vector3(sc, sc, sc), 0.2);
    });
    // 熔爐：滑過時光環亮起；登入框還沒開時提示閃爍
    const furnHov = hover && hover.type === "furnace" ? 1 : 0;
    furnHalo.material.opacity = 0.25 * (loginOpen ? 0 : 1) * (0.5 + 0.5 * Math.sin(total * 4)) + 0.7 * furnHov;
    loginHint.material.opacity = loginOpen ? Math.max(0, loginHint.material.opacity - dt * 2.5) : 0.75 + 0.25 * Math.sin(total * 3);
    bronze.emissiveIntensity = 0.4 + 0.8 * furnHov;
    herbRing.material.opacity = 0.35 + 0.5 * (hover && hover.type === "herbs" ? 1 : 0);

    // 候選分子成形（4.6–5.8）
    const mk = seg(t, 4.6, 5.8) * (1 - seg(t, 11.2, 11.9));
    molecule.scale.setScalar(Math.max(0.001, mk * 0.8)); molecule.rotation.y = total * 0.9; molecule.rotation.x = Math.sin(total * 0.7) * 0.3;
    molGlow.material.opacity = 0.7 * mk; molLabel.material.opacity = mk;
    ring1.material.opacity = 0.4 + 0.5 * mk;
    const aim = new T.Vector3().subVectors(TARGET, new T.Vector3(FURN_X, PLAT_Y + 0.35, 0));
    barrelPivot.rotation.z = -Math.atan2(aim.y, -aim.x);

    // 取出 DNA 報告（0–1.6）：從胸口浮出、縮小 → 向右推展成完整螺旋
    const ex = seg(t, 0.15, 1.6) * (1 - seg(t, 11.3, 11.95));
    chestGlow.material.opacity = 0.9 * seg(t, 0, 0.4) * (1 - seg(t, 0.9, 1.5));
    dna.position.copy(lerpV(bodyHome, dnaHome, ex)); dna.position.z = 0.9 * (1 - ex);
    dna.scale.setScalar(0.18 + 0.82 * ex); dna.rotation.y = total * 0.6;
    dna.visible = t > 0.1 && t < 11.95;
    dnaLabel.material.opacity = seg(t, 1.2, 1.7) * (1 - seg(t, 11.2, 11.7));

    // 沿螺旋掃描（1.6–3.2），經過致病基因時亮起
    const sk = seg(t, 1.6, 3.0), scanY = DNA_Y + RUNGS * STEP - sk * RUNGS * STEP;
    const scanOn = seg(t, 1.5, 1.7) * (1 - seg(t, 3.0, 3.3));
    scanRing.position.set(DNA_X, scanY, 0); scanDisc.position.set(DNA_X, scanY, 0);
    scanRing.material.opacity = 0.9 * scanOn; scanDisc.material.opacity = 0.1 * scanOn;
    const found = seg(t, 2.15, 2.4) * (1 - seg(t, 11.0, 11.6));
    dnaRungs.forEach((r, k) => {
      const near = ex > 0.95 && Math.abs(DNA_Y + k * STEP - scanY) < 0.3 && scanOn > 0.1;
      const isGene = Math.abs(k - GENE_K) <= 1 && found > 0;
      r.material.color.copy(isGene ? tmpCol.set(0xff6b5e) : r.userData.base);
      r.material.opacity = isGene ? 1 : (near ? 1 : 0.5);
    });
    geneGlow.material.opacity = found * (0.55 + 0.35 * Math.sin(total * 8)) * (1 - 0.6 * seg(t, LAST_HIT, LAST_HIT + 0.6));
    if (geneSprite) geneSprite.material.opacity = seg(t, 2.4, 2.8) * (1 - seg(t, 11.0, 11.6));

    // 在螺旋上標定靶點（3.2–4.2）：準星收縮、蛋白在致病基因位置成形
    target.rotation.z = total * 0.6; ret2.rotation.z = -total * 1.4;
    target.scale.setScalar(1.6 - 0.6 * seg(t, 3.2, 4.2));
    retMat.opacity = 0.85 * seg(t, 3.2, 3.7) * (1 - seg(t, 10.8, 11.5));
    targetLabel.material.opacity = seg(t, 3.4, 3.9) * (1 - seg(t, 10.8, 11.5));

    // 瞄準光線（5.9 起）：從砲口射向靶點，閃爍
    const aimOn = seg(t, AIM_AT, AIM_AT + 0.35) * (1 - seg(t, LAST_HIT, LAST_HIT + 0.4));
    const mw = muzzleWorld();
    placeBeam(aimBeam, mw, TARGET); placeBeam(aimCore, mw, TARGET);
    aimBeam.material.opacity = aimOn * (0.75 + 0.25 * Math.sin(total * 40));
    aimCore.material.opacity = aimOn * 0.12;
    aimDot.material.opacity = aimOn * (0.6 + 0.4 * Math.sin(total * 18));

    // 逐一發射（6.5 起，每 0.55 秒一發）；每發命中，蛋白虛弱一級
    let hitBoost = 0, hits = 0;
    shots.forEach((s, i) => {
      const t0 = FIRE_AT + i * SHOT_GAP, k = (t - t0) / SHOT_FLIGHT;
      const flying = k >= 0 && k <= 1;
      s.m.visible = s.trail.visible = flying;
      if (flying) {
        s.m.position.copy(shotPos(k)); s.m.rotation.x += 0.3; s.m.rotation.y += 0.25;
        for (let j = 0; j < s.trailN; j++) { const p = shotPos(Math.max(0, k - j * 0.025)); s.tp[j * 3] = p.x; s.tp[j * 3 + 1] = p.y; s.tp[j * 3 + 2] = p.z; }
        s.trail.geometry.attributes.position.needsUpdate = true;
      }
      const since = t - (t0 + SHOT_FLIGHT);
      if (since >= 0) hits++;
      if (since >= 0 && since < 0.3) hitBoost = Math.max(hitBoost, 1 - since / 0.3);
      if (k >= 0 && k < 0.15) muzzleFlash.material.opacity = Math.max(muzzleFlash.material.opacity, 1 - k / 0.15);
    });
    muzzleFlash.material.opacity *= 0.82;
    barrel.position.x = -1.05 + 0.14 * muzzleFlash.material.opacity;
    hitFlash.material.opacity = hitBoost * 0.7;
    shock.material.opacity = hitBoost * 0.8; shock.scale.setScalar(1 + (1 - hitBoost) * 2.2); shock.lookAt(camera.position);

    // 蛋白：命中幾發就虛弱幾成（縮小、褪成灰色、結構鬆散、光暈熄滅）
    const weak = Math.min(1, hits / SHOTS) * (1 - seg(t, 11.3, 11.9));
    const appear = seg(t, 3.4, 4.1) * (1 - seg(t, 11.3, 11.9));
    protein.visible = appear > 0.01;
    protein.scale.setScalar(appear * (1 - 0.5 * weak) * (1 + hitBoost * 0.12));
    protein.rotation.y = total * (0.8 - 0.6 * weak); protein.rotation.x = total * 0.35;
    proteinMat.color.copy(P_HOT).lerp(P_WEAK, weak); proteinMat.emissiveIntensity = 0.8 * (1 - weak) + 0.6 * hitBoost;
    proteinMat.opacity = 1 - 0.45 * weak;
    blobs.forEach((b, i) => {
      const jitter = hitBoost * 0.12 * Math.sin(i * 12.9 + total * 60);
      b.position.copy(b.userData.home).multiplyScalar(1 + 0.35 * weak + jitter);
    });
    proteinGlow.material.opacity = 0.5 * (1 - weak) + hitBoost * 0.5;
    weakLabel.material.opacity = seg(t, LAST_HIT + 0.1, LAST_HIT + 0.5) * (1 - seg(t, 10.8, 11.4));

    // 聖光（9.3–11.2）：整個人體轉為金色發光，光束從天而降、頭頂光環、光點上升
    const v = seg(t, LAST_HIT + 0.05, LAST_HIT + 0.9) * (1 - seg(t, 10.8, 11.7));
    holo.color.copy(HOLO_CYAN).lerp(HOLO_GOLD, v); holo.opacity = 0.32 + 0.38 * v;
    holoFill.color.copy(lin(0x0d3a50)).lerp(lin(0x8a6a20), v); holoFill.opacity = 0.25 + 0.3 * v;
    rays.forEach((r, k) => { r.material.opacity = v * (0.028 + 0.016 * Math.sin(total * 2 + k)); r.rotation.y = total * 0.15 + k; });
    halo.material.opacity = v * 0.95; halo.rotation.z = total * 0.8;
    bodyAura.material.opacity = v * 0.26;
    for (let i = 0; i < SPARK; i++) {
      const s = sparkSeed[i], k = (total * 0.3 + s) % 1, a = s * 50;
      sparkPos[i * 3] = Math.cos(a) * (0.8 + s * 2.2); sparkPos[i * 3 + 1] = k * 12; sparkPos[i * 3 + 2] = Math.sin(a) * (0.8 + s * 2.2);
    }
    sparkGeo.attributes.position.needsUpdate = true; sparks.material.opacity = v * 0.95;
    winLabel.material.opacity = seg(t, LAST_HIT + 0.5, LAST_HIT + 1.0) * (1 - seg(t, 10.7, 11.4));

    // HUD 步驟
    steps.forEach((el, i) => {
      el.classList.toggle("on", t >= STEP_AT[i] && t < STEP_END[i]);
      el.classList.toggle("done", t >= STEP_END[i]);
    });

    if (composer) composer.render(); else renderer.render(scene, camera);
    updateLabels();
    if (!reduceMotion) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    setActive(on) { active = on; labelLayer.style.display = on ? "" : "none"; if (on) { last = performance.now(); resize(); } },
    setLoginOpen(on) { loginOpen = on; resize(); },
    seek(s) { clockT = s; },        // 測試用
    pause(on) { paused = on; },     // 測試用
    screenPoints() {                // 測試用：熔爐、七本秘笈、花園前緣、人與 DNA 的螢幕座標
      const rect = canvas.getBoundingClientRect();
      const box = (o, x0, x1, y0, y1) => {          // o 的區域座標矩形 → 畫面 [左, 右, 上, 下]
        const a = at(o, new T.Vector3(x0, y1, 0)), b = at(o, new T.Vector3(x1, y0, 0));
        return [Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])];
      };
      const at = (o, local) => {
        const v = (local || new T.Vector3()).clone(); o.localToWorld(v); v.project(camera);
        return [rect.left + (v.x + 1) / 2 * rect.width, rect.top + (1 - v.y) / 2 * rect.height];
      };
      return { furnace: at(body, new T.Vector3(0, 0.1, 0)), books: plaques.map((p) => at(p.m)),
               herbs: at(herbHit, new T.Vector3(0, -(HERB_R - 0.8), 0)),
               body: at(scene, new T.Vector3(BODY_X + 1.7, 3, 0)), dna: at(scene, new T.Vector3(DNA_X + 0.8, DNA_Y + 4, 0)),
               bookZ: plaques.map(() => 0), glow: plaques.map((p) => p.g.material.opacity),
               // 書（含左側星名與上方星點）與熔爐、平台＋候選分子、砲管的畫面矩形，用來驗證互不重疊
               bookRects: plaques.map((p) => box(p.grp, -BOOK_W / 2 - 0.85, BOOK_W / 2, -BOOK_H / 2, BOOK_H / 2 + 0.4)),
               keepRects: [box(scene, FURN_X - 2.0, FURN_X + 2.0, FURN_Y - 2.0, FURN_Y + 1.4), box(scene, FURN_X - 1.8, FURN_X + 1.8, PLAT_Y - 0.3, PLAT_Y + 3.0),
                           box(scene, FURN_X - 2.6, FURN_X, PLAT_Y, PLAT_Y + 0.7)] };
    },
  };
};

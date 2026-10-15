// 登入頁 3D 研究流程動畫的場景（v1.46.4）。由 js/login-3d.js 在條件符合時延後載入並呼叫 startLogin3D()。
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
  const camera = new T.PerspectiveCamera(42, 1, 0.1, 200);
  const CAM_TARGET = new T.Vector3(-4.6, 4.6, 0);
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
  function sprite(lines, height, opt) {
    const { tex, aspect } = labelTexture(lines, opt);
    const m = new T.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false });
    const s = new T.Sprite(m); s.scale.set(height * aspect, height, 1);
    return s;
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
  const FURN_X = 3.2;
  const herbs = new T.Group(); herbs.position.set(FURN_X, -0.4, 0); scene.add(herbs);
  const leafGeo = new T.SphereGeometry(1, 8, 6); leafGeo.scale(0.16, 0.035, 0.07);
  const leafMat = new T.MeshStandardMaterial({ roughness: 0.55, metalness: 0.15 });
  const herbMesh = new T.InstancedMesh(leafGeo, leafMat, HERB_COUNT);
  const tmpM = new T.Matrix4(), tmpQ = new T.Quaternion(), tmpE = new T.Euler(), tmpC = new T.Color();
  const herbPal = [0xe2b866, 0x6fe0b0, 0xc9de8f, 0xd99a4e, 0x8fd9a6];
  const herbPos = [];
  for (let i = 0; i < HERB_COUNT; i++) {
    const f = i / (HERB_COUNT - 1), r = 1.35 + 4.4 * Math.sqrt(f), a = i * 2.399963;
    const p = new T.Vector3(r * Math.cos(a), 0.08 * Math.sin(i * 1.7), r * Math.sin(a));
    herbPos.push(p);
    tmpE.set(0, -a + Math.PI / 2, 0.15 * Math.sin(i)); tmpQ.setFromEuler(tmpE);
    const sc = 0.85 + 0.6 * ((i * 37) % 11) / 11;
    tmpM.compose(p, tmpQ, new T.Vector3(sc, sc, sc)); herbMesh.setMatrixAt(i, tmpM);
    herbMesh.setColorAt(i, tmpC.setHex(herbPal[i % herbPal.length]).convertSRGBToLinear());
  }
  herbs.add(herbMesh);
  const herbRing = new T.Mesh(new T.RingGeometry(5.9, 6.0, 96), new T.MeshBasicMaterial({ color: 0xe2b866, transparent: true, opacity: 0.35, side: T.DoubleSide }));
  herbRing.rotation.x = -Math.PI / 2; herbs.add(herbRing);
  const herbLabel = sprite(["502 種中藥"], 0.62, { color: "#e2b866" }); herbLabel.position.set(FURN_X, -0.1, 6.9); scene.add(herbLabel);

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
  for (let k = 0; k < 3; k++) {
    const a = k * Math.PI * 2 / 3 + Math.PI / 6;
    const leg = new T.Mesh(new T.CylinderGeometry(0.12, 0.2, 1.7, 10), bronze);
    leg.position.set(Math.cos(a) * 0.95, -1.75, Math.sin(a) * 0.95); leg.rotation.z = Math.cos(a) * 0.12; leg.rotation.x = -Math.sin(a) * 0.12;
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

  // 七塊資料庫銘牌：環繞丹爐旋轉，熔煉時依序點亮
  const dbRing = new T.Group(); dbRing.position.set(FURN_X, FURN_Y + 0.2, 0); scene.add(dbRing);
  const plaques = DBS.map(([name, role, color], i) => {
    const { tex, aspect } = labelTexture([name, role], { size: 56, bg: "rgba(5,16,20,.88)", color });
    const mat = new T.MeshBasicMaterial({ map: tex, transparent: true, side: T.DoubleSide, depthWrite: false, toneMapped: false, opacity: 0.55 });
    const h = 0.78, m = new T.Mesh(new T.PlaneGeometry(h * aspect, h), mat);
    const a = i / DBS.length * Math.PI * 2;
    m.position.set(Math.cos(a) * 4.7, (i % 2 ? 0.55 : -0.35), Math.sin(a) * 4.7);
    const g = glow(new T.Color(color), 2.2, 0); g.position.copy(m.position);
    dbRing.add(m); dbRing.add(g);
    // 銘牌與爐子之間的能量線
    const lg = new T.BufferGeometry().setFromPoints([new T.Vector3(0, 0, 0), m.position.clone()]);
    const line = new T.Line(lg, new T.LineBasicMaterial({ color: new T.Color(color), transparent: true, opacity: 0.15, toneMapped: false }));
    dbRing.add(line);
    return { m, g, line };
  });

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
  const BODY_X = -13.2;
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
  const bodyLabel = sprite(["受檢者"], 0.45, { color: "#5fd4ff" }); bodyLabel.position.set(BODY_X, -3.2, 0.5); scene.add(bodyLabel);
  const HOLO_CYAN = lin(0x5fd4ff), HOLO_GOLD = lin(0xffe7a8);

  // ---------------- DNA 報告：從人體取出，向右推展成雙股螺旋 ----------------
  const DNA_X = -7.0, DNA_Y = -0.3, RUNGS = 34, STEP = 0.24;
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
    const cardZone = Math.max(340 + pad + 24, Math.min(460, w * 0.36) + pad);
    const wide = true;
    camera.setViewOffset(w, h, cardZone * 0.5, 0, w, h);
    // 窄螢幕把鏡頭拉遠，整個場景放得下
    const fitDist = wide ? 31 : 31 * Math.min(2.0, Math.max(1, 1.5 / (w / h)));
    camera.userData.dist = fitDist;
    camera.updateProjectionMatrix();
    if (composer) { composer.setSize(w, h); bloom.setSize(w, h); }
    hud.root.style.setProperty("--art-w", (w - cardZone) + "px");
  }
  window.addEventListener("resize", resize); resize();

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
    const ang = orbitOn && !reduceMotion ? Math.sin(total * 0.12) * 0.26 : 0;
    camera.position.set(CAM_TARGET.x + Math.sin(ang) * dist, CAM_TARGET.y + 3.2 + Math.sin(total * 0.09) * 0.6, Math.cos(ang) * dist);
    camera.lookAt(CAM_TARGET);

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

    // 七大資料庫依序點亮（1.0–5.2 秒）
    dbRing.rotation.y = total * 0.22;
    plaques.forEach((p, i) => {
      p.m.lookAt(camera.position);
      const on = seg(t, 1.0 + i * 0.6, 1.3 + i * 0.6) * (1 - seg(t, 10.5, 11.5));
      p.m.material.opacity = 0.5 + 0.5 * on; p.g.material.opacity = 0.55 * on; p.line.material.opacity = 0.12 + 0.6 * on;
      p.m.scale.setScalar(1 + 0.12 * on);
    });

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
    if (!reduceMotion) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    setActive(on) { active = on; if (on) { last = performance.now(); resize(); } },
    seek(s) { clockT = s; },        // 測試用
    pause(on) { paused = on; },     // 測試用
  };
};

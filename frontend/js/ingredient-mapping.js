// 成分標準化（PubChem）後台頁 — 功能代碼 F1-6
// PubChem 回來的欄位是第三方內容，一律經過 esc() 才寫進 DOM

let currentStatus = "pending";
let queueItems = [];

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const STATUS_LABEL = {
  auto: "自動採用", confirmed: "已確認", pending: "待確認",
  unresolved: "查無結果", rejected: "已否決", error: "連線失敗",
};
const METHOD_LABEL = {
  exact: "原名精確命中", cleaned: "清理名稱後命中", cas: "以 CAS 反查", manual: "人工指定",
};

function statusPill(st) {
  return `<span class="st-pill st-${esc(st)}">${esc(STATUS_LABEL[st] || st)}</span>`;
}

// PubChem 的結構式圖直接用 <img> 顯示。網址由後端組好（只接受純數字 CID），
// 前端再驗一次來源網域——圖片網址是要塞進 DOM 的，不能照單全收
function structImg(url, alt) {
  if (!url || !/^https:\/\/pubchem\.ncbi\.nlm\.nih\.gov\//.test(url)) {
    return `<div class="struct" style="display:flex;align-items:center;justify-content:center;
            font-size:11px;color:#aaa;">無結構圖</div>`;
  }
  return `<img class="struct" src="${esc(url)}" alt="${esc(alt || "結構式")}" loading="lazy" />`;
}

// 分子量比對是這一頁的核心資訊，不能只給一個數字——要讓人看出差的量級代表什麼
function mwCell(item) {
  const t = item.tcmsp_mw, p = item.molecular_weight, d = item.mw_delta;
  if (!t && !p) return `<span class="hint-msg">無資料</span>`;
  if (d == null) {
    return `<div class="mono">TCMSP ${esc(t || "—")}<br>PubChem ${esc(p || "—")}</div>
            <div class="hint-msg">無法比對</div>`;
  }
  const bad = parseFloat(d) > 0.5;
  return `<div class="mono">TCMSP ${esc(t || "—")}<br>PubChem ${esc(p || "—")}</div>
          <div class="${bad ? "mw-bad" : "mw-ok"}">差 ${esc(d)} Da</div>`;
}

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

// ---------------------------------------------------------------- 覆蓋率

async function loadStats() {
  const s = await api("/tcmsp/ingredient-mapping/stats");
  const bs = s.by_status;
  const boxes = [
    ["成分總數", s.total_ingredients, false],
    ["已標準化", s.resolved, false],
    ["尚未處理", s.remaining, false],
    ["有 SMILES", s.with_smiles, false],
    ["有 CAS", s.with_cas, false],
    ["分子量不符（待確認）", s.mw_mismatch_pending, true],
  ];
  document.getElementById("statGrid").innerHTML = boxes.map(([lbl, num, alert]) => `
    <div class="stat-box ${alert && num ? "alert" : ""}">
      <div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)}</div></div>`).join("");

  const pct = Math.round((s.coverage || 0) * 1000) / 10;
  document.getElementById("coverageBar").style.width = `${pct}%`;
  document.getElementById("coverageHint").textContent =
    `覆蓋率 ${pct}%（自動採用 ${bs.auto}、已確認 ${bs.confirmed}、待確認 ${bs.pending}、` +
    `查無結果 ${bs.unresolved}、已否決 ${bs.rejected}、連線失敗 ${bs.error}）`;
}

// ---------------------------------------------------------------- 批次解析

async function runBatch() {
  const btn = document.getElementById("resolveBtn");
  const msg = document.getElementById("resolveMsg");
  const log = document.getElementById("resolveLog");
  btn.disabled = true;
  msg.textContent = "執行中，請不要關閉頁面…";
  try {
    const r = await api("/tcmsp/ingredient-mapping/resolve", {
      method: "POST",
      body: JSON.stringify({
        limit: parseInt(document.getElementById("batchLimit").value, 10),
        retry_errors: document.getElementById("retryErrors").checked,
        active_only: document.getElementById("activeOnly").checked,
      }),
    });
    const line = r.processed === 0
      ? "這一批沒有需要處理的成分了。"
      : `本批處理 ${r.processed} 筆：自動採用 ${r.auto}、待確認 ${r.pending}` +
        `（其中 ${r.mw_mismatch} 筆是分子量不符）、查無結果 ${r.unresolved}、` +
        `連線失敗 ${r.error}；尚未處理 ${r.remaining} 筆。`;
    log.textContent = `${new Date().toLocaleTimeString()}  ${line}\n${log.textContent}`;
    msg.textContent = r.remaining > 0 ? "還沒跑完，可以再按一次。" : "全部處理完畢。";
    if (r.error && r.error === r.processed) {
      msg.textContent = "整批都連線失敗——這個環境可能連不到 PubChem，請改在 Render 上執行。";
    }
    await loadStats();
    await loadQueue();
  } catch (err) {
    msg.textContent = `執行失敗：${err.message || err}`;
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- 審核清單

async function loadQueue() {
  const mwOnly = document.getElementById("mwOnly").checked;
  const params = new URLSearchParams({ status: currentStatus, limit: 200 });
  if (mwOnly) params.set("mw_mismatch_only", "true");
  const r = await api(`/tcmsp/ingredient-mapping/review?${params}`);
  queueItems = r.items || [];
  document.getElementById("queueHint").textContent =
    queueItems.length ? `共 ${r.total} 筆（最多顯示 200 筆）`
                      : "這個分類目前沒有資料。";

  document.getElementById("queueBody").innerHTML = queueItems.map((it, idx) => {
    const cands = it.candidates || [];
    let result;
    if (it.cid) {
      result = `<div><b>CID ${esc(it.cid)}</b> ${esc(it.molecular_formula || "")}</div>
        ${it.inchikey ? `<div class="mono">${esc(it.inchikey)}</div>` : ""}
        ${it.canonical_smiles ? `<div class="mono">${esc(it.canonical_smiles)}</div>` : ""}`;
    } else if (cands.length) {
      result = `<span class="hint-msg">${cands.length} 個候選：` +
        esc(cands.slice(0, 3).map(c => `CID ${c.cid}`).join("、")) + "</span>";
    } else {
      result = `<span class="hint-msg">—</span>`;
    }
    return `
      <tr>
        <td>${structImg(it.image_url, it.molecule_name)}</td>
        <td class="mono">${esc(it.mol_id)}</td>
        <td>${esc(it.molecule_name || "")}
          <div class="hint-msg">${esc(METHOD_LABEL[it.method] || it.method)}</div>
          ${it.note ? `<div class="hint-msg">${esc(it.note)}</div>` : ""}</td>
        <td>${result}</td>
        <td>${mwCell(it)}</td>
        <td>${statusPill(it.status)}</td>
        <td class="actions"><button class="secondary" data-review="${idx}">審核</button></td>
      </tr>`;
  }).join("");

  document.getElementById("queueBody").querySelectorAll("[data-review]").forEach(btn => {
    btn.addEventListener("click", () => openReview(parseInt(btn.dataset.review, 10)));
  });
}

// ---------------------------------------------------------------- 審核彈窗

function openReview(idx) {
  const it = queueItems[idx];
  if (!it) return;
  document.getElementById("reviewMolId").value = it.mol_id;
  document.getElementById("reviewName").textContent =
    `${it.mol_id}　${it.molecule_name || ""}　（TCMSP 分子量 ${it.tcmsp_mw || "—"}）`;
  document.getElementById("reviewNote").innerHTML =
    it.note ? `<b>解析註記：</b>${esc(it.note)}` : "";
  document.getElementById("reviewCid").value = it.cid || "";
  document.getElementById("reviewComment").value = "";
  document.getElementById("reviewMsg").textContent = "";

  const cands = (it.candidates || []).length ? it.candidates : (it.cid ? [it] : []);
  document.getElementById("reviewCandidates").innerHTML = cands.length
    ? `<label>PubChem 候選（點一下帶入）</label>` + cands.map((c, i) => `
        <div class="cand" data-cand="${i}">
          ${structImg(c.image_url ||
            (String(c.cid || "").match(/^\d+$/)
              ? `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${c.cid}/PNG` : ""),
            c.iupac_name)}
          <div class="meta">
            <b>CID ${esc(c.cid || "—")}</b> ${esc(c.molecular_formula || "")}
            <div class="hint-msg">分子量 ${esc(c.molecular_weight || "—")}
              ${it.tcmsp_mw ? `／ TCMSP ${esc(it.tcmsp_mw)}` : ""}</div>
            ${c.inchikey ? `<div class="mono">${esc(c.inchikey)}</div>` : ""}
            ${c.iupac_name ? `<div class="hint-msg">${esc(c.iupac_name)}</div>` : ""}
          </div>
        </div>`).join("")
    : `<p class="hint-msg">沒有候選結果，可直接人工輸入 CID。</p>`;

  document.getElementById("reviewCandidates").querySelectorAll("[data-cand]").forEach(el => {
    el.addEventListener("click", () => {
      const c = cands[parseInt(el.dataset.cand, 10)];
      document.getElementById("reviewCid").value = c.cid || "";
      document.getElementById("reviewCandidates").querySelectorAll(".cand")
        .forEach(x => x.classList.remove("sel"));
      el.classList.add("sel");
    });
  });

  document.getElementById("reviewModal").style.display = "flex";
}

function closeReview() {
  document.getElementById("reviewModal").style.display = "none";
}

async function submitConfirm() {
  const msg = document.getElementById("reviewMsg");
  const cid = document.getElementById("reviewCid").value.trim();
  if (!cid) { msg.textContent = "請先選擇候選，或輸入 PubChem CID。"; return; }
  try {
    await api("/tcmsp/ingredient-mapping/confirm", {
      method: "POST",
      body: JSON.stringify({
        mol_id: document.getElementById("reviewMolId").value, cid,
        note: document.getElementById("reviewComment").value.trim() || null,
      }),
    });
    closeReview(); await loadStats(); await loadQueue();
  } catch (err) { msg.textContent = `確認失敗：${err.message || err}`; }
}

async function submitReject() {
  const msg = document.getElementById("reviewMsg");
  const note = document.getElementById("reviewComment").value.trim();
  if (!note) {
    msg.textContent = "否決請填備註，寫清楚為什麼這個成分沒有合適的 PubChem 對應。";
    return;
  }
  try {
    await api("/tcmsp/ingredient-mapping/reject", {
      method: "POST",
      body: JSON.stringify({ mol_id: document.getElementById("reviewMolId").value, note }),
    });
    closeReview(); await loadStats(); await loadQueue();
  } catch (err) { msg.textContent = `否決失敗：${err.message || err}`; }
}

// ---------------------------------------------------------------- 反查

async function runLookup() {
  const key = document.getElementById("lookupInput").value.trim();
  const box = document.getElementById("lookupResult");
  if (!key) { box.innerHTML = ""; return; }
  try {
    const r = await api(`/tcmsp/ingredient-mapping/lookup?key=${encodeURIComponent(key)}`);
    if (!r.total) {
      box.innerHTML = `<p class="hint-msg">${esc(r.key)}：沒有對應到任何已標準化的 TCMSP 成分。</p>`;
      return;
    }
    box.innerHTML = `<p class="hint-msg">${esc(r.key)} 對應到 ${r.total} 個成分：</p>` +
      r.items.map(it => `
        <div class="cand">
          ${structImg(it.image_url, it.molecule_name)}
          <div class="meta">
            <b>${esc(it.molecule_name || "")}</b>
            <div class="mono">${esc(it.mol_id)} / CID ${esc(it.cid || "—")}</div>
            ${it.inchikey ? `<div class="mono">${esc(it.inchikey)}</div>` : ""}
            ${it.cas_number ? `<div class="hint-msg">CAS ${esc(it.cas_number)}</div>` : ""}
          </div>
        </div>`).join("");
  } catch (err) {
    box.innerHTML = `<p class="hint-msg">反查失敗：${esc(err.message || err)}</p>`;
  }
}

// ---------------------------------------------------------------- 初始化

document.addEventListener("DOMContentLoaded", async () => {
  loadUserInfo();
  document.getElementById("refreshBtn").addEventListener("click", async () => {
    await loadStats(); await loadQueue();
  });
  document.getElementById("resolveBtn").addEventListener("click", runBatch);
  document.getElementById("lookupBtn").addEventListener("click", runLookup);
  document.getElementById("lookupInput").addEventListener("keydown", e => {
    if (e.key === "Enter") runLookup();
  });
  document.getElementById("mwOnly").addEventListener("change", loadQueue);
  document.getElementById("reviewCancel").addEventListener("click", closeReview);
  document.getElementById("reviewConfirm").addEventListener("click", submitConfirm);
  document.getElementById("reviewReject").addEventListener("click", submitReject);

  document.getElementById("queueTabs").querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.getElementById("queueTabs").querySelectorAll("button")
        .forEach(b => b.classList.remove("on"));
      btn.classList.add("on");
      currentStatus = btn.dataset.status;
      await loadQueue();
    });
  });

  try { await loadStats(); await loadQueue(); }
  catch (err) {
    document.getElementById("coverageHint").textContent = `載入失敗：${err.message || err}`;
  }
});

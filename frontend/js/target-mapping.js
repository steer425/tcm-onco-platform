// 靶點標準化（UniProt）後台頁 — 功能代碼 F1-4
// UniProt 回來的欄位是第三方內容，一律經過 esc() 才寫進 DOM（跟新聞模組同一條規矩）

let currentQueueStatus = "pending";
let queueItems = [];

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

const STATUS_LABEL = {
  auto: "自動採用", confirmed: "已確認", pending: "待確認",
  unresolved: "查無結果", rejected: "已否決", error: "連線失敗",
};
const METHOD_LABEL = {
  exact: "完整名稱", stripped: "去修飾詞", fulltext: "全文檢索", manual: "人工指定",
};

function statusPill(st) {
  return `<span class="st-pill st-${esc(st)}">${esc(STATUS_LABEL[st] || st)}</span>`;
}

// ---------------------------------------------------------------- 覆蓋率

async function loadStats() {
  const s = await api("/tcmsp/target-mapping/stats");
  const boxes = [
    ["靶點總數", s.total_targets],
    ["已標準化", s.resolved],
    ["尚未處理", s.remaining],
    ["不重複基因符號", s.distinct_gene_symbols],
    ["有 KEGG 交叉引用", s.with_kegg_xref],
    ["待人工確認", s.by_status.pending],
  ];
  document.getElementById("statGrid").innerHTML = boxes.map(([lbl, num]) => `
    <div class="stat-box"><div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)}</div></div>
  `).join("");

  const pct = Math.round((s.coverage || 0) * 1000) / 10;
  document.getElementById("coverageBar").style.width = `${pct}%`;
  const bs = s.by_status;
  document.getElementById("coverageHint").textContent =
    `覆蓋率 ${pct}%（自動採用 ${bs.auto}、已確認 ${bs.confirmed}、待確認 ${bs.pending}、` +
    `查無結果 ${bs.unresolved}、已否決 ${bs.rejected}、連線失敗 ${bs.error}）`;
  return s;
}

// ---------------------------------------------------------------- 批次解析

async function runBatch() {
  const btn = document.getElementById("resolveBtn");
  const msg = document.getElementById("resolveMsg");
  const log = document.getElementById("resolveLog");
  btn.disabled = true;
  msg.textContent = "執行中，請不要關閉頁面…";
  try {
    const r = await api("/tcmsp/target-mapping/resolve", {
      method: "POST",
      body: JSON.stringify({
        limit: parseInt(document.getElementById("batchLimit").value, 10),
        retry_errors: document.getElementById("retryErrors").checked,
      }),
    });
    const line = r.processed === 0
      ? "這一批沒有需要處理的靶點了。"
      : `本批處理 ${r.processed} 筆：自動採用 ${r.auto}、待確認 ${r.pending}、` +
        `查無結果 ${r.unresolved}、連線失敗 ${r.error}；尚未處理 ${r.remaining} 筆。`;
    log.textContent = `${new Date().toLocaleTimeString()}  ${line}\n${log.textContent}`;
    msg.textContent = r.remaining > 0 ? "還沒跑完，可以再按一次。" : "全部處理完畢。";
    if (r.error && r.error === r.processed) {
      msg.textContent = "整批都連線失敗——這個環境可能連不到 rest.uniprot.org，請改在 Render 上執行。";
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
  const r = await api(`/tcmsp/target-mapping/review?status=${encodeURIComponent(currentQueueStatus)}&limit=200`);
  queueItems = r.items || [];
  document.getElementById("queueHint").textContent =
    queueItems.length ? `共 ${r.total} 筆（最多顯示 200 筆）` : "這個分類目前沒有資料。";

  document.getElementById("queueBody").innerHTML = queueItems.map((it, idx) => {
    const cands = it.candidates || [];
    let result;
    if (it.gene_symbol || it.accession) {
      result = `<b>${esc(it.gene_symbol || "—")}</b> <span class="mono">${esc(it.accession || "")}</span>` +
               `<div class="hint-msg">${esc(it.protein_name || "")}</div>`;
    } else if (cands.length) {
      result = `<span class="hint-msg">${cands.length} 個候選：` +
               esc(cands.slice(0, 3).map(c => `${c.gene_symbol || "?"}(${c.accession})`).join("、")) + "</span>";
    } else {
      result = `<span class="hint-msg">${esc(it.note || "無結果")}</span>`;
    }
    return `
      <tr>
        <td class="mono">${esc(it.tar_id)}</td>
        <td>${esc(it.target_name || "")}</td>
        <td>${result}</td>
        <td>${esc(METHOD_LABEL[it.method] || it.method)}</td>
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
  document.getElementById("reviewTarId").value = it.tar_id;
  document.getElementById("reviewTargetName").textContent =
    `${it.tar_id}　${it.target_name || ""}`;
  document.getElementById("reviewAccession").value = it.accession || "";
  document.getElementById("reviewGeneSymbol").value = it.gene_symbol || "";
  document.getElementById("reviewNote").value = it.note || "";
  document.getElementById("reviewMsg").textContent = "";

  const cands = it.candidates || [];
  document.getElementById("reviewCandidates").innerHTML = cands.length
    ? `<label>UniProt 候選（點一下帶入）</label>` + cands.map((c, i) => `
        <div class="cand" data-cand="${i}">
          <b>${esc(c.gene_symbol || "（無基因符號）")}</b>
          <span class="mono">${esc(c.accession || "")}</span>
          ${c.organism_id === 9606 ? "" : `<span class="st-pill st-error" style="margin-left:6px;">非人類 ${esc(c.organism_id)}</span>`}
          <div class="hint-msg">${esc(c.protein_name || "")}</div>
          ${(c.gene_synonyms || []).length ? `<div class="hint-msg">同義詞：${esc((c.gene_synonyms || []).join("、"))}</div>` : ""}
        </div>`).join("")
    : `<p class="hint-msg">沒有候選結果，可直接人工輸入 accession。</p>`;

  document.getElementById("reviewCandidates").querySelectorAll("[data-cand]").forEach(el => {
    el.addEventListener("click", () => {
      const c = cands[parseInt(el.dataset.cand, 10)];
      document.getElementById("reviewAccession").value = c.accession || "";
      document.getElementById("reviewGeneSymbol").value = c.gene_symbol || "";
      document.getElementById("reviewCandidates").querySelectorAll(".cand").forEach(x => x.classList.remove("sel"));
      el.classList.add("sel");
    });
  });

  document.getElementById("reviewModal").style.display = "flex";
}

async function submitConfirm() {
  const msg = document.getElementById("reviewMsg");
  const accession = document.getElementById("reviewAccession").value.trim();
  if (accession.length < 4) {
    msg.textContent = "請先選擇候選，或輸入 UniProt accession（例如 P10275）。";
    return;
  }
  try {
    await api("/tcmsp/target-mapping/confirm", {
      method: "POST",
      body: JSON.stringify({
        tar_id: document.getElementById("reviewTarId").value,
        accession,
        gene_symbol: document.getElementById("reviewGeneSymbol").value.trim() || null,
        note: document.getElementById("reviewNote").value.trim() || null,
      }),
    });
    closeReview();
    await loadStats();
    await loadQueue();
  } catch (err) {
    msg.textContent = `確認失敗：${err.message || err}`;
  }
}

async function submitReject() {
  const msg = document.getElementById("reviewMsg");
  const note = document.getElementById("reviewNote").value.trim();
  if (!note) {
    msg.textContent = "否決請填備註，寫清楚為什麼這個靶點沒有合適的 UniProt 對應。";
    return;
  }
  try {
    await api("/tcmsp/target-mapping/reject", {
      method: "POST",
      body: JSON.stringify({ tar_id: document.getElementById("reviewTarId").value, note }),
    });
    closeReview();
    await loadStats();
    await loadQueue();
  } catch (err) {
    msg.textContent = `否決失敗：${err.message || err}`;
  }
}

function closeReview() {
  document.getElementById("reviewModal").style.display = "none";
}

// ---------------------------------------------------------------- 反查

async function runLookup() {
  const sym = document.getElementById("lookupInput").value.trim();
  const box = document.getElementById("lookupResult");
  if (!sym) { box.innerHTML = ""; return; }
  try {
    const r = await api(`/tcmsp/target-mapping/lookup?symbol=${encodeURIComponent(sym)}`);
    if (!r.total) {
      box.innerHTML = `<p class="hint-msg">${esc(r.symbol)}：目前沒有對應到任何已標準化的 TCMSP 靶點。` +
                      `（可能是還沒解析到，也可能 TCMSP 本來就沒收錄這個蛋白）</p>`;
      return;
    }
    box.innerHTML = `<p class="hint-msg">${esc(r.symbol)} 對應到 ${r.total} 個靶點：</p>` +
      r.items.map(it => `
        <div class="cand">
          <b>${esc(it.target_name || "")}</b>
          <span class="mono">${esc(it.tar_id)} / ${esc(it.accession || "")}</span>
          <span class="st-pill ${it.matched_as === "primary" ? "st-auto" : "st-pending"}" style="margin-left:6px;">
            ${it.matched_as === "primary" ? "主要符號" : "同義詞"}
          </span>
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
  document.getElementById("reviewCancel").addEventListener("click", closeReview);
  document.getElementById("reviewConfirm").addEventListener("click", submitConfirm);
  document.getElementById("reviewReject").addEventListener("click", submitReject);

  document.getElementById("queueTabs").querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.getElementById("queueTabs").querySelectorAll("button").forEach(b => b.classList.remove("on"));
      btn.classList.add("on");
      currentQueueStatus = btn.dataset.status;
      await loadQueue();
    });
  });

  try {
    await loadStats();
    await loadQueue();
  } catch (err) {
    document.getElementById("coverageHint").textContent = `載入失敗：${err.message || err}`;
  }
});

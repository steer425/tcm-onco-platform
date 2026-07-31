(async () => {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) { /* ignore */ }
})();

// ---------- 主機資訊 ----------
async function loadHosts() {
  const list = document.getElementById("hostsList");
  try {
    const hosts = await api("/project-info/hosts");
    list.innerHTML = hosts.map(h => `
      <div class="host-row">
        <div>
          <div class="host-name">${h.name}</div>
          <div class="host-role">${h.role}</div>
          <div class="host-detail">${h.detail || ""}</div>
        </div>
        <a class="link" href="${h.url}" target="_blank" style="font-size:12px;">開啟 ↗</a>
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

// ---------- 版本資訊 ----------
let versionHistoryCache = [];
async function loadVersion() {
  const badge = document.getElementById("currentVersionBadge");
  const list = document.getElementById("versionList");
  try {
    const data = await api("/project-info/version");
    badge.textContent = "v" + data.current_version;
    versionHistoryCache = data.history;
    list.innerHTML = data.history.map((v, idx) => `
      <div class="version-item">
        <span class="v-tag">${v.version}</span>
        <span class="v-summary" title="${escapeHtml(v.summary)}">${escapeHtml(v.summary)}</span>
        <button class="secondary" onclick="openVersionDetail(${idx})">詳細</button>
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

window.openVersionDetail = (idx) => {
  const v = versionHistoryCache[idx];
  document.getElementById("versionDetailTitle").textContent = `${v.version}${v.date ? "（" + v.date + "）" : ""}`;
  document.getElementById("versionDetailBody").innerHTML = marked.parse(v.detail || "（無詳細內容）");
  document.getElementById("versionDetailModal").style.display = "flex";
};
window.closeVersionDetail = () => {
  document.getElementById("versionDetailModal").style.display = "none";
};

// ---------- 專案文件 ----------
async function loadDocs() {
  const list = document.getElementById("docList");
  try {
    const docs = await api("/project-info/docs");
    list.innerHTML = docs.map(d => `<button onclick="openDoc('${d.id}')">${d.title}</button>`).join("");
  } catch (err) {
    list.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

window.openDoc = async (docId) => {
  const modal = document.getElementById("docModal");
  const titleEl = document.getElementById("docModalTitle");
  const bodyEl = document.getElementById("docModalBody");
  bodyEl.innerHTML = "載入中...";
  modal.style.display = "flex";
  try {
    const doc = await api(`/project-info/docs/${docId}`);
    titleEl.textContent = doc.title;
    bodyEl.innerHTML = marked.parse(doc.content || "");
  } catch (err) {
    bodyEl.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
};
window.closeDoc = () => {
  document.getElementById("docModal").style.display = "none";
};

// ---------- 2026 年工作目標（摘要卡片，完整內容點按鈕看文件）----------
const GOALS_SUMMARY = [
  { title: "目標一：確認人參的靶點與疾病資訊", status: "pending", note: "Step 1 已完成，Step 2-6 進行中" },
  { title: "目標二：尋找下一個可量產的中藥候選", status: "pending", note: "規劃中，待目標一完成後啟動" },
  { title: "目標三：BioNeMo/AlphaGenome DNA 檢測", status: "pending", note: "待解決 AlphaGenome 商業授權問題" },
  { title: "目標四：中藥複方癌症病患服用建議", status: "pending", note: "待建立醫師審核機制" },
  { title: "目標五：中藥行地理推薦", status: "done", note: "已完成並上線（v1.1.0）" },
];

function renderGoals() {
  const list = document.getElementById("goalsList");
  list.innerHTML = GOALS_SUMMARY.map(g => `
    <div class="goal-item">
      <div class="goal-title">${g.title} <span class="${g.status === 'done' ? 'goal-status-done' : 'goal-status-pending'}">${g.status === 'done' ? '✓ 已完成' : '○ 進行中'}</span></div>
      <div class="host-detail">${g.note}</div>
    </div>
  `).join("");
}

// ---------- 依後台「功能項目管理」設定，決定要顯示哪些 Dashboard 小工具 ----------
const WIDGET_CARD_MAP = {
  "F0-13-1": "cardHosts",
  "F0-13-2": "cardVersion",
  "F0-13-3": "cardDocs",
  "F0-13-4": "cardGoals",
};

async function applyWidgetVisibility() {
  try {
    const menu = await api("/nav/menu");
    const visibleCodes = new Set(menu.map(i => i.code));
    for (const [code, cardId] of Object.entries(WIDGET_CARD_MAP)) {
      const el = document.getElementById(cardId);
      if (!el) continue;
      el.style.display = visibleCodes.has(code) ? "" : "none";
    }
  } catch (err) {
    // 取得失敗時保守作法：全部照常顯示，不影響既有使用體驗
  }
}

loadHosts();
loadVersion();
loadDocs();
renderGoals();
applyWidgetVisibility();

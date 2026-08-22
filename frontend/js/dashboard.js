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

// ---------- 公告 ----------
function fmtAnnDate(dt) {
  if (!dt) return "不自動下架";
  return new Date(dt).toLocaleString("zh-Hant", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function loadAnnouncements() {
  const list = document.getElementById("announcementsList");
  try {
    const items = await api("/announcements/public/active");
    if (!items.length) {
      list.innerHTML = '<p class="hint-msg" style="margin:0;">目前沒有公告</p>';
      return;
    }
    list.innerHTML = items.map(a => `
      <div class="ann-item">
        <div class="ann-title">${a.title}</div>
        <div class="ann-meta">${fmtAnnDate(a.start_at)} ～ ${fmtAnnDate(a.end_at)}</div>
        <div>${(a.content || "").replace(/\n/g, "<br>")}</div>
        ${a.files.length ? `<div class="ann-files">${a.files.map(f => `<a href="#" onclick="downloadAnnFile('${f.id}','${f.filename.replace(/'/g, "\\'")}'); return false;">📎 ${f.filename}</a>`).join("")}</div>` : ""}
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<p class="hint-msg">載入失敗：${err.message}</p>`;
  }
}

window.downloadAnnFile = async (fileId, filename) => {
  try {
    const token = getToken();
    const res = await fetch((API_BASE || "") + `/announcements/files/${fileId}/download`, {
      headers: { "Authorization": "Bearer " + token },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  } catch (err) {
    alert("下載失敗：" + err.message);
  }
};

// ---------- 依後台「功能項目管理」設定，決定要顯示哪些 Dashboard 小工具 ----------
const WIDGET_CARD_MAP = {
  "F0-13-1": "cardHosts",
  "F0-13-2": "cardVersion",
  "F0-13-3": "cardDocs",
  "F0-13-4": "cardGoals",
  "F0-13-5": "cardAnnouncements",
  "F0-13-6": "cardNews",
};

async function applyWidgetVisibility() {
  try {
    const [menu, me] = await Promise.all([api("/nav/menu"), api("/auth/me")]);
    const isAdmin = (me.role_names || []).includes("管理者");
    const byCode = {};
    menu.forEach(i => { byCode[i.code] = i; });

    for (const [code, cardId] of Object.entries(WIDGET_CARD_MAP)) {
      const el = document.getElementById(cardId);
      if (!el) continue;
      const item = byCode[code];
      // 管理者檢查「顯示於後台」欄位，一般使用者檢查「顯示於前台」欄位——
      // 這樣同一個 Dashboard 頁面，管理者跟一般使用者可以看到不同組合的小工具。
      const visible = item ? (isAdmin ? item.show_backend : item.show_frontend) : false;
      el.style.display = visible ? "" : "none";
    }
  } catch (err) {
    // 取得失敗時保守作法：全部照常顯示，不影響既有使用體驗
  }
}

// ---------- Dashboard 版面編輯模式（僅管理者可見）----------
let widgetFeatureCache = {}; // code -> feature 完整物件（含 id），管理者才會載入

async function initLayoutEditor() {
  let isAdmin = false;
  try {
    const me = await api("/auth/me");
    isAdmin = (me.role_names || []).includes("管理者");
  } catch (err) { return; }
  if (!isAdmin) return;

  const btn = document.getElementById("editLayoutBtn");
  btn.style.display = "inline-block";

  try {
    const features = await api("/features");
    Object.keys(WIDGET_CARD_MAP).forEach((code) => {
      const f = features.find(x => x.code === code);
      if (f) widgetFeatureCache[code] = f;
    });
  } catch (err) {
    return;
  }

  applyCardOrder();

  btn.addEventListener("click", () => {
    const grid = document.getElementById("dashGrid");
    const editing = grid.classList.toggle("edit-mode");
    btn.classList.toggle("active", editing);
    btn.textContent = editing ? "✓ 完成編輯" : "🛠 編輯版面";
    if (editing) {
      // 編輯模式：把目前隱藏的卡片也強制顯示出來（半透明），讓管理者能重新打開
      document.querySelectorAll(".dash-card[data-widget-code]").forEach(c => { c.style.display = ""; });
      syncToggleStates();
      enableDragReorder();
    } else {
      // 離開編輯模式：恢復正常的顯示規則
      applyWidgetVisibility();
    }
  });
}

function applyCardOrder() {
  const grid = document.getElementById("dashGrid");
  const cards = Array.from(grid.querySelectorAll(".dash-card"));
  cards.sort((a, b) => {
    const fa = widgetFeatureCache[a.dataset.widgetCode];
    const fb = widgetFeatureCache[b.dataset.widgetCode];
    return (fa ? fa.sort_order : 0) - (fb ? fb.sort_order : 0);
  });
  cards.forEach(c => grid.appendChild(c));
}

function syncToggleStates() {
  document.querySelectorAll(".dash-card[data-widget-code]").forEach((card) => {
    const code = card.dataset.widgetCode;
    const f = widgetFeatureCache[code];
    const checkbox = card.querySelector(".widget-visible-toggle");
    if (!f || !checkbox) return;
    // 管理者在編輯 Dashboard 時，切換的是「後台視角」的顯示與否（show_backend）
    checkbox.checked = f.show_backend;
    checkbox.onchange = async () => {
      try {
        const updated = await api(`/features/${f.id}`, {
          method: "PUT",
          body: JSON.stringify({ show_backend: checkbox.checked }),
        });
        widgetFeatureCache[code] = updated;
        card.style.opacity = checkbox.checked ? "1" : "0.4";
      } catch (err) {
        alert("更新失敗：" + err.message);
        checkbox.checked = !checkbox.checked;
      }
    };
    card.style.opacity = f.show_backend ? "1" : "0.4";
  });
}

function enableDragReorder() {
  const grid = document.getElementById("dashGrid");
  const cards = Array.from(grid.querySelectorAll(".dash-card"));
  let draggedEl = null;

  cards.forEach((card) => {
    card.setAttribute("draggable", "true");
    card.ondragstart = (e) => {
      draggedEl = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    };
    card.ondragend = () => {
      card.classList.remove("dragging");
      cards.forEach(c => c.classList.remove("drag-over"));
      persistCardOrder();
    };
    card.ondragover = (e) => {
      e.preventDefault();
      if (card !== draggedEl) card.classList.add("drag-over");
    };
    card.ondragleave = () => card.classList.remove("drag-over");
    card.ondrop = (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      if (!draggedEl || draggedEl === card) return;
      const allCards = Array.from(grid.querySelectorAll(".dash-card"));
      const draggedIdx = allCards.indexOf(draggedEl);
      const targetIdx = allCards.indexOf(card);
      if (draggedIdx < targetIdx) {
        card.after(draggedEl);
      } else {
        card.before(draggedEl);
      }
    };
  });
}

async function persistCardOrder() {
  const grid = document.getElementById("dashGrid");
  const cards = Array.from(grid.querySelectorAll(".dash-card[data-widget-code]"));
  const updates = [];
  cards.forEach((card, idx) => {
    const code = card.dataset.widgetCode;
    const f = widgetFeatureCache[code];
    const newOrder = (idx + 1) * 10; // 留間隔，方便之後手動微調
    if (f && f.sort_order !== newOrder) {
      updates.push(api(`/features/${f.id}`, { method: "PUT", body: JSON.stringify({ sort_order: newOrder }) })
        .then(updated => { widgetFeatureCache[code] = updated; }));
    }
  });
  try {
    await Promise.all(updates);
  } catch (err) {
    alert("排序儲存失敗：" + err.message);
  }
}

loadHosts();
loadVersion();
loadDocs();
renderGoals();
loadAnnouncements();
applyWidgetVisibility();
initLayoutEditor();

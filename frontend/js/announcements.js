requireLogin();

let allAnnouncements = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

function computeStatusLabel(a) {
  if (a.status === "inactive") return { text: "已下架", cls: "status-off" };
  const now = new Date();
  const start = new Date(a.start_at);
  if (now < start) return { text: "排程中", cls: "status-scheduled" };
  if (a.end_at && now > new Date(a.end_at)) return { text: "已過期", cls: "status-expired" };
  return { text: "顯示中", cls: "status-live" };
}

function fmt(dt) {
  if (!dt) return "（不自動下架）";
  const d = new Date(dt);
  return d.toLocaleString("zh-Hant", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function loadAnnouncements() {
  const kw = document.getElementById("searchInput").value.trim();
  const statusFilter = document.getElementById("statusFilter").value;
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (statusFilter !== "") params.set("only_visible", statusFilter);
  allAnnouncements = await api(`/announcements?${params.toString()}`);
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = "";
  allAnnouncements.forEach((a) => {
    const st = computeStatusLabel(a);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.title}</td>
      <td>${fmt(a.start_at)} ～ ${fmt(a.end_at)}</td>
      <td><span class="status-pill ${st.cls}">${st.text}</span></td>
      <td>${a.files.length ? a.files.length + " 個檔案" : "-"}</td>
      <td>${a.notes || ""}</td>
      <td class="actions">
        <button class="secondary" onclick="openEdit('${a.id}')">編輯</button>
        ${a.status === "active" ? `<button class="danger" onclick="deleteAnnouncement('${a.id}')">下架</button>` : ""}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("searchInput").addEventListener("input", loadAnnouncements);
document.getElementById("statusFilter").addEventListener("change", loadAnnouncements);

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

document.getElementById("newBtn").addEventListener("click", () => {
  document.getElementById("annModalTitle").textContent = "新增公告";
  document.getElementById("annId").value = "";
  document.getElementById("annTitle").value = "";
  document.getElementById("annContent").value = "";
  document.getElementById("annStart").value = toDatetimeLocalValue(new Date().toISOString());
  document.getElementById("annEnd").value = "";
  document.getElementById("annNotes").value = "";
  document.getElementById("annModalMsg").textContent = "";
  document.getElementById("annFilesSection").style.display = "none";
  document.getElementById("annModal").style.display = "flex";
});

window.openEdit = (id) => {
  const a = allAnnouncements.find(x => x.id === id);
  document.getElementById("annModalTitle").textContent = "編輯公告";
  document.getElementById("annId").value = a.id;
  document.getElementById("annTitle").value = a.title;
  document.getElementById("annContent").value = a.content || "";
  document.getElementById("annStart").value = toDatetimeLocalValue(a.start_at);
  document.getElementById("annEnd").value = a.end_at ? toDatetimeLocalValue(a.end_at) : "";
  document.getElementById("annNotes").value = a.notes || "";
  document.getElementById("annModalMsg").textContent = "";
  document.getElementById("annFilesSection").style.display = "block";
  renderFilesList(a.files);
  document.getElementById("annModal").style.display = "flex";
};

function renderFilesList(files) {
  const el = document.getElementById("annFilesList");
  if (!files.length) {
    el.innerHTML = '<span class="hint-msg">尚未上傳任何附件</span>';
    return;
  }
  el.innerHTML = files.map(f => `
    <span class="file-chip">
      <a href="#" onclick="downloadFile('${f.id}','${f.filename.replace(/'/g, "\\'")}'); return false;">${f.filename}</a>
      <button class="danger" onclick="deleteFile('${f.id}')">✕</button>
    </span>
  `).join("");
}

document.getElementById("annModalCancel").addEventListener("click", () => {
  document.getElementById("annModal").style.display = "none";
});

document.getElementById("annModalSave").addEventListener("click", async () => {
  const id = document.getElementById("annId").value;
  const msg = document.getElementById("annModalMsg");
  const startVal = document.getElementById("annStart").value;
  const endVal = document.getElementById("annEnd").value;
  if (!startVal) { msg.textContent = "請填寫開始顯示時間"; return; }
  const payload = {
    title: document.getElementById("annTitle").value.trim(),
    content: document.getElementById("annContent").value.trim(),
    // <input type="datetime-local"> 給的是「瀏覽器當地時間」的字串，沒有時區資訊；
    // 用 new Date(...) 解讀成當地時間後，再用 toISOString() 轉成正確的 UTC 時間字串送給後端，
    // 否則後端會把這串文字誤當成 UTC 時間，導致「現在」被判斷成還沒到（或已經過了）。
    start_at: new Date(startVal).toISOString(),
    end_at: endVal ? new Date(endVal).toISOString() : null,
    notes: document.getElementById("annNotes").value.trim(),
  };
  try {
    if (id) {
      await api(`/announcements/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      const created = await api("/announcements", { method: "POST", body: JSON.stringify(payload) });
      document.getElementById("annId").value = created.id;
      document.getElementById("annFilesSection").style.display = "block";
      renderFilesList(created.files);
    }
    msg.textContent = "已儲存";
    await loadAnnouncements();
  } catch (err) {
    msg.textContent = "儲存失敗：" + err.message;
  }
});

document.getElementById("annFileUploadBtn").addEventListener("click", async () => {
  const id = document.getElementById("annId").value;
  const input = document.getElementById("annFileInput");
  const msg = document.getElementById("annModalMsg");
  if (!id) { msg.textContent = "請先儲存公告，才能上傳附件"; return; }
  if (!input.files.length) { msg.textContent = "請先選擇檔案"; return; }
  const file = input.files[0];
  const formData = new FormData();
  formData.append("file", file);
  try {
    const token = getToken();
    const res = await fetch((API_BASE || "") + `/announcements/${id}/files`, {
      method: "POST",
      headers: { "Authorization": "Bearer " + token },
      body: formData,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }
    input.value = "";
    msg.textContent = "附件上傳成功";
    await loadAnnouncements();
    const updated = allAnnouncements.find(a => a.id === id);
    if (updated) renderFilesList(updated.files);
  } catch (err) {
    msg.textContent = "上傳失敗：" + err.message;
  }
});

window.deleteFile = async (fileId) => {
  if (!confirm("確定刪除這個附件？")) return;
  try {
    await api(`/announcements/files/${fileId}`, { method: "DELETE" });
    await loadAnnouncements();
    const id = document.getElementById("annId").value;
    const updated = allAnnouncements.find(a => a.id === id);
    if (updated) renderFilesList(updated.files);
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

window.downloadFile = async (fileId, filename) => {
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

window.deleteAnnouncement = async (id) => {
  if (!confirm("確定要下架這則公告嗎？")) return;
  try {
    await api(`/announcements/${id}`, { method: "DELETE" });
    await loadAnnouncements();
  } catch (err) {
    alert("下架失敗：" + err.message);
  }
};

loadUserInfo();
loadAnnouncements();

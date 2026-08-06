let allPatients = [];
let currentEncounters = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadPatients() {
  const kw = document.getElementById("searchInput").value.trim();
  const statusFilter = document.getElementById("statusFilter").value;
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (statusFilter) params.set("status_filter", statusFilter);
  allPatients = await api(`/patients?${params.toString()}`);
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = allPatients.map(p => `
    <tr data-id="${p.id}">
      <td>${escapeHtml(p.patient_id)}</td>
      <td>${escapeHtml(p.name)}</td>
      <td>${escapeHtml(p.sex_code || "")}</td>
      <td>${escapeHtml(p.birth_date || "")}</td>
      <td class="id-number-cell">
        <span id="idnum-${p.id}">${escapeHtml(p.id_number_masked)}</span>
        <button onclick="revealIdNumber('${p.id}')">顯示明碼</button>
      </td>
      <td>${escapeHtml(p.medical_record_no || "")}</td>
      <td>${p.encounter_count}</td>
      <td><span class="status-pill ${p.status === 'active' ? 'status-active' : 'status-inactive'}">${p.status === 'active' ? '使用中' : '已刪除'}</span></td>
      <td class="actions">
        <button class="secondary" onclick="openEdit('${p.id}')">編輯</button>
        ${p.status === 'active' ? `<button class="danger" onclick="deletePatient('${p.id}')">刪除</button>` : ''}
      </td>
    </tr>
  `).join("");
}

window.revealIdNumber = async (patId) => {
  try {
    const data = await api(`/patients/${patId}/id-number`);
    document.getElementById(`idnum-${patId}`).textContent = data.id_number || "（未填寫）";
  } catch (err) {
    alert("查詢失敗：" + err.message);
  }
};

document.getElementById("searchInput").addEventListener("input", loadPatients);
document.getElementById("statusFilter").addEventListener("change", loadPatients);

function clearPatientForm() {
  ["patPatientId", "patName", "patIdType", "patIdNumber", "patSex", "patBirth",
   "patNationality", "patEthnicity", "patPhone", "patMrn", "patAddress", "patNotes"]
    .forEach(id => { document.getElementById(id).value = ""; });
}

document.getElementById("newBtn").addEventListener("click", () => {
  document.getElementById("patientModalTitle").textContent = "新增病患";
  document.getElementById("patId").value = "";
  clearPatientForm();
  document.getElementById("patientModalMsg").textContent = "";
  document.getElementById("encounterSection").style.display = "none";
  document.getElementById("patientModal").style.display = "flex";
});

window.openEdit = (patId) => {
  const p = allPatients.find(x => x.id === patId);
  if (!p) return;
  document.getElementById("patientModalTitle").textContent = "編輯病患";
  document.getElementById("patId").value = p.id;
  document.getElementById("patPatientId").value = p.patient_id;
  document.getElementById("patName").value = p.name;
  document.getElementById("patIdType").value = p.id_type || "";
  document.getElementById("patIdNumber").value = ""; // 不預先填入證件號碼，避免意外顯示在畫面上
  document.getElementById("patIdNumber").placeholder = `目前：${p.id_number_masked}（留空＝不修改）`;
  document.getElementById("patSex").value = p.sex_code || "";
  document.getElementById("patBirth").value = p.birth_date || "";
  document.getElementById("patNationality").value = p.nationality_code || "";
  document.getElementById("patEthnicity").value = p.ethnicity_code || "";
  document.getElementById("patPhone").value = p.telephone || "";
  document.getElementById("patMrn").value = p.medical_record_no || "";
  document.getElementById("patAddress").value = p.address || "";
  document.getElementById("patNotes").value = p.notes || "";
  document.getElementById("patientModalMsg").textContent = "";
  document.getElementById("encounterSection").style.display = "block";
  loadEncounters(p.id);
  document.getElementById("patientModal").style.display = "flex";
};

document.getElementById("patientModalCancel").addEventListener("click", () => {
  document.getElementById("patientModal").style.display = "none";
});

document.getElementById("patientModalSave").addEventListener("click", async () => {
  const patId = document.getElementById("patId").value;
  const msg = document.getElementById("patientModalMsg");
  const idNumberInput = document.getElementById("patIdNumber").value.trim();

  try {
    if (patId) {
      const payload = {
        name: document.getElementById("patName").value.trim(),
        id_type: document.getElementById("patIdType").value.trim(),
        sex_code: document.getElementById("patSex").value.trim(),
        birth_date: document.getElementById("patBirth").value || null,
        nationality_code: document.getElementById("patNationality").value.trim(),
        ethnicity_code: document.getElementById("patEthnicity").value.trim(),
        telephone: document.getElementById("patPhone").value.trim(),
        medical_record_no: document.getElementById("patMrn").value.trim(),
        address: document.getElementById("patAddress").value.trim(),
        notes: document.getElementById("patNotes").value.trim(),
      };
      if (idNumberInput) payload.id_number = idNumberInput; // 留空就不覆蓋既有證件號碼
      await api(`/patients/${patId}`, { method: "PUT", body: JSON.stringify(payload) });
      msg.textContent = "已儲存";
      await loadPatients();
    } else {
      const payload = {
        patient_id: document.getElementById("patPatientId").value.trim(),
        name: document.getElementById("patName").value.trim(),
        id_type: document.getElementById("patIdType").value.trim(),
        id_number: idNumberInput,
        sex_code: document.getElementById("patSex").value.trim(),
        birth_date: document.getElementById("patBirth").value || null,
        nationality_code: document.getElementById("patNationality").value.trim(),
        ethnicity_code: document.getElementById("patEthnicity").value.trim(),
        telephone: document.getElementById("patPhone").value.trim(),
        medical_record_no: document.getElementById("patMrn").value.trim(),
        address: document.getElementById("patAddress").value.trim(),
        notes: document.getElementById("patNotes").value.trim(),
      };
      if (!payload.patient_id || !payload.name) {
        msg.textContent = "病患識別碼與姓名為必填";
        return;
      }
      const created = await api("/patients", { method: "POST", body: JSON.stringify(payload) });
      document.getElementById("patId").value = created.id;
      document.getElementById("encounterSection").style.display = "block";
      msg.textContent = "已儲存，現在可以新增就診紀錄";
      await loadPatients();
      loadEncounters(created.id);
    }
  } catch (err) {
    msg.textContent = "儲存失敗：" + err.message;
  }
});

window.deletePatient = async (patId) => {
  if (!confirm("確定要刪除這位病患的資料嗎？（軟刪除，資料仍會保留）")) return;
  try {
    await api(`/patients/${patId}`, { method: "DELETE" });
    await loadPatients();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

// ---------- 就診紀錄 ----------
async function loadEncounters(patId) {
  const listEl = document.getElementById("encounterList");
  listEl.innerHTML = "載入中...";
  try {
    currentEncounters = await api(`/patients/${patId}/encounters`);
    renderEncounters();
  } catch (err) {
    listEl.innerHTML = "載入失敗：" + err.message;
  }
}

function renderEncounters() {
  const listEl = document.getElementById("encounterList");
  if (!currentEncounters.length) {
    listEl.innerHTML = '<p class="hint-msg" style="margin:0;">尚無就診紀錄</p>';
    return;
  }
  listEl.innerHTML = currentEncounters.map(e => `
    <div class="encounter-row">
      <div>
        <b>${escapeHtml(e.encounter_id)}</b>　${escapeHtml(e.encounter_date || "")}　
        ${escapeHtml(e.medical_institution || "")} ${escapeHtml(e.department || "")}<br>
        <span class="hint-msg">診斷：${escapeHtml(e.diagnosis_code || "")} ${escapeHtml(e.diagnosis_name || "")}</span>
      </div>
      <div>
        ${e.status === 'active' ? `<button class="danger" onclick="deleteEncounter('${e.id}')">刪除</button>` : '<span class="hint-msg">已刪除</span>'}
      </div>
    </div>
  `).join("");
}

document.getElementById("addEncounterBtn").addEventListener("click", async () => {
  const patId = document.getElementById("patId").value;
  const msg = document.getElementById("patientModalMsg");
  if (!patId) { msg.textContent = "請先儲存病患資料"; return; }
  const encounterIdVal = document.getElementById("encId").value.trim();
  if (!encounterIdVal) { msg.textContent = "請填寫就診識別碼"; return; }
  const payload = {
    encounter_id: encounterIdVal,
    patient_id: patId,
    encounter_date: document.getElementById("encDate").value || null,
    medical_institution: document.getElementById("encInstitution").value.trim(),
    department: document.getElementById("encDept").value.trim(),
    diagnosis_code: document.getElementById("encDiagCode").value.trim(),
    diagnosis_name: document.getElementById("encDiagName").value.trim(),
  };
  try {
    await api(`/patients/${patId}/encounters`, { method: "POST", body: JSON.stringify(payload) });
    ["encId", "encDate", "encInstitution", "encDept", "encDiagCode", "encDiagName"].forEach(id => { document.getElementById(id).value = ""; });
    msg.textContent = "已新增就診紀錄";
    await loadEncounters(patId);
    await loadPatients();
  } catch (err) {
    msg.textContent = "新增失敗：" + err.message;
  }
});

window.deleteEncounter = async (encId) => {
  if (!confirm("確定刪除這筆就診紀錄？")) return;
  const patId = document.getElementById("patId").value;
  try {
    await api(`/patients/encounters/${encId}`, { method: "DELETE" });
    await loadEncounters(patId);
    await loadPatients();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

loadUserInfo();
loadPatients();

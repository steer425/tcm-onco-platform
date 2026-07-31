let allPharmacies = [];

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
  } catch (err) {}
}

const statusLabel = { active: "上架", inactive: "下架" };

async function loadPharmacies() {
  const kw = document.getElementById("searchInput").value.trim();
  const params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  allPharmacies = await api(`/pharmacies?${params.toString()}`);
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = "";
  allPharmacies.forEach((p) => {
    const tr = document.createElement("tr");
    const ratingText = p.avg_rating ? `★ ${p.avg_rating}（${p.review_count} 則）` : "尚無評價";
    tr.innerHTML = `
      <td>${p.name}</td>
      <td>${p.address}</td>
      <td>${p.phone || ""}</td>
      <td><span class="tag">${statusLabel[p.status] || p.status}</span></td>
      <td>${ratingText}</td>
      <td>${p.notes || ""}</td>
      <td class="actions">
        <button class="secondary" onclick="openEdit('${p.id}')">編輯</button>
        <button class="secondary" onclick="openReviews('${p.id}','${p.name}')">評價</button>
        <button class="danger" onclick="deletePharmacy('${p.id}')">刪除</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("searchInput").addEventListener("input", loadPharmacies);

document.getElementById("newBtn").addEventListener("click", () => {
  document.getElementById("modalTitle").textContent = "新增中藥行";
  document.getElementById("pharmacyId").value = "";
  ["fName","fAddress","fPhone","fHours","fLat","fLng","fDesc","fNotes"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("fStatus").value = "active";
  document.getElementById("modalMsg").textContent = "";
  document.getElementById("pharmacyModal").style.display = "flex";
});

window.openEdit = (id) => {
  const p = allPharmacies.find(x => x.id === id);
  document.getElementById("modalTitle").textContent = "編輯中藥行";
  document.getElementById("pharmacyId").value = p.id;
  document.getElementById("fName").value = p.name;
  document.getElementById("fAddress").value = p.address;
  document.getElementById("fPhone").value = p.phone || "";
  document.getElementById("fHours").value = p.business_hours || "";
  document.getElementById("fLat").value = p.latitude;
  document.getElementById("fLng").value = p.longitude;
  document.getElementById("fDesc").value = p.description || "";
  document.getElementById("fStatus").value = p.status;
  document.getElementById("fNotes").value = p.notes || "";
  document.getElementById("modalMsg").textContent = "";
  document.getElementById("pharmacyModal").style.display = "flex";
};

document.getElementById("modalCancel").addEventListener("click", () => {
  document.getElementById("pharmacyModal").style.display = "none";
});

document.getElementById("modalSave").addEventListener("click", async () => {
  const id = document.getElementById("pharmacyId").value;
  const msg = document.getElementById("modalMsg");
  const lat = parseFloat(document.getElementById("fLat").value);
  const lng = parseFloat(document.getElementById("fLng").value);
  if (isNaN(lat) || isNaN(lng)) {
    msg.textContent = "請填寫正確的經緯度數字";
    return;
  }
  try {
    if (id) {
      await api(`/pharmacies/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: document.getElementById("fName").value.trim(),
          address: document.getElementById("fAddress").value.trim(),
          phone: document.getElementById("fPhone").value.trim(),
          business_hours: document.getElementById("fHours").value.trim(),
          latitude: lat, longitude: lng,
          description: document.getElementById("fDesc").value.trim(),
          status: document.getElementById("fStatus").value,
          notes: document.getElementById("fNotes").value.trim(),
        }),
      });
    } else {
      await api("/pharmacies", {
        method: "POST",
        body: JSON.stringify({
          name: document.getElementById("fName").value.trim(),
          address: document.getElementById("fAddress").value.trim(),
          phone: document.getElementById("fPhone").value.trim(),
          business_hours: document.getElementById("fHours").value.trim(),
          latitude: lat, longitude: lng,
          description: document.getElementById("fDesc").value.trim(),
          notes: document.getElementById("fNotes").value.trim(),
        }),
      });
    }
    document.getElementById("pharmacyModal").style.display = "none";
    await loadPharmacies();
  } catch (err) {
    msg.textContent = err.message;
  }
});

window.deletePharmacy = async (id) => {
  if (!confirm("確定要下架（軟刪除）此中藥行嗎？")) return;
  try {
    await api(`/pharmacies/${id}`, { method: "DELETE" });
    await loadPharmacies();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

window.openReviews = async (id, name) => {
  document.getElementById("reviewsPharmacyName").textContent = name;
  const reviews = await api(`/pharmacies/${id}/reviews`);
  const tbody = document.getElementById("reviewsBody");
  tbody.innerHTML = "";
  if (reviews.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:#6b7a70;">尚無評價</td></tr>`;
  }
  reviews.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.account || ""}</td>
      <td>★ ${r.rating}</td>
      <td>${r.comment || ""}</td>
      <td>${r.notes || ""}</td>
      <td class="actions">
        <button class="secondary" onclick="editReviewNote('${r.id}', '${(r.notes||'').replace(/'/g,"\\'")}')">補充備注</button>
        <button class="danger" onclick="deleteReview('${r.id}','${id}','${name.replace(/'/g,"\\'")}')">刪除</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
  document.getElementById("reviewsModal").style.display = "flex";
};

window.editReviewNote = async (reviewId, current) => {
  const notes = prompt("管理備注：", current || "");
  if (notes === null) return;
  try {
    await api(`/pharmacy-reviews/${reviewId}/notes`, { method: "PUT", body: JSON.stringify({ notes }) });
    alert("已更新，請重新點開該中藥行的評價查看");
  } catch (err) {
    alert("更新失敗：" + err.message);
  }
};

window.deleteReview = async (reviewId, pharmacyId, pharmacyName) => {
  if (!confirm("確定刪除此則評價？")) return;
  try {
    await api(`/pharmacy-reviews/${reviewId}`, { method: "DELETE" });
    await openReviews(pharmacyId, pharmacyName);
    await loadPharmacies();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

document.getElementById("reviewsClose").addEventListener("click", () => {
  document.getElementById("reviewsModal").style.display = "none";
});

loadUserInfo();
loadPharmacies();

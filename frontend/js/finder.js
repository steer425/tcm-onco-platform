requireLogin();

let pharmacies = [];
let myLocation = null; // { lat, lng }
let currentUserId = null;

async function loadUserInfo() {
  try {
    const data = await api("/dashboard");
    document.getElementById("userInfo").textContent =
      `${data.account}（${(data.role_names || []).join("、") || "無角色"}）`;
    // /dashboard 目前未回傳 user id，改由 /auth/me 取得
    const me = await api("/auth/me");
    currentUserId = me.id;
  } catch (err) {}
}

document.getElementById("logoutLink").addEventListener("click", async (e) => {
  e.preventDefault();
  try { await api(`/auth/logout?login_log_id=${getLoginLogId()}`, { method: "POST" }); } catch (e) {}
  clearSession();
  window.location.href = "index.html";
});

// Haversine 距離計算（公里）
function distanceKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

async function loadPharmacies() {
  pharmacies = await api("/public/pharmacies");
  for (const p of pharmacies) {
    p.reviews = await api(`/public/pharmacies/${p.id}/reviews`);
  }
  render();
}

function render() {
  let list = [...pharmacies];
  if (myLocation) {
    list.forEach(p => { p.distance = distanceKm(myLocation.lat, myLocation.lng, p.latitude, p.longitude); });
    list.sort((a, b) => a.distance - b.distance);
  } else {
    list.sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"));
  }

  const container = document.getElementById("pharmacyList");
  container.innerHTML = "";
  list.forEach((p) => {
    const myReview = (p.reviews || []).find(r => r.user_id === currentUserId);
    const div = document.createElement("div");
    div.className = "card pharmacy-item";
    div.innerHTML = `
      <h4>${p.name} ${p.distance !== undefined ? `<span style="color:#6b7a70; font-size:13px; font-weight:normal;">距離約 ${p.distance.toFixed(1)} 公里</span>` : ""}</h4>
      <div class="pharmacy-meta">📍 ${p.address}　${p.phone ? "📞 " + p.phone : ""}</div>
      <div class="pharmacy-meta">⏰ ${p.business_hours || "營業時間未提供"}</div>
      <div>${p.description || ""}</div>
      <div class="pharmacy-meta" style="margin-top:8px;">
        <span class="stars">${p.avg_rating ? "★".repeat(Math.round(p.avg_rating)) : "尚無評價"}</span>
        ${p.avg_rating ? `${p.avg_rating} 分（${p.review_count} 則評價）` : ""}
      </div>

      <div class="review-box">
        <strong style="font-size:13px;">使用者評價</strong>
        <div id="reviews-${p.id}">
          ${(p.reviews || []).map(r => `<div class="review-line">★ ${r.rating}　${r.account || ""}：${r.comment || ""}</div>`).join("") || '<div class="review-line" style="color:#6b7a70;">目前尚無評價</div>'}
        </div>

        <div style="margin-top:10px;">
          <strong style="font-size:13px;">${myReview ? "編輯我的評價" : "新增我的評價"}</strong>
          <div class="rating-select" id="rating-${p.id}">
            ${[1,2,3,4,5].map(n => `<button data-n="${n}" onclick="selectRating('${p.id}', ${n})">${n}★</button>`).join("")}
          </div>
          <textarea id="comment-${p.id}" rows="2" placeholder="分享您的使用心得...">${myReview ? (myReview.comment || "") : ""}</textarea>
          <div style="margin-top:6px; display:flex; gap:8px;">
            <button onclick="submitReview('${p.id}')">${myReview ? "更新評價" : "送出評價"}</button>
            ${myReview ? `<button class="danger" onclick="removeReview('${myReview.id}')">刪除我的評價</button>` : ""}
          </div>
        </div>
      </div>
    `;
    container.appendChild(div);
    if (myReview) markSelectedRating(p.id, myReview.rating);
  });
}

window.selectRating = (pharmacyId, n) => {
  const wrap = document.getElementById(`rating-${pharmacyId}`);
  wrap.dataset.selected = n;
  markSelectedRating(pharmacyId, n);
};

function markSelectedRating(pharmacyId, n) {
  const wrap = document.getElementById(`rating-${pharmacyId}`);
  wrap.dataset.selected = n;
  Array.from(wrap.children).forEach((btn) => {
    btn.classList.toggle("selected", Number(btn.dataset.n) === n);
  });
}

window.submitReview = async (pharmacyId) => {
  const wrap = document.getElementById(`rating-${pharmacyId}`);
  const rating = Number(wrap.dataset.selected || 0);
  const comment = document.getElementById(`comment-${pharmacyId}`).value.trim();
  if (!rating) {
    alert("請先選擇星等");
    return;
  }
  const p = pharmacies.find(x => x.id === pharmacyId);
  const myReview = (p.reviews || []).find(r => r.user_id === currentUserId);
  try {
    if (myReview) {
      await api(`/public/reviews/${myReview.id}`, { method: "PUT", body: JSON.stringify({ rating, comment }) });
    } else {
      await api(`/public/pharmacies/${pharmacyId}/reviews`, { method: "POST", body: JSON.stringify({ rating, comment }) });
    }
    await refreshPharmacy(pharmacyId);
  } catch (err) {
    alert("送出失敗：" + err.message);
  }
};

window.removeReview = async (reviewId) => {
  if (!confirm("確定刪除您的評價？")) return;
  try {
    await api(`/public/reviews/${reviewId}`, { method: "DELETE" });
    await loadPharmacies();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
};

async function refreshPharmacy(pharmacyId) {
  const updated = await api(`/public/pharmacies/${pharmacyId}`);
  updated.reviews = await api(`/public/pharmacies/${pharmacyId}/reviews`);
  const idx = pharmacies.findIndex(p => p.id === pharmacyId);
  pharmacies[idx] = updated;
  render();
}

document.getElementById("locateBtn").addEventListener("click", () => {
  const statusEl = document.getElementById("locationStatus");
  if (!navigator.geolocation) {
    statusEl.textContent = "您的瀏覽器不支援定位功能";
    return;
  }
  statusEl.textContent = "定位中...";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      myLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      statusEl.textContent = "已取得您的位置，已依距離排序";
      render();
    },
    (err) => {
      statusEl.textContent = "無法取得位置（" + err.message + "），請確認已授權瀏覽器使用您的位置";
    }
  );
});

loadUserInfo().then(loadPharmacies);

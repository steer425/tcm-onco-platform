let pharmacies = [];
let myLocation = null; // { lat, lng }
let currentUserId = null;
let pharmacyMap = null;
let pharmacyMarkers = {}; // pharmacy.id -> L.Marker
let myLocationMarker = null;

function initMap() {
  pharmacyMap = L.map('pharmacyMap').setView([25.0478, 121.5319], 12); // 預設中心：台北車站附近
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 貢獻者',
    maxZoom: 19,
  }).addTo(pharmacyMap);
}

function renderMapMarkers() {
  // 清掉舊標記
  Object.values(pharmacyMarkers).forEach(m => pharmacyMap.removeLayer(m));
  pharmacyMarkers = {};

  const bounds = [];
  pharmacies.forEach((p) => {
    if (p.latitude == null || p.longitude == null) return;
    const lat = parseFloat(p.latitude), lng = parseFloat(p.longitude);
    const marker = L.marker([lat, lng]).addTo(pharmacyMap);
    marker.bindPopup(`
      <b>${escapeHtmlFinder(p.name)}</b>
      ${p.address ? escapeHtmlFinder(p.address) + '<br>' : ''}
      ${p.avg_rating ? '★'.repeat(Math.round(p.avg_rating)) + ' ' + p.avg_rating + ' 分' : '尚無評價'}
    `);
    marker.on('click', () => highlightPharmacyCard(p.id));
    pharmacyMarkers[p.id] = marker;
    bounds.push([lat, lng]);
  });

  if (myLocation) {
    if (myLocationMarker) pharmacyMap.removeLayer(myLocationMarker);
    myLocationMarker = L.circleMarker([myLocation.lat, myLocation.lng], {
      radius: 8, color: '#2563a8', fillColor: '#4a90d9', fillOpacity: 0.8,
    }).addTo(pharmacyMap).bindPopup('您目前的位置');
    bounds.push([myLocation.lat, myLocation.lng]);
  }

  if (bounds.length) {
    pharmacyMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
  }
}

function highlightPharmacyCard(pharmacyId) {
  document.querySelectorAll('.pharmacy-item').forEach(el => el.classList.remove('highlighted'));
  const card = document.getElementById(`pharmacy-card-${pharmacyId}`);
  if (card) {
    card.classList.add('highlighted');
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function escapeHtmlFinder(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

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

  if (pharmacyMap) renderMapMarkers();

  const container = document.getElementById("pharmacyList");
  container.innerHTML = "";
  list.forEach((p) => {
    const myReview = (p.reviews || []).find(r => r.user_id === currentUserId);
    const div = document.createElement("div");
    div.className = "card pharmacy-item";
    div.id = `pharmacy-card-${p.id}`;
    div.style.cursor = "pointer";
    div.addEventListener("click", (e) => {
      if (e.target.closest("button, textarea, .rating-select")) return; // 不要干擾評價互動
      const marker = pharmacyMarkers[p.id];
      if (marker && pharmacyMap) {
        pharmacyMap.setView(marker.getLatLng(), 16);
        marker.openPopup();
      }
    });
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

initMap();
loadUserInfo().then(loadPharmacies);

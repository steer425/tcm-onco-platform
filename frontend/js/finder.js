let pharmacies = [];
let myLocation = null; // { lat, lng }
let currentUserId = null;
let pharmacyMap = null;
let pharmacyMarkers = {}; // pharmacy.id -> L.Marker
let myLocationMarker = null;
let currentSort = "distance";
let ratingMode = "weighted";
let checkinScope = "all";
let priceOrder = "asc";
let checkinTargetId = null;

function initMap() {
  pharmacyMap = L.map('pharmacyMap').setView([25.0478, 121.5319], 12); // 預設中心：台北車站附近
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 貢獻者',
    maxZoom: 19,
  }).addTo(pharmacyMap);
}

function renderMapMarkers(list) {
  Object.values(pharmacyMarkers).forEach(m => pharmacyMap.removeLayer(m));
  pharmacyMarkers = {};

  const bounds = [];
  (list || pharmacies).forEach((p) => {
    if (p.latitude == null || p.longitude == null) return;
    const lat = parseFloat(p.latitude), lng = parseFloat(p.longitude);
    const marker = L.marker([lat, lng]).addTo(pharmacyMap);
    const reviews = p.reviews || [];
    const reviewLines = reviews.slice(0, 5).map(r =>
      `<div style="margin-top:4px; font-size:12px;">${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)}　${escapeHtmlFinder(r.account || '匿名')}：${escapeHtmlFinder(r.comment || '（無留言）')}</div>`
    ).join("");
    marker.bindPopup(`
      <div style="max-width:240px;">
        <b>${escapeHtmlFinder(p.name)}</b><br>
        ${p.address ? escapeHtmlFinder(p.address) + '<br>' : ''}
        ${p.avg_rating ? '★'.repeat(Math.round(p.avg_rating)) + '☆'.repeat(5 - Math.round(p.avg_rating)) + ` ${p.avg_rating} 分（${reviews.length} 則評價）` : '尚無評價'}
        ${reviewLines ? `<div style="margin-top:6px; padding-top:6px; border-top:1px solid #eee; max-height:140px; overflow-y:auto;">${reviewLines}</div>` : ''}
      </div>
    `, { maxWidth: 260 });
    marker.on('click', () => { highlightPharmacyCard(p.id); trackAction(p.id, 'view'); });
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
    const me = await api("/auth/me");
    currentUserId = me.id;
  } catch (err) {}
}

function distanceKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

const BUSINESS_STATUS_LABEL = {
  open: "營業中", closing_soon: "即將打烊", opening_soon: "即將開門", closed: "休息中", unknown: "營業時間未提供",
};

// ---------- 排序按鈕 ----------
document.querySelectorAll(".sort-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sort-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentSort = btn.dataset.sort;
    renderSortSubOptions();
    loadPharmacies();
  });
});

function renderSortSubOptions() {
  const wrap = document.getElementById("sortSubOptions");
  if (currentSort === "rating") {
    wrap.style.display = "flex";
    wrap.innerHTML = `
      評分模式：
      <label><input type="radio" name="ratingMode" value="weighted" ${ratingMode === 'weighted' ? 'checked' : ''}> 加權星等</label>
      <label><input type="radio" name="ratingMode" value="average" ${ratingMode === 'average' ? 'checked' : ''}> 平均星等</label>
      <label><input type="radio" name="ratingMode" value="total" ${ratingMode === 'total' ? 'checked' : ''}> 總星等</label>
    `;
    wrap.querySelectorAll('input[name="ratingMode"]').forEach(r => r.addEventListener("change", (e) => { ratingMode = e.target.value; loadPharmacies(); }));
  } else if (currentSort === "checkin") {
    wrap.style.display = "flex";
    wrap.innerHTML = `
      範圍：
      <label><input type="radio" name="checkinScope" value="all" ${checkinScope === 'all' ? 'checked' : ''}> 全部使用者</label>
      <label><input type="radio" name="checkinScope" value="mine" ${checkinScope === 'mine' ? 'checked' : ''}> 只看我自己</label>
    `;
    wrap.querySelectorAll('input[name="checkinScope"]').forEach(r => r.addEventListener("change", (e) => { checkinScope = e.target.value; loadPharmacies(); }));
  } else if (currentSort === "price") {
    wrap.style.display = "flex";
    wrap.innerHTML = `
      順序：
      <label><input type="radio" name="priceOrder" value="asc" ${priceOrder === 'asc' ? 'checked' : ''}> 由低到高</label>
      <label><input type="radio" name="priceOrder" value="desc" ${priceOrder === 'desc' ? 'checked' : ''}> 由高到低</label>
    `;
    wrap.querySelectorAll('input[name="priceOrder"]').forEach(r => r.addEventListener("change", (e) => { priceOrder = e.target.value; loadPharmacies(); }));
  } else {
    wrap.style.display = "none";
    wrap.innerHTML = "";
  }
}

document.getElementById("relevanceSearchBtn").addEventListener("click", () => {
  const kw = document.getElementById("relevanceInput").value.trim();
  if (!kw) { alert("請輸入關鍵字"); return; }
  document.querySelectorAll(".sort-btn").forEach(b => b.classList.remove("active"));
  currentSort = "relevance";
  document.getElementById("sortSubOptions").style.display = "none";
  loadPharmacies();
});

async function loadPharmacies() {
  const params = new URLSearchParams();
  if (currentSort !== "distance") {
    params.set("sort", currentSort);
    if (currentSort === "rating") params.set("rating_mode", ratingMode);
    if (currentSort === "checkin") params.set("checkin_scope", checkinScope);
    if (currentSort === "price") params.set("price_order", priceOrder);
    if (currentSort === "relevance") params.set("keyword", document.getElementById("relevanceInput").value.trim());
  }
  pharmacies = await api(`/public/pharmacies?${params.toString()}`);
  for (const p of pharmacies) {
    p.reviews = await api(`/public/pharmacies/${p.id}/reviews`);
  }
  render();
}

async function trackAction(pharmacyId, action) {
  try { await api(`/public/pharmacies/${pharmacyId}/${action}`, { method: "POST" }); } catch (e) { /* 追蹤失敗不影響主功能 */ }
}

function render() {
  let list = [...pharmacies];

  if (currentSort === "distance") {
    if (myLocation) {
      list.forEach(p => { p.distance = distanceKm(myLocation.lat, myLocation.lng, p.latitude, p.longitude); });
      list.sort((a, b) => a.distance - b.distance);
      const limitInput = document.getElementById("nearestLimitInput");
      const limit = limitInput ? parseInt(limitInput.value, 10) : 0;
      if (limit && limit > 0) list = list.slice(0, limit);
    } else {
      list.sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"));
    }
  } else if (myLocation) {
    // 非距離排序模式下，仍然計算距離供卡片顯示參考（但不影響排序，後端已排好序）
    list.forEach(p => { p.distance = distanceKm(myLocation.lat, myLocation.lng, p.latitude, p.longitude); });
  }

  if (pharmacyMap) renderMapMarkers(list);

  const container = document.getElementById("pharmacyList");
  container.innerHTML = "";
  list.forEach((p) => {
    const myReview = (p.reviews || []).find(r => r.user_id === currentUserId);
    const div = document.createElement("div");
    div.className = "card pharmacy-item";
    div.id = `pharmacy-card-${p.id}`;
    div.style.cursor = "pointer";
    div.addEventListener("click", (e) => {
      if (e.target.closest("button, textarea, .rating-select")) return;
      trackAction(p.id, "view");
      const marker = pharmacyMarkers[p.id];
      if (marker && pharmacyMap) {
        pharmacyMap.setView(marker.getLatLng(), 16);
        marker.openPopup();
      }
    });

    const statsLine = [
      `打卡 ${p.checkin_count} 次`,
      p.avg_spending ? `均消 NT$${Math.round(p.avg_spending)}` : null,
      `瀏覽 ${p.view_count}`,
      `收藏 ${p.favorite_count}`,
      `分享 ${p.share_count}`,
    ].filter(Boolean).join("　·　");

    div.innerHTML = `
      <h4>${escapeHtmlFinder(p.name)}
        ${p.distance !== undefined ? `<span style="color:#6b7a70; font-size:13px; font-weight:normal;">距離約 ${p.distance.toFixed(1)} 公里</span>` : ""}
        <span class="business-status-pill bs-${p.business_status}">${BUSINESS_STATUS_LABEL[p.business_status] || p.business_status}</span>
        ${p.discount_percent ? `<span class="discount-badge">🏷️ ${p.discount_description || (p.discount_percent + '% off')}</span>` : ""}
      </h4>
      <div class="pharmacy-meta">📍 ${escapeHtmlFinder(p.address)}　${p.phone ? "📞 " + escapeHtmlFinder(p.phone) : ""}</div>
      <div class="pharmacy-meta">⏰ ${escapeHtmlFinder(p.business_hours) || "營業時間未提供"}</div>
      <div>${escapeHtmlFinder(p.description) || ""}</div>
      <div class="pharmacy-meta" style="margin-top:8px;">
        <span class="stars">${p.avg_rating ? "★".repeat(Math.round(p.avg_rating)) : "尚無評價"}</span>
        ${p.avg_rating ? `${p.avg_rating} 分（${p.review_count} 則評價，加權 ${p.weighted_rating}）` : ""}
      </div>
      <div class="pharmacy-meta" style="margin-top:4px; font-size:11.5px;">${statsLine}</div>

      <div class="pharmacy-actions">
        <button onclick="openCheckinModal('${p.id}', '${escapeHtmlFinder(p.name).replace(/'/g, "\\'")}')">✅ 打卡${p.my_checkin_count ? `（我已打卡 ${p.my_checkin_count} 次）` : ''}</button>
        <button class="${p.is_favorited ? 'favorited' : ''}" onclick="toggleFavorite('${p.id}', ${p.is_favorited})">${p.is_favorited ? '❤️ 已收藏' : '🤍 收藏'}</button>
        <button onclick="doNavigate('${p.id}')">🧭 路線規劃</button>
        <button onclick="doShare('${p.id}', '${escapeHtmlFinder(p.name).replace(/'/g, "\\'")}')">📤 分享</button>
      </div>

      <div class="review-box">
        <strong style="font-size:13px;">使用者評價</strong>
        <div id="reviews-${p.id}">
          ${(p.reviews || []).map(r => `<div class="review-line">★ ${r.rating}　${escapeHtmlFinder(r.account) || ""}：${escapeHtmlFinder(r.comment) || ""}</div>`).join("") || '<div class="review-line" style="color:#6b7a70;">目前尚無評價</div>'}
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
  if (!rating) { alert("請先選擇星等"); return; }
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

// ---------- 打卡 ----------
window.openCheckinModal = (pharmacyId, name) => {
  checkinTargetId = pharmacyId;
  document.getElementById("checkinModalTitle").textContent = `打卡：${name}`;
  document.getElementById("checkinSpending").value = "";
  document.getElementById("checkinNotes").value = "";
  document.getElementById("checkinModal").style.display = "flex";
};
document.getElementById("checkinCancel").addEventListener("click", () => {
  document.getElementById("checkinModal").style.display = "none";
});
document.getElementById("checkinConfirm").addEventListener("click", async () => {
  const spendingVal = document.getElementById("checkinSpending").value;
  try {
    await api(`/public/pharmacies/${checkinTargetId}/checkin`, {
      method: "POST",
      body: JSON.stringify({
        spending_amount: spendingVal ? parseInt(spendingVal, 10) : null,
        notes: document.getElementById("checkinNotes").value.trim() || null,
      }),
    });
    document.getElementById("checkinModal").style.display = "none";
    await refreshPharmacy(checkinTargetId);
  } catch (err) {
    alert("打卡失敗：" + err.message);
  }
});

// ---------- 收藏 ----------
window.toggleFavorite = async (pharmacyId, isFavorited) => {
  try {
    if (isFavorited) {
      await api(`/public/pharmacies/${pharmacyId}/favorite`, { method: "DELETE" });
    } else {
      await api(`/public/pharmacies/${pharmacyId}/favorite`, { method: "POST" });
    }
    await refreshPharmacy(pharmacyId);
  } catch (err) {
    alert("操作失敗：" + err.message);
  }
};

// ---------- 路線規劃 / 導航 ----------
window.doNavigate = async (pharmacyId) => {
  try {
    const res = await api(`/public/pharmacies/${pharmacyId}/navigate`, { method: "POST" });
    window.open(res.navigation_url, "_blank");
    await refreshPharmacy(pharmacyId);
  } catch (err) {
    alert("開啟路線規劃失敗：" + err.message);
  }
};

// ---------- 分享 ----------
window.doShare = async (pharmacyId, name) => {
  const url = window.location.origin + window.location.pathname + `?pharmacy=${pharmacyId}`;
  try {
    if (navigator.share) {
      await navigator.share({ title: name, text: `推薦中藥行：${name}`, url });
    } else {
      await navigator.clipboard.writeText(url);
      alert("已複製分享連結到剪貼簿");
    }
    await trackAction(pharmacyId, "share");
    await refreshPharmacy(pharmacyId);
  } catch (err) {
    // 使用者取消分享視窗也會進到這裡，不用特別跳錯誤訊息
  }
};

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

document.getElementById("nearestLimitInput").addEventListener("input", (e) => {
  let v = parseInt(e.target.value, 10);
  if (!isNaN(v)) {
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    e.target.value = v;
  }
  render();
});

initMap();
loadUserInfo().then(loadPharmacies);

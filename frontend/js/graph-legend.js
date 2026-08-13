// 全站關聯網絡圖通用圖例元件。
//
// 用途：在每個查詢站的關聯圖（含主畫面小圖跟全螢幕大圖）左上角顯示一個小方塊，
// 列出這張圖裡每種節點類型對應的顏色（例如「● 藥材」「● 成分」「● 靶點」），
// 讓使用者不用猜顏色代表什麼。點色塊可以打開顏色選擇器自訂顏色，
// 自訂後的顏色會存進 localStorage（依「頁面 + 節點類型 key」區分），
// 下次載入這個頁面會自動套用，且會立刻觸發重繪讓使用者馬上看到套用結果。
//
// 使用方式（每個查詢站頁面自己呼叫）：
//   const legend = createGraphLegend('tcmsp_query', [
//     { key: 'herb', label: '藥材', defaultColor: '#c99a3d' },
//     { key: 'ingredient', label: '成分', defaultColor: '#3b82c4' },
//     { key: 'target', label: '靶點', defaultColor: '#3a9d63' },
//     { key: 'disease', label: '疾病', defaultColor: '#c0533e' },
//   ], () => { renderNetwork('network', false); if (modalOpen) renderNetwork('networkModalCanvas', true); });
//
//   // 建圖時，顏色不要再寫死 hex 字串，改成呼叫：
//   legend.getColor('herb')   // 會自動回傳「使用者自訂的顏色」或「預設顏色」
//
//   // 在容器裡插入圖例本身（容器要是 position:relative，圖例用 position:absolute 疊在左上角）：
//   legend.mount('network');
//   legend.mount('networkModalCanvas');  // 全螢幕檢視也要另外掛一次，兩邊是各自獨立的 DOM

(function () {
  function createGraphLegend(pageKey, items, onColorChange) {
    const storageKey = `tcm_graph_legend_${pageKey}`;

    function loadCustomColors() {
      try {
        const raw = localStorage.getItem(storageKey);
        return raw ? JSON.parse(raw) : {};
      } catch (e) {
        return {};
      }
    }

    let customColors = loadCustomColors();

    function saveCustomColors() {
      try {
        localStorage.setItem(storageKey, JSON.stringify(customColors));
      } catch (e) { /* localStorage 滿了或被封鎖時，安靜放棄儲存，不影響當次使用 */ }
    }

    function getColor(key) {
      const item = items.find((i) => i.key === key);
      if (!item) return "#999";
      return customColors[key] || item.defaultColor;
    }

    function setColor(key, color) {
      customColors[key] = color;
      saveCustomColors();
      if (typeof onColorChange === "function") onColorChange();
    }

    function resetColor(key) {
      delete customColors[key];
      saveCustomColors();
      if (typeof onColorChange === "function") onColorChange();
    }

    // 把圖例掛到指定容器的左上角。同一個 legend 物件可以掛到多個容器
    // （例如主畫面小圖跟全螢幕大圖各掛一次），每個容器各自維護自己的一份 DOM，
    // 但共用同一份顏色資料，改一邊顏色，兩邊下次重繪都會套用到。
    function mount(containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      // 避免重複掛載（例如頁面重新渲染時 mount 被呼叫第二次）
      const existing = container.querySelector(".tcm-graph-legend");
      if (existing) existing.remove();

      if (getComputedStyle(container).position === "static") {
        container.style.position = "relative";
      }

      const box = document.createElement("div");
      box.className = "tcm-graph-legend";
      box.style.cssText = "position:absolute; top:8px; left:8px; z-index:5; background:rgba(20,22,26,0.85); border:1px solid #3a3d44; border-radius:6px; padding:6px 8px; font-size:11px; color:#eee; line-height:1.9; pointer-events:auto;";

      items.forEach((item) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex; align-items:center; gap:6px; cursor:pointer;";
        row.title = "點一下可以自訂這個顏色";

        const swatch = document.createElement("span");
        swatch.style.cssText = `display:inline-block; width:10px; height:10px; border-radius:50%; background:${getColor(item.key)}; flex-shrink:0;`;

        const label = document.createElement("span");
        label.textContent = item.label;

        // 隱藏的原生顏色選擇器，點色塊時觸發它打開
        const picker = document.createElement("input");
        picker.type = "color";
        picker.value = getColor(item.key);
        picker.style.cssText = "width:0; height:0; opacity:0; position:absolute; pointer-events:none;";
        picker.addEventListener("input", (e) => {
          setColor(item.key, e.target.value);
          swatch.style.background = e.target.value;
        });

        row.addEventListener("click", () => picker.click());
        row.appendChild(swatch);
        row.appendChild(label);
        row.appendChild(picker);
        box.appendChild(row);
      });

      // 「還原預設顏色」的小連結，放在最下面，避免使用者自訂完忘記怎麼調回去
      const resetLink = document.createElement("div");
      resetLink.textContent = "還原預設顏色";
      resetLink.style.cssText = "margin-top:4px; padding-top:4px; border-top:1px solid #3a3d44; color:#7db8e8; cursor:pointer; font-size:10.5px;";
      resetLink.addEventListener("click", () => {
        items.forEach((item) => resetColor(item.key));
        mount(containerId); // 重新掛載，讓色塊顯示恢復成預設顏色
      });
      box.appendChild(resetLink);

      container.appendChild(box);
    }

    return { getColor, mount };
  }

  window.createGraphLegend = createGraphLegend;
})();

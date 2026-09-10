"""TCMSP 成分 → PubChem 標準化解析（目標一 Step 2）。

背景見 `models.TcmspIngredientPubchem` 的說明：靶點那側已經標準化，
成分那側目前只有名稱，沒有 SMILES／InChIKey／CAS／結構。

## 這支跟 `tcmsp_uniprot.py` 最重要的差別：有獨立的驗算依據

靶點只能靠名稱比對，對不對只能靠人看。但 **TCMSP 自己存了分子量**
（`tcmsp_ingredients.mw`），所以每一筆解析都能拿它跟 PubChem 回傳的
分子量對照，作為「名稱有沒有解析到正確化合物」的獨立證據。

名稱對上就當作成功，是這類工作最容易犯、最難發現的錯——
畫面上一切正常，只是那個 SMILES 屬於別的分子。常見成因：

  * 同名異物（不同來源用同一個俗名）
  * 鹽類 vs 游離態（差幾十 Da）
  * 水合物（差 18 的倍數）
  * **糖苷 vs 苷元**（差糖基的整數倍，己糖 162.14／去氧己糖 146.14／戊糖 132.12）
    —— 這是本資料集最常見的一種，見 cleaned_name() 對 `_qt` 的說明
  * 立體異構物混淆（分子量相同，這種靠 MW 抓不到，只能靠人）

所以分子量不符時**一律進待確認**，不自動採用。

⚠️ 這支需要對外連到 `pubchem.ncbi.nlm.nih.gov`。Cowork 沙箱與本機 VM 都連不到，
實際執行必須在 Render 上。測試以 fixture 取代網路層。
"""

from __future__ import annotations

import itertools
import json
import logging
import re
import time
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
PROPS = ("CanonicalSMILES,IsomericSMILES,InChIKey,MolecularFormula,"
         "MolecularWeight,IUPACName")

# 結構式圖片（前端直接用 <img> 顯示）
IMAGE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"

METHOD_CONFIDENCE = {"exact": 1.0, "cleaned": 0.8, "cas": 1.0, "manual": 1.0}

# 分子量相符的容許值（道爾頓）。同一個化合物在不同資料庫之間的差異
# 只來自同位素慣例與四捨五入，0.5 Da 已經非常寬鬆；
# 超過這個值幾乎都代表是不同的化學實體（鹽、水合物、同名異物）。
MW_TOLERANCE = 0.5

# 天然物糖苷的糖基殘基質量（接上去時失去一分子水，所以是脫水後的值）。
# 差值等於這些的整數倍或組合時，幾乎都代表 PubChem 回傳的是**帶糖基的母體苷**，
# 而 TCMSP 那一筆要的是苷元——名稱對上了，但不是同一個分子。
SUGAR_RESIDUES = {
    "己糖（葡萄糖等）": 162.1424,
    "去氧己糖（鼠李糖等）": 146.1430,
    "戊糖（木糖、阿拉伯糖等）": 132.1161,
}
MAX_SUGAR_UNITS = 4        # 皂苷最多接到四個糖基

PROTON_MASS = 1.008        # 酸式 vs 陰離子式
WATER_MASS = 18.015
MAX_HYDRATE_UNITS = 3      # 見 _hydrate_units() 的說明，不要放大

# TCMSP 用 `_qt` 後綴表示苷元（aglycone）。**這不是 quantitative。**
AGLYCONE_SUFFIX = "_qt"

CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).strip(" .;,")


def cleaned_name(name: str) -> str:
    """把 TCMSP 名稱裡常見的雜訊拿掉，供第二層查詢使用。

    TCMSP 的成分名稱常帶括號註記、`_qt` 之類的後綴、或前面掛著編號。
    **刻意不動立體化學前綴**（(+)-、(-)-、alpha-、beta-、(2S)- 等）——
    beta-sitosterol 與 sitosterol 不是同一件事，剝掉會解析到錯的化合物，
    而那正是這整支程式最不能出的錯。
    """
    n = normalize(name)
    # ⚠️ `_qt` 是**苷元**（aglycone），不是 quantitative——舊註解寫錯了。
    # 剝掉它之後查到的必然是**帶糖基的母體苷**，也就是 TCMSP 不要的那一個。
    # 實測：全庫 81 筆分子量不符屬於這個成因，其中 75 筆（93%）名稱以 _qt 結尾，
    # 方向一致（PubChem 較重 80:1）。詳見
    # `claude/成分標準化_人參Step2驗收與苷元誤配.md`。
    #
    # 這裡仍然剝除，因為那是目前唯一能拿到候選的方式；但 mw_check() 會在
    # 分子量重出糖基組合時明講「這是苷元誤配、請否決」，避免被誤按確認。
    # **真正的解法是 CAS／InChIKey 第二層查詢**，尚未實作。
    n = re.sub(r"_qt$", "", n, flags=re.I)
    n = re.sub(r"\s*\[[^\]]*\]\s*", " ", n)         # 方括號註記
    n = re.sub(r"\s*\((?!\+|-|[0-9]*[RSEZ])[^)]*\)\s*", " ", n)  # 括號註記，但保留立體標示
    return normalize(n)


def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _sugar_combination(delta: float):
    """差值能不能用 1~MAX_SUGAR_UNITS 個糖基的組合解釋。

    回傳 `(說明, 總質量)`，解釋不了則回 None。由少到多試，
    先命中的組合糖基數最少，也最可能是真的。
    """
    names = list(SUGAR_RESIDUES)
    for n in range(1, MAX_SUGAR_UNITS + 1):
        for combo in itertools.combinations_with_replacement(names, n):
            total = sum(SUGAR_RESIDUES[c] for c in combo)
            if abs(delta - total) <= MW_TOLERANCE:
                parts = " + ".join(f"{combo.count(c)}×{c}"
                                   for c in dict.fromkeys(combo))
                return parts, total
    return None


def _hydrate_units(delta: float):
    """差值是不是 1~3 個水分子。是就回個數，否則 None。

    **上限刻意壓在 3。** 舊版寫成 `delta % 18.015` 判斷「接近水的倍數」，
    結果 162.1（一個葡萄糖）距離 9 個水只差 0.035、324.2 距離 18 個水差 0.07，
    兩筆都會被判成水合物——而水合物暗示「同一個化合物」，
    正好把審核的人往「按確認」推。**那比沒有提示更糟。**

    三個水以上的水合物本來就罕見，而糖基差在這個資料集裡很常見。
    """
    for n in range(1, MAX_HYDRATE_UNITS + 1):
        if abs(delta - n * WATER_MASS) <= 0.6:
            return n
    return None


def mw_check(tcmsp_mw, pubchem_mw, name: str | None = None) -> dict:
    """分子量交叉驗證。回傳 {agree, delta, reason}。

    `agree` 只有三種值，不要簡化成布林值：
      True   兩邊都有值且相符 → 可以自動採用
      False  兩邊都有值但不符 → 進待確認，並在 note 裡寫出差多少
      None   有一邊沒有值 → **無法驗證**，這跟「驗證通過」是兩回事，
             會降低信心分數但不強制人工確認
    """
    a, b = _num(tcmsp_mw), _num(pubchem_mw)
    if a is None or b is None:
        return {"agree": None, "delta": None,
                "reason": "TCMSP 或 PubChem 缺少分子量，無法交叉驗證"}
    delta = round(abs(a - b), 3)
    if delta <= MW_TOLERANCE:
        return {"agree": True, "delta": delta, "reason": ""}

    # 提示的順序就是「這個差值最可能是什麼」的順序。
    # 糖基要排在水合物前面：162.14（一個葡萄糖）與 9 個水只差 0.035，
    # 先判水合物就會把苷元誤配講成水合物，而水合物暗示同一個化合物。
    is_aglycone = (name or "").strip().lower().endswith(AGLYCONE_SUFFIX)
    pubchem_heavier = b > a
    hint = ""

    if abs(delta - PROTON_MASS) <= 0.2:
        hint = ("（差一個氫，是酸式與陰離子式的差別，"
                "通常是同一個化合物，可以確認）")
    else:
        sugar = _sugar_combination(delta)
        hydrate = _hydrate_units(delta)
        if sugar and pubchem_heavier:
            parts, total = sugar
            if is_aglycone:
                hint = (f"（苷元誤配：名稱的 {AGLYCONE_SUFFIX} 表示苷元，"
                        f"但 PubChem 這一筆重出 {parts}＝{total:.2f} Da，"
                        f"查到的是帶糖基的母體苷，不是同一個分子。"
                        f"請否決並重新解析，不要確認）")
            else:
                hint = (f"（差值等於 {parts}＝{total:.2f} Da 且 PubChem 較重，"
                        f"很可能查到的是糖苷而非苷元，請先確認是不是同一個分子）")
        elif hydrate:
            hint = (f"（差值接近 {hydrate} 個水分子，"
                    f"可能是水合物與無水物的差別）")
        elif is_aglycone:
            hint = (f"（名稱的 {AGLYCONE_SUFFIX} 表示苷元。"
                    f"苷元常因名稱查詢而解析到母體苷，請特別確認分子是否相同）")
        elif delta > 20:
            hint = "（差值偏大，可能是鹽類與游離態，或根本是同名異物）"

    return {"agree": False, "delta": delta,
            "reason": f"分子量不符：TCMSP {a}、PubChem {b}，相差 {delta} Da{hint}"}


def parse_property(entry: dict) -> dict:
    """PubChem property 回應的一筆 → 我們要存的形狀。防禦性解析。"""
    return {
        "cid": str(entry.get("CID") or "") or None,
        "canonical_smiles": entry.get("CanonicalSMILES") or entry.get("SMILES"),
        "isomeric_smiles": entry.get("IsomericSMILES"),
        "inchikey": entry.get("InChIKey"),
        "molecular_formula": entry.get("MolecularFormula"),
        "molecular_weight": (str(entry["MolecularWeight"])
                             if entry.get("MolecularWeight") is not None else None),
        "iupac_name": entry.get("IUPACName"),
    }


def pick_cas(synonyms) -> str | None:
    """從同義詞清單裡挑出 CAS 號。

    PubChem 的 synonyms 是一長串（有時上百筆），CAS 號混在裡面，
    格式固定為 `數字-數字-單一檢查碼`。取第一個符合的即可——
    PubChem 的同義詞是依相關性排序的。
    """
    for s in synonyms or []:
        if CAS_RE.match((s or "").strip()):
            return s.strip()
    return None


# ---------------------------------------------------------------------------
# 外部呼叫（測試裡整支被取代）
# ---------------------------------------------------------------------------

def _get(client: httpx.Client, url: str):
    resp = client.get(url)
    if resp.status_code == 404:
        return None          # PubChem 對查無資料就是回 404，這不是錯誤
    resp.raise_for_status()
    return resp.json()


def search_by_name(client: httpx.Client, name: str) -> list:
    """以名稱查詢，回傳 property 清單（可能多筆）。

    成分名稱會直接進網址路徑，一定要編碼——TCMSP 的名稱裡有斜線、括號、
    逗號、加減號（`(+)-Catechin`、`Vitamin B1/B2`），不編碼會拆錯路徑或送出壞請求。
    `safe=""` 讓斜線也一併編碼，否則 `A/B` 會被 PubChem 當成兩層路徑。
    """
    url = f"{BASE}/name/{quote(name, safe='')}/property/{PROPS}/JSON"
    data = _get(client, url)
    if not data:
        return []
    return (data.get("PropertyTable") or {}).get("Properties") or []


def fetch_synonyms(client: httpx.Client, cid: str) -> list:
    data = _get(client, f"{BASE}/cid/{cid}/synonyms/JSON")
    if not data:
        return []
    info = (data.get("InformationList") or {}).get("Information") or []
    return (info[0].get("Synonym") if info else []) or []


def resolve_name(client: httpx.Client, name: str, tcmsp_mw=None) -> dict:
    """解析單一成分名稱。回傳一定包含 method／confidence／status。

    status：
      auto        自動採用（單一命中且分子量相符）
      pending     需要人確認（多筆命中、分子量不符、或只有清理後才查得到）
      unresolved  查不到
      error       連線或 API 失敗，之後可重跑
    """
    try:
        for method, query in (("exact", normalize(name)),
                              ("cleaned", cleaned_name(name))):
            if not query:
                continue
            if method == "cleaned" and query == normalize(name):
                continue          # 清理後沒變就不用重查一次

            results = search_by_name(client, query)
            if not results:
                continue

            parsed = [parse_property(r) for r in results]

            if len(parsed) > 1:
                return {"method": method, "confidence": METHOD_CONFIDENCE[method],
                        "status": "pending", "candidates": parsed[:5],
                        "tcmsp_mw": tcmsp_mw, "mw_delta": None,
                        "note": f"名稱命中 {len(parsed)} 筆化合物，需人工判斷是哪一個"}

            hit = parsed[0]
            check = mw_check(tcmsp_mw, hit.get("molecular_weight"), name=name)
            hit["tcmsp_mw"] = tcmsp_mw
            hit["mw_delta"] = check["delta"]

            if check["agree"] is False:
                # 名稱對上但分子量不符——這是最危險的情況，絕不自動採用
                return {**hit, "method": method,
                        "confidence": round(METHOD_CONFIDENCE[method] * 0.4, 2),
                        "status": "pending", "candidates": [hit],
                        "note": check["reason"]}

            if method == "cleaned":
                # 清理過名稱才查得到，就算分子量相符也請人看一眼
                return {**hit, "method": method,
                        "confidence": METHOD_CONFIDENCE[method], "status": "pending",
                        "candidates": [hit],
                        "note": f"原名查無結果，以清理後的「{query}」命中" +
                                ("；分子量相符" if check["agree"] else "；" + check["reason"])}

            if check["agree"] is None:
                return {**hit, "method": method, "confidence": 0.7, "status": "auto",
                        "candidates": [], "note": check["reason"]}

            return {**hit, "method": method, "confidence": METHOD_CONFIDENCE[method],
                    "status": "auto", "candidates": [], "note": None}

        return {"method": "exact", "confidence": 0.0, "status": "unresolved",
                "candidates": [], "tcmsp_mw": tcmsp_mw,
                "note": "以原名與清理後的名稱查詢，PubChem 都查無此化合物"}

    except Exception as exc:  # noqa: BLE001
        logger.error("PubChem 解析失敗（%s）：%s", name, exc)
        return {"method": "exact", "confidence": 0.0, "status": "error",
                "candidates": [], "tcmsp_mw": tcmsp_mw,
                "note": f"查詢失敗：{str(exc)[:200]}"}


def resolve_many(items: list, *, timeout: float = 25.0, pause: float = 0.25,
                 with_synonyms: bool = True) -> dict:
    """批次解析。`items` 是 [(mol_id, name, mw), ...]，回傳 {mol_id: 結果}。

    每次查詢間隔 0.25 秒：PubChem 明文要求不要超過每秒 5 次請求。
    抓 CAS 需要對每個命中的 CID 再打一次 synonyms，所以實際上是每筆兩次請求——
    間隔照樣留著，寧可慢也不要被擋。
    """
    out: dict = {}
    if not items:
        return out
    headers = {"Accept": "application/json",
               "User-Agent": "TCM-Onco-Platform/1.0 (research; ingredient standardisation)"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for i, (mol_id, name, mw) in enumerate(items):
            result = resolve_name(client, name, tcmsp_mw=mw)
            if with_synonyms and result.get("cid") and result.get("status") in ("auto", "pending"):
                try:
                    time.sleep(pause)
                    syns = fetch_synonyms(client, result["cid"])
                    result["synonyms"] = syns[:20]
                    result["cas_number"] = pick_cas(syns)
                except Exception as exc:  # noqa: BLE001
                    # 拿不到 CAS 不該讓整筆解析失敗——主要欄位已經有了
                    logger.warning("取 CAS 失敗（cid=%s）：%s", result.get("cid"), exc)
            out[mol_id] = result
            if i + 1 < len(items):
                time.sleep(pause)
    return out


def image_url(cid) -> str | None:
    cid = str(cid or "").strip()
    return IMAGE_URL.format(cid=cid) if cid.isdigit() else None


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)

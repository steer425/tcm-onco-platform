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

所以分子量不符時**一律進待確認**，不自動採用；唯一的例外是能確定錯在哪的
`_qt` 苷元誤配，直接否決（glycoside_mismatch()）。

⚠️ 這支需要對外連到 `pubchem.ncbi.nlm.nih.gov`。Cowork 沙箱與本機 VM 都連不到，
實際執行必須在 Render 上。測試以 fixture 取代網路層。
"""

from __future__ import annotations

import base64
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

METHOD_CONFIDENCE = {"exact": 1.0, "cleaned": 0.8, "aglycone_parent": 0.5,
                     "aglycone_formula": 0.6, "cas": 1.0, "manual": 1.0}

# 多筆命中、但只有一筆分子量吻合時的信心分數。名稱與分子量兩條獨立證據都指向它，
# 但名稱本身有歧義，所以不給滿分。
MW_PICK_CONFIDENCE = 0.9

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

    TCMSP 的成分名稱常帶括號註記、或前面掛著編號。
    **刻意不動立體化學前綴**（(+)-、(-)-、alpha-、beta-、(2S)- 等）——
    beta-sitosterol 與 sitosterol 不是同一件事，剝掉會解析到錯的化合物，
    而那正是這整支程式最不能出的錯。

    **v1.42.9 起不再剝 `_qt`。** `_qt` 不是雜訊，是 TCMSP 的苷元（aglycone）標記；
    剝掉它是另一條有自己判定規則的路徑，見 `aglycone_parent_name()`。
    以前在這裡靜默剝除，審核者看到的 method 是「清理名稱後命中」，
    完全看不出查詢字串已經變成帶糖基的母體苷名稱。
    """
    n = normalize(name)
    n = re.sub(r"\s*\[[^\]]*\]\s*", " ", n)         # 方括號註記
    n = re.sub(r"\s*\((?!\+|-|[0-9]*[RSEZ])[^)]*\)\s*", " ", n)  # 括號註記，但保留立體標示
    return normalize(n)


def is_aglycone(name: str | None) -> bool:
    """名稱是否帶 TCMSP 的苷元標記 `_qt`。"""
    return (name or "").strip().lower().endswith(AGLYCONE_SUFFIX)


def aglycone_parent_name(name: str) -> str | None:
    """`_qt` 苷元 → 去掉標記後的名稱，也就是**母體苷**的名稱。不是苷元則回 None。

    ⚠️ 用這個名稱查 PubChem，查到的**幾乎必然是帶糖基的母體苷**，不是 TCMSP 要的苷元。
    實測全庫 81 筆糖基差裡 75 筆（93%）以 `_qt` 結尾，方向 PubChem 較重 80:1
    （見 `claude/成分標準化_人參Step2驗收與苷元誤配.md`）。

    之所以還查，是因為少數 `_qt` 成分的「母體名」在 PubChem 上其實就是苷元本身
    （分子量會相符）。所以這條路徑的結果一律交給 `resolve_name()` 依分子量判定：
    重出糖基組合 → 否決；相符 → 待確認；其他 → 待確認。**永遠不會自動採用。**
    """
    if not is_aglycone(name):
        return None
    n = normalize(re.sub(r"_qt$", "", normalize(name), flags=re.I))
    return cleaned_name(n) or None


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
    combo = _sugar_combo(delta)
    if not combo:
        return None
    parts = " + ".join(f"{combo.count(c)}×{c}" for c in dict.fromkeys(combo))
    return parts, sum(SUGAR_RESIDUES[c] for c in combo)


def _sugar_combo(delta: float):
    """`_sugar_combination()` 的內部：回傳糖基名稱的 tuple（可重複），解釋不了則 None。

    第二層查詢要用它從母體苷的分子式**扣掉**糖基，所以需要的是「哪幾個糖」，不只是說明文字。
    """
    names = list(SUGAR_RESIDUES)
    for n in range(1, MAX_SUGAR_UNITS + 1):
        for combo in itertools.combinations_with_replacement(names, n):
            if abs(delta - sum(SUGAR_RESIDUES[c] for c in combo)) <= MW_TOLERANCE:
                return combo
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
    aglycone = is_aglycone(name)
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
            if aglycone:
                hint = (f"（苷元誤配：名稱的 {AGLYCONE_SUFFIX} 表示苷元，"
                        f"但 PubChem 這一筆重出 {parts}＝{total:.2f} Da，"
                        f"查到的是帶糖基的母體苷，不是同一個分子。"
                        f"請否決並重新解析，不要確認）")
            else:
                hint = (f"（差值等於 {parts}＝{total:.2f} Da 且 PubChem 較重，"
                        f"很可能查到的是糖苷而非苷元，請先確認是不是同一個分子）")
        elif hydrate and pubchem_heavier:
            hint = (f"（差值接近 {hydrate} 個水分子且 PubChem 較重，可能是水合物，"
                    f"但天然物差 18 也常是羥基化——請確認分子式）")
        elif hydrate:
            hint = (f"（PubChem 少了 {hydrate} 個水分子，這通常是脫水產物，"
                    f"**不是同一個化合物**，請確認分子式）")
        elif aglycone:
            hint = (f"（名稱的 {AGLYCONE_SUFFIX} 表示苷元。"
                    f"苷元常因名稱查詢而解析到母體苷，請特別確認分子是否相同）")
        elif delta > 20:
            hint = "（差值偏大，可能是鹽類與游離態，或根本是同名異物）"

    return {"agree": False, "delta": delta,
            "reason": f"分子量不符：TCMSP {a}、PubChem {b}，相差 {delta} Da{hint}"}


def glycoside_mismatch(name, tcmsp_mw, pubchem_mw) -> str | None:
    """是否為「確定的苷元誤配」。是就回說明（含糖基組合），否則 None。

    三個條件同時成立才算：
      1. 名稱帶 `_qt`（TCMSP 指的是苷元）
      2. PubChem 那一筆**較重**
      3. 差值剛好是 1~4 個糖基的組合

    這是 `resolve_name()` 與 `reclassify_ingredient_queue` 共用的唯一判定，
    **不要在別處重寫一份**（理由同 v1.40.1 的 `_ingredient_pool()`）。

    不帶 `_qt` 的糖基差**不在這裡判否決**：那可能是 TCMSP 自己記錯分子量，
    或名稱本來就指糖苷——方向沒有 `_qt` 那麼確定，留給人看（mw_check 會給提示）。
    """
    if not is_aglycone(name):
        return None
    a, b = _num(tcmsp_mw), _num(pubchem_mw)
    if a is None or b is None or b <= a:
        return None
    sugar = _sugar_combination(round(b - a, 3))
    if not sugar:
        return None
    parts, total = sugar
    return (f"苷元誤配，自動否決：名稱的 {AGLYCONE_SUFFIX} 表示苷元，"
            f"PubChem 這一筆重出 {parts}＝{total:.2f} Da（TCMSP {a}、PubChem {b}），"
            f"是帶糖基的母體苷，不是同一個分子。需以 CAS／InChIKey 第二層查詢重新解析")


def same_compound_form(tcmsp_mw, pubchem_mw) -> str | None:
    """差值是否只是「同一個化合物的不同寫法」。是就回說明，否則 None。

    只認兩種，而且刻意保守：
      ≈0      0.5 Da 內，兩邊小數位慣例不同
      ≈1 質子  酸式 vs 陰離子式（例：arachidonic acid 304.5 vs arachidonate 303.5）

    **v1.42.10 起不再認「差一個水分子」。** v1.42.9 把它當成水合物 vs 無水物，
    正式資料庫跑出來的 3 筆裡至少 1 筆是**不同的化合物**：
    Isotanshinone II（TCMSP 294.37，C19H18O3）查回 276.3——PubChem 比較**輕**，
    那不是水合物，是少了一個水的脫水產物，共價結構不一樣。
    天然物裡差 18 多半是羥基化／脫水這類真正的結構差異，不是結晶水。
    差一個水的一律留給人看。

    供 `reclassify_ingredient_queue` 整批採用時使用；`resolve_name()` 不用它自動採用。
    """
    a, b = _num(tcmsp_mw), _num(pubchem_mw)
    if a is None or b is None:
        return None
    d = abs(a - b)
    if d <= MW_TOLERANCE:
        return "分子量相符（小數位差異）"
    if abs(d - PROTON_MASS) <= 0.2:
        return "差一個氫（酸式 vs 陰離子式），同一化合物"
    return None


def rank_by_mw(parsed: list, tcmsp_mw, name) -> tuple[list, list]:
    """多筆候選依分子量排序。回傳 (排序後全部候選, 分子量相符的候選)。

    每一筆都帶上 `mw_delta`，相符的排前面，其餘依差值由小到大。
    **一定要在截斷前排序**——舊版直接取 `parsed[:5]`，
    分子量相符的那一筆如果排在第 6 個，審核者根本看不到它。
    """
    ranked = []
    for c in parsed:
        chk = mw_check(tcmsp_mw, c.get("molecular_weight"), name=name)
        ranked.append({**c, "mw_delta": chk["delta"], "_agree": chk["agree"]})
    ranked.sort(key=lambda c: (c["_agree"] is not True,
                               c["mw_delta"] if c["mw_delta"] is not None else 1e9))
    agree = [c for c in ranked if c["_agree"] is True]
    for c in ranked:
        c.pop("_agree", None)
    return ranked, agree


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
# 第二層：苷元以「分子式推算＋子結構比對」重新解析（v1.47.0）
# ---------------------------------------------------------------------------
#
# 為什麼不是「用 CAS／InChIKey 查」：TCMSP 只給名稱與分子量，**沒有** CAS、InChIKey、
# 分子式或結構——這些欄位是我們從 PubChem 查回來的，不能拿來當查 PubChem 的鑰匙。
# 對被否決的 `_qt` 苷元，手上真正可靠的是兩件事：
#   1. 母體苷的分子式（第一層查回來的，確定是那個糖苷）
#   2. 差了哪幾個糖基（glycoside_mismatch() 用分子量差算出來的）
# 糖苷水解＝每個糖基斷開時補回一分子水，所以「母體分子式 − 糖基殘基」就是苷元的分子式。
# 再用 PubChem 的子結構指紋排序同分子式的候選：苷元必須是母體苷結構的一部分。
#
# 結果**永遠不自動採用**：同分子式異構物很多，指紋也分不出立體異構物，一律交給人確認。

# 糖基殘基（脫水後）的分子式，與 SUGAR_RESIDUES 的質量一一對應
SUGAR_FORMULA = {
    "己糖（葡萄糖等）": {"C": 6, "H": 10, "O": 5},
    "去氧己糖（鼠李糖等）": {"C": 6, "H": 10, "O": 4},
    "戊糖（木糖、阿拉伯糖等）": {"C": 5, "H": 8, "O": 4},
}
ATOMIC_MASS = {"C": 12.011, "H": 1.008, "N": 14.007, "O": 15.999, "S": 32.06, "P": 30.974,
               "F": 18.998, "Cl": 35.45, "Br": 79.904, "I": 126.904}
FORMULA_RE = re.compile(r"([A-Z][a-z]?)(\d*)")
FORMULA_MAX_RECORDS = 2000      # 分子式查詢最多取幾個 CID（大分子的異構物可能上千）
PROP_CHUNK = 150                # 一次查幾個 CID 的性質（放在網址裡，不能太長）
CONTAIN_MIN = 0.9               # 候選的指紋至少要有這麼多比例包含在母體苷裡，才算「像是它的一部分」
SECOND_TIER_KEEP = 8            # 存幾個候選給審核者看


def parse_formula(formula: str | None) -> dict | None:
    """'C30H52O4' → {'C': 30, 'H': 52, 'O': 4}。帶電荷、點號（鹽、混合物）或認不得的元素回 None。"""
    f = (formula or "").strip()
    if not f or re.search(r"[^A-Za-z0-9]", f):
        return None
    out: dict = {}
    pos = 0
    for m in FORMULA_RE.finditer(f):
        if m.start() != pos:
            return None
        el, n = m.group(1), int(m.group(2) or 1)
        if el not in ATOMIC_MASS:
            return None
        out[el] = out.get(el, 0) + n
        pos = m.end()
    return out if pos == len(f) and out else None


def format_formula(counts: dict) -> str:
    """Hill 排序：C、H 在前，其餘依字母。與 PubChem 的寫法一致。"""
    keys = [k for k in ("C", "H") if counts.get(k)] + sorted(k for k in counts if k not in ("C", "H") and counts[k])
    return "".join(f"{k}{counts[k] if counts[k] != 1 else ''}" for k in keys)


def formula_mass(counts: dict) -> float:
    return round(sum(ATOMIC_MASS[k] * n for k, n in counts.items()), 3)


def aglycone_formula(parent_formula, tcmsp_mw, parent_mw) -> dict:
    """從母體苷推算苷元的分子式。回傳 {ok, formula, mass, sugars, reason}。

    三道檢查都過才算 ok：
      1. 分子量差能用 1~4 個糖基解釋（與 glycoside_mismatch() 同一套組合）
      2. 母體分子式扣得動（每個元素都不會變成負數）
      3. 扣完後的計算分子量與 TCMSP 的分子量相符（±0.5 Da）——這是獨立的驗算，
         確保「差值湊得出糖基」不是巧合
    """
    a, b = _num(tcmsp_mw), _num(parent_mw)
    parent = parse_formula(parent_formula)
    if a is None or b is None or parent is None:
        return {"ok": False, "reason": "缺少 TCMSP 分子量、母體苷分子量或可解析的母體分子式"}
    combo = _sugar_combo(round(b - a, 3)) if b > a else None
    if not combo:
        return {"ok": False, "reason": f"分子量差 {round(b - a, 3)} Da 無法以 1~{MAX_SUGAR_UNITS} 個糖基解釋"}
    agly = dict(parent)
    for sugar in combo:
        for el, n in SUGAR_FORMULA[sugar].items():
            agly[el] = agly.get(el, 0) - n
    if any(v < 0 for v in agly.values()):
        return {"ok": False, "reason": f"母體分子式 {parent_formula} 扣不掉這些糖基"}
    agly = {k: v for k, v in agly.items() if v}
    mass = formula_mass(agly)
    sugars = " + ".join(f"{combo.count(c)}×{c}" for c in dict.fromkeys(combo))
    if abs(mass - a) > MW_TOLERANCE:
        return {"ok": False, "reason": f"扣除 {sugars} 後算出 {format_formula(agly)}（{mass}），"
                                       f"與 TCMSP 分子量 {a} 不符"}
    return {"ok": True, "formula": format_formula(agly), "mass": mass, "sugars": sugars, "reason": ""}


def fp_bits(b64: str | None) -> set | None:
    """PubChem `Fingerprint2D`（881 位元子結構指紋，base64）→ 有設的位元編號集合。

    格式：前 4 個位元組是位元數（big-endian），之後依序是位元，每個位元組由高位開始。
    """
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None
    if len(raw) < 5:
        return None
    n = int.from_bytes(raw[:4], "big")
    data = raw[4:]
    return {i for i in range(min(n, len(data) * 8)) if (data[i // 8] >> (7 - i % 8)) & 1}


def fp_containment(candidate: set, parent: set) -> float:
    """候選的特徵有多少比例也出現在母體苷裡（1.0 = 全部都有）。

    PubChem 的子結構指紋是「含有某種結構片段」的位元，片段越多位元越多；
    如果候選真的是母體苷的一部分，它有的片段母體苷一定也有。
    **這是必要條件不是充分條件**——1.0 不代表一定是子結構，但低於 1 多半不是。
    """
    if not candidate:
        return 0.0
    return round(len(candidate & parent) / len(candidate), 4)


def fp_tanimoto(a: set, b: set) -> float:
    u = len(a | b)
    return round(len(a & b) / u, 4) if u else 0.0


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


def search_by_formula(client: httpx.Client, formula: str,
                      max_records: int = FORMULA_MAX_RECORDS) -> list:
    """以分子式查 CID（只含這些元素，不允許其他元素）。"""
    data = _get(client, f"{BASE}/fastformula/{quote(formula, safe='')}/cids/JSON"
                        f"?MaxRecords={int(max_records)}")
    if not data:
        return []
    return [str(c) for c in ((data.get("IdentifierList") or {}).get("CID") or [])]


def fetch_properties(client: httpx.Client, cids: list, pause: float = 0.25) -> list:
    """一批 CID 的性質（含子結構指紋），分段查詢以免網址過長。"""
    out = []
    cids = [str(c) for c in cids if str(c).isdigit()]
    for i in range(0, len(cids), PROP_CHUNK):
        if i:
            time.sleep(pause)
        chunk = ",".join(cids[i:i + PROP_CHUNK])
        data = _get(client, f"{BASE}/cid/{chunk}/property/{PROPS},Fingerprint2D/JSON")
        out.extend(((data or {}).get("PropertyTable") or {}).get("Properties") or [])
    return out


def resolve_aglycone(client: httpx.Client, name: str, tcmsp_mw, parent: dict) -> dict:
    """第二層：被否決的 `_qt` 苷元，從母體苷推算分子式後重新找候選。

    `parent` 是第一層查回來的母體苷（至少要有 cid、molecular_formula、molecular_weight）。
    回傳的 status 只有 pending（找到像樣的候選，等人確認）、unresolved（推算不出或找不到）、
    error（連線失敗，之後可重跑）。**永遠不會是 auto。**
    """
    try:
        derived = aglycone_formula(parent.get("molecular_formula"), tcmsp_mw,
                                   parent.get("molecular_weight"))
        base = {"method": "aglycone_formula", "tcmsp_mw": tcmsp_mw, "candidates": [],
                "derived_formula": derived.get("formula")}
        head = (f"第一層以母體名查到 CID {parent.get('cid')}（{parent.get('molecular_formula')}，"
                f"{parent.get('molecular_weight')}）是帶糖基的母體苷，已否決。")
        if not derived["ok"]:
            return {**base, "status": "unresolved", "confidence": 0.0,
                    "note": f"{head}第二層無法推算苷元分子式：{derived['reason']}"}

        cids = search_by_formula(client, derived["formula"])
        cids = [c for c in cids if c != str(parent.get("cid"))]
        step = (f"{head}第二層：扣除 {derived['sugars']} 推算苷元為 {derived['formula']}"
                f"（計算分子量 {derived['mass']}，TCMSP {tcmsp_mw}）")
        if not cids:
            return {**base, "status": "unresolved", "confidence": 0.0,
                    "note": f"{step}，但 PubChem 查無此分子式的化合物"}

        time.sleep(0.25)
        props = fetch_properties(client, cids + [str(parent.get("cid"))])
        pfp = next((fp_bits(p.get("Fingerprint2D")) for p in props
                    if str(p.get("CID")) == str(parent.get("cid"))), None)
        if not pfp:
            return {**base, "status": "error", "confidence": 0.0,
                    "note": f"{step}；取不到母體苷的結構指紋，稍後重跑"}

        ranked = []
        for p in props:
            if str(p.get("CID")) == str(parent.get("cid")):
                continue
            fp = fp_bits(p.get("Fingerprint2D"))
            if not fp:
                continue
            c = parse_property(p)
            c["containment"] = fp_containment(fp, pfp)
            c["similarity"] = fp_tanimoto(fp, pfp)
            c["mw_delta"] = mw_check(tcmsp_mw, c.get("molecular_weight"))["delta"]
            ranked.append(c)
        ranked.sort(key=lambda c: (-c["containment"], -c["similarity"],
                                   c["mw_delta"] if c["mw_delta"] is not None else 1e9))
        top = ranked[0] if ranked else None
        if not top or top["containment"] < CONTAIN_MIN:
            return {**base, "status": "unresolved", "confidence": 0.0,
                    "candidates": ranked[:SECOND_TIER_KEEP],
                    "note": f"{step}；PubChem 有 {len(cids)} 筆同分子式化合物，"
                            f"但沒有一筆的結構特徵像是母體苷的一部分"}

        # 同一平面結構（InChIKey 第一段相同）的立體異構物，指紋分不出來
        conn = (top.get("inchikey") or "")[:14]
        same_2d = [c for c in ranked if conn and (c.get("inchikey") or "")[:14] == conn]
        full = [c for c in ranked if c["containment"] >= 1.0]
        clear = top["containment"] >= 1.0 and len({(c.get("inchikey") or "")[:14] for c in full}) == 1
        note = (f"{step}；PubChem 有 {len(cids)} 筆同分子式化合物，依「是否為母體苷結構的一部分」排序，"
                f"第一名 CID {top['cid']} 的結構特徵 {round(top['containment'] * 100)}% 包含在母體苷中")
        if len(same_2d) > 1:
            note += f"；其中 {len(same_2d)} 筆是同一平面結構的立體異構物（指紋分不出），請依母體苷的立體構型挑選"
        elif not clear:
            note += "；另有不同結構的候選同樣吻合，請比對結構"
        note += "。結構推算結果一律需人工確認"
        return {**top, **base, "candidates": ranked[:SECOND_TIER_KEEP], "status": "pending",
                "confidence": METHOD_CONFIDENCE["aglycone_formula"] if clear else 0.4, "note": note}
    except Exception as exc:  # noqa: BLE001
        logger.error("苷元第二層解析失敗（%s）：%s", name, exc)
        return {"method": "aglycone_formula", "status": "error", "confidence": 0.0,
                "candidates": [], "tcmsp_mw": tcmsp_mw, "note": f"第二層查詢失敗：{str(exc)[:200]}"}


def resolve_name(client: httpx.Client, name: str, tcmsp_mw=None) -> dict:
    """解析單一成分名稱。回傳一定包含 method／confidence／status。

    status：
      auto        自動採用（單一命中且分子量相符；或多筆命中但只有一筆分子量相符）
      pending     需要人確認（分子量不符、多筆都相符、或只有清理後才查得到）
      rejected    確定是錯的分子（`_qt` 苷元查回母體苷，見 glycoside_mismatch()）
      unresolved  查不到
      error       連線或 API 失敗，之後可重跑

    查詢分三層，**由嚴到寬**：
      exact            原名
      cleaned          拿掉括號、方括號註記（保留立體標示）
      aglycone_parent  只對 `_qt` 苷元：去掉標記改查母體名，結果永不自動採用
    """
    try:
        attempts = [("exact", normalize(name)), ("cleaned", cleaned_name(name))]
        parent = aglycone_parent_name(name)
        if parent:
            attempts.append(("aglycone_parent", parent))

        tried = set()
        for method, query in attempts:
            if not query or query in tried:
                continue          # 清理後沒變就不用重查一次
            tried.add(query)

            results = search_by_name(client, query)
            if not results:
                continue

            parsed = [parse_property(r) for r in results]
            conf = METHOD_CONFIDENCE[method]

            if len(parsed) > 1:
                ranked, agree = rank_by_mw(parsed, tcmsp_mw, name)
                base = {"method": method, "tcmsp_mw": tcmsp_mw,
                        "candidates": ranked[:5]}
                if len(agree) == 1:
                    hit = {**agree[0], "tcmsp_mw": tcmsp_mw}
                    pick_note = (f"名稱命中 {len(parsed)} 筆化合物，"
                                 f"其中只有 CID {hit['cid']} 的分子量與 TCMSP 相符"
                                 f"（差 {hit['mw_delta']} Da）")
                    if method == "exact":
                        return {**hit, **base, "confidence": MW_PICK_CONFIDENCE,
                                "status": "auto", "note": pick_note + "，自動採用"}
                    where = ("以母體名" if method == "aglycone_parent" else "以清理後的名稱")
                    return {**hit, **base, "confidence": conf, "status": "pending",
                            "note": f"原名查無結果，{where}「{query}」命中；{pick_note}，請確認"}
                if not agree and method == "aglycone_parent":
                    reasons = [glycoside_mismatch(name, tcmsp_mw, c.get("molecular_weight"))
                               for c in ranked]
                    if all(reasons):
                        return {**base, "cid": None, "mw_delta": ranked[0]["mw_delta"],
                                "confidence": 0.0, "status": "rejected",
                                "note": f"母體名「{query}」命中 {len(parsed)} 筆，全部是"
                                        f"帶糖基的母體苷。{reasons[0]}"}
                if agree:
                    note = (f"名稱命中 {len(parsed)} 筆化合物，其中 {len(agree)} 筆分子量都相符"
                            f"（可能是立體異構物，分子量分不出來），需人工判斷是哪一個")
                else:
                    note = (f"名稱命中 {len(parsed)} 筆化合物，沒有一筆分子量與 TCMSP 相符，"
                            f"需人工判斷")
                return {**base, "confidence": conf, "status": "pending",
                        "mw_delta": None, "note": note}

            hit = parsed[0]
            check = mw_check(tcmsp_mw, hit.get("molecular_weight"), name=name)
            hit["tcmsp_mw"] = tcmsp_mw
            hit["mw_delta"] = check["delta"]

            if method == "aglycone_parent":
                wrong = glycoside_mismatch(name, tcmsp_mw, hit.get("molecular_weight"))
                if wrong:
                    # 結構欄位照樣留著（與人工否決一致），rejected 不在 ACCEPTED_STATUS，
                    # 反查與覆蓋率都不會用到它；留著是讓人看得到「當初查到了什麼」
                    return {**hit, "method": method, "confidence": 0.0,
                            "status": "rejected", "candidates": [hit], "note": wrong}
                verdict = ("分子量相符，可能母體名在 PubChem 上就是苷元本身"
                           if check["agree"] else check["reason"])
                return {**hit, "method": method,
                        "confidence": round(conf * (1 if check["agree"] else 0.4), 2),
                        "status": "pending", "candidates": [hit],
                        "note": f"原名查無結果，去掉苷元標記 {AGLYCONE_SUFFIX} 以母體名"
                                f"「{query}」命中；{verdict}。請確認是不是苷元，不是母體苷"}

            if check["agree"] is False:
                # 名稱對上但分子量不符——這是最危險的情況，絕不自動採用
                return {**hit, "method": method,
                        "confidence": round(conf * 0.4, 2),
                        "status": "pending", "candidates": [hit],
                        "note": check["reason"]}

            if method == "cleaned":
                # 清理過名稱才查得到，就算分子量相符也請人看一眼
                return {**hit, "method": method,
                        "confidence": conf, "status": "pending",
                        "candidates": [hit],
                        "note": f"原名查無結果，以清理後的「{query}」命中" +
                                ("；分子量相符" if check["agree"] else "；" + check["reason"])}

            if check["agree"] is None:
                return {**hit, "method": method, "confidence": 0.7, "status": "auto",
                        "candidates": [], "note": check["reason"]}

            return {**hit, "method": method, "confidence": conf,
                    "status": "auto", "candidates": [], "note": None}

        return {"method": "exact", "confidence": 0.0, "status": "unresolved",
                "candidates": [], "tcmsp_mw": tcmsp_mw,
                "note": ("以原名、清理後的名稱與母體名查詢，PubChem 都查無此化合物"
                         if parent else
                         "以原名與清理後的名稱查詢，PubChem 都查無此化合物")}

    except Exception as exc:  # noqa: BLE001
        logger.error("PubChem 解析失敗（%s）：%s", name, exc)
        return {"method": "exact", "confidence": 0.0, "status": "error",
                "candidates": [], "tcmsp_mw": tcmsp_mw,
                "note": f"查詢失敗：{str(exc)[:200]}"}


# 只有這兩種狀態算「已標準化」，與 app/routers/ingredient_mapping.py 的 ACCEPTED 一致。
ACCEPTED_STATUS = ("auto", "confirmed")


def best_mapping_by_mol(db, mol_ids):
    """回傳 {mol_id: 最佳映射列}。**全站唯一一份判定，不要再各自寫一次。**

    `tcmsp_ingredient_pubchem` 的唯一鍵是 `(mol_id, cid)`，同一個成分合法可以有
    多筆（人工確認時挑了不同 CID 就會出現）。「哪一筆代表這個成分」必須只有一個
    答案——已採用（auto／confirmed）優先，其次才是 pending 之類的候選。

    v1.40.1 的事故就是同一個母體判定被寫了兩份、兩邊回答了不同的問題
    （見 `rules.md`「進度數字與批次佇列必須共用同一支母體判定」）。這裡先把
    「最佳映射」收斂成一支，避免驗收腳本與前台端點日後各自漂移。
    """
    from app import models
    if not mol_ids:
        return {}
    rows = (db.query(models.TcmspIngredientPubchem)
            .filter(models.TcmspIngredientPubchem.mol_id.in_(list(mol_ids))).all())
    best = {}
    for r in rows:
        cur = best.get(r.mol_id)
        if cur is None:
            best[r.mol_id] = r
        elif r.status in ACCEPTED_STATUS and cur.status not in ACCEPTED_STATUS:
            best[r.mol_id] = r
    return best


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


def resolve_aglycones_many(items: list, *, timeout: float = 30.0, pause: float = 0.25) -> dict:
    """第二層批次。`items` 是 [(mol_id, name, tcmsp_mw, parent), ...]，回傳 {mol_id: 結果}。

    每筆約 2～15 次請求（分子式查詢＋分段取性質＋第一名的同義詞），間隔照樣 0.25 秒。
    """
    out: dict = {}
    if not items:
        return out
    headers = {"Accept": "application/json",
               "User-Agent": "TCM-Onco-Platform/1.0 (research; aglycone resolution)"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for i, (mol_id, name, mw, parent) in enumerate(items):
            result = resolve_aglycone(client, name, mw, parent)
            if result.get("status") == "pending" and result.get("cid"):
                try:
                    time.sleep(pause)
                    syns = fetch_synonyms(client, result["cid"])
                    result["synonyms"] = syns[:20]
                    result["cas_number"] = pick_cas(syns)
                except Exception as exc:  # noqa: BLE001
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

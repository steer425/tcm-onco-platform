"""
疾病的腫瘤分類（v1.46.0）——判定規則只有這一份。

TCMSP 的 837 種疾病沒有「是不是腫瘤」的欄位，腫瘤是混在一般疾病裡的子集合。
這支模組替每一筆疾病判定 `tumor_class`，寫回 `tcmsp_diseases`：

    malignant    惡性腫瘤（癌症）       ICD-10 C00–C97／ICD-9 140–209
    in_situ      原位癌                 ICD-10 D00–D09／ICD-9 230–234
    benign       良性腫瘤               ICD-10 D10–D36、D3A／ICD-9 210–229
    uncertain    性質未明的腫瘤         ICD-10 D37–D49／ICD-9 235–239
    unspecified  腫瘤，但無法分良惡性   只有病名（例如 "Solid tumors"、"Neoplasms"）
    None         非腫瘤

判定依據 `tumor_basis` 依優先順序：
    manual  管理者在後台手動指定 —— **自動分類永遠不覆蓋**
    icd10   ICD-10 代碼
    icd9    ICD-9 代碼（沒有 ICD-10 時）
    name    病名關鍵字（兩種 ICD 都沒有時）
    None    非腫瘤，且沒有任何依據指向腫瘤

設計上刻意的取捨：
1. **ICD 優先於病名**。病名含 cancer 不代表是腫瘤本身（"Cancer pain" 是 R52 疼痛），
   病名不含任何關鍵字也可能是腫瘤（"Polycythemia vera" 是 D45）。
   兩者不一致時依 ICD，但列進 `conflicts` 給人看——資料本身的 ICD 也可能填錯，
   那就用後台手動指定修正。
2. **多個代碼取最嚴重的**：同一筆疾病可能同時掛 C 與 D 碼（例如 "C50,D05"），
   以 malignant > in_situ > uncertain > benign 排序取第一個。
3. **病名比對用完整字詞清單，不用 `-oma` 字尾**：glaucoma、hematoma、granuloma、
   trachoma 都不是腫瘤。
4. **Benign prostatic hyperplasia 不是腫瘤**（ICD-10 N40，增生不是贅生），
   neurofibromatosis 歸在先天異常（Q85），aneurysm／動脈瘤 是血管疾病。
"""
import re
from typing import Dict, List, Optional, Tuple

# 顯示用的中文名稱（前端另有同一份對照，見 frontend/js/tumor-class.js）
TUMOR_CLASS_LABELS = {
    "malignant": "惡性腫瘤",
    "in_situ": "原位癌",
    "benign": "良性腫瘤",
    "uncertain": "性質未明的腫瘤",
    "unspecified": "腫瘤（未分良惡性）",
}
TUMOR_BASIS_LABELS = {"manual": "管理者指定", "icd10": "ICD-10", "icd9": "ICD-9", "name": "病名"}
VALID_CLASSES = set(TUMOR_CLASS_LABELS)

# 多個代碼時取最嚴重的
_SEVERITY = ["malignant", "in_situ", "uncertain", "benign", "unspecified"]

# ---------------------------------------------------------------------------
# ICD
# ---------------------------------------------------------------------------
# ICD-10：一個英文字母＋兩位數（第二位可能是字母，例如 ICD-10-CM 的 C7A、D3A），可帶小數
_ICD10_RE = re.compile(r"\b([A-Z])(\d)([0-9A-Z])(?:\.[0-9A-Z]+)?\b")
_ICD10_RANGE_RE = re.compile(r"\b([A-Z])(\d{2})(?:\.\d+)?\s*[-–~]\s*\1?(\d{2})(?:\.\d+)?\b")
# ICD-9：三位數字可帶小數；V／E 碼是補充分類，跟腫瘤無關，不採
_ICD9_RE = re.compile(r"(?<![A-Za-z\d.])(\d{3})(?:\.\d+)?(?![\d])")
_ICD9_RANGE_RE = re.compile(r"(?<![A-Za-z\d.])(\d{3})(?:\.\d+)?\s*[-–~]\s*(\d{3})(?:\.\d+)?(?![\d])")


def _icd10_class(letter: str, num: int, second_alpha: bool = False) -> Optional[str]:
    if letter == "C":
        return "malignant"           # C00–C97（含 ICD-10-CM 的 C7A／C7B）
    if letter == "D":
        if second_alpha:              # D3A 良性神經內分泌腫瘤
            return "benign"
        if num <= 9:
            return "in_situ"
        if num <= 36:
            return "benign"
        if num <= 49:
            return "uncertain"        # D37–D48（WHO），D49（ICD-10-CM 未明性質）
    return None


def _icd9_class(num: int) -> Optional[str]:
    if 140 <= num <= 209:
        return "malignant"
    if 210 <= num <= 229:
        return "benign"
    if 230 <= num <= 234:
        return "in_situ"
    if 235 <= num <= 239:
        return "uncertain"
    return None


def _worst(classes: List[Optional[str]]) -> Optional[str]:
    found = [c for c in classes if c]
    if not found:
        return None
    return min(found, key=_SEVERITY.index)


def classify_icd10(value: Optional[str]) -> Tuple[bool, Optional[str]]:
    """回傳 (有沒有可用的 ICD-10 代碼, 腫瘤分類)。"""
    if not value or not str(value).strip():
        return False, None
    s = str(value).upper()
    classes, any_code = [], False
    for m in _ICD10_RANGE_RE.finditer(s):
        any_code = True
        letter, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        for n in range(min(a, b), max(a, b) + 1):
            classes.append(_icd10_class(letter, n))
    for m in _ICD10_RE.finditer(s):
        any_code = True
        letter, d1, d2 = m.group(1), m.group(2), m.group(3)
        if d2.isdigit():
            classes.append(_icd10_class(letter, int(d1 + d2)))
        else:
            classes.append(_icd10_class(letter, int(d1) * 10, second_alpha=True))
    return any_code, _worst(classes)


def classify_icd9(value: Optional[str]) -> Tuple[bool, Optional[str]]:
    if not value or not str(value).strip():
        return False, None
    s = str(value).upper()
    classes, any_code = [], False
    for m in _ICD9_RANGE_RE.finditer(s):
        any_code = True
        a, b = int(m.group(1)), int(m.group(2))
        for n in range(min(a, b), max(a, b) + 1):
            classes.append(_icd9_class(n))
    for m in _ICD9_RE.finditer(s):
        any_code = True
        classes.append(_icd9_class(int(m.group(1))))
    return any_code, _worst(classes)


# ---------------------------------------------------------------------------
# 病名
# ---------------------------------------------------------------------------
_MALIGNANT_WORDS = [
    r"cancers?", r"carcinomas?", r"adenocarcinomas?", r"carcinomatosis", r"sarcomas?",
    r"leuka?emias?", r"lymphomas?", r"myelomas?", r"melanomas?", r"mesotheliomas?",
    r"gliomas?", r"glioblastomas?", r"astrocytomas?", r"oligodendrogliomas?", r"ependymomas?",
    r"neuroblastomas?", r"retinoblastomas?", r"medulloblastomas?", r"hepatoblastomas?",
    r"nephroblastomas?", r"blastomas?", r"hepatomas?", r"seminomas?", r"choriocarcinomas?",
    r"teratocarcinomas?", r"germinomas?", r"malignan\w*", r"metasta\w*", r"hodgkin\w*",
    r"wilms", r"kaposi\w*", r"waldenstr\w*", r"macroglobulinemia", r"mycosis fungoides",
    r"sezary", r"insulinomas?", r"gastrinomas?", r"pheochromocytomas?", r"carcinoids?",
]
_UNCERTAIN_WORDS = [
    r"myelodysplastic\w*", r"myeloproliferative\w*", r"polycyth(?:a)?emia vera",
    r"essential thrombocyth(?:a)?emia", r"myelofibrosis",
]
_BENIGN_WORDS = [
    r"adenomas?", r"fibromas?", r"lipomas?", r"leiomyomas?", r"myomas?", r"fibroids?",
    r"h(?:a)?emangiomas?", r"papillomas?", r"meningiomas?", r"neuromas?", r"schwannomas?",
    r"osteomas?", r"chondromas?", r"prolactinomas?",
]
_GENERIC_WORDS = [r"tumou?rs?", r"neoplasms?", r"neoplasia", r"oncolog\w*"]

# 病名有腫瘤字樣，但指的是腫瘤的併發症或治療副作用，不是腫瘤本身
_COMPLICATION_WORDS = [
    r"pain", r"cachexia", r"nausea", r"vomiting", r"emesis", r"an(?:a)?emia", r"neutropenia",
    r"mucositis", r"fatigue", r"lysis", r"hypercalc(?:a)?emia", r"induced", r"related",
    r"necrosis factor",
]
# 長得像腫瘤字樣但不是腫瘤
_NOT_TUMOR_WORDS = [
    r"hyperplasia", r"neurofibromatosis", r"aneurysms?", r"glaucoma", r"h(?:a)?ematomas?",
    r"granulomas?", r"trachoma",
]

_CN_MALIGNANT = ["癌", "肉瘤", "白血病", "淋巴瘤", "骨髓瘤", "黑色素瘤", "膠質瘤", "胶质瘤", "母細胞瘤", "母细胞瘤"]
_CN_BENIGN = ["腺瘤", "肌瘤", "纖維瘤", "纤维瘤", "脂肪瘤", "血管瘤", "乳突瘤", "乳头状瘤", "腦膜瘤", "脑膜瘤"]
_CN_GENERIC = ["腫瘤", "肿瘤", "贅生物", "赘生物"]
_CN_NOT_TUMOR = ["動脈瘤", "动脉瘤", "增生", "痛", "惡病質", "恶病质"]


def _rx(words):
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)


_RX_MAL, _RX_UNC, _RX_BEN, _RX_GEN = _rx(_MALIGNANT_WORDS), _rx(_UNCERTAIN_WORDS), _rx(_BENIGN_WORDS), _rx(_GENERIC_WORDS)
_RX_COMPLICATION, _RX_NOT = _rx(_COMPLICATION_WORDS), _rx(_NOT_TUMOR_WORDS)


def classify_name(name: Optional[str], cn_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """回傳 (腫瘤分類, 排除原因)。排除原因非空時分類為 None，但代表病名有腫瘤字樣、值得人看一眼。"""
    en = (name or "").strip()
    cn = (cn_name or "").strip()
    hit = None
    if en:
        if _RX_UNC.search(en):
            hit = "uncertain"
        elif _RX_MAL.search(en):
            hit = "malignant"
        elif _RX_BEN.search(en):
            hit = "benign"
        elif _RX_GEN.search(en):
            hit = "unspecified"
    if not hit and cn:
        if any(w in cn for w in _CN_MALIGNANT):
            hit = "malignant"
        elif any(w in cn for w in _CN_BENIGN):
            hit = "benign"
        elif any(w in cn for w in _CN_GENERIC):
            hit = "unspecified"
    if not hit:
        return None, None
    if en and _RX_NOT.search(en):
        return None, "病名含腫瘤字樣，但屬於非腫瘤疾病（" + _RX_NOT.search(en).group(0) + "）"
    if en and _RX_COMPLICATION.search(en):
        return None, "病名含腫瘤字樣，但指的是腫瘤併發症／治療副作用（" + _RX_COMPLICATION.search(en).group(0) + "）"
    if not en and any(w in cn for w in _CN_NOT_TUMOR):
        return None, "中文病名含腫瘤字樣，但屬於非腫瘤疾病"
    return hit, None


# ---------------------------------------------------------------------------
# 整合
# ---------------------------------------------------------------------------
def classify_disease(name, cn_name, icd9, icd10) -> Dict:
    """
    回傳 {"tumor_class", "tumor_basis", "conflict"}。
    conflict 是給人看的說明：ICD 與病名判斷不一致、或病名有腫瘤字樣但被排除。
    """
    name_cls, name_excluded = classify_name(name, cn_name)
    has10, cls10 = classify_icd10(icd10)
    if has10:
        cls, basis = cls10, ("icd10" if cls10 else None)
    else:
        has9, cls9 = classify_icd9(icd9)
        if has9:
            cls, basis = cls9, ("icd9" if cls9 else None)
        else:
            cls, basis = name_cls, ("name" if name_cls else None)
            return {"tumor_class": cls, "tumor_basis": basis, "conflict": name_excluded}

    conflict = None
    if bool(cls) != bool(name_cls) and not name_excluded:
        if cls:
            conflict = f"ICD 判定為{TUMOR_CLASS_LABELS[cls]}，但病名沒有腫瘤字樣"
        else:
            conflict = f"病名判定為{TUMOR_CLASS_LABELS[name_cls]}，但 ICD 代碼不在腫瘤範圍"
    elif name_excluded and cls:
        conflict = f"ICD 判定為{TUMOR_CLASS_LABELS[cls]}；" + name_excluded
    return {"tumor_class": cls, "tumor_basis": basis, "conflict": conflict}


def apply_tumor_classification(db, dry_run: bool = False) -> Dict:
    """
    對所有疾病重新判定並寫回（`tumor_basis == "manual"` 的不動）。
    回傳統計與需要人工看一眼的清單；dry_run 時不寫入。
    可重複執行，結果只取決於疾病本身的病名與 ICD，不取決於執行順序。
    """
    from app import models

    diseases = db.query(models.TcmspDisease).all()
    counts = {c: 0 for c in list(VALID_CLASSES) + ["none"]}
    by_basis = {"manual": 0, "icd10": 0, "icd9": 0, "name": 0}
    changed, conflicts = [], []
    for d in diseases:
        if d.tumor_basis == "manual":
            counts[d.tumor_class or "none"] += 1
            by_basis["manual"] += 1
            continue
        r = classify_disease(d.disease_name, d.disease_cn_name, d.icd9, d.icd10)
        counts[r["tumor_class"] or "none"] += 1
        if r["tumor_basis"]:
            by_basis[r["tumor_basis"]] += 1
        if (d.tumor_class, d.tumor_basis) != (r["tumor_class"], r["tumor_basis"]):
            changed.append({"dis_id": d.dis_id, "disease_name": d.disease_name,
                            "from": d.tumor_class, "to": r["tumor_class"], "basis": r["tumor_basis"]})
            if not dry_run:
                d.tumor_class, d.tumor_basis = r["tumor_class"], r["tumor_basis"]
        if r["conflict"]:
            conflicts.append({"dis_id": d.dis_id, "disease_name": d.disease_name, "icd9": d.icd9,
                              "icd10": d.icd10, "tumor_class": r["tumor_class"], "note": r["conflict"]})
    if not dry_run:
        db.commit()
    return {
        "total": len(diseases),
        "tumor_total": sum(v for k, v in counts.items() if k != "none"),
        "counts": counts,
        "by_basis": by_basis,
        "changed": changed,
        "conflicts": conflicts,
    }

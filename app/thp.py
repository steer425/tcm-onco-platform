"""F1-10 兩岸中藥典比較：臺灣中藥典第四版的載入與 TCMSP 藥材比對（v1.51.0）。

## 載入：不需要任何人在本機輸入正式資料庫連線字串

`app/data/thp_v4.json` 由 tools/parse_thp_pdf.py 從衛福部公告的 PDF 解析而來、進版控。
伺服器每次啟動呼叫 `ensure_loaded()`：檔案雜湊與 system_settings 裡記的一樣就什麼都不做；
不一樣（第一次上線、或日後重新解析）才整批 upsert，接著重跑比對。

## 比對：為什麼不能只比名稱

臺灣中藥典是繁體、TCMSP 是簡體 → JSON 裡已先轉好簡體（name_s）。
拉丁名兩邊的「種類」不同：臺灣中藥典是**拉丁生藥名**（GINSENG RADIX ET RHIZOMA，屬名屬格＋藥用部位），
TCMSP 的 herb_en_name 多為**植物學名**（Panax Ginseng C. A. Mey）——不能直接比。所以用三種證據：

  name     簡體中文名完全相同（藥材名或子名）
  species  TCMSP 學名的前兩個字（屬＋種小名）在臺灣中藥典基原的物種清單裡
           ——清單含第四版「基原植物學名修正對照表」的第三版舊學名，TCMSP 是 2014 年資料，多用舊學名
  latin    TCMSP 名稱若是生藥名寫法（Radix Ginseng），字詞都出現在臺灣的拉丁生藥名裡（不計順序）

判定：
  name＋(species 或 latin)           → auto
  只有 name                          → pending；TCMSP 名稱看得出是另一個物種 → 旗標「同名異物」
  只有 species／latin（名稱不同）     → pending，旗標「異名同物」
  飲片只比中文名（例：紅參 ↔ 红参），且跳過與所屬藥材同名的飲片（大黃的飲片「大黃」）
  濃縮製劑不比對

**重新比對只動 auto／pending；confirmed、rejected 與人工指定的列一律不碰**（與成分／靶點標準化相同的原則）。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from app import models

DATA_PATH = Path(__file__).resolve().parent / "data" / "thp_v4.json"
VERSION_KEY = "thp_data_version"
SITE_URL = "https://www.cmthp.mohw.gov.tw/Search/SearchDetail?v=4&p={site_no}"
ACCEPTED = ("auto", "confirmed")
REVIEWED = ("confirmed", "rejected")          # 人工判過的，重新比對不碰
FIELDS = ["origin", "content", "description", "identification", "impurity", "assay", "storage",
          "category", "nature_meridian", "functions", "usage_dosage", "precautions"]
LATIN_STOP = {"et", "cum", "seu", "vel", "praeparata", "praeparatum", "preparata"}

_data_cache: dict | None = None


def load_json() -> dict:
    global _data_cache
    if _data_cache is None:
        _data_cache = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return _data_cache


def data_version() -> str:
    return hashlib.sha1(DATA_PATH.read_bytes()).hexdigest()[:16]


def site_url(site_no: str | None) -> str | None:
    return SITE_URL.format(site_no=site_no) if site_no else None


# ---------------------------------------------------------------------------
# 載入
# ---------------------------------------------------------------------------
def _get_setting(db, key):
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return row.value if row else None


def _set_setting(db, key, value):
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(models.SystemSetting(key=key, value=value))


def ensure_loaded(db, force: bool = False) -> dict:
    """JSON 有變才寫入。回傳 {loaded: 筆數或 0, matched: 比對結果或 None}。"""
    version = data_version()
    if not force and _get_setting(db, VERSION_KEY) == version \
            and db.query(models.ThpMonograph).count() > 0:
        # 資料沒變；但若 TCMSP 藥材是之後才匯入的，比對表會一直是空的 → 補跑一次
        if db.query(models.ThpTcmspMap).count() == 0 \
                and db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active").count() > 0:
            return {"loaded": 0, "matched": rematch(db), "version": version}
        return {"loaded": 0, "matched": None, "version": version}
    data = load_json()
    by_name_parent = {}
    existing = {m.seq: m for m in db.query(models.ThpMonograph).all()}
    for it in data["items"]:
        row = existing.get(it["seq"]) or models.ThpMonograph(seq=it["seq"])
        row.site_no = it["site_no"]
        row.kind = it["kind"]
        row.name_zh = it["name_zh"]
        row.name_s = it.get("name_s")
        row.latin_name = it.get("latin_name")
        row.en_name = it.get("en_name")
        for f in FIELDS:
            setattr(row, f, it.get(f))
        row.species = json.dumps(it.get("species") or [], ensure_ascii=False)
        row.extra = json.dumps(it["extra"], ensure_ascii=False) if it.get("extra") else None
        row.amendment = json.dumps(it["amendment"], ensure_ascii=False) if it.get("amendment") else None
        row.book_page = it.get("book_page")
        row.data_version = version
        if it["kind"] != "processed":
            by_name_parent[it["name_zh"]] = it["seq"]
        if it["seq"] not in existing:
            db.add(row)
    db.flush()
    # 飲片 → 所屬藥材（parent 存的是中文名；同名不同品項不會發生在藥材層）
    for it in data["items"]:
        if it["kind"] == "processed":
            m = db.query(models.ThpMonograph).filter(models.ThpMonograph.seq == it["seq"]).first()
            m.parent_seq = by_name_parent.get(it["parent"])
    _set_setting(db, VERSION_KEY, version)
    db.commit()
    matched = rematch(db)
    return {"loaded": len(data["items"]), "matched": matched, "version": version}


# ---------------------------------------------------------------------------
# 比對
# ---------------------------------------------------------------------------
# 兩岸慣用字不同、但確定是同一味藥的字（中國藥典「黄芪」／臺灣中藥典「黃耆」）。只放確定的；
# 其餘名稱差異交給學名比對，結果進待確認，不要在這裡越加越多（加錯會把不同的藥自動採用）
CN_VARIANTS = str.maketrans({"芪": "耆"})


def _norm_cn(s: str | None) -> str:
    return re.sub(r"[\s（）()·．・]", "", s or "").translate(CN_VARIANTS)


# 生藥名的藥用部位字。TCMSP 若寫成「Radix Bupleuri」，長得跟學名一樣是「大寫字＋小寫字」，
# 不先排除會被當成物種「radix bupleuri」，還會誤標同名異物（第一版測試就踩到）
PART_WORDS = {"radix", "rhizoma", "herba", "folium", "flos", "fructus", "semen", "cortex", "ramulus", "caulis",
              "pericarpium", "bulbus", "concha", "spica", "lignum", "resina", "medulla", "pollen", "exocarpium",
              "cacumen", "stigma", "tuber", "squama", "carapax", "cornu", "os", "fel", "periostracum", "galla",
              "massa", "pulvis", "oleum", "aloe", "endothelium", "plastrum", "nodus", "fasciculus", "sclerotium"}


def _species_of_tcmsp(en: str | None) -> str | None:
    """「Panax Ginseng C. A. Mey」→「panax ginseng」；不像學名（第一個字小寫、只有一個字、是生藥名）回 None。"""
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", en or "")
    if len(words) < 2 or not words[0][0].isupper() or words[0].lower() in PART_WORDS \
            or words[1].lower() in PART_WORDS:
        return None
    return f"{words[0].lower()} {words[1].lower()}"


def _latin_tokens(s: str | None) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z]+", s or "")} - LATIN_STOP


def species_index() -> dict[str, set[str]]:
    """第四版新學名 ↔ 第三版舊學名，雙向都認。"""
    syn: dict[str, set[str]] = {}
    for r in load_json().get("synonyms", []):
        a, b = (r.get("new_species") or "").lower(), (r.get("old_species") or "").lower()
        if a and b and a != b:
            syn.setdefault(a, set()).add(b)
            syn.setdefault(b, set()).add(a)
    return syn


def thp_species(m, syn) -> set[str]:
    base = {s.lower() for s in json.loads(m.species or "[]")}
    out = set(base)
    for s in base:
        out |= syn.get(s, set())
    return out


def candidates(m, herbs, syn) -> dict[int, dict]:
    """一個臺灣中藥典品項 → {herb_id: {method, status, flags}}。"""
    if m.kind == "preparation":
        return {}
    name = _norm_cn(m.name_s)
    sp = thp_species(m, syn)
    lat = _latin_tokens(m.latin_name)
    out = {}
    for h in herbs:
        ev, flags = [], []
        names = {_norm_cn(h.herb_cn_name), _norm_cn(h.child_cn_name)} - {""}
        if name and name in names:
            ev.append("name")
        if m.kind != "processed":
            hs = _species_of_tcmsp(h.herb_en_name) or _species_of_tcmsp(h.child_en_name)
            if hs and hs in sp:
                ev.append("species")
            ht = _latin_tokens(h.herb_en_name)
            if not hs and len(ht) >= 2 and lat and ht <= lat:
                ev.append("latin")
        if not ev:
            continue
        if m.kind == "processed":
            flags.append("processed")
        if "name" in ev and len(ev) > 1:
            status = "auto"
        else:
            status = "pending"
            if ev == ["name"] and m.kind != "processed":
                hs = _species_of_tcmsp(h.herb_en_name)
                if hs and sp and hs not in sp:
                    flags.append("same_name_diff_species")
            elif "name" not in ev:
                flags.append("diff_name_same_species")
        out[h.id] = {"method": "+".join(ev), "status": status, "flags": flags}
    return out


def rematch(db) -> dict:
    """重算所有 auto／pending；人工判過的（confirmed／rejected／人工指定）不動。回傳統計。"""
    herbs = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active").all()
    syn = species_index()
    mons = db.query(models.ThpMonograph).all()
    name_of = {m.seq: m.name_zh for m in mons}
    existing = {}
    for r in db.query(models.ThpTcmspMap).all():
        existing[(r.thp_seq, r.herb_id)] = r
    seen = set()
    added = updated = removed = 0
    for m in mons:
        # 與所屬藥材同名的飲片（大黃的飲片「大黃」、黃耆的飲片「黃耆」）：對應關係跟藥材本身一樣，
        # 再比一次只會在審核佇列多一筆重複的待確認
        if m.kind == "processed" and name_of.get(m.parent_seq) == m.name_zh:
            continue
        for herb_id, c in candidates(m, herbs, syn).items():
            key = (m.seq, herb_id)
            seen.add(key)
            row = existing.get(key)
            if row is None:
                db.add(models.ThpTcmspMap(thp_seq=m.seq, herb_id=herb_id, method=c["method"],
                                          status=c["status"], flags=json.dumps(c["flags"]) if c["flags"] else None))
                added += 1
            elif row.status not in REVIEWED and row.method != "manual":
                if (row.method, row.status, row.flags) != (c["method"], c["status"], json.dumps(c["flags"]) if c["flags"] else None):
                    row.method, row.status = c["method"], c["status"]
                    row.flags = json.dumps(c["flags"]) if c["flags"] else None
                    updated += 1
    for key, row in existing.items():
        if key not in seen and row.status not in REVIEWED and row.method != "manual":
            db.delete(row)
            removed += 1
    db.commit()
    return {"added": added, "updated": updated, "removed": removed, **stats(db)}


def stats(db) -> dict:
    mons = db.query(models.ThpMonograph).all()
    maps = db.query(models.ThpTcmspMap).all()
    by_seq = {}
    for r in maps:
        by_seq.setdefault(r.thp_seq, []).append(r)
    comparable = [m for m in mons if m.kind != "preparation"]
    accepted = [m for m in comparable if any(r.status in ACCEPTED for r in by_seq.get(m.seq, []))]
    pending = [m for m in comparable if m not in accepted
               and any(r.status == "pending" for r in by_seq.get(m.seq, []))]
    herbs_matched = {r.herb_id for r in maps if r.status in ACCEPTED}
    n_herbs = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active").count()
    return {
        "thp_items": len(mons), "comparable": len(comparable),
        "matched": len(accepted), "pending_only": len(pending),
        "thp_only": len(comparable) - len(accepted) - len(pending),
        "tcmsp_herbs": n_herbs, "tcmsp_matched": len(herbs_matched),
        "same_name_diff_species": sum(1 for r in maps if r.flags and "same_name_diff_species" in r.flags
                                      and r.status != "rejected"),
        "review_queue": sum(1 for r in maps if r.status == "pending"),
    }


def review(db, row, action: str, user, note: str | None = None):
    row.status = {"confirm": "confirmed", "reject": "rejected"}[action]
    row.reviewed_by = user.id if user else None
    row.reviewed_at = datetime.utcnow()
    if note is not None:
        row.note = note

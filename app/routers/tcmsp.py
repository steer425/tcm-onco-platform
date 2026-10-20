import json
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db, get_query_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/tcmsp", tags=["目標一/二：TCMSP 藥材關聯資料庫"])

# 完整資料量約 10 萬筆關聯，每次即時查詢+序列化組裝耗時較久，改用簡易記憶體快取，
# 直接快取「已序列化好的 JSON bytes」，命中快取時完全跳過查詢與序列化開銷。
# 資料只會透過「後台下架藥材」或「重新執行匯入腳本」變動，變動頻率低，
# 快取 TTL 設定 10 分鐘；後台下架藥材時另外主動清除快取，確保立即生效。
_full_data_cache = {"json_bytes": None, "expires_at": 0}
_CACHE_TTL_SECONDS = 600


def _invalidate_full_data_cache():
    _full_data_cache["json_bytes"] = None
    _full_data_cache["expires_at"] = 0


def _disease_out(d):
    """前台各查詢站共用的疾病欄位。tumor_class／tumor_basis 見 app/disease_tumor.py（v1.46.0）。"""
    return {
        "dis_id": d.dis_id, "disease_id": d.disease_id, "disease_name": d.disease_name,
        "disease_cn_name": d.disease_cn_name, "icd9": d.icd9, "icd10": d.icd10,
        "tumor_class": d.tumor_class, "tumor_basis": d.tumor_basis,
    }


def _val(v):
    """資料庫欄位皆以字串儲存，這裡嘗試轉回數值型別供前端使用（轉換失敗則維持字串/None）"""
    if v is None or v == "":
        return None
    try:
        if "." in v:
            return float(v)
        return int(v)
    except (ValueError, TypeError):
        return v


# ---------------------------------------------------------------------------
# 前台／一般登入使用者：查詢用（供 tcmsp_query.html 使用）
# ---------------------------------------------------------------------------

@router.get("/herbs/public/list", summary="（前台）取得藥材清單（輕量，不含關聯資料，供左側清單快速載入；靶點數為預先計算好的統計欄位）")
def public_list_herbs(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    herbs = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active").all()
    return [
        {
            "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
            "herb_en_name": h.herb_en_name, "child_cn_name": h.child_cn_name, "child_en_name": h.child_en_name,
            "target_count": h.target_count, "dark_gene_count": h.dark_gene_count,
        }
        for h in herbs
    ]


@router.get("/herbs/public/{herb_id}/detail", summary="（前台）取得單一藥材的完整關聯資料（成分/靶點/疾病，範圍限定在這個藥材）")
def public_get_herb_detail(herb_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id, models.TcmspHerb.status == "active").first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.herb_id == herb_id).all()
    mol_ids = [r.mol_id for r in herb_ingredient_rows]

    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.mol_id.in_(mol_ids)).all() if mol_ids else []
    tar_ids = list({r.tar_id for r in ingredient_target_rows})

    target_disease_rows = db.query(models.TcmspTargetDisease).filter(models.TcmspTargetDisease.tar_id.in_(tar_ids)).all() if tar_ids else []
    dis_ids = list({r.dis_id for r in target_disease_rows})

    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    targets = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id.in_(tar_ids)).all() if tar_ids else []
    diseases = db.query(models.TcmspDisease).filter(models.TcmspDisease.dis_id.in_(dis_ids)).all() if dis_ids else []

    return {
        "herbs": [{
            "herb_id": herb.id, "herb_cn_name": herb.herb_cn_name, "herb_pinyin": herb.herb_pinyin,
            "herb_en_name": herb.herb_en_name, "child_cn_name": herb.child_cn_name, "child_en_name": herb.child_en_name,
        }],
        "ingredients": [
            {
                "mol_id": i.mol_id, "molecule_name": i.molecule_name, "mw": _val(i.mw),
                "hdon": _val(i.hdon), "hacc": _val(i.hacc), "alogp": _val(i.alogp),
                "halflife": _val(i.halflife), "ob": _val(i.ob), "caco2": _val(i.caco2),
                "bbb": _val(i.bbb), "dl": _val(i.dl), "fasa": _val(i.fasa),
                "tpsa": _val(i.tpsa), "rbn": _val(i.rbn), "source": i.source,
            }
            for i in ingredients
        ],
        "targets": [
            {
                "tar_id": t.tar_id, "target_id": t.target_id, "drugbank_id": t.drugbank_id,
                "target_name": t.target_name, "kegg": t.kegg, "source": t.source,
            }
            for t in targets
        ],
        "diseases": [
            _disease_out(d)
            for d in diseases
        ],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
        "ingredient_target": [
            {"mol_id": r.mol_id, "tar_id": r.tar_id, "validated": r.validated, "svm_score": _val(r.svm_score), "rf_score": _val(r.rf_score)}
            for r in ingredient_target_rows
        ],
        "target_disease": [{"tar_id": r.tar_id, "dis_id": r.dis_id} for r in target_disease_rows],
    }


@router.get("/herbs/public/{herb_id}/active-ingredients",
            summary="（前台）藥材的活性成分清單與 PubChem 標準化狀態（目標一 Step 1＋Step 2）")
def public_herb_active_ingredients(
        herb_id: int,
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_query_db)):
    """回答一句話：**這味藥材的活性成分，每一個都拿到化學結構了嗎？**

    F1-6 頁面的覆蓋率是**全庫**數字（例：1,303／2,632），它回答不了目標一真正的
    驗收條件——那是逐一藥材、逐一成分的問題。全庫 49.5% 可能代表某味藥 22 筆全中，
    也可能一筆都沒中，兩者在全庫卡片上長得一模一樣。

    活性成分判定一律呼叫 `pathways.active_ingredients()`、最佳映射一律呼叫
    `tcmsp_pubchem.best_mapping_by_mol()`，**兩者都不在這裡重寫**
    （見 `rules.md`「進度數字與批次佇列必須共用同一支母體判定」）。

    ⚠️ 回傳的成分名稱是 TCMSP 的英文原名。**資料庫沒有成分的中文名稱，也沒有化學
    分類欄位**，所以這裡不提供——要顯示就得另建對照表，那是另一件事，不能在端點裡
    臨時湊。
    """
    from app import pathways, tcmsp_pubchem as pc

    herb = (db.query(models.TcmspHerb)
            .filter(models.TcmspHerb.id == herb_id,
                    models.TcmspHerb.status == "active").first())
    if not herb:
        raise HTTPException(status_code=404, detail="找不到這個藥材，或它已被下架。")

    ob_min, dl_min = pathways.adme_thresholds(db)
    meta = pathways.active_ingredients(db, herb_id, ob_min, dl_min)
    mol_ids = meta["passed"]
    # v1.49.2：非活性成分（OB／DL 未達或 ADME 缺值）也列出來，原因由 active_ingredients() 判定
    failed = {f["mol_id"]: f["reason"] for f in meta.get("failed", [])}
    all_ids = list(mol_ids) + list(failed)

    ings = {}
    if all_ids:
        ings = {i.mol_id: i for i in
                db.query(models.TcmspIngredient)
                .filter(models.TcmspIngredient.mol_id.in_(all_ids)).all()}
    mapping = pc.best_mapping_by_mol(db, all_ids)

    def _has(v):
        return bool((v or "").strip())

    def _item(mol_id):
        ing = ings.get(mol_id)
        m = mapping.get(mol_id)
        return {
            "mol_id": mol_id,
            "molecule_name": ing.molecule_name if ing else None,
            "mw": _val(ing.mw) if ing else None,
            "ob": _val(ing.ob) if ing else None,
            "dl": _val(ing.dl) if ing else None,
            # 沒有映射列代表這個成分還沒被批次解析處理過，與「查無結果」不同
            "status": m.status if m else "untouched",
            "cid": m.cid if m else None,
            "inchikey": m.inchikey if m else None,
            "cas_number": m.cas_number if m else None,
            "has_smiles": _has(m.canonical_smiles) if m else False,
            "has_cas": _has(m.cas_number) if m else False,
            "has_inchikey": _has(m.inchikey) if m else False,
            "mw_delta": _val(m.mw_delta) if m else None,
            # IUPAC 系統名稱（PubChem 回傳）：化合物沒有拉丁文名稱，國際通用的標準命名是這個
            "iupac_name": (m.iupac_name or None) if m else None,
            "note": m.note if m else None,
        }

    items = [_item(mol_id) for mol_id in sorted(mol_ids)]
    inactive_items = []
    for mol_id in sorted(failed):
        it = _item(mol_id)
        it["reason"] = failed[mol_id]
        inactive_items.append(it)

    accepted = [i for i in items if i["status"] in pc.ACCEPTED_STATUS]
    by_status = {}
    for i in items:
        by_status[i["status"]] = by_status.get(i["status"], 0) + 1

    return {
        "herb": {
            "herb_id": herb.id, "herb_cn_name": herb.herb_cn_name,
            "herb_en_name": herb.herb_en_name, "herb_pinyin": herb.herb_pinyin,
        },
        "thresholds": {"ob_min": ob_min, "dl_min": dl_min},
        "totals": {
            "all_ingredients": meta["total"],
            "active": meta["passed_count"],
            "inactive": len(inactive_items),
            "missing_adme": meta["missing_adme"],
            "standardised": len(accepted),
            "with_smiles": sum(1 for i in accepted if i["has_smiles"]),
            "with_cas": sum(1 for i in accepted if i["has_cas"]),
            "with_inchikey": sum(1 for i in accepted if i["has_inchikey"]),
        },
        "by_status": by_status,
        "items": items,
        # 不計入上面任何統計（已標準化、有 SMILES…都只算活性成分）
        "inactive_items": inactive_items,
    }


@router.get("/data/full", summary="取得完整 TCMSP 關聯資料（前台查詢站使用，內建快取）")
def get_full_data(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    now = time.time()
    if _full_data_cache["json_bytes"] is not None and _full_data_cache["expires_at"] > now:
        return Response(content=_full_data_cache["json_bytes"], media_type="application/json")

    herbs = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active").all()
    ingredients = db.query(models.TcmspIngredient).all()
    targets = db.query(models.TcmspTarget).all()
    diseases = db.query(models.TcmspDisease).all()
    herb_ingredient = db.query(models.TcmspHerbIngredient).all()
    ingredient_target = db.query(models.TcmspIngredientTarget).all()
    target_disease = db.query(models.TcmspTargetDisease).all()

    active_herb_ids = {h.id for h in herbs}

    result = {
        "herbs": [
            {
                "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
                "herb_en_name": h.herb_en_name, "child_cn_name": h.child_cn_name, "child_en_name": h.child_en_name,
            }
            for h in herbs
        ],
        "ingredients": [
            {
                "mol_id": i.mol_id, "molecule_name": i.molecule_name, "mw": _val(i.mw),
                "hdon": _val(i.hdon), "hacc": _val(i.hacc), "alogp": _val(i.alogp),
                "halflife": _val(i.halflife), "ob": _val(i.ob), "caco2": _val(i.caco2),
                "bbb": _val(i.bbb), "dl": _val(i.dl), "fasa": _val(i.fasa),
                "tpsa": _val(i.tpsa), "rbn": _val(i.rbn), "source": i.source,
            }
            for i in ingredients
        ],
        "targets": [
            {
                "tar_id": t.tar_id, "target_id": t.target_id, "drugbank_id": t.drugbank_id,
                "target_name": t.target_name, "kegg": t.kegg, "source": t.source,
            }
            for t in targets
        ],
        "diseases": [
            _disease_out(d)
            for d in diseases
        ],
        "herb_ingredient": [
            {"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient if r.herb_id in active_herb_ids
        ],
        "ingredient_target": [
            {
                "mol_id": r.mol_id, "tar_id": r.tar_id,
                "validated": r.validated, "svm_score": _val(r.svm_score), "rf_score": _val(r.rf_score),
            }
            for r in ingredient_target
        ],
        "target_disease": [{"tar_id": r.tar_id, "dis_id": r.dis_id} for r in target_disease],
    }

    _full_data_cache["json_bytes"] = json.dumps(result, ensure_ascii=False).encode("utf-8")
    _full_data_cache["expires_at"] = now + _CACHE_TTL_SECONDS
    return Response(content=_full_data_cache["json_bytes"], media_type="application/json")


# ---------------------------------------------------------------------------
# 後台管理（僅限管理者）：藥材資料 CRUD（依 F0-9 全站 CRUD 規範）
# 成分/靶點/疾病/關聯表資料量龐大且為批次匯入的參考資料，暫不提供逐筆後台編輯，
# 如需更新請重新執行 app/import_tcmsp_data.py 匯入腳本。
# ---------------------------------------------------------------------------

@router.get("/herbs", summary="（後台）查詢藥材列表")
def admin_list_herbs(keyword: Optional[str] = None, status_filter: Optional[str] = None,
                      db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.TcmspHerb)
    if keyword:
        q = q.filter(
            (models.TcmspHerb.herb_cn_name.ilike(f"%{keyword}%")) |
            (models.TcmspHerb.herb_en_name.ilike(f"%{keyword}%")) |
            (models.TcmspHerb.herb_pinyin.ilike(f"%{keyword}%"))
        )
    if status_filter:
        q = q.filter(models.TcmspHerb.status == status_filter)
    herbs = q.order_by(models.TcmspHerb.id).all()
    return [
        {
            "id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
            "herb_en_name": h.herb_en_name, "child_cn_name": h.child_cn_name,
            "child_en_name": h.child_en_name, "status": h.status, "notes": h.notes,
        }
        for h in herbs
    ]


@router.put("/herbs/{herb_id}", summary="（後台）編輯藥材（狀態/備注）")
def admin_update_herb(herb_id: int, payload: dict, db: Session = Depends(get_db),
                       admin: models.User = Depends(require_admin)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id).first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")
    if "status" in payload:
        herb.status = payload["status"]
    if "notes" in payload:
        herb.notes = payload["notes"]
    db.commit()
    _invalidate_full_data_cache()
    write_audit_log(db, admin, "update_tcmsp_herb", "tcmsp_herb", str(herb_id), f"編輯藥材 {herb.herb_en_name}")
    return {"message": "已更新"}


@router.delete("/herbs/{herb_id}", summary="（後台）刪除藥材（軟刪除：下架，不會出現在前台查詢站）")
def admin_delete_herb(herb_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id).first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")
    herb.status = "inactive"
    db.commit()
    _invalidate_full_data_cache()
    write_audit_log(db, admin, "delete_tcmsp_herb_soft", "tcmsp_herb", str(herb_id), f"下架藥材 {herb.herb_en_name}")
    return {"message": "已下架（軟刪除）"}


# ---------------------------------------------------------------------------
# 後台管理（僅限管理者）：疾病中文名稱維護
# 疾病本身不提供新增/刪除（隨 TCMSP 匯入腳本管理），只開放編輯中文名稱／備注，
# 供管理者逐步補齊、修正翻譯。
# ---------------------------------------------------------------------------

@router.get("/diseases/public/list", summary="（前台）取得疾病清單（輕量，不含關聯資料，供左側清單快速載入；靶點數為預先計算好的統計欄位）")
def public_list_diseases(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    diseases = db.query(models.TcmspDisease).all()
    return [
        {**_disease_out(d), "target_count": d.target_count}
        for d in diseases
    ]


@router.get("/diseases/public/{dis_id}/detail", summary="（前台）取得單一疾病的完整關聯資料（靶點/成分/藥材，範圍限定在這個疾病）")
def public_get_disease_detail(dis_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    disease = db.query(models.TcmspDisease).filter(models.TcmspDisease.dis_id == dis_id).first()
    if not disease:
        raise HTTPException(status_code=404, detail="找不到疾病資料")

    target_disease_rows = db.query(models.TcmspTargetDisease).filter(models.TcmspTargetDisease.dis_id == dis_id).all()
    tar_ids = [r.tar_id for r in target_disease_rows]

    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.tar_id.in_(tar_ids)).all() if tar_ids else []
    mol_ids = list({r.mol_id for r in ingredient_target_rows})

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    herb_ids = list({r.herb_id for r in herb_ingredient_rows})

    targets = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id.in_(tar_ids)).all() if tar_ids else []
    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    herbs = db.query(models.TcmspHerb).filter(models.TcmspHerb.id.in_(herb_ids), models.TcmspHerb.status == "active").all() if herb_ids else []

    return {
        "diseases": [_disease_out(disease)],
        "targets": [
            {"tar_id": t.tar_id, "target_id": t.target_id, "drugbank_id": t.drugbank_id, "target_name": t.target_name, "kegg": t.kegg, "source": t.source}
            for t in targets
        ],
        "ingredients": [
            {
                "mol_id": i.mol_id, "molecule_name": i.molecule_name, "mw": _val(i.mw),
                "hdon": _val(i.hdon), "hacc": _val(i.hacc), "alogp": _val(i.alogp),
                "halflife": _val(i.halflife), "ob": _val(i.ob), "caco2": _val(i.caco2),
                "bbb": _val(i.bbb), "dl": _val(i.dl), "fasa": _val(i.fasa),
                "tpsa": _val(i.tpsa), "rbn": _val(i.rbn), "source": i.source,
            }
            for i in ingredients
        ],
        "herbs": [
            {
                "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
                "herb_en_name": h.herb_en_name, "child_cn_name": h.child_cn_name, "child_en_name": h.child_en_name,
            }
            for h in herbs
        ],
        "target_disease": [{"tar_id": r.tar_id, "dis_id": r.dis_id} for r in target_disease_rows],
        "ingredient_target": [
            {"mol_id": r.mol_id, "tar_id": r.tar_id, "validated": r.validated, "svm_score": _val(r.svm_score), "rf_score": _val(r.rf_score)}
            for r in ingredient_target_rows
        ],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
    }


@router.get("/diseases", summary="（後台）查詢疾病列表（可搜尋、可篩選尚無中文名稱的項目）")
def admin_list_diseases(keyword: Optional[str] = None, missing_cn_only: Optional[bool] = None,
                         tumor: Optional[str] = None,
                         db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.TcmspDisease)
    if keyword:
        q = q.filter(
            (models.TcmspDisease.disease_name.ilike(f"%{keyword}%")) |
            (models.TcmspDisease.disease_cn_name.ilike(f"%{keyword}%")) |
            (models.TcmspDisease.dis_id.ilike(f"%{keyword}%"))
        )
    if missing_cn_only:
        q = q.filter(
            (models.TcmspDisease.disease_cn_name.is_(None)) | (models.TcmspDisease.disease_cn_name == "")
        )
    # tumor：tumor＝只看腫瘤、non_tumor＝只看非腫瘤、manual＝只看管理者手動指定過的、
    # review＝自動判定與病名不一致（需要人工看一眼）。review 要逐筆跑判定，放在 SQL 篩選之後
    if tumor == "tumor":
        q = q.filter(models.TcmspDisease.tumor_class.isnot(None))
    elif tumor == "non_tumor":
        q = q.filter(models.TcmspDisease.tumor_class.is_(None))
    elif tumor == "manual":
        q = q.filter(models.TcmspDisease.tumor_basis == "manual")
    diseases = q.order_by(models.TcmspDisease.disease_id).all()
    from app.disease_tumor import classify_disease
    out = []
    for d in diseases:
        auto = classify_disease(d.disease_name, d.disease_cn_name, d.icd9, d.icd10)
        if tumor == "review" and not auto["conflict"]:
            continue
        out.append({
            **_disease_out(d), "notes": d.notes,
            # 自動判定的結果與需要確認的原因：手動指定過的也照樣算出來，讓管理者看得到「如果交回自動會是什麼」
            "tumor_auto_class": auto["tumor_class"], "tumor_auto_basis": auto["tumor_basis"],
            "tumor_review_note": auto["conflict"],
        })
    return out


@router.put("/diseases/{dis_id}", summary="（後台）編輯疾病中文名稱／備注／腫瘤分類")
def admin_update_disease(dis_id: str, payload: dict, db: Session = Depends(get_db),
                          admin: models.User = Depends(require_admin)):
    disease = db.query(models.TcmspDisease).filter(models.TcmspDisease.dis_id == dis_id).first()
    if not disease:
        raise HTTPException(status_code=404, detail="找不到疾病資料")
    if "disease_cn_name" in payload:
        disease.disease_cn_name = payload["disease_cn_name"] or None
    if "notes" in payload:
        disease.notes = payload["notes"]

    # 腫瘤分類（v1.46.0）：值是分類代碼＝手動指定；"none"＝手動指定為非腫瘤；"auto"＝交回自動判定。
    # 沒帶這個欄位就不動——中文名稱的儲存按鈕不能順手把分類改掉
    from app.disease_tumor import TUMOR_CLASS_LABELS, VALID_CLASSES, classify_disease
    tumor_note = ""
    if "tumor_class" in payload:
        want = (payload["tumor_class"] or "").strip()
        before = (disease.tumor_class, disease.tumor_basis)
        if want == "auto":
            r = classify_disease(disease.disease_name, disease.disease_cn_name, disease.icd9, disease.icd10)
            disease.tumor_class, disease.tumor_basis = r["tumor_class"], r["tumor_basis"]
        elif want in ("none", ""):
            disease.tumor_class, disease.tumor_basis = None, "manual"
        elif want in VALID_CLASSES:
            disease.tumor_class, disease.tumor_basis = want, "manual"
        else:
            raise HTTPException(status_code=400, detail=f"不認得的腫瘤分類：{want}")
        if (disease.tumor_class, disease.tumor_basis) != before:
            lbl = lambda c: TUMOR_CLASS_LABELS.get(c, "非腫瘤") if c else "非腫瘤"
            how = "交回自動判定" if want == "auto" else "手動指定"
            tumor_note = f"腫瘤分類 {lbl(before[0])} → {lbl(disease.tumor_class)}（{how}）"
    db.commit()
    _invalidate_full_data_cache()
    parts = []
    if "disease_cn_name" in payload:
        parts.append(f"中文名稱 → {disease.disease_cn_name}")
    if tumor_note:
        parts.append(tumor_note)
    write_audit_log(db, admin, "update_tcmsp_disease", "tcmsp_disease", dis_id,
                     f"編輯疾病 {disease.disease_name}：" + ("；".join(parts) or "備注"))
    return {
        "dis_id": disease.dis_id, "disease_name": disease.disease_name,
        "disease_cn_name": disease.disease_cn_name, "notes": disease.notes,
        "tumor_class": disease.tumor_class, "tumor_basis": disease.tumor_basis,
    }

import json
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
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

@router.get("/data/full", summary="取得完整 TCMSP 關聯資料（前台查詢站使用，內建快取）")
def get_full_data(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
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
            {
                "dis_id": d.dis_id, "disease_id": d.disease_id, "disease_name": d.disease_name,
                "icd9": d.icd9, "icd10": d.icd10,
            }
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

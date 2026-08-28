"""成分標準化（TCMSP → PubChem）後台 API。功能代碼 F1-6。

跟靶點標準化（F1-4）同一套形狀：批次、可重複執行、回傳還剩幾筆、
已人工確認或否決的不被重跑覆蓋。

差別在**驗收方式**：靶點只能靠人看名稱對不對，成分可以拿 TCMSP 既有的
分子量跟 PubChem 交叉驗證，所以「名稱對上但分子量不符」會被自動攔下來
進待確認，不會靜默採用到錯的化合物。

⚠️ 解析需要對外連到 pubchem.ncbi.nlm.nih.gov，必須在 Render 上執行。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, tcmsp_pubchem as pc
from app.database import get_db, get_query_db
from app.deps import get_current_user, require_admin, write_audit_log
from app.news.service import dumps, loads

router = APIRouter(prefix="/tcmsp/ingredient-mapping",
                   tags=["目標一 Step 2：成分標準化（PubChem）"])

FEATURE = "F1-6"
ACCEPTED = ("auto", "confirmed")


def _row_out(row: models.TcmspIngredientPubchem, name: str | None = None) -> dict:
    return {
        "id": row.id, "mol_id": row.mol_id, "molecule_name": name,
        "cid": row.cid, "canonical_smiles": row.canonical_smiles,
        "isomeric_smiles": row.isomeric_smiles, "inchikey": row.inchikey,
        "molecular_formula": row.molecular_formula,
        "molecular_weight": row.molecular_weight,
        "iupac_name": row.iupac_name, "cas_number": row.cas_number,
        "synonyms": loads(row.synonyms, []),
        "tcmsp_mw": row.tcmsp_mw, "mw_delta": row.mw_delta,
        "image_url": pc.image_url(row.cid),
        "method": row.method, "confidence": float(row.confidence or 0),
        "status": row.status, "candidates": loads(row.candidates, []),
        "note": row.note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/stats", summary="（後台）成分標準化覆蓋率")
def mapping_stats(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    total = db.query(models.TcmspIngredient).count()
    rows = (db.query(models.TcmspIngredientPubchem.status,
                     func.count(models.TcmspIngredientPubchem.id))
            .group_by(models.TcmspIngredientPubchem.status).all())
    by_status = {s: c for s, c in rows}
    done = (db.query(func.count(func.distinct(models.TcmspIngredientPubchem.mol_id)))
            .filter(models.TcmspIngredientPubchem.status.in_(ACCEPTED)).scalar() or 0)
    touched = (db.query(func.count(func.distinct(
        models.TcmspIngredientPubchem.mol_id))).scalar() or 0)
    with_smiles = (db.query(models.TcmspIngredientPubchem)
                   .filter(models.TcmspIngredientPubchem.canonical_smiles.isnot(None),
                           models.TcmspIngredientPubchem.status.in_(ACCEPTED)).count())
    with_cas = (db.query(models.TcmspIngredientPubchem)
                .filter(models.TcmspIngredientPubchem.cas_number.isnot(None),
                        models.TcmspIngredientPubchem.status.in_(ACCEPTED)).count())
    # 分子量不符而被攔下來的筆數——這個數字本身就是驗證有沒有在運作的指標
    mw_flagged = (db.query(models.TcmspIngredientPubchem)
                  .filter(models.TcmspIngredientPubchem.status == "pending",
                          models.TcmspIngredientPubchem.mw_delta.isnot(None)).count())
    return {
        "total_ingredients": total,
        "resolved": done,
        "remaining": max(0, total - touched),
        "coverage": round(done / total, 4) if total else 0,
        "with_smiles": with_smiles,
        "with_cas": with_cas,
        "mw_mismatch_pending": mw_flagged,
        "by_status": {k: by_status.get(k, 0) for k in
                      ("auto", "confirmed", "pending", "rejected", "unresolved", "error")},
    }


class ResolveIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    retry_errors: bool = Field(default=False)
    active_only: bool = Field(
        default=True,
        description="只解析通過 OB／DL 篩選的活性成分（預設）。"
                    "TCMSP 有 29384 個成分，全部解析要跑很久，而分析真正用到的是活性成分。")


@router.post("/resolve", summary="（後台）批次解析尚未處理的成分")
def resolve_batch(payload: ResolveIn,
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    done_ids = db.query(models.TcmspIngredientPubchem.mol_id)
    if payload.retry_errors:
        done_ids = done_ids.filter(models.TcmspIngredientPubchem.status != "error")

    # ob／dl 是 String 欄位（可攜型別規範，見 rules.md），資料庫端無法可靠地
    # 做數值比較——SQLite 與 Postgres 的字串轉數字語法不同，而且遇到 'NA' 會炸。
    # 所以撈出候選之後在 Python 端精確篩選，再取這一批。
    # 先在 SQL 端限定欄位，避免把近三萬筆完整資料列全部載進記憶體。
    rows = (db.query(models.TcmspIngredient.mol_id, models.TcmspIngredient.molecule_name,
                     models.TcmspIngredient.mw, models.TcmspIngredient.ob,
                     models.TcmspIngredient.dl)
            .filter(~models.TcmspIngredient.mol_id.in_(done_ids),
                    models.TcmspIngredient.molecule_name.isnot(None))
            .order_by(models.TcmspIngredient.mol_id).all())

    if payload.active_only:
        # 只解析活性成分。TCMSP 收錄近三萬個成分，絕大多數口服吸收率極低或
        # 不具類藥性，根本不會出現在任何分析裡——先花時間解析它們沒有意義，
        # 而且每筆要打兩次 PubChem，全跑一遍是好幾個小時。
        ob_min, dl_min = _adme_thresholds(db)
        rows = [r for r in rows if _is_active(r.ob, r.dl, ob_min, dl_min)]

    remaining_before = len(rows)
    items = rows[:payload.limit]
    if not items:
        return {"processed": 0, "auto": 0, "pending": 0, "unresolved": 0,
                "error": 0, "mw_mismatch": 0, "remaining": 0}

    if payload.retry_errors:
        stale = (db.query(models.TcmspIngredientPubchem)
                 .filter(models.TcmspIngredientPubchem.status == "error",
                         models.TcmspIngredientPubchem.mol_id.in_(
                             [i.mol_id for i in items])).all())
        for row in stale:
            db.delete(row)
        db.flush()

    results = pc.resolve_many([(i.mol_id, i.molecule_name, i.mw) for i in items])

    tally = {"auto": 0, "pending": 0, "unresolved": 0, "error": 0}
    mw_mismatch = 0
    for item in items:
        r = results.get(item.mol_id) or {}
        status = r.get("status", "error")
        tally[status] = tally.get(status, 0) + 1
        if r.get("mw_delta") is not None and status == "pending":
            mw_mismatch += 1
        db.add(models.TcmspIngredientPubchem(
            mol_id=item.mol_id, cid=r.get("cid"),
            canonical_smiles=r.get("canonical_smiles"),
            isomeric_smiles=r.get("isomeric_smiles"),
            inchikey=r.get("inchikey"),
            molecular_formula=r.get("molecular_formula"),
            molecular_weight=r.get("molecular_weight"),
            iupac_name=r.get("iupac_name"), cas_number=r.get("cas_number"),
            synonyms=dumps(r.get("synonyms") or []),
            tcmsp_mw=str(item.mw) if item.mw not in (None, "") else None,
            mw_delta=str(r["mw_delta"]) if r.get("mw_delta") is not None else None,
            method=r.get("method", "exact"), confidence=str(r.get("confidence", 0)),
            status=status, candidates=dumps(r.get("candidates") or []),
            note=r.get("note")))

    write_audit_log(db, current_user, "tcmsp_resolve_ingredients",
                    target_type="tcmsp_ingredient_pubchem",
                    detail=dumps({"processed": len(items), **tally,
                                  "mw_mismatch": mw_mismatch}))
    db.commit()
    return {"processed": len(items), **tally, "mw_mismatch": mw_mismatch,
            "remaining": max(0, remaining_before - len(items))}


def _adme_thresholds(db: Session):
    from app import pathways as pw
    return pw.adme_thresholds(db)


def _is_active(ob, dl, ob_min: float, dl_min: float) -> bool:
    """跟 `app/pathways.py` 的活性成分判定用同一套規則：
    ADME 缺值（空字串或 'NA'）一律排除，不當成通過。"""
    a, b = pc._num(ob), pc._num(dl)
    return a is not None and b is not None and a >= ob_min and b >= dl_min


@router.get("/review", summary="（後台）待人工確認／查無結果的清單")
def review_queue(status: str = Query("pending", pattern="^(pending|unresolved|error|rejected)$"),
                 mw_mismatch_only: bool = False,
                 limit: int = Query(50, ge=1, le=200),
                 current_user: models.User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    q = (db.query(models.TcmspIngredientPubchem, models.TcmspIngredient.molecule_name)
         .join(models.TcmspIngredient,
               models.TcmspIngredient.mol_id == models.TcmspIngredientPubchem.mol_id)
         .filter(models.TcmspIngredientPubchem.status == status))
    if mw_mismatch_only:
        # 分子量不符的優先看：那些是「名稱對上但化合物可能是錯的」，
        # 比單純查無結果危險得多
        q = q.filter(models.TcmspIngredientPubchem.mw_delta.isnot(None))
    rows = q.order_by(models.TcmspIngredientPubchem.mol_id).limit(limit).all()
    return {"status": status, "total": len(rows),
            "items": [_row_out(r, name) for r, name in rows]}


class ConfirmIn(BaseModel):
    mol_id: str
    cid: str = Field(min_length=1, max_length=20)
    note: Optional[str] = Field(default=None, max_length=300)


@router.post("/confirm", summary="（後台）確認一筆映射")
def confirm_mapping(payload: ConfirmIn,
                    current_user: models.User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    row = (db.query(models.TcmspIngredientPubchem)
           .filter(models.TcmspIngredientPubchem.mol_id == payload.mol_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="這個成分還沒有解析紀錄，請先執行批次解析。")

    picked = next((c for c in loads(row.candidates, [])
                   if str(c.get("cid")) == str(payload.cid)), None)
    if picked:
        for field in ("canonical_smiles", "isomeric_smiles", "inchikey",
                      "molecular_formula", "molecular_weight", "iupac_name"):
            setattr(row, field, picked.get(field))
        row.cid = str(picked.get("cid"))
        row.method = row.method if row.method == "exact" else "manual"
    else:
        row.cid = payload.cid
        row.method = "manual"

    row.confidence = "1.0"
    row.status = "confirmed"
    row.note = payload.note or row.note
    row.reviewed_by = current_user.id
    row.reviewed_at = datetime.utcnow()

    write_audit_log(db, current_user, "tcmsp_confirm_ingredient_mapping",
                    target_type="tcmsp_ingredient_pubchem", target_id=payload.mol_id,
                    detail=dumps({"cid": row.cid, "inchikey": row.inchikey}))
    db.commit()
    return {"ok": True, **_row_out(row)}


class RejectIn(BaseModel):
    mol_id: str
    note: Optional[str] = Field(default=None, max_length=300)


@router.post("/reject", summary="（後台）否決一筆映射")
def reject_mapping(payload: RejectIn,
                   current_user: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    row = (db.query(models.TcmspIngredientPubchem)
           .filter(models.TcmspIngredientPubchem.mol_id == payload.mol_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="這個成分還沒有解析紀錄。")
    row.status = "rejected"
    row.note = payload.note or row.note
    row.reviewed_by = current_user.id
    row.reviewed_at = datetime.utcnow()
    write_audit_log(db, current_user, "tcmsp_reject_ingredient_mapping",
                    target_type="tcmsp_ingredient_pubchem", target_id=payload.mol_id,
                    detail=dumps({"note": payload.note}))
    db.commit()
    return {"ok": True, "mol_id": payload.mol_id, "status": "rejected"}


@router.get("/lookup", summary="（前台/後台）以 InChIKey／CAS／CID 反查 TCMSP 成分")
def lookup(key: str = Query(min_length=2, max_length=60),
           current_user: models.User = Depends(get_current_user),
           db: Session = Depends(get_query_db)):
    """跨資料庫比對的入口——這正是標準化的目的。

    有了 InChIKey，別的資料庫（DepMap 藥物、臨床試驗用藥、文獻）
    提到的化合物才對得回 TCMSP 的成分。用名稱是永遠對不起來的。
    """
    k = (key or "").strip()
    q = (db.query(models.TcmspIngredientPubchem, models.TcmspIngredient.molecule_name)
         .join(models.TcmspIngredient,
               models.TcmspIngredient.mol_id == models.TcmspIngredientPubchem.mol_id)
         .filter(models.TcmspIngredientPubchem.status.in_(ACCEPTED))
         .filter((models.TcmspIngredientPubchem.inchikey == k.upper()) |
                 (models.TcmspIngredientPubchem.cas_number == k) |
                 (models.TcmspIngredientPubchem.cid == k)))
    rows = q.all()
    return {"key": k, "total": len(rows), "items": [{
        "mol_id": r.mol_id, "molecule_name": name, "cid": r.cid,
        "inchikey": r.inchikey, "cas_number": r.cas_number,
        "canonical_smiles": r.canonical_smiles,
        "image_url": pc.image_url(r.cid),
    } for r, name in rows]}

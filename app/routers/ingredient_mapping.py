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


def _live_mw_hint(row: models.TcmspIngredientPubchem, name: str | None) -> str | None:
    """以**現在**的判讀規則重算分子量提示。回傳 None 代表沒有話要說。

    ## 為什麼不是直接修好 note

    `note` 是**解析當下**寫進資料庫的，不會回頭更新。v1.40.2 把 `mw_check()`
    的提示修對之後，只有之後新解析的筆數受惠——佇列裡既有的 81 筆糖基差
    仍然顯示舊的說法（而且舊說法把苷元誤配講成水合物，等於在鼓勵按確認）。
    **審核佇列正是誤按確認會發生的地方**，所以這裡即時重算。

    ## 為什麼不覆寫 note 欄位

    `confirm`／`reject` 會把審核者填的意見寫進同一個欄位
    （`row.note = payload.note or row.note`）。覆寫它等於把人工審核意見洗掉——
    修好一個誤導，換來一筆資料遺失。

    所以兩個欄位並存，語意也不同：
      note     當時記了什麼，或人工寫了什麼（歷史）
      mw_hint  以現在的知識重看這筆是什麼（判讀）

    並存其實比取代更有用：審核者會看到「當初寫水合物、現在判定是苷元誤配」。

    判斷邏輯一律呼叫 `pc.mw_check()`，**不在這裡重寫一份**——
    理由同 v1.40.1 的 `_ingredient_pool()`：同一個判定寫兩份就會分岔。
    """
    if not (row.tcmsp_mw and row.molecular_weight):
        return None
    check = pc.mw_check(row.tcmsp_mw, row.molecular_weight, name=name)
    return check["reason"] if check["agree"] is False else None


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
        # 即時重算，與 note 並存。見 _live_mw_hint() 的說明。
        "mw_hint": _live_mw_hint(row, name),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


def _adme_thresholds(db: Session):
    from app import pathways as pw
    return pw.adme_thresholds(db)


def _active_reason(ob, dl, ob_min: float, dl_min: float):
    """回傳 None 代表通過活性篩選；否則回傳被排除的原因代碼。

    跟 `app/pathways.py` 的活性成分判定用同一套規則：ADME 缺值（空字串或 'NA'）
    一律排除，不當成通過。但**缺值與不達標要分得開**——缺值是資料問題、
    不達標是化合物本身的性質，混在一起看不出「這個庫有多少成分根本沒有 ADME 資料」。
    """
    a, b = pc._num(ob), pc._num(dl)
    if a is None or b is None:
        return "adme_missing"
    if a < ob_min or b < dl_min:
        return "below_threshold"
    return None


def _ingredient_pool(db: Session, active_only: bool):
    """成分標準化的**母體**：`/stats` 與 `/resolve` 一律呼叫這一支。

    ## 為什麼要有這個函式（v1.40.1 修的實際事故）

    在此之前 `/stats` 自己數全表 13,728 筆、`/resolve` 另外套兩層篩選（名稱非空
    ＋ OB／DL），兩支查詢的母體不同。結果是覆蓋率卡片顯示「尚未處理 11,096」，
    而批次連按十三次都回「這一批沒有需要處理的成分了」——**程式跑得動、數字都在
    合理範圍、畫面很合理，但兩個數字回答的是不同的問題**。

    這跟 v1.38.0 把八處靶點比對邏輯收斂到 `app/target_index.py` 是同一個原則：
    要改篩選條件就改這一處，不要在任何一邊就地重寫。

    回傳 `(pool, excluded)`：
      pool     —— 這個母體裡的成分列（含 mol_id / molecule_name / mw / ob / dl）
      excluded —— 被排除的筆數，依原因分開，讓畫面可以說清楚「未納入」是哪來的
    """
    rows = (db.query(models.TcmspIngredient.mol_id, models.TcmspIngredient.molecule_name,
                     models.TcmspIngredient.mw, models.TcmspIngredient.ob,
                     models.TcmspIngredient.dl)
            .order_by(models.TcmspIngredient.mol_id).all())

    excluded = {"no_name": 0, "adme_missing": 0, "below_threshold": 0}

    # 名稱是唯一的查詢鍵，空白名稱在任何模式下都解析不了——
    # 舊版 `/resolve` 只擋 NULL，空字串會被送去查 PubChem，查了也一定查不到。
    named = []
    for r in rows:
        if not (r.molecule_name or "").strip():
            excluded["no_name"] += 1
        else:
            named.append(r)

    if not active_only:
        return named, excluded

    ob_min, dl_min = _adme_thresholds(db)
    pool = []
    for r in named:
        reason = _active_reason(r.ob, r.dl, ob_min, dl_min)
        if reason is None:
            pool.append(r)
        else:
            excluded[reason] += 1
    return pool, excluded


_STATUSES = ("auto", "confirmed", "pending", "rejected", "unresolved", "error")


def _aggregate(maps, ids):
    """把映射列彙總成**不重複成分數**。`ids` 為 None 代表不限母體。

    一律用 distinct mol_id，不用筆數：`TcmspIngredientPubchem` 的唯一鍵是
    `(mol_id, cid)`，同一個成分合法可以有多筆（人工確認時挑了不同 CID 就會出現）。
    舊版 `with_smiles`／`with_cas`／`by_status` 數的是筆數，而 `total`／`remaining`
    數的是成分數——同一張卡片混兩種單位，多筆映射一出現加總就對不起來。
    """
    by_status = {k: set() for k in _STATUSES}
    touched, accepted, smiles, cas, mw = set(), set(), set(), set(), set()
    for mol_id, status, smi, cas_no, delta in maps:
        if ids is not None and mol_id not in ids:
            continue
        touched.add(mol_id)
        by_status.setdefault(status, set()).add(mol_id)
        if status in ACCEPTED:
            accepted.add(mol_id)
            if smi:
                smiles.add(mol_id)
            if cas_no:
                cas.add(mol_id)
        if status == "pending" and delta is not None:
            mw.add(mol_id)
    return {
        "touched": len(touched), "resolved": len(accepted),
        "with_smiles": len(smiles), "with_cas": len(cas),
        "mw_mismatch_pending": len(mw),
        "by_status": {k: len(by_status.get(k, ())) for k in _STATUSES},
    }


@router.get("/stats", summary="（後台）成分標準化覆蓋率")
def mapping_stats(active_only: bool = Query(
                      True,
                      description="母體只算活性成分（與批次解析的預設一致）。"
                                  "關掉之後母體變成「所有有名稱的成分」。"),
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """覆蓋率。**母體與批次佇列必定一致**（兩邊都走 `_ingredient_pool`）。

    `remaining` 的定義是「在佇列裡、還沒跑到的」，所以它會歸零；
    被篩掉、預設就不會被排進佇列的算 `excluded`，那不是進度。
    """
    total_all = db.query(models.TcmspIngredient).count()
    ob_min, dl_min = _adme_thresholds(db)
    pool, excluded = _ingredient_pool(db, active_only)
    pool_ids = {r.mol_id for r in pool}
    pool_total = len(pool_ids)

    maps = db.query(models.TcmspIngredientPubchem.mol_id,
                    models.TcmspIngredientPubchem.status,
                    models.TcmspIngredientPubchem.canonical_smiles,
                    models.TcmspIngredientPubchem.cas_number,
                    models.TcmspIngredientPubchem.mw_delta).all()

    sel = _aggregate(maps, pool_ids)
    whole = _aggregate(maps, None)

    return {
        "active_only": active_only,
        "ob_min": ob_min, "dl_min": dl_min,
        # 母體（畫面主要指標與進度條吃這一組）
        "pool_total": pool_total,
        "resolved": sel["resolved"],
        "remaining": max(0, pool_total - sel["touched"]),
        "coverage": round(sel["resolved"] / pool_total, 4) if pool_total else 0,
        "with_smiles": sel["with_smiles"],
        "with_cas": sel["with_cas"],
        "mw_mismatch_pending": sel["mw_mismatch_pending"],
        "by_status": sel["by_status"],
        # 未納入：不是進度，是「照設定就不會被排進佇列」的
        "excluded_total": max(0, total_all - pool_total),
        "excluded_breakdown": excluded,
        # 全庫視角，供對照
        "total_ingredients": total_all,
        "overall": {
            "total": total_all,
            "resolved": whole["resolved"],
            "touched": whole["touched"],
            "coverage": round(whole["resolved"] / total_all, 4) if total_all else 0,
        },
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
    done_q = db.query(models.TcmspIngredientPubchem.mol_id)
    if payload.retry_errors:
        done_q = done_q.filter(models.TcmspIngredientPubchem.status != "error")
    done = {m for (m,) in done_q.all()}

    # 母體與覆蓋率卡片共用同一支（見 `_ingredient_pool` 的說明）。
    # ob／dl 是 String 欄位（可攜型別規範，見 rules.md），資料庫端無法可靠地做數值
    # 比較——SQLite 與 Postgres 的字串轉數字語法不同，遇到 'NA' 會炸，所以在 Python 端篩。
    pool, _excluded = _ingredient_pool(db, payload.active_only)
    rows = [r for r in pool if r.mol_id not in done]

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
    # 帶上成分名稱，否則 mw_hint 認不出 `_qt` 苷元，判讀會退化成一般提示
    name = (db.query(models.TcmspIngredient.molecule_name)
            .filter(models.TcmspIngredient.mol_id == row.mol_id).scalar())
    return {"ok": True, **_row_out(row, name)}


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

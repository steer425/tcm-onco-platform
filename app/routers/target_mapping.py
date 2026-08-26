"""靶點標準化（TCMSP → UniProt）後台 API。功能代碼 F1-4。

設計取向跟新聞模組的「摘要回補」一致：**批次、可重複執行、回傳還剩幾筆**。
1751 個靶點一次跑完會讓請求逾時，而且對方是別人免費提供的公共服務。
管理者按幾次就補幾批，進度隨時看得見。

⚠️ 解析需要對外連到 rest.uniprot.org。實際執行必須在 Render 上（對外連線是通的），
Cowork 的沙箱與本機 VM 都連不到（代理回 403）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, tcmsp_uniprot
from app.database import get_db, get_query_db
from app.deps import get_current_user, require_admin, write_audit_log
from app.news.service import dumps, loads

router = APIRouter(prefix="/tcmsp/target-mapping", tags=["目標一/二：靶點標準化（UniProt）"])

FEATURE = "F1-4"


def _row_out(row: models.TcmspTargetUniprot, target_name: str | None = None) -> dict:
    return {
        "id": row.id, "tar_id": row.tar_id, "target_name": target_name,
        "accession": row.accession, "gene_symbol": row.gene_symbol,
        "gene_synonyms": loads(row.gene_synonyms, []),
        "protein_name": row.protein_name, "organism_id": row.organism_id,
        "kegg_id": row.kegg_id, "reactome_ids": loads(row.reactome_ids, []),
        "method": row.method, "confidence": float(row.confidence or 0),
        "status": row.status, "candidates": loads(row.candidates, []),
        "note": row.note,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.get("/stats", summary="（後台）靶點標準化覆蓋率")
def mapping_stats(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    total = db.query(models.TcmspTarget).count()
    rows = db.query(models.TcmspTargetUniprot.status,
                    func.count(models.TcmspTargetUniprot.id)).group_by(
                        models.TcmspTargetUniprot.status).all()
    by_status = {s: c for s, c in rows}
    done = db.query(func.count(func.distinct(models.TcmspTargetUniprot.tar_id))).filter(
        models.TcmspTargetUniprot.status.in_(("auto", "confirmed"))).scalar() or 0
    touched = db.query(func.count(func.distinct(
        models.TcmspTargetUniprot.tar_id))).scalar() or 0
    with_symbol = db.query(func.count(func.distinct(
        models.TcmspTargetUniprot.gene_symbol))).filter(
            models.TcmspTargetUniprot.gene_symbol.isnot(None),
            models.TcmspTargetUniprot.status.in_(("auto", "confirmed"))).scalar() or 0
    with_kegg = db.query(models.TcmspTargetUniprot).filter(
        models.TcmspTargetUniprot.kegg_id.isnot(None)).count()
    return {
        "total_targets": total,
        "resolved": done,
        "remaining": max(0, total - touched),
        "coverage": round(done / total, 4) if total else 0,
        "distinct_gene_symbols": with_symbol,
        "with_kegg_xref": with_kegg,
        "by_status": {k: by_status.get(k, 0) for k in
                      ("auto", "confirmed", "pending", "rejected", "unresolved", "error")},
    }


class ResolveIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=200,
                       description="這一批最多處理幾個靶點")
    retry_errors: bool = Field(default=False,
                               description="連上次連線失敗的也一起重跑")


@router.post("/resolve", summary="（後台）批次解析尚未處理的靶點")
def resolve_batch(payload: ResolveIn,
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """只處理「還沒有映射紀錄」的靶點，可重複按到 remaining 歸零。

    已經人工確認（confirmed）或否決（rejected）的一律不動——
    重跑時把人的判斷洗掉，是這種批次工具最容易犯也最傷的錯。
    """
    done_ids = db.query(models.TcmspTargetUniprot.tar_id)
    if payload.retry_errors:
        done_ids = done_ids.filter(models.TcmspTargetUniprot.status != "error")

    todo_q = (db.query(models.TcmspTarget)
              .filter(~models.TcmspTarget.tar_id.in_(done_ids),
                      models.TcmspTarget.target_name.isnot(None))
              .order_by(models.TcmspTarget.tar_id))
    remaining_before = todo_q.count()
    targets = todo_q.limit(payload.limit).all()
    if not targets:
        return {"processed": 0, "auto": 0, "pending": 0, "unresolved": 0, "error": 0,
                "remaining": 0}

    if payload.retry_errors:
        stale = (db.query(models.TcmspTargetUniprot)
                 .filter(models.TcmspTargetUniprot.status == "error",
                         models.TcmspTargetUniprot.tar_id.in_(
                             [t.tar_id for t in targets])).all())
        for row in stale:
            db.delete(row)
        db.flush()

    results = tcmsp_uniprot.resolve_many([t.target_name for t in targets])

    tally = {"auto": 0, "pending": 0, "unresolved": 0, "error": 0}
    for t in targets:
        r = results.get(t.target_name) or {}
        status = r.get("status", "error")
        tally[status] = tally.get(status, 0) + 1
        db.add(models.TcmspTargetUniprot(
            tar_id=t.tar_id,
            accession=r.get("accession"), gene_symbol=r.get("gene_symbol"),
            gene_synonyms=dumps(r.get("gene_synonyms") or []),
            protein_name=r.get("protein_name"), organism_id=r.get("organism_id"),
            kegg_id=r.get("kegg_id"), reactome_ids=dumps(r.get("reactome_ids") or []),
            method=r.get("method", "exact"), confidence=str(r.get("confidence", 0)),
            status=status, candidates=dumps(r.get("candidates") or []),
            note=r.get("note"),
        ))

    write_audit_log(db, current_user, "tcmsp_resolve_targets",
                    target_type="tcmsp_target_uniprot",
                    detail=dumps({"processed": len(targets), **tally}))
    db.commit()
    return {"processed": len(targets), **tally,
            "remaining": max(0, remaining_before - len(targets))}


@router.get("/review", summary="（後台）待人工確認／查無結果的清單")
def review_queue(status: str = Query("pending", pattern="^(pending|unresolved|error|rejected)$"),
                 limit: int = Query(50, ge=1, le=200),
                 current_user: models.User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    rows = (db.query(models.TcmspTargetUniprot, models.TcmspTarget.target_name)
            .join(models.TcmspTarget,
                  models.TcmspTarget.tar_id == models.TcmspTargetUniprot.tar_id)
            .filter(models.TcmspTargetUniprot.status == status)
            .order_by(models.TcmspTargetUniprot.tar_id)
            .limit(limit).all())
    return {"status": status, "total": len(rows),
            "items": [_row_out(r, name) for r, name in rows]}


class ConfirmIn(BaseModel):
    tar_id: str
    # 從候選裡挑一個（accession），或直接人工輸入
    accession: str = Field(min_length=4, max_length=20)
    gene_symbol: Optional[str] = Field(default=None, max_length=40)
    note: Optional[str] = Field(default=None, max_length=300)


@router.post("/confirm", summary="（後台）確認一筆映射（從候選挑選或人工指定）")
def confirm_mapping(payload: ConfirmIn,
                    current_user: models.User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    row = (db.query(models.TcmspTargetUniprot)
           .filter(models.TcmspTargetUniprot.tar_id == payload.tar_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="這個靶點還沒有解析紀錄，請先執行批次解析。")

    picked = next((c for c in loads(row.candidates, [])
                   if c.get("accession") == payload.accession), None)
    if picked:
        row.accession = picked.get("accession")
        row.gene_symbol = picked.get("gene_symbol")
        row.gene_synonyms = dumps(picked.get("gene_synonyms") or [])
        row.protein_name = picked.get("protein_name")
        row.organism_id = picked.get("organism_id")
        row.kegg_id = picked.get("kegg_id")
        row.reactome_ids = dumps(picked.get("reactome_ids") or [])
        row.method = row.method if row.method != "fulltext" else "manual"
    else:
        # 候選裡沒有 → 管理者自己輸入的，一律標成 manual
        row.accession = payload.accession
        row.gene_symbol = payload.gene_symbol or row.gene_symbol
        row.method = "manual"

    row.confidence = "1.0"
    row.status = "confirmed"
    row.note = payload.note or row.note
    row.reviewed_by = current_user.id
    row.reviewed_at = datetime.utcnow()

    write_audit_log(db, current_user, "tcmsp_confirm_target_mapping",
                    target_type="tcmsp_target_uniprot", target_id=payload.tar_id,
                    detail=dumps({"accession": row.accession, "gene": row.gene_symbol}))
    db.commit()
    return {"ok": True, **_row_out(row)}


class RejectIn(BaseModel):
    tar_id: str
    note: Optional[str] = Field(default=None, max_length=300)


@router.post("/reject", summary="（後台）否決一筆映射（這個靶點沒有合適的 UniProt 對應）")
def reject_mapping(payload: RejectIn,
                   current_user: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """否決之後不會再被批次解析重跑。

    有些 TCMSP 靶點本來就不是人類蛋白（或根本是資料錯誤），
    留一個明確的「看過了，沒有對應」比讓它一直躺在待確認清單裡有用得多。
    """
    row = (db.query(models.TcmspTargetUniprot)
           .filter(models.TcmspTargetUniprot.tar_id == payload.tar_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="這個靶點還沒有解析紀錄。")
    row.status = "rejected"
    row.note = payload.note or row.note
    row.reviewed_by = current_user.id
    row.reviewed_at = datetime.utcnow()
    write_audit_log(db, current_user, "tcmsp_reject_target_mapping",
                    target_type="tcmsp_target_uniprot", target_id=payload.tar_id,
                    detail=dumps({"note": payload.note}))
    db.commit()
    return {"ok": True, "tar_id": payload.tar_id, "status": "rejected"}


@router.get("/lookup", summary="（前台/後台）以基因符號反查 TCMSP 靶點")
def lookup_by_symbol(symbol: str = Query(min_length=1, max_length=40),
                     current_user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_query_db)):
    """給暗黑基因、GenCC、新聞實體連結共用的反查入口。

    同時比對主要符號與同義詞——UniProt 的同義詞欄位正是為了處理
    「同一個蛋白在不同資料庫叫不同名字」這件事，不用就浪費了。
    """
    sym = (symbol or "").strip().upper()
    rows = (db.query(models.TcmspTargetUniprot, models.TcmspTarget.target_name)
            .join(models.TcmspTarget,
                  models.TcmspTarget.tar_id == models.TcmspTargetUniprot.tar_id)
            .filter(models.TcmspTargetUniprot.status.in_(("auto", "confirmed"))).all())
    hits = []
    for row, name in rows:
        symbols = {(row.gene_symbol or "").upper()}
        symbols |= {s.upper() for s in loads(row.gene_synonyms, [])}
        symbols.discard("")
        if sym in symbols:
            hits.append({"tar_id": row.tar_id, "target_name": name,
                         "accession": row.accession, "gene_symbol": row.gene_symbol,
                         "matched_as": "primary" if sym == (row.gene_symbol or "").upper()
                                       else "synonym"})
    return {"symbol": sym, "total": len(hits), "items": hits}

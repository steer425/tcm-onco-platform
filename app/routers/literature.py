"""F1-9 文獻證據分級（目標一 Step 5）的 API。

分級規則一律在 `app/literature_evidence.py`；要查的靶點清單一律來自
`app/depmap_analysis.select_herb_targets()`（與 F1-8 同一份），**不在這裡重寫**。

三個端點：
  GET  /literature/herbs/{herb_id}                     藥材 → Step 6 通過門檻的靶點＋各自的文獻摘要
  GET  /literature/herbs/{herb_id}/genes/{symbol}      單一組合的查詢式與逐篇分級
  POST /literature/herbs/{herb_id}/collect             向 PubMed 查詢（需 F1-9 can_execute）

讀取走 `get_query_db`（唯讀模式可用快取）；查詢會寫資料，走 `get_db`，唯讀模式下照常被擋。
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import depmap_analysis as dm
from app import literature_evidence as le
from app import models
from app.database import get_db, get_query_db
from app.deps import get_current_user, has_permission, require_permission, write_audit_log

router = APIRouter(prefix="/literature", tags=["目標一 Step 5：文獻證據分級（PubMed）"])

DISCLAIMER = ("PubMed 命中只代表藥材／成分、靶點與癌症三組詞共同出現（文獻共現），"
              "不等於該成分作用於該靶點。研究設計層級依出版類型與摘要字詞判定，未讀全文、未判斷結論正負。"
              "網絡藥理學論文的靶點多取自 TCMSP，與本平台同源，不計入獨立證據。"
              "本平台為科研輔助工具，不作為醫療診斷或治療建議。")


def _herb_or_404(db: Session, herb_id: int):
    herb = (db.query(models.TcmspHerb)
            .filter(models.TcmspHerb.id == herb_id, models.TcmspHerb.status == "active").first())
    if not herb:
        raise HTTPException(status_code=404, detail="找不到這個藥材，或它已被下架。")
    return herb


def _selection(db: Session, herb_id: int, max_ratio: float):
    rel, _run = dm.resolve_release(db, None)
    if not rel:
        raise HTTPException(status_code=404,
                            detail="尚未匯入 DepMap 資料，請先執行 python -m app.import_depmap。"
                                   "文獻查詢的靶點清單來自 Step 6 的選擇性門檻。")
    return rel, le.herb_selection(db, herb_id, rel, max_ratio)


def _search_out(s) -> dict | None:
    if s is None:
        return None
    return {"search_id": s.id, "status": s.status, "error": s.error,
            "total_count": s.total_count, "n_fetched": s.n_fetched,
            "searched_at": s.searched_at.isoformat() if s.searched_at else None,
            "stale_grading": s.grading_version != le.GRADING_VERSION}


@router.get("/herbs/{herb_id}", summary="（前台）藥材 → 通過選擇性門檻的靶點與各自的文獻摘要")
def herb_literature(herb_id: int,
                    max_ratio: float = Query(dm.DEFAULT_MAX_RATIO, gt=0, le=1),
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_query_db),
                    perm_db: Session = Depends(get_db)):
    herb = _herb_or_404(db, herb_id)
    rel, sel = _selection(db, herb_id, max_ratio)

    searches = {s.gene_symbol: s for s in db.query(models.LiteratureSearch)
                .filter(models.LiteratureSearch.herb_id == herb_id).all()}
    ids = [s.id for s in searches.values()]
    by_search: dict = {}
    if ids:
        for r in (db.query(models.LiteratureEvidence)
                  .filter(models.LiteratureEvidence.search_id.in_(ids)).all()):
            by_search.setdefault(r.search_id, []).append(r)

    rows = []
    for s in sel["gated"]:
        srch = searches.get(s.gene_symbol)
        rows.append({
            "gene_symbol": s.gene_symbol,
            "protein_name": le.protein_name_for_symbol(db, sel, s.gene_symbol),
            "min_effect": dm.num(s.min_effect),
            "n_dependent": s.n_dependent, "n_lines_total": s.n_lines_total,
            "receptor_warning": dm.is_receptor(s.gene_symbol),
            "ingredients": le.ingredients_for_symbol(db, sel, s.gene_symbol),
            "search": _search_out(srch),
            "summary": le.summarize(by_search.get(srch.id, [])) if srch else None,
        })

    queue = le.collect_queue(db, herb_id, sel)
    return {
        "herb": {"herb_id": herb.id, "herb_cn_name": herb.herb_cn_name,
                 "herb_en_name": herb.herb_en_name, "herb_pinyin": herb.herb_pinyin},
        "release": rel,
        "params": {"max_ratio": max_ratio, "retmax": le.RETMAX,
                   "grading_version": le.GRADING_VERSION},
        "counts": {"genes": len(rows), "searched": len(rows) - len(queue), "remaining": len(queue)},
        "levels": [{"code": k, "rank": v[0], "label": v[1]} for k, v in le.LEVELS.items()],
        "genes": rows,
        # 前端依這個決定要不要顯示「開始查詢」。用的是跟 POST /collect 同一個判定
        # （has_permission ↔ require_permission，同一張權限矩陣），畫面與後端不會各說各話。
        # 權限表不在唯讀快取裡，所以另外走 get_db。
        "can_collect": _can_collect(perm_db, current_user),
        "disclaimer": DISCLAIMER,
    }


def _can_collect(db: Session, user) -> bool:
    try:
        return has_permission(db, user, "F1-9", need_execute=True)
    except Exception:  # noqa: BLE001 — 查不到權限就當沒有，按鈕不顯示；後端照樣會擋
        return False


@router.get("/herbs/{herb_id}/genes/{symbol}", summary="（前台）單一（藥材, 靶點）組合的查詢式與逐篇分級")
def gene_articles(herb_id: int, symbol: str,
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_query_db)):
    _herb_or_404(db, herb_id)
    s = (db.query(models.LiteratureSearch)
         .filter(models.LiteratureSearch.herb_id == herb_id,
                 models.LiteratureSearch.gene_symbol == symbol).first())
    if not s:
        raise HTTPException(status_code=404, detail="這個組合還沒有向 PubMed 查詢過。")
    rows = (db.query(models.LiteratureEvidence)
            .filter(models.LiteratureEvidence.search_id == s.id).all())
    rows.sort(key=lambda r: (r.level_rank, {"sentence": 0, "abstract": 1}.get(r.comention, 2),
                             -(r.pub_year or 0), r.pmid))
    return {
        "gene_symbol": symbol,
        "query_term": s.query_term,
        "pubmed_search_url": ("https://pubmed.ncbi.nlm.nih.gov/?term=" + quote(s.query_term))
        if s.query_term else None,
        "search": _search_out(s),
        "summary": le.summarize(rows),
        "articles": [le.article_out(r) for r in rows],
        "disclaimer": DISCLAIMER,
    }


class CollectBody(BaseModel):
    limit: int = Field(3, ge=1, le=10, description="這次最多查幾個靶點（每個約 1 秒）")
    genes: list[str] | None = Field(None, max_length=10, description="只查指定的基因符號（須在清單內）")
    refresh: bool = Field(False, description="已查過的也重查")
    max_ratio: float = Field(dm.DEFAULT_MAX_RATIO, gt=0, le=1)


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True,
                        headers={"User-Agent": f"{le.TOOL}/1.0"})


@router.post("/herbs/{herb_id}/collect", summary="（需執行權限）向 PubMed 查詢並分級，一次最多 10 個靶點")
def collect(herb_id: int, body: CollectBody,
            current_user: models.User = Depends(require_permission("F1-9", need_execute=True)),
            db: Session = Depends(get_db)):
    herb = _herb_or_404(db, herb_id)
    _rel, sel = _selection(db, herb_id, body.max_ratio)
    queue = le.collect_queue(db, herb_id, sel, refresh=body.refresh, genes=body.genes)
    batch = queue[:body.limit]
    email = os.environ.get("NEWS_CONTACT_EMAIL")
    api_key = os.environ.get("PUBMED_API_KEY")

    results = []
    with _client() as client:
        for sym in batch:
            results.append(le.collect_one(db, client, herb, sel, sym, user_id=current_user.id,
                                          email=email, api_key=api_key))
    remaining = len(le.collect_queue(db, herb_id, sel, refresh=False))
    write_audit_log(db, current_user, "literature_collect", target_type="tcmsp_herb",
                    target_id=str(herb_id),
                    detail=json.dumps({"genes": batch, "refresh": body.refresh,
                                       "ok": sum(r["status"] == "ok" for r in results),
                                       "empty": sum(r["status"] == "empty" for r in results),
                                       "error": sum(r["status"] == "error" for r in results)},
                                      ensure_ascii=False))
    return {"processed": len(results), "results": results, "remaining": remaining}

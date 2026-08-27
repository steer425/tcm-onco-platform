"""通路富集分析 API（KEGG／Reactome，目標一 Step 4）。功能代碼 F1-5。

兩類端點分得很開：
  - `/sync`（後台，僅管理者）：跟外部資料庫要通路目錄，重建靶點↔通路關聯。
    要連 `rest.kegg.jp` 與 `reactome.org`，必須在 Render 上跑。
  - 其餘查詢端點：純讀本地資料，走 `get_query_db`，唯讀模式下照樣可用。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, pathways as pw
from app.database import get_db, get_query_db
from app.deps import get_current_user, require_admin, write_audit_log
from app.news.service import dumps

router = APIRouter(prefix="/pathways", tags=["目標一 Step 4：通路富集（KEGG／Reactome）"])

FEATURE = "F1-5"
SOURCES = ("kegg", "reactome")


@router.get("/stats", summary="（後台/前台）通路資料覆蓋率")
def pathway_stats(current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_query_db)):
    out = {}
    for source in SOURCES:
        total = db.query(models.Pathway).filter(models.Pathway.source == source).count()
        cancer = (db.query(models.Pathway)
                  .filter(models.Pathway.source == source,
                          models.Pathway.is_cancer_related.is_(True)).count())
        links = (db.query(models.TargetPathway)
                 .filter(models.TargetPathway.source == source).count())
        targets = (db.query(func.count(func.distinct(models.TargetPathway.tar_id)))
                   .filter(models.TargetPathway.source == source).scalar() or 0)
        last = (db.query(func.max(models.Pathway.synced_at))
                .filter(models.Pathway.source == source).scalar())
        out[source] = {
            "pathways": total, "cancer_related": cancer,
            "links": links, "targets_with_pathway": targets,
            "background_total": pw.get_background_total(db, source),
            "synced_at": last.isoformat() if last else None,
        }

    standardised = (db.query(func.count(func.distinct(models.TcmspTargetUniprot.tar_id)))
                    .filter(models.TcmspTargetUniprot.status.in_(("auto", "confirmed")))
                    .scalar() or 0)
    ob_min, dl_min = pw.adme_thresholds(db)
    return {"by_source": out, "standardised_targets": standardised,
            "total_targets": db.query(models.TcmspTarget).count(),
            "adme": {"ob_min": ob_min, "dl_min": dl_min}}


class SyncIn(BaseModel):
    source: str = Field(default="kegg", pattern="^(kegg|reactome)$")


@router.post("/sync", summary="（後台）同步通路目錄並重建靶點↔通路關聯")
def sync_source(payload: SyncIn,
                current_user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    """一次同步一個來源。

    分開跑是刻意的：Reactome 那個檔案有數十 MB，抓失敗或逾時不該把
    已經成功的 KEGG 一起拖下水。兩邊互不相干，各自可重跑。
    """
    source = payload.source
    try:
        data = pw.fetch_kegg() if source == "kegg" else pw.fetch_reactome()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"連不到 {source} 的資料來源：{str(exc)[:200]}。"
                   f"這個端點需要對外網路，請在已部署的 Render 環境執行。")

    result = pw.sync_pathways(db, source, data)
    write_audit_log(db, current_user, "pathway_sync",
                    target_type="pathways", target_id=source, detail=dumps(result))
    db.commit()
    return result


@router.get("/list", summary="（前台）通路清單（可篩癌症相關／關鍵字）")
def list_pathways(source: str = Query("kegg", pattern="^(kegg|reactome)$"),
                  cancer_only: bool = False, keyword: Optional[str] = None,
                  limit: int = Query(100, ge=1, le=500),
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_query_db)):
    q = db.query(models.Pathway).filter(models.Pathway.source == source)
    if cancer_only:
        q = q.filter(models.Pathway.is_cancer_related.is_(True))
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(models.Pathway.name.ilike(like))
    rows = q.order_by(models.Pathway.pathway_id).limit(limit).all()
    return {"total": len(rows), "items": [{
        "pathway_id": r.pathway_id, "name": r.name, "name_tw": r.name_tw,
        "category": r.category, "is_cancer_related": bool(r.is_cancer_related),
        "gene_count": r.background_gene_count,
    } for r in rows]}


@router.get("/herb/{herb_id}", summary="（前台）藥材的通路富集分析")
def herb_enrichment(herb_id: int,
                    source: str = Query("kegg", pattern="^(kegg|reactome)$"),
                    background: str = Query("genome", pattern="^(genome|tcmsp)$"),
                    cancer_only: bool = False,
                    exclude_noncancer_disease: bool = True,
                    apply_adme: bool = True,
                    sort: str = Query("p", pattern="^(p|fold)$"),
                    limit: int = Query(50, ge=1, le=200),
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_query_db)):
    """藥材 → 成分 → 靶點 → 通路，做過度代表分析。

    三個預設值都是刻意的，關掉之前要知道自己在關什麼：

    `apply_adme=True`
        先用 OB ≥ 30%、DL ≥ 0.18 篩出活性成分——這是 TCMSP 原始論文的建議值，
        也是 `docs/2026_goals.md` 目標一 Step 1 白紙黑字寫的條件。
        不篩等於宣稱這個藥材裡每一個偵測得到的化合物都在體內作用。

    `exclude_noncancer_disease=True`
        排除 KEGG 裡非癌症的疾病類通路（結核病、動脈粥狀硬化…）。
        那些通路是通用發炎凋亡基因的大雜燴，任何靶點集合都會對它們「顯著」。

    `background`
        兩種母體的差別見 `app.pathways.enrich`。畫面上必須顯示用的是哪一種——
        同一個藥材換母體會得到不同排序，看到數字卻不知道母體是什麼就沒有意義。

    `sort`
        `p`（預設）依統計顯著性；`fold` 依富集倍率。
        p 值天生偏袒基因數多的大通路（k 大則檢定力高），
        依 p 值排會把高特異性的小通路往後推——人參的 Apoptosis 是 19.2 倍
        卻排第 20 就是這樣來的。兩種排序都看一次比較不會漏掉東西。
    """
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id).first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")

    tar_ids, ingredient_meta = pw.targets_for_herb(db, herb_id, apply_adme=apply_adme)
    result = pw.enrich(db, tar_ids, source=source, background=background,
                       cancer_only=cancer_only,
                       exclude_noncancer_disease=exclude_noncancer_disease,
                       sort=sort, limit=limit)
    result["herb"] = {"id": herb.id, "herb_en_name": herb.herb_en_name,
                      "herb_cn_name": herb.herb_cn_name,
                      "target_count": len(tar_ids)}
    result["ingredients"] = ingredient_meta
    result["apply_adme"] = apply_adme
    return result


class TargetsIn(BaseModel):
    tar_ids: list[str] = Field(min_length=1, max_length=5000)
    source: str = Field(default="kegg", pattern="^(kegg|reactome)$")
    background: str = Field(default="genome", pattern="^(genome|tcmsp)$")
    cancer_only: bool = False
    exclude_noncancer_disease: bool = True
    sort: str = Field(default="p", pattern="^(p|fold)$")
    limit: int = Field(default=50, ge=1, le=200)


@router.post("/enrich", summary="（前台）對任意一組靶點做通路富集")
def enrich_targets(payload: TargetsIn,
                   current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_query_db)):
    """給複方（多味藥材）、暗黑基因反查等場景共用的通用入口。"""
    return pw.enrich(db, set(payload.tar_ids), source=payload.source,
                     background=payload.background,
                     cancer_only=payload.cancer_only,
                     exclude_noncancer_disease=payload.exclude_noncancer_disease,
                     sort=payload.sort, limit=payload.limit)


@router.get("/target/{tar_id}", summary="（前台）單一靶點參與的通路")
def target_pathways(tar_id: str,
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_query_db)):
    rows = (db.query(models.TargetPathway, models.Pathway)
            .join(models.Pathway, models.Pathway.id == models.TargetPathway.pathway_ref_id)
            .filter(models.TargetPathway.tar_id == tar_id)
            .order_by(models.Pathway.source, models.Pathway.pathway_id).all())
    return {"tar_id": tar_id, "total": len(rows), "items": [{
        "source": link.source, "pathway_id": p.pathway_id, "name": p.name,
        "name_tw": p.name_tw, "category": p.category,
        "is_cancer_related": bool(p.is_cancer_related),
        "via_symbol": link.via_symbol,
    } for link, p in rows]}

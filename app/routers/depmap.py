"""F1-8 腫瘤細胞株依賴查詢站（目標一 Step 6）的 API。

分析鏈路第五站「腫瘤細胞」的畫面端點。判定一律呼叫 `app/depmap_analysis.py`，
與報表腳本 `python -m app.inspect_depmap` 共用同一份規則，**不在這裡重寫**。

四個端點：
  GET /depmap/meta                       資料版本、門檻、母體、授權標註
  GET /depmap/herbs/{herb_id}/selective  藥材 → 選擇性依賴靶點（含被刷掉的與原因）
  GET /depmap/genes/{symbol}/lines       基因 → 依賴它的細胞株（由強到弱）
  GET /depmap/lines/{depmap_id}          細胞株 → 它依賴的、本藥材打得到的靶點

⚠️ 刻意**不提供** lineage 富集：人參的三個「顯著」lineage 經對照基因集檢定，
全部落在隨機對照範圍內。只給 q 值不給對照，是選擇性呈現。

全部是唯讀查詢，走 `get_query_db`；需要的資料表已加進 `local_cache.CACHED_TABLES`。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import depmap_analysis as dm
from app import models
from app.database import get_query_db
from app.deps import get_current_user

router = APIRouter(prefix="/depmap", tags=["目標一 Step 6：腫瘤細胞株依賴（DepMap）"])


def _release_or_404(db: Session, release: str | None):
    rel, run = dm.resolve_release(db, release)
    if not rel:
        raise HTTPException(status_code=404,
                            detail="尚未匯入 DepMap 資料，請先執行 python -m app.import_depmap。")
    return rel, run


def _line_out(m) -> dict | None:
    if m is None:
        return None
    return {"depmap_id": m.id, "cell_line_name": m.cell_line_name,
            "lineage": m.oncotree_lineage, "primary_disease": m.oncotree_primary_disease,
            "subtype": m.oncotree_subtype,
            "depmap_url": dm.DEPMAP_LINE_URL.format(id=m.id)}


def _summary_out(s, strong: dict, line=None) -> dict:
    r = dm.ratio(s)
    return {
        "gene_symbol": s.gene_symbol,
        "n_dependent": s.n_dependent, "n_lines_total": s.n_lines_total,
        "ratio": round(r, 4) if r != 9 else None,
        "n_strong": strong.get(s.gene_symbol, 0),
        "min_effect": dm.num(s.min_effect), "mean_effect": dm.num(s.mean_effect),
        "is_common_essential": bool(s.is_common_essential),
        "receptor_warning": dm.is_receptor(s.gene_symbol),
        "best_line": line,
        "depmap_url": dm.DEPMAP_GENE_URL.format(symbol=s.gene_symbol),
    }


@router.get("/meta", summary="（前台）DepMap 資料版本、門檻與授權標註")
def depmap_meta(current_user: models.User = Depends(get_current_user),
                db: Session = Depends(get_query_db)):
    rel, run = _release_or_404(db, None)
    n_lines = (db.query(models.DepMapGeneSummary.n_lines_total)
               .filter(models.DepMapGeneSummary.release == rel)
               .order_by(models.DepMapGeneSummary.n_lines_total.desc()).limit(1).scalar()) or 0
    return {
        "release": rel,
        "effect_threshold": dm.num(run.effect_threshold) if run else None,
        "strong_effect": dm.STRONG_EFFECT,
        "default_max_ratio": dm.DEFAULT_MAX_RATIO,
        "gene_scope": run.gene_scope if run else None,
        "imported_at": run.created_at.isoformat() if run and run.created_at else None,
        "n_lines_screened": n_lines,
        "attribution": dm.ATTRIBUTION.format(release=rel),
    }


@router.get("/herbs/{herb_id}/selective",
            summary="（前台）藥材 → 選擇性依賴靶點（選擇性當門檻、效應量當排序）")
def herb_selective(herb_id: int,
                   max_ratio: float = Query(dm.DEFAULT_MAX_RATIO, gt=0, le=1,
                                            description="選擇性門檻：依賴株數佔母體的比例上限"),
                   current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_query_db)):
    herb = (db.query(models.TcmspHerb)
            .filter(models.TcmspHerb.id == herb_id,
                    models.TcmspHerb.status == "active").first())
    if not herb:
        raise HTTPException(status_code=404, detail="找不到這個藥材，或它已被下架。")
    rel, run = _release_or_404(db, None)

    sel = dm.select_herb_targets(db, herb_id, rel, max_ratio)
    sources = dm.symbol_sources(db, sel)

    line_ids = {s.min_effect_depmap_id for s in sel["gated"] + sel["dropped"]
                if s.min_effect_depmap_id}
    lines = ({m.id: m for m in db.query(models.DepMapModel)
              .filter(models.DepMapModel.id.in_(list(line_ids))).all()} if line_ids else {})

    def row(s, reason=None):
        out = _summary_out(s, sel["strong"], _line_out(lines.get(s.min_effect_depmap_id)))
        out["ingredients"] = sources.get(s.gene_symbol, [])
        if reason:
            out["dropped_reason"] = reason
        return out

    meta = sel["meta"]
    return {
        "herb": {"herb_id": herb.id, "herb_cn_name": herb.herb_cn_name,
                 "herb_en_name": herb.herb_en_name, "herb_pinyin": herb.herb_pinyin},
        "release": rel,
        "params": {"max_ratio": max_ratio, "strong_effect": dm.STRONG_EFFECT,
                   "effect_threshold": dm.num(run.effect_threshold) if run else None,
                   "ob_min": sel["ob_min"], "dl_min": sel["dl_min"]},
        # 漏斗每一層都要給：使用者要看得到「從 22 個成分怎麼走到這 68 個」，
        # 不然前 15 名看起來像憑空出現
        "funnel": {
            "all_ingredients": meta["total"],
            "active_ingredients": meta["passed_count"],
            "missing_adme": meta["missing_adme"],
            "targets": len(sel["tar_ids"]),
            "symbols": len(sel["symbols"]),
            "with_depmap": len(sel["hit"]),
            "common_essential": len(sel["essential"]),
            "no_dependency": len(sel["no_dep"]),
            "selective": len(sel["selective"]),
            "gated": len(sel["gated"]),
            "dropped": len(sel["dropped"]),
            "gated_with_strong": sum(1 for s in sel["gated"] if sel["strong"].get(s.gene_symbol)),
        },
        "gated": [row(s) for s in sel["gated"]],
        "dropped": [row(s, f"依賴範圍過廣（{dm.ratio(s) * 100:.1f}% 的細胞株），"
                           f"超過選擇性門檻 {max_ratio * 100:.0f}%，接近泛必需")
                    for s in sel["dropped"]],
        "excluded_essential": sorted(s.gene_symbol for s in sel["essential"]),
        "attribution": dm.ATTRIBUTION.format(release=rel),
    }


@router.get("/genes/{symbol}/lines", summary="（前台）依賴這個基因的細胞株，由強到弱")
def gene_lines(symbol: str,
               limit: int = Query(100, ge=1, le=500),
               current_user: models.User = Depends(get_current_user),
               db: Session = Depends(get_query_db)):
    rel, run = _release_or_404(db, None)
    sym = symbol.strip().upper()
    s = (db.query(models.DepMapGeneSummary)
         .filter(models.DepMapGeneSummary.release == rel,
                 models.DepMapGeneSummary.gene_symbol == sym).first())
    if not s:
        raise HTTPException(status_code=404, detail=f"DepMap {rel} 沒有 {sym} 的資料。")
    deps = (db.query(models.DepMapGeneDependency, models.DepMapModel)
            .join(models.DepMapModel, models.DepMapModel.id == models.DepMapGeneDependency.depmap_id)
            .filter(models.DepMapGeneDependency.release == rel,
                    models.DepMapGeneDependency.gene_symbol == sym).all())
    items = [{**_line_out(m), "gene_effect": dm.num(d.gene_effect),
              "strong": (dm.num(d.gene_effect) or 0) <= dm.STRONG_EFFECT}
             for d, m in deps]
    items.sort(key=lambda x: (x["gene_effect"] if x["gene_effect"] is not None else 0,
                              x["cell_line_name"] or ""))
    strong = {sym: sum(1 for i in items if i["strong"])}
    return {"release": rel, "summary": _summary_out(s, strong),
            "total": len(items), "items": items[:limit],
            # 只存達門檻的配對，沒列出來的細胞株不是「沒測過」
            "note": (f"只列出 gene effect ≤ {run.effect_threshold if run else '門檻'} 的細胞株；"
                     f"其餘 {max(0, s.n_lines_total - len(items))} 株有測過但未達依賴門檻。"),
            "attribution": dm.ATTRIBUTION.format(release=rel)}


@router.get("/lines/search", summary="（前台）以名稱搜尋細胞株")
def search_lines(q: str = Query(min_length=1, max_length=60),
                 limit: int = Query(20, ge=1, le=100),
                 current_user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_query_db)):
    rel, _run = _release_or_404(db, None)
    k = f"%{q.strip()}%"
    M = models.DepMapModel
    rows = (db.query(M).filter(M.release == rel)
            .filter(M.cell_line_name.ilike(k) | M.stripped_cell_line_name.ilike(k)
                    | M.id.ilike(k) | M.oncotree_primary_disease.ilike(k))
            .order_by(M.cell_line_name).limit(limit).all())
    return {"release": rel, "items": [_line_out(m) for m in rows]}


@router.get("/lines/{depmap_id}", summary="（前台）細胞株 → 它依賴、且本藥材打得到的靶點")
def line_detail(depmap_id: str,
                herb_id: int = Query(..., description="限定在這味藥材的選擇性靶點"),
                max_ratio: float = Query(dm.DEFAULT_MAX_RATIO, gt=0, le=1),
                current_user: models.User = Depends(get_current_user),
                db: Session = Depends(get_query_db)):
    """規格 B：從細胞株反查選擇性依賴靶點，再回連 TCMSP 成分。"""
    rel, _run = _release_or_404(db, None)
    m = db.query(models.DepMapModel).filter(models.DepMapModel.id == depmap_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="找不到這株細胞。")
    sel = dm.select_herb_targets(db, herb_id, rel, max_ratio)
    gated = {s.gene_symbol: s for s in sel["gated"]}
    deps = (db.query(models.DepMapGeneDependency)
            .filter(models.DepMapGeneDependency.release == rel,
                    models.DepMapGeneDependency.depmap_id == depmap_id,
                    models.DepMapGeneDependency.gene_symbol.in_(list(gated))).all()
            if gated else [])
    sources = dm.symbol_sources(db, sel)
    items = [{**_summary_out(gated[d.gene_symbol], sel["strong"]),
              "gene_effect_in_line": dm.num(d.gene_effect),
              "ingredients": sources.get(d.gene_symbol, [])} for d in deps]
    items.sort(key=lambda x: x["gene_effect_in_line"] if x["gene_effect_in_line"] is not None else 0)
    return {"release": rel, "line": _line_out(m), "herb_id": herb_id,
            "total": len(items), "items": items,
            "attribution": dm.ATTRIBUTION.format(release=rel)}

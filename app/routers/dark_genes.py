import csv
import io
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/dark-genes", tags=["暗黑基因管理（癌症基因參考資料，目標三）"])


def _yn_to_bool(v: Optional[str]) -> bool:
    return (v or "").strip().lower() == "yes"


# ---------------------------------------------------------------------------
# 前台／一般登入使用者：查詢
# ---------------------------------------------------------------------------

def _build_target_word_index(db: Session):
    """建立「單詞 → 是否有任何 TCMSP 靶點名稱包含這個詞」的索引，
    這樣判斷「1245 個基因裡哪些比對得到靶點」時，每個基因只需要查表，
    不需要每個基因都重新掃過一次全部 1751 個靶點名稱。"""
    all_targets = db.query(models.TcmspTarget.target_name).all()
    word_set = set()
    for (name,) in all_targets:
        word_set |= set(re.findall(r"[A-Za-z0-9]+", (name or "").upper()))
    return word_set


def _gene_has_tcmsp_target(gene: models.DarkGene, target_word_set) -> bool:
    symbols = _gene_symbols_for_match(gene)
    return any(s in target_word_set for s in symbols)


@router.get("/public/stats", summary="（前台）暗黑基因統計：依 Gene Type 分組，統計有/沒有比對到 TCMSP 靶點的基因數")
def public_get_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    genes = db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()
    target_word_set = _build_target_word_index(db)

    by_type = {}
    total_with_target = 0
    for g in genes:
        gtype = g.gene_type or "（未分類）"
        has_target = _gene_has_tcmsp_target(g, target_word_set)
        if gtype not in by_type:
            by_type[gtype] = {"gene_type": gtype, "total": 0, "with_target": 0, "without_target": 0}
        by_type[gtype]["total"] += 1
        if has_target:
            by_type[gtype]["with_target"] += 1
            total_with_target += 1
        else:
            by_type[gtype]["without_target"] += 1

    rows = sorted(by_type.values(), key=lambda r: -r["total"])
    for r in rows:
        r["percent_with_target"] = round(r["with_target"] / r["total"] * 100, 1) if r["total"] else 0.0

    return {
        "total_genes": len(genes),
        "total_with_target": total_with_target,
        "total_without_target": len(genes) - total_with_target,
        "by_type": rows,
    }


@router.get("/public/gene-stats", summary="（前台）逐基因統計：以 Hugo Symbol 為主，列出每個基因比對到的靶點數與候選中藥數")
def public_get_gene_stats(only_with_target: bool = True, current_user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    genes = db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()
    all_targets = db.query(models.TcmspTarget).all()

    # 建立「單詞 -> 符合的靶點 tar_id 集合」索引，避免每個基因都重新掃一次全部 1751 個靶點
    word_to_target_ids = {}
    for t in all_targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        for w in words:
            word_to_target_ids.setdefault(w, set()).add(t.tar_id)

    results = []
    for g in genes:
        symbols = _gene_symbols_for_match(g)
        matched_tar_ids = set()
        for sym in symbols:
            matched_tar_ids |= word_to_target_ids.get(sym, set())

        herb_count = 0
        if matched_tar_ids:
            mol_ids = {
                r.mol_id for r in db.query(models.TcmspIngredientTarget.mol_id).filter(
                    models.TcmspIngredientTarget.tar_id.in_(matched_tar_ids)
                ).distinct().all()
            }
            if mol_ids:
                herb_count = db.query(models.TcmspHerbIngredient.herb_id).filter(
                    models.TcmspHerbIngredient.mol_id.in_(mol_ids)
                ).distinct().count()

        if only_with_target and not matched_tar_ids:
            continue

        results.append({
            "id": g.id, "hugo_symbol": g.hugo_symbol, "gene_type": g.gene_type,
            "entrez_gene_id": g.entrez_gene_id, "gene_aliases": g.gene_aliases,
            "target_count": len(matched_tar_ids), "herb_count": herb_count,
        })

    results.sort(key=lambda r: (-r["target_count"], -r["herb_count"], r["hugo_symbol"]))
    return {"total": len(results), "genes": results}


@router.get("/public/herb-stats", summary="（前台）中藥暗黑基因覆蓋統計：以藥材為主，列出每種藥材連結到幾個不重複的暗黑基因（統計數字為預先計算好的資料庫欄位）")
def public_get_herb_stats(only_with_gene: bool = True, current_user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    # dark_gene_count 直接讀資料庫欄位（app/recompute_stats.py 預先算好），
    # 不用每次請求都重新掃一次全部靶點/成分/藥材關聯，篩選跟排序也都能直接在 SQL 層做
    q = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active")
    if only_with_gene:
        q = q.filter(models.TcmspHerb.dark_gene_count > 0)
    herbs = q.order_by(models.TcmspHerb.dark_gene_count.desc(), models.TcmspHerb.herb_cn_name).all()

    if not herbs:
        return {"total": 0, "herbs": []}

    # gene_symbols（比對到的基因清單，用於畫面上顯示標籤）沒有另外存成資料表，
    # 只針對「這次真的要回傳的藥材」現算，範圍已經被上面的資料庫欄位篩選過，比全藥材下去掃快很多
    herb_ids = [h.id for h in herbs]
    genes = db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()
    genes_by_id = {g.id: g for g in genes}
    all_targets = db.query(models.TcmspTarget).all()

    word_to_target_ids = {}
    for t in all_targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        for w in words:
            word_to_target_ids.setdefault(w, set()).add(t.tar_id)

    target_to_gene_ids = {}
    for g in genes:
        for sym in _gene_symbols_for_match(g):
            for tar_id in word_to_target_ids.get(sym, set()):
                target_to_gene_ids.setdefault(tar_id, set()).add(g.id)

    relevant_tar_ids = set(target_to_gene_ids.keys())
    mol_to_gene_ids = {}
    if relevant_tar_ids:
        for r in db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.tar_id.in_(relevant_tar_ids)).all():
            mol_to_gene_ids.setdefault(r.mol_id, set()).update(target_to_gene_ids.get(r.tar_id, set()))

    herb_to_gene_ids = {}
    relevant_mol_ids = set(mol_to_gene_ids.keys())
    if relevant_mol_ids:
        for r in db.query(models.TcmspHerbIngredient).filter(
            models.TcmspHerbIngredient.herb_id.in_(herb_ids), models.TcmspHerbIngredient.mol_id.in_(relevant_mol_ids)
        ).all():
            herb_to_gene_ids.setdefault(r.herb_id, set()).update(mol_to_gene_ids.get(r.mol_id, set()))

    results = []
    for h in herbs:
        gene_ids = herb_to_gene_ids.get(h.id, set())
        results.append({
            "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
            "herb_en_name": h.herb_en_name,
            "dark_gene_count": h.dark_gene_count,  # 資料庫欄位，非現算
            "gene_symbols": sorted([genes_by_id[gid].hugo_symbol for gid in gene_ids if gid in genes_by_id]),
        })
    return {"total": len(results), "herbs": results}


@router.get("/public/list", response_model=List[schemas.DarkGeneOut], summary="（前台）查詢暗黑基因清單（含是否有中藥靶點標記，為預先計算好的統計欄位，供查詢站使用）")
def public_list_genes(keyword: Optional[str] = None, gene_type: Optional[str] = None,
                       has_tcmsp_target: Optional[bool] = None,
                       current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.DarkGene).filter(models.DarkGene.status == "active")
    if keyword:
        q = q.filter(
            (models.DarkGene.hugo_symbol.ilike(f"%{keyword}%")) |
            (models.DarkGene.gene_aliases.ilike(f"%{keyword}%"))
        )
    if gene_type:
        q = q.filter(models.DarkGene.gene_type == gene_type)
    if has_tcmsp_target is not None:
        q = q.filter(models.DarkGene.has_tcmsp_target == has_tcmsp_target)
    genes = q.order_by(models.DarkGene.hugo_symbol).all()
    return [schemas.DarkGeneOut.model_validate(g) for g in genes]


# ---------------------------------------------------------------------------
# 後台管理（僅限管理者）：CRUD + 匯入
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.DarkGeneOut], summary="（後台）查詢暗黑基因列表")
def admin_list_genes(keyword: Optional[str] = None, status_filter: Optional[str] = None,
                      gene_type: Optional[str] = None,
                      db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.DarkGene)
    if keyword:
        q = q.filter(
            (models.DarkGene.hugo_symbol.ilike(f"%{keyword}%")) |
            (models.DarkGene.gene_aliases.ilike(f"%{keyword}%"))
        )
    if status_filter:
        q = q.filter(models.DarkGene.status == status_filter)
    if gene_type:
        q = q.filter(models.DarkGene.gene_type == gene_type)
    return q.order_by(models.DarkGene.hugo_symbol).all()


@router.post("", response_model=schemas.DarkGeneOut, summary="（後台）新增暗黑基因")
def create_gene(payload: schemas.DarkGeneCreate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    if db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == payload.hugo_symbol).first():
        raise HTTPException(status_code=400, detail="這個基因符號（Hugo Symbol）已存在")
    gene = models.DarkGene(**payload.model_dump())
    db.add(gene)
    db.commit()
    db.refresh(gene)
    write_audit_log(db, admin, "create_dark_gene", "dark_gene", gene.id, f"新增暗黑基因 {gene.hugo_symbol}")
    return gene


@router.put("/{gene_id}", response_model=schemas.DarkGeneOut, summary="（後台）編輯暗黑基因")
def update_gene(gene_id: str, payload: schemas.DarkGeneUpdate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(gene, field, value)
    db.commit()
    db.refresh(gene)
    write_audit_log(db, admin, "update_dark_gene", "dark_gene", gene.id, f"編輯暗黑基因 {gene.hugo_symbol}")
    return gene


@router.delete("/{gene_id}", summary="（後台）刪除暗黑基因（軟刪除）")
def delete_gene(gene_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")
    gene.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_dark_gene_soft", "dark_gene", gene.id, f"刪除（軟刪除）暗黑基因 {gene.hugo_symbol}")
    return {"message": "已刪除（軟刪除）"}


@router.post("/import", summary="（後台）匯入暗黑基因 TSV 檔案（例如 OncoKB 癌症基因列表），依 Hugo Symbol upsert")
async def import_genes(file: UploadFile = File(...), db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="檔案編碼無法解析，請確認是 UTF-8 編碼的 TSV 檔案")

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required_cols = {"Hugo Symbol", "Entrez Gene ID", "Gene Type"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"檔案欄位格式不符，至少需要包含：{', '.join(required_cols)}")

    created, updated = 0, 0
    for row in reader:
        symbol = (row.get("Hugo Symbol") or "").strip()
        if not symbol:
            continue
        existing = db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == symbol).first()
        fields = {
            "entrez_gene_id": (row.get("Entrez Gene ID") or "").strip() or None,
            "grch37_isoform": (row.get("GRCh37 Isoform") or "").strip() or None,
            "grch37_refseq": (row.get("GRCh37 RefSeq") or "").strip() or None,
            "grch38_isoform": (row.get("GRCh38 Isoform") or "").strip() or None,
            "grch38_refseq": (row.get("GRCh38 RefSeq") or "").strip() or None,
            "gene_type": (row.get("Gene Type") or "").strip() or None,
            "occurrence_count": int(row["# of occurrence within resources (Column K-P)"])
                if (row.get("# of occurrence within resources (Column K-P)") or "").strip().isdigit() else None,
            "oncokb_annotated": _yn_to_bool(row.get("OncoKB Annotated")),
            "msk_impact": _yn_to_bool(row.get("MSK-IMPACT")),
            "msk_heme": _yn_to_bool(row.get("MSK-HEME")),
            "foundation_one": _yn_to_bool(row.get("FOUNDATION ONE")),
            "foundation_one_heme": _yn_to_bool(row.get("FOUNDATION ONE HEME")),
            "vogelstein": _yn_to_bool(row.get("Vogelstein")),
            "cosmic_cgc": _yn_to_bool(row.get("COSMIC CGC (v99)")),
            "gene_aliases": (row.get("Gene Aliases") or "").strip() or None,
        }
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(models.DarkGene(hugo_symbol=symbol, **fields))
            created += 1

    db.commit()
    write_audit_log(db, admin, "import_dark_genes", "dark_gene", "bulk",
                     f"匯入暗黑基因清單：新增 {created} 筆、更新 {updated} 筆（檔案：{file.filename}）")
    return {"message": "匯入完成", "created": created, "updated": updated}


# ---------------------------------------------------------------------------
# 暗黑基因－靶點關聯：拿基因符號（含別名）去比對 TCMSP 靶點名稱，
# 找出相關的成分／候選藥材。屬於研究輔助功能（機制層級關聯，非臨床療效證據），
# 正式提供醫療建議前仍需要醫師/專業人員審核（詳見 rules.md）。
# ---------------------------------------------------------------------------

def _gene_symbols_for_match(gene: models.DarkGene) -> List[str]:
    symbols = [gene.hugo_symbol.strip().upper()]
    if gene.gene_aliases:
        symbols += [a.strip().upper() for a in gene.gene_aliases.split(",") if a.strip()]
    return symbols


@router.get("/{gene_id}/tcmsp-links", summary="查詢暗黑基因-靶點關聯：比對 TCMSP 靶點名稱，列出候選藥材")
def get_gene_tcmsp_links(gene_id: str, current_user: models.User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")

    symbols = set(_gene_symbols_for_match(gene))
    all_targets = db.query(models.TcmspTarget).all()
    matched_targets = []
    for t in all_targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        if words & symbols:
            matched_targets.append(t)

    if not matched_targets:
        return {
            "gene": {"id": gene.id, "hugo_symbol": gene.hugo_symbol, "gene_aliases": gene.gene_aliases},
            "matched_targets": [], "ingredients": [], "herbs": [],
        }

    tar_ids = [t.tar_id for t in matched_targets]
    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(
        models.TcmspIngredientTarget.tar_id.in_(tar_ids)
    ).all()
    mol_ids = list({r.mol_id for r in ingredient_target_rows})

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(
        models.TcmspHerbIngredient.mol_id.in_(mol_ids)
    ).all() if mol_ids else []
    herb_ids = list({r.herb_id for r in herb_ingredient_rows})

    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    herbs = db.query(models.TcmspHerb).filter(
        models.TcmspHerb.id.in_(herb_ids), models.TcmspHerb.status == "active"
    ).all() if herb_ids else []

    # 每種藥材附上「透過幾個成分連結到這個基因」的計數，方便排序找出關聯性較強的候選藥材
    mol_to_herbs = {}
    for r in herb_ingredient_rows:
        mol_to_herbs.setdefault(r.mol_id, set()).add(r.herb_id)
    herb_hit_count = {}
    for mol_id in mol_ids:
        for herb_id in mol_to_herbs.get(mol_id, set()):
            herb_hit_count[herb_id] = herb_hit_count.get(herb_id, 0) + 1

    return {
        "gene": {"id": gene.id, "hugo_symbol": gene.hugo_symbol, "gene_aliases": gene.gene_aliases, "gene_type": gene.gene_type},
        "matched_targets": [
            {"tar_id": t.tar_id, "target_name": t.target_name, "drugbank_id": t.drugbank_id, "kegg": t.kegg}
            for t in matched_targets
        ],
        "ingredients": [
            {"mol_id": i.mol_id, "molecule_name": i.molecule_name, "ob": i.ob, "dl": i.dl}
            for i in ingredients
        ],
        "ingredient_target": [{"mol_id": r.mol_id, "tar_id": r.tar_id} for r in ingredient_target_rows],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
        "herbs": sorted([
            {
                "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
                "herb_en_name": h.herb_en_name, "matched_ingredient_count": herb_hit_count.get(h.id, 0),
            }
            for h in herbs
        ], key=lambda x: -x["matched_ingredient_count"]),
    }


# ---------------------------------------------------------------------------
# 藥材－暗黑基因關聯（反向查詢）：給一個藥材，找出它的成分連結到哪些 TCMSP 靶點，
# 再拿這些靶點名稱去比對暗黑基因清單，列出「這個藥材的成分可能作用在哪些癌症基因上」。
# 跟「暗黑基因-靶點關聯」是同一套比對演算法，只是方向相反（藥材出發，而不是基因出發）。
# ---------------------------------------------------------------------------

@router.get("/herb-links/{herb_id}", summary="查詢藥材-暗黑基因關聯：這個藥材的成分連結到哪些靶點，再比對出哪些暗黑基因")
def get_herb_dark_gene_links(herb_id: int, current_user: models.User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id, models.TcmspHerb.status == "active").first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.herb_id == herb_id).all()
    mol_ids = [r.mol_id for r in herb_ingredient_rows]

    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(
        models.TcmspIngredientTarget.mol_id.in_(mol_ids)
    ).all() if mol_ids else []
    tar_ids = list({r.tar_id for r in ingredient_target_rows})

    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    targets = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id.in_(tar_ids)).all() if tar_ids else []

    # 建立「單詞 -> 符合的暗黑基因」索引（同一套演算法，只是索引方向相反），
    # 避免每個靶點都重新掃一次全部 1245 個基因。
    all_genes = db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()
    word_to_genes = {}
    for g in all_genes:
        for sym in _gene_symbols_for_match(g):
            word_to_genes.setdefault(sym, []).append(g)

    target_gene_matches = {}  # tar_id -> [gene, ...]
    all_matched_genes = {}  # gene.id -> {gene info, matched_target_ids: set()}
    for t in targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        matched = []
        for w in words:
            matched.extend(word_to_genes.get(w, []))
        target_gene_matches[t.tar_id] = matched
        for g in matched:
            if g.id not in all_matched_genes:
                all_matched_genes[g.id] = {
                    "id": g.id, "hugo_symbol": g.hugo_symbol, "gene_type": g.gene_type,
                    "entrez_gene_id": g.entrez_gene_id, "matched_target_ids": set(),
                }
            all_matched_genes[g.id]["matched_target_ids"].add(t.tar_id)

    target_gene_edges = []
    for tar_id, genes in target_gene_matches.items():
        for g in genes:
            target_gene_edges.append({"tar_id": tar_id, "gene_id": g.id})

    return {
        "herb": {
            "herb_id": herb.id, "herb_cn_name": herb.herb_cn_name, "herb_pinyin": herb.herb_pinyin,
            "herb_en_name": herb.herb_en_name,
        },
        "ingredients": [
            {"mol_id": i.mol_id, "molecule_name": i.molecule_name, "ob": i.ob, "dl": i.dl}
            for i in ingredients
        ],
        "targets": [
            {
                "tar_id": t.tar_id, "target_name": t.target_name, "drugbank_id": t.drugbank_id,
                "matched_genes": [
                    {"id": g.id, "hugo_symbol": g.hugo_symbol, "gene_type": g.gene_type}
                    for g in target_gene_matches.get(t.tar_id, [])
                ],
            }
            for t in targets
        ],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
        "ingredient_target": [{"mol_id": r.mol_id, "tar_id": r.tar_id} for r in ingredient_target_rows],
        "target_gene": target_gene_edges,
        "matched_genes": sorted([
            {
                "id": v["id"], "hugo_symbol": v["hugo_symbol"], "gene_type": v["gene_type"],
                "entrez_gene_id": v["entrez_gene_id"], "matched_target_count": len(v["matched_target_ids"]),
            }
            for v in all_matched_genes.values()
        ], key=lambda x: -x["matched_target_count"]),
    }


# ---------------------------------------------------------------------------
# 病患暗黑基因彙總 -> 候選中藥（機制層級研究參考，非醫療建議，需醫師/專業人員審核）
# ---------------------------------------------------------------------------

@router.get("/patient-herb-suggestions/{patient_id}", summary="病患暗黑基因彙總的候選中藥（研究參考，非醫療建議）")
def get_patient_herb_suggestions(patient_id: str, db: Session = Depends(get_db),
                                  admin: models.User = Depends(require_admin)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="找不到病患資料")

    dark_genes_by_symbol = {g.hugo_symbol.upper(): g for g in db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()}
    variants = db.query(models.Variant).join(models.DnaImportBatch).filter(
        models.Variant.patient_id == patient_id, models.DnaImportBatch.status == "active"
    ).all()

    matched_gene_ids = set()
    for v in variants:
        if v.gene_symbol and v.gene_symbol.upper() in dark_genes_by_symbol:
            matched_gene_ids.add(dark_genes_by_symbol[v.gene_symbol.upper()].id)

    if not matched_gene_ids:
        return {"patient_id": patient_id, "matched_genes": [], "herbs": []}

    matched_genes = [g for g in dark_genes_by_symbol.values() if g.id in matched_gene_ids]
    all_targets = db.query(models.TcmspTarget).all()

    target_to_gene_ids = {}
    for g in matched_genes:
        for sym in _gene_symbols_for_match(g):
            for t in all_targets:
                words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
                if sym in words:
                    target_to_gene_ids.setdefault(t.tar_id, set()).add(g.id)

    herb_to_gene_ids = {}
    if target_to_gene_ids:
        relevant_tar_ids = set(target_to_gene_ids.keys())
        mol_to_gene_ids = {}
        for r in db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.tar_id.in_(relevant_tar_ids)).all():
            mol_to_gene_ids.setdefault(r.mol_id, set()).update(target_to_gene_ids.get(r.tar_id, set()))
        relevant_mol_ids = set(mol_to_gene_ids.keys())
        if relevant_mol_ids:
            for r in db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.mol_id.in_(relevant_mol_ids)).all():
                herb_to_gene_ids.setdefault(r.herb_id, set()).update(mol_to_gene_ids.get(r.mol_id, set()))

    herb_ids = list(herb_to_gene_ids.keys())
    herbs = db.query(models.TcmspHerb).filter(
        models.TcmspHerb.id.in_(herb_ids), models.TcmspHerb.status == "active"
    ).all() if herb_ids else []

    herb_results = sorted([
        {
            "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin, "herb_en_name": h.herb_en_name,
            "covered_gene_count": len(herb_to_gene_ids.get(h.id, set())),
            "covered_genes": sorted([g.hugo_symbol for g in matched_genes if g.id in herb_to_gene_ids.get(h.id, set())]),
        }
        for h in herbs
    ], key=lambda x: -x["covered_gene_count"])

    return {
        "patient_id": patient_id, "patient_name": patient.name,
        "matched_genes": [{"id": g.id, "hugo_symbol": g.hugo_symbol, "gene_type": g.gene_type} for g in matched_genes],
        "herbs": herb_results,
    }

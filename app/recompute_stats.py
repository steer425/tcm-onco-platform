"""
重新計算並寫入資料庫的統計欄位，取代原本「每次查詢站列表載入時即時運算」的做法。

涵蓋四個地方：
    1. 疾病關聯查詢站：TcmspDisease.target_count（這個疾病連結到幾個不重複的 TCMSP 靶點）
    2. 藥材關聯查詢站：TcmspHerb.target_count（這個藥材連結到幾個不重複的 TCMSP 靶點）
    3. 暗黑基因關聯查詢站：DarkGene.has_tcmsp_target（這個基因是否比對到任何 TCMSP 靶點）
    4. 藥材與暗黑基因關聯：TcmspHerb.dark_gene_count（這個藥材連結到幾個不重複的暗黑基因）

使用方式：
    python -m app.recompute_stats

執行時機：
    - 每次匯入/更新 TCMSP 資料（app/import_tcmsp_data.py）之後
    - 每次匯入/更新暗黑基因資料（app/import_dark_genes.py）之後
    - 後台也提供 POST /system-settings/recompute-stats 端點，管理者可以手動觸發重算
      （例如只是手動編輯了少量資料，不想重跑整個匯入流程時）

這支腳本本身不會修改任何原始資料（藥材/疾病/基因/成分/靶點的內容都不動），
只更新上面四個統計欄位，可以重複執行，執行順序不影響結果。
"""
import re
import sys

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base


def _build_target_word_index(db: Session):
    """建立「單詞 -> 是否有任何 TCMSP 靶點名稱包含這個詞」的索引，供暗黑基因比對使用。"""
    all_targets = db.query(models.TcmspTarget.target_name).all()
    word_set = set()
    for (name,) in all_targets:
        word_set |= set(re.findall(r"[A-Za-z0-9]+", (name or "").upper()))
    return word_set


def _gene_symbols_for_match(gene: models.DarkGene):
    symbols = [gene.hugo_symbol.upper()] if gene.hugo_symbol else []
    if gene.gene_aliases:
        symbols += [a.strip().upper() for a in gene.gene_aliases.split(",") if a.strip()]
    return symbols


def recompute_herb_target_counts(db: Session):
    """藥材 -> 成分 -> 靶點，統計每個藥材連結到幾個不重複的靶點。"""
    print("步驟 1/6：重算藥材的靶點統計（TcmspHerb.target_count）...")
    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).all()
    ingredient_target_rows = db.query(models.TcmspIngredientTarget).all()

    mol_to_targets = {}
    for r in ingredient_target_rows:
        mol_to_targets.setdefault(r.mol_id, set()).add(r.tar_id)

    herb_to_targets = {}
    for r in herb_ingredient_rows:
        herb_to_targets.setdefault(r.herb_id, set()).update(mol_to_targets.get(r.mol_id, set()))

    herbs = db.query(models.TcmspHerb).all()
    for h in herbs:
        h.target_count = len(herb_to_targets.get(h.id, set()))
    db.commit()
    print(f"  完成，共更新 {len(herbs)} 筆藥材資料")


def recompute_disease_target_counts(db: Session):
    """疾病 -> 靶點，統計每個疾病連結到幾個不重複的靶點（直接關聯，不用經過成分）。"""
    print("步驟 2/6：重算疾病的靶點統計（TcmspDisease.target_count）...")
    target_disease_rows = db.query(models.TcmspTargetDisease).all()
    disease_to_targets = {}
    for r in target_disease_rows:
        disease_to_targets.setdefault(r.dis_id, set()).add(r.tar_id)

    diseases = db.query(models.TcmspDisease).all()
    for d in diseases:
        d.target_count = len(disease_to_targets.get(d.dis_id, set()))
    db.commit()
    print(f"  完成，共更新 {len(diseases)} 筆疾病資料")


def recompute_dark_gene_has_target(db: Session):
    """暗黑基因是否比對到任何 TCMSP 靶點（基因符號/別名 vs 靶點名稱的單詞比對）。"""
    print("步驟 3/6：重算暗黑基因的中藥靶點比對結果（DarkGene.has_tcmsp_target）...")
    target_word_set = _build_target_word_index(db)
    genes = db.query(models.DarkGene).all()
    matched_count = 0
    for g in genes:
        symbols = _gene_symbols_for_match(g)
        has_target = any(s in target_word_set for s in symbols)
        g.has_tcmsp_target = has_target
        if has_target:
            matched_count += 1
    db.commit()
    print(f"  完成，共更新 {len(genes)} 筆基因資料，其中 {matched_count} 筆比對到中藥靶點")


def recompute_herb_dark_gene_counts(db: Session):
    """藥材 -> 成分 -> 靶點 -> 暗黑基因，統計每個藥材連結到幾個不重複的暗黑基因。"""
    print("步驟 4/6：重算藥材的暗黑基因關聯統計（TcmspHerb.dark_gene_count）...")
    genes = db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()
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

    herbs = db.query(models.TcmspHerb).all()
    if not target_to_gene_ids:
        for h in herbs:
            h.dark_gene_count = 0
        db.commit()
        print("  完成（目前沒有任何靶點比對到暗黑基因，全部藥材統計為 0）")
        return

    relevant_tar_ids = set(target_to_gene_ids.keys())
    mol_to_gene_ids = {}
    for r in db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.tar_id.in_(relevant_tar_ids)).all():
        mol_to_gene_ids.setdefault(r.mol_id, set()).update(target_to_gene_ids.get(r.tar_id, set()))

    relevant_mol_ids = set(mol_to_gene_ids.keys())
    herb_to_gene_ids = {}
    if relevant_mol_ids:
        for r in db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.mol_id.in_(relevant_mol_ids)).all():
            herb_to_gene_ids.setdefault(r.herb_id, set()).update(mol_to_gene_ids.get(r.mol_id, set()))

    for h in herbs:
        h.dark_gene_count = len(herb_to_gene_ids.get(h.id, set()))
    db.commit()
    print(f"  完成，共更新 {len(herbs)} 筆藥材資料")


def recompute_gencc_disease_has_target(db: Session):
    """GenCC 可編碼蛋白區疾病是否比對到任何 TCMSP 靶點（gene_symbol vs 靶點名稱的單詞比對）。
    跟暗黑基因用同一套比對演算法，差別是 GenCC 沒有別名欄位，只用 gene_symbol 單一欄位比對，
    資料量遠大於暗黑基因（可能 1.5~2 萬筆），這裡的迴圈本身仍是 O(n) 的 set 查找，不會太慢，
    但要注意如果之後資料量再往上一個量級，可能需要考慮批次處理或非同步背景任務。"""
    print("步驟 5/6：重算 GenCC 可編碼蛋白區疾病的中藥靶點比對結果（GenccDisease.has_tcmsp_target）...")
    target_word_set = _build_target_word_index(db)
    diseases = db.query(models.GenccDisease).filter(models.GenccDisease.status == "active").all()
    matched_count = 0
    for d in diseases:
        symbol = (d.gene_symbol or "").upper()
        has_target = symbol in target_word_set
        d.has_tcmsp_target = has_target
        if has_target:
            matched_count += 1
    db.commit()
    print(f"  完成，共更新 {len(diseases)} 筆資料，其中 {matched_count} 筆比對到中藥靶點")


def recompute_herb_gencc_disease_counts(db: Session):
    """藥材 -> 成分 -> 靶點 -> GenCC 疾病（透過 gene_symbol），統計每個藥材連結到幾個不重複的可編碼蛋白區疾病。"""
    print("步驟 6/6：重算藥材的 GenCC 可編碼蛋白區疾病關聯統計（TcmspHerb.gencc_disease_count）...")
    diseases = db.query(models.GenccDisease).filter(models.GenccDisease.status == "active").all()
    all_targets = db.query(models.TcmspTarget).all()

    word_to_target_ids = {}
    for t in all_targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        for w in words:
            word_to_target_ids.setdefault(w, set()).add(t.tar_id)

    target_to_disease_ids = {}
    for d in diseases:
        symbol = (d.gene_symbol or "").upper()
        for tar_id in word_to_target_ids.get(symbol, set()):
            target_to_disease_ids.setdefault(tar_id, set()).add(d.id)

    herbs = db.query(models.TcmspHerb).all()
    if not target_to_disease_ids:
        for h in herbs:
            h.gencc_disease_count = 0
        db.commit()
        print("  完成（目前沒有任何靶點比對到 GenCC 疾病，全部藥材統計為 0）")
        return

    relevant_tar_ids = set(target_to_disease_ids.keys())
    mol_to_disease_ids = {}
    for r in db.query(models.TcmspIngredientTarget).filter(models.TcmspIngredientTarget.tar_id.in_(relevant_tar_ids)).all():
        mol_to_disease_ids.setdefault(r.mol_id, set()).update(target_to_disease_ids.get(r.tar_id, set()))

    relevant_mol_ids = set(mol_to_disease_ids.keys())
    herb_to_disease_ids = {}
    if relevant_mol_ids:
        for r in db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.mol_id.in_(relevant_mol_ids)).all():
            herb_to_disease_ids.setdefault(r.herb_id, set()).update(mol_to_disease_ids.get(r.mol_id, set()))

    for h in herbs:
        h.gencc_disease_count = len(herb_to_disease_ids.get(h.id, set()))
    db.commit()
    print(f"  完成，共更新 {len(herbs)} 筆藥材資料")


def recompute_all_stats(db: Session):
    recompute_herb_target_counts(db)
    recompute_disease_target_counts(db)
    recompute_dark_gene_has_target(db)
    recompute_herb_dark_gene_counts(db)
    recompute_gencc_disease_has_target(db)
    recompute_herb_gencc_disease_counts(db)


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        recompute_all_stats(db)
        print("\n全部統計欄位重算完成。")
    finally:
        db.close()

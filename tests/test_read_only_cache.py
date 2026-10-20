"""唯讀模式本機快取的完整性驗收（v1.49.4）。

唯讀模式開啟後，所有用 `get_query_db` 的查詢端點改讀 `backups/local_query_cache.db`，
而那份檔案**只含 `local_cache.CACHED_TABLES` 列的表**。端點只要讀到清單外的任何一張表，
唯讀模式一開就是 `no such table` → 500，而唯讀模式關閉時一切正常——平常測不到。

v1.43.0 補過一次（F1-7／F1-8 漏了 system_settings、depmap_* 等），但只盤點了當時新增的頁面。
這支測試改成**不靠人記**：

  1. 從 FastAPI 的路由表自動找出所有依賴 `get_query_db` 的端點（新增的端點自動納入）；
  2. 讓 `get_query_db` 的連線走一個獨立的 engine，記錄每個端點實際查了哪些表，
     與 CACHED_TABLES 比對——缺哪張表、哪個端點用到，直接印出來；
  3. 走真正的流程：建備份 → `rebuild_local_cache()` → 開唯讀模式 → 每個端點再打一次，
     回應狀態碼必須與唯讀模式關閉時相同（不能有 500）。

跟其他驗收腳本一樣**不是 pytest**，用 `python -m tests.test_read_only_cache` 執行，
或 `python -m tests.run_all` 一起跑。
"""
import os
import sys

DB_FILE = "test_read_only_cache.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{DB_FILE}")
# ⛔ 測試會寫入、刪除資料，絕不能跑在正式資料庫上（v1.43.0 實際發生過）
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。")
if os.environ["DATABASE_URL"] == f"sqlite:///./{DB_FILE}" and os.path.exists(DB_FILE):
    os.remove(DB_FILE)

import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import local_cache, models
from app.backup_service import write_backup_stream
from app.database import Base, SessionLocal, get_query_db
from app.main import app

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


# ---------------------------------------------------------------------------
# 測試資料：一條完整的鏈 藥材 → 成分 → 靶點（BCL2）→ 疾病／通路／細胞株／文獻／新聞，
# 讓每個端點都走到最深的那一層查詢，而不是在第一步就 404。
# ---------------------------------------------------------------------------
HERB = 1
DEPMAP_ID = "ACH-000001"
TODAY = datetime.utcnow().strftime("%Y-%m-%d")  # noqa


def seed(db):
    db.add(models.TcmspHerb(id=HERB, herb_cn_name="人参", herb_pinyin="Ren Shen",
                            herb_en_name="Panax Ginseng C. A. Mey", status="active",
                            target_count=2, dark_gene_count=1, gencc_disease_count=1))
    db.add_all([
        models.TcmspIngredient(mol_id="MOL1", molecule_name="ginsenoside rh2", mw="622.9", ob="36.3", dl="0.56"),
        models.TcmspIngredient(mol_id="MOL2", molecule_name="sucrose", mw="342.3", ob="7.2", dl="0.23"),
        models.TcmspTarget(tar_id="TAR1", target_id=1, target_name="Apoptosis regulator Bcl-2"),
        models.TcmspTarget(tar_id="TAR2", target_id=2, target_name="Caspase-3"),
        models.TcmspDisease(dis_id="DIS1", disease_id=1, disease_name="Lymphoma", disease_cn_name="淋巴瘤",
                            target_count=1, tumor_class="tumor"),
    ])
    db.add_all([
        models.TcmspHerbIngredient(herb_id=HERB, mol_id="MOL1"),
        models.TcmspHerbIngredient(herb_id=HERB, mol_id="MOL2"),
        models.TcmspIngredientTarget(mol_id="MOL1", tar_id="TAR1", svm_score="0.9"),
        models.TcmspIngredientTarget(mol_id="MOL1", tar_id="TAR2", svm_score="0.8"),
        models.TcmspTargetDisease(tar_id="TAR1", dis_id="DIS1"),
        models.TcmspTargetUniprot(tar_id="TAR1", accession="P10415", gene_symbol="BCL2", status="confirmed"),
        models.TcmspTargetUniprot(tar_id="TAR2", accession="P42574", gene_symbol="CASP3", status="confirmed"),
        models.TcmspIngredientPubchem(mol_id="MOL1", cid="119307", status="confirmed",
                                      inchikey="RWXIFXNRCLMQCD-JBVRGBGGSA-N", canonical_smiles="CC",
                                      iupac_name="x", cas_number="78214-33-2"),
    ])
    pw = models.Pathway(source="kegg", pathway_id="hsa05200", name="Pathways in cancer",
                        is_cancer_related=True, background_gene_count=500)
    pw2 = models.Pathway(source="reactome", pathway_id="R-HSA-109581", name="Apoptosis",
                         is_cancer_related=False, background_gene_count=180)
    db.add_all([pw, pw2])
    db.flush()
    db.add_all([
        models.TargetPathway(tar_id="TAR1", pathway_ref_id=pw.id, source="kegg", via_symbol="BCL2"),
        models.TargetPathway(tar_id="TAR2", pathway_ref_id=pw.id, source="kegg", via_symbol="CASP3"),
        models.TargetPathway(tar_id="TAR1", pathway_ref_id=pw2.id, source="reactome", via_symbol="BCL2"),
    ])
    db.add_all([
        models.DepMapModel(id=DEPMAP_ID, cell_line_name="OCI-LY-19", stripped_cell_line_name="OCILY19",
                           oncotree_lineage="Lymphoid", oncotree_primary_disease="Non-Hodgkin Lymphoma",
                           release="24Q2"),
        models.DepMapGeneDependency(depmap_id=DEPMAP_ID, gene_symbol="BCL2", gene_effect="-1.4", release="24Q2"),
        models.DepMapGeneSummary(gene_symbol="BCL2", release="24Q2", n_lines_total=1000, n_dependent=20,
                                 mean_effect="-0.2", sd_effect="0.3", min_effect="-1.4",
                                 min_effect_depmap_id=DEPMAP_ID),
        models.DepMapGeneSummary(gene_symbol="CASP3", release="24Q2", n_lines_total=1000, n_dependent=0,
                                 mean_effect="0.0", sd_effect="0.1", min_effect="-0.3"),
        models.DepMapImportRun(release="24Q2", effect_threshold="-0.5", gene_scope="tcmsp", n_models=1,
                               n_genes_scanned=2, n_dependency_rows=1),
    ])
    s = models.LiteratureSearch(herb_id=HERB, gene_symbol="BCL2", query_term="q", total_count=1,
                                n_fetched=1, status="ok", grading_version="1")
    db.add(s)
    db.flush()
    db.add(models.LiteratureEvidence(search_id=s.id, pmid="1", title="Ginsenoside Rh2 downregulates BCL2",
                                     level="cell", level_rank=5, comention="sentence"))
    dg = models.DarkGene(hugo_symbol="BCL2", gene_type="ONCOGENE", has_tcmsp_target=True, status="active")
    gd = models.GenccDisease(sgc_id="SGC1", gene_symbol="BCL2", disease_curie="MONDO:1",
                             disease_title="follicular lymphoma", classification_title="Definitive",
                             has_tcmsp_target=True, status="active")
    db.add_all([dg, gd])
    src = models.NewsSource(slug="pubmed", name_zh="PubMed", name_en="PubMed", homepage="https://pubmed.ncbi.nlm.nih.gov",
                            kind=models.NewsCollectorKind.api,
                            evidence_level=models.NewsEvidenceLevel.literature_index)
    db.add(src)
    db.flush()
    art = models.NewsArticle(source_id=src.id, url="https://example.org/a", url_hash="h1", title="Ginseng and BCL2",
                             evidence_level=models.NewsEvidenceLevel.literature_index,
                             published_at=datetime.utcnow() - timedelta(hours=3),
                             collected_at=datetime.utcnow() - timedelta(hours=2))
    db.add(art)
    db.flush()
    db.add_all([
        models.NewsArticleEntity(article_id=art.id, entity_type=models.NewsEntityType.target,
                                 entity_key="TAR1", tar_id="TAR1", display_name="BCL2"),
        models.NewsArticleEntity(article_id=art.id, entity_type=models.NewsEntityType.herb,
                                 entity_key="1", herb_id=HERB, display_name="人参"),
        models.NewsDailyDigest(digest_date=TODAY, article_id=art.id, rank=1),
        models.NewsArticleSummary(article_id=art.id, lang="en", summary="s", char_limit=200),
    ])
    db.commit()
    return dg.id, gd.id


# ---------------------------------------------------------------------------
# 自動找出所有讀快取的端點，並組出要打的網址
# ---------------------------------------------------------------------------
def _uses(dep, target):
    return any(d.call is target or _uses(d, target) for d in dep.dependencies)


def cached_routes():
    return [r for r in app.routes if isinstance(r, APIRoute) and _uses(r.dependant, get_query_db)]


def build_requests(dark_gene_id, gencc_id):
    """每個端點一個請求。路徑參數依名稱填值；**新端點用到沒見過的參數名稱會直接列為失敗**，
    請在這裡補上，不要讓它默默沒被測到。"""
    path_vals = {"herb_id": HERB, "dis_id": "DIS1", "tar_id": "TAR1", "symbol": "BCL2",
                 "depmap_id": DEPMAP_ID, "gene_id": dark_gene_id, "disease_id": gencc_id,
                 "seq": 2}                       # 臺灣中藥典第 2 筆＝人參（v1.51.0，啟動時自動載入）
    required_query = {"symbol": "BCL2", "key": "RWXIFXNRCLMQCD-JBVRGBGGSA-N", "q": "OCI", "herb_id": HERB}
    bodies = {"/pathways/enrich": {"tar_ids": ["TAR1", "TAR2"]}}
    reqs, unknown = [], []
    for r in cached_routes():
        url = r.path
        for p in r.dependant.path_params:
            if p.name not in path_vals:
                unknown.append(f"{r.path} 的路徑參數 {p.name}")
                continue
            url = url.replace("{" + p.name + "}", str(path_vals[p.name]))
        qs = []
        for p in r.dependant.query_params:
            if p.required:
                if p.name not in required_query:
                    unknown.append(f"{r.path} 的必填查詢參數 {p.name}")
                    continue
                qs.append(f"{p.name}={required_query[p.name]}")
        if qs:
            url += "?" + "&".join(qs)
        for m in sorted(r.methods):
            reqs.append((m, url, r.path, bodies.get(r.path)))
    return reqs, unknown


def call(client, headers, method, url, body):
    if method == "GET":
        return client.get(url, headers=headers)
    return client.request(method, url, headers=headers, json=body)


# ---------------------------------------------------------------------------
def main():
    all_tables = set(Base.metadata.tables)
    cached = set(local_cache.CACHED_TABLES)

    # with：跑 startup，建好預設角色與 admin；伺服器錯誤要回 500 讓測試看見，不要直接丟例外
    with TestClient(app, raise_server_exceptions=False) as client:
        db = SessionLocal()
        print("\n【測試資料】")
        dark_gene_id, gencc_id = seed(db)
        check("一條完整鏈的測試資料就緒", db.query(models.TcmspHerb).count() == 1)

        r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
        H = {"Authorization": f"Bearer {r.json()['access_token']}"}

        reqs, unknown = build_requests(dark_gene_id, gencc_id)
        print(f"\n【自動找出的快取端點：{len(reqs)} 個】")
        check("每個端點的參數都知道怎麼填（新端點用到新參數名稱要在 build_requests 補上）",
              not unknown, unknown)
        check("至少涵蓋 v1.51.0 的 39 個端點（v1.49.4 盤點 35＋兩岸中藥典 4）", len(reqs) >= 39, len(reqs))

        # ---------- 第一階段：唯讀關閉，記錄每個端點查了哪些表 ----------
        print("\n【第一階段：記錄各端點實際查詢的資料表】")
        spy_engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
        SpySession = sessionmaker(bind=spy_engine, autoflush=False, autocommit=False)
        seen = []

        @event.listens_for(spy_engine, "before_cursor_execute")
        def _record(conn, cursor, statement, params, context, executemany):
            seen.append(statement)

        def spy_query_db():
            s = SpySession()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_query_db] = spy_query_db
        baseline, missing_by_route, writes_by_route, bodies_off = {}, {}, {}, {}
        try:
            for method, url, path, body in reqs:
                seen.clear()
                resp = call(client, H, method, url, body)
                baseline[(method, url)] = resp.status_code
                bodies_off[(method, url)] = resp.content
                used = {t for t in all_tables for st in seen if re.search(rf'\b{re.escape(t)}\b', st)}
                miss = sorted(used - cached)
                if miss:
                    missing_by_route[f"{method} {path}"] = miss
                w = [st.split()[0] for st in seen if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", st, re.I)]
                if w:
                    writes_by_route[f"{method} {path}"] = sorted(set(w))
                if resp.status_code >= 500:
                    print(f"     {method} {url} → {resp.status_code}（唯讀關閉就已經 500）")
        finally:
            app.dependency_overrides.pop(get_query_db, None)

        bad = [k for k, v in baseline.items() if v >= 500]
        check("唯讀關閉時沒有端點回 500（基準本身要正常）", not bad, bad)
        not_ok = {k: v for k, v in baseline.items() if v != 200}
        check("唯讀關閉時每個端點都回 200（測試資料夠深，沒有提早 404）", not not_ok, not_ok)
        for route, miss in sorted(missing_by_route.items()):
            print(f"     {route} 讀到不在快取裡的表：{', '.join(miss)}")
        check("**每個快取端點讀到的表都在 CACHED_TABLES 裡**", not missing_by_route,
              f"{len(missing_by_route)} 個端點有缺表" if missing_by_route else "")
        # 快取是唯讀的副本，寫進去的東西不會回到正式庫；唯讀模式也據此放行 POST /pathways/enrich
        check("**快取端點都不寫入（不發出 INSERT／UPDATE／DELETE）**", not writes_by_route, writes_by_route)

        # ---------- 第二階段：真正的唯讀流程 ----------
        print("\n【第二階段：建備份 → 重建本機快取 → 開唯讀模式 → 每個端點再打一次】")
        tmp = Path(tempfile.mkdtemp(prefix="tcm_ro_"))
        backup_path = tmp / "backup.enc"
        with open(backup_path, "wb") as f:
            write_backup_stream(db, f)
        # 不要碰開發者自己的 backups/local_query_cache.db
        orig_path = local_cache.LOCAL_CACHE_DB_PATH
        local_cache.LOCAL_CACHE_DB_PATH = tmp / "local_query_cache.db"
        local_cache._local_engine = None
        try:
            rows = local_cache.rebuild_local_cache(SimpleNamespace(file_path=str(backup_path)))
            check("本機快取重建成功", rows > 0 and local_cache.is_local_cache_available(), rows)

            setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "read_only_mode").first()
            if setting:
                setting.value = "true"
            else:
                db.add(models.SystemSetting(key="read_only_mode", value="true"))
            db.commit()

            # 確認真的在讀快取：快取只該有 CACHED_TABLES
            from sqlalchemy import inspect as _inspect
            cache_tables = set(_inspect(local_cache._get_local_engine()).get_table_names())
            check("快取檔裡的表＝CACHED_TABLES（沒有多帶帳號等敏感表）",
                  cache_tables <= cached and "users" not in cache_tables, sorted(cache_tables - cached))

            diffs, content_diffs = {}, []
            for method, url, path, body in reqs:
                resp = call(client, H, method, url, body)
                if resp.status_code != baseline[(method, url)]:
                    diffs[f"{method} {url}"] = (baseline[(method, url)], resp.status_code,
                                                 resp.text[:160])
                elif resp.content != bodies_off[(method, url)]:
                    content_diffs.append(f"{method} {url}")
            for k, v in diffs.items():
                print(f"     {k}：唯讀關閉 {v[0]} → 唯讀開啟 {v[1]}　{v[2]}")
            check("**唯讀模式開啟後，每個端點的狀態碼與關閉時相同（沒有 500）**", not diffs,
                  f"{len(diffs)} 個不同" if diffs else "")
            # 快取是備份還原出來的副本，內容應該逐位元組相同；不同代表有欄位在備份／還原時走樣（例如日期格式）
            check("唯讀模式開啟後，每個端點的回應內容與關閉時完全相同", not content_diffs, content_diffs)
        finally:
            setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "read_only_mode").first()
            if setting:
                setting.value = "false"
                db.commit()
            local_cache.LOCAL_CACHE_DB_PATH = orig_path
            local_cache._local_engine = None
            db.close()

    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print(f"   - {f}")
        raise SystemExit(1)
    print("✅ 唯讀模式本機快取驗證全部通過")


if __name__ == "__main__":
    main()

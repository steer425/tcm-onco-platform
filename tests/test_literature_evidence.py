"""F1-9 文獻證據分級（Step 5）— 端對端驗證。

執行：`python -m tests.test_literature_evidence`（從專案根目錄）。
不連外網：PubMed 的 esearch／efetch 以假資料替換；DepMap／TCMSP 沿用 test_depmap_page 的人參形狀
（BCL2、AHR、NOISE1 通過選擇性門檻；PSMG1 被刷掉；CDK1 泛必需）。

假文章刻意涵蓋每一種「看起來是證據、其實不是」的情況：
  網絡藥理學（循環論證）、綜述、撤稿、只靠索引命中、只提到成分沒提到藥材。
最重要的斷言：
  1. 查的靶點就是 Step 6 通過門檻的那一份（共用 select_herb_targets）
  2. 「獨立證據」排除循環論證／綜述／撤稿／索引命中
  3. 統計端點的 remaining == 批次端點真正會處理的筆數（rules.md 4-1）
  4. 唯讀快取上讀取端點可用
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_literature.db")
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    import sys as _sys
    _sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。\n"
              "   請先清掉：Remove-Item Env:DATABASE_URL　或開一個新的 PowerShell 視窗再跑。")
if (os.environ["DATABASE_URL"] == "sqlite:///./test_literature.db"
        and os.path.exists("test_literature.db")):
    os.remove("test_literature.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import literature_evidence as le, models
from app.database import SessionLocal, engine as main_engine
from app.local_cache import CACHED_TABLES
from app.main import app
from app.routers import literature as lit_router
from tests.test_depmap_page import seed

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra != '' else ''}")
    if not cond:
        FAIL.append(label)


# ---------------------------------------------------------------------------
# 假 PubMed
# ---------------------------------------------------------------------------
def art(pmid, title, abstract, pub_types=("Journal Article",), year=2023):
    return {"pmid": pmid, "title": title, "abstract": abstract, "journal": "J Test",
            "year": year, "doi": f"10.1000/{pmid}", "pub_types": list(pub_types)}


BCL2_ARTS = [
    art("101", "Ginsenoside Rh2 induces apoptosis in lymphoma cells",
        "We treated OCI-LY-19 cells in vitro. Ginsenoside Rh2 induced apoptosis by downregulating BCL2 expression."),
    art("102", "Panax ginseng extract suppresses xenograft growth",
        "Nude mice bearing tumors were treated. Panax Ginseng extract decreased Bcl-2 and increased Bax in tumors."),
    art("103", "Network pharmacology of Panax Ginseng in lymphoma",
        "Targets were retrieved from TCMSP. Molecular docking showed Panax Ginseng components bind BCL2 in cancer."),
    art("104", "Ginseng and apoptosis: a review",
        "This review summarizes studies in mice and cells. Panax Ginseng modulates BCL2 in tumors.",
        pub_types=("Journal Article", "Review")),
    art("105", "Kaempferol inhibits BCL2 in breast cancer cells",
        "MCF7 cells were used. Kaempferol inhibited BCL2 expression in a dose-dependent manner."),
    art("106", "Saponins and the intrinsic apoptosis pathway in tumors",
        "Intrinsic apoptosis regulators in tumors are discussed in relation to saponin fractions."),
    art("107", "A randomized controlled trial of Panax Ginseng in lymphoma patients",
        "Patients received Panax Ginseng or placebo for 12 weeks. Serum BCL2 levels were reduced at week 12.",
        pub_types=("Journal Article", "Randomized Controlled Trial")),
    art("108", "Retracted: Ginsenoside Rh2 downregulates BCL2 in leukemia cells",
        "K562 cells in vitro. Ginsenoside Rh2 suppressed BCL2.",
        pub_types=("Journal Article", "Retracted Publication")),
]

CALLS = {"esearch": [], "efetch": []}


def fake_esearch(client, term, *, email=None, api_key=None, retmax=le.RETMAX):
    CALLS["esearch"].append(term)
    if '"BCL2"' in term:
        return 57, [a["pmid"] for a in BCL2_ARTS] + ["101"]   # 重複的 PMID 也要能處理
    if '"Aryl hydrocarbon receptor"' in term:
        raise RuntimeError("HTTP 429 Too Many Requests")
    return 0, []


def fake_efetch(client, pmids, *, email=None, api_key=None):
    CALLS["efetch"].append(list(pmids))
    by = {a["pmid"]: a for a in BCL2_ARTS}
    return [by[p] for p in pmids if p in by]


le.esearch, le.efetch = fake_esearch, fake_efetch


def unit_checks():
    print("\n【分級規則（純函式）】")
    g = lambda a: le.grade_design(a["pub_types"], a["title"] + "\n" + a["abstract"])
    by = {a["pmid"]: a for a in BCL2_ARTS}
    check("細胞實驗", g(by["101"]) == ("cell", []), g(by["101"]))
    check("動物實驗", g(by["102"])[0] == "animal", g(by["102"]))
    check("**網絡藥理＋對接 → 計算預測、標循環論證**", g(by["103"]) == ("computational", ["circular"]), g(by["103"]))
    check("**出版類型是綜述 → 綜述**（即使摘要提到 mice、cells）", g(by["104"])[0] == "review", g(by["104"]))
    check("RCT 出版類型 → 臨床試驗", g(by["107"])[0] == "trial", g(by["107"]))
    check("撤稿 → 標 retracted", "retracted" in g(by["108"])[1], g(by["108"]))
    check("統合分析優先於其他", le.grade_design(["Meta-Analysis"], "mice cells")[0] == "meta")
    check("**摘要寫 patients 但只有細胞實驗 → 不升成人體研究**",
          le.grade_design([], "For patients with lymphoma, new drugs are needed. HL-60 cells were treated in vitro.")[0] == "cell")
    check("有濕實驗又有網絡藥理 → 保留濕實驗層級、帶循環與計算旗標",
          le.grade_design([], "Network pharmacology predicted targets; xenograft in nude mice confirmed.")
          == ("animal", ["circular", "includes_computational"]))

    check("基因詞：BCL2、BCL-2、蛋白名稱",
          le.gene_terms("BCL2", "Apoptosis regulator Bcl-2") == ["BCL2", "BCL-2", "Apoptosis regulator Bcl-2"])
    check("**兩個字母的符號（AR）不放進查詢式**，只用蛋白名稱",
          le.gene_terms("AR", "Androgen receptor") == ["Androgen receptor"])
    check("太短的名稱不當查詢詞", le._clean_term("Q10") is None and le._clean_term('a"bc"d') == "abcd")
    check("希臘字母轉寫（β-sitosterol → beta-sitosterol）", le._clean_term("β-sitosterol") == "beta-sitosterol")

    ents = [{"kind": "herb", "term": "Panax Ginseng", "mol_id": None},
            {"kind": "ingredient", "term": "ginsenoside rh2", "mol_id": "MOLA01"}]
    gt = ["BCL2", "BCL-2"]
    t = le.analyse_text(by["101"]["title"], by["101"]["abstract"], ents, gt)
    check("同句共現、方向下調（induce apoptosis 不算上調）",
          t["comention"] == "sentence" and t["direction"] == "down" and "downregulating BCL2" in t["sentence"], t)
    t = le.analyse_text(by["102"]["title"], by["102"]["abstract"], ents, gt)
    check("**「降 Bcl-2、升 Bax」→ 取靶點所在子句 → 下調**（不是混合）", t["direction"] == "down", t)
    t = le.analyse_text(by["107"]["title"], by["107"]["abstract"], ents, gt)
    check("藥材與靶點在不同句 → 摘要層級共現", t["comention"] == "abstract" and t["direction"] is None, t)
    t = le.analyse_text(by["106"]["title"], by["106"]["abstract"], ents, gt)
    check("文字裡找不到 → 只靠索引命中", t["comention"] == "index_only" and t["matched"] == [], t)
    t = le.analyse_text("x", "Rh2 decreased BCL2 but increased BCL2 phosphorylation. Panax Ginseng.",
                        [{"kind": "ingredient", "term": "Rh2", "mol_id": None}], gt)
    check("同一句兩個方向 → 混合", t["direction"] == "mixed", t)
    t = le.analyse_text("ar in tumors", "Panax Ginseng and ar.", ents, ["AR"])
    check("三個字以下的基因詞大小寫要一致（ar 不算 AR）", t["comention"] == "index_only", t)


def main(client):
    print("\n" + "=" * 60)
    print("F1-9 文獻證據分級 端對端驗證")
    print("=" * 60)
    unit_checks()

    db = SessionLocal()
    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("\n尚未匯入 DepMap → 404 並說明靶點清單來自 Step 6",
          client.get("/literature/herbs/336", headers=A).status_code == 404)
    seed(db)
    r = client.post("/auth/login", json={"account": "dmuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    print("\n【查詢前】")
    check("未帶 token → 401", client.get("/literature/herbs/336").status_code == 401)
    check("已下架的藥材 → 404", client.get("/literature/herbs/999", headers=U).status_code == 404)
    d = client.get("/literature/herbs/336", headers=U).json()
    genes = [x["gene_symbol"] for x in d["genes"]]
    check("**靶點就是 Step 6 通過門檻的那一份、同樣順序**", genes == ["BCL2", "AHR", "NOISE1"], genes)
    dm_genes = [x["gene_symbol"] for x in
                client.get("/depmap/herbs/336/selective", headers=U).json()["gated"]]
    check("與 F1-8 端點逐一相同", genes == dm_genes, dm_genes)
    check("尚未查詢：remaining 3、每列 search 為空",
          d["counts"] == {"genes": 3, "searched": 0, "remaining": 3}
          and all(x["search"] is None and x["summary"] is None for x in d["genes"]), d["counts"])
    check("**打到 BCL2 的成分只列活性成分**",
          [i["mol_id"] for i in d["genes"][0]["ingredients"]] == ["MOLA01", "MOLA02"], d["genes"][0]["ingredients"])
    check("回傳附免責與「文獻共現不等於作用」說明",
          "文獻共現" in d["disclaimer"] and "同源" in d["disclaimer"] and "醫療診斷" in d["disclaimer"])
    check("**一般使用者的頁面資料標 can_collect=false**（前端據此隱藏查詢鈕）", d["can_collect"] is False, d.get("can_collect"))
    check("管理者 can_collect=true",
          client.get("/literature/herbs/336", headers=A).json()["can_collect"] is True)
    check("一般使用者不能查詢 PubMed（無 can_execute）→ 403",
          client.post("/literature/herbs/336/collect", json={}, headers=U).status_code == 403)
    check("limit 超出範圍 → 422",
          client.post("/literature/herbs/336/collect", json={"limit": 11}, headers=A).status_code == 422)
    check("未查過的組合 → 404",
          client.get("/literature/herbs/336/genes/BCL2", headers=U).status_code == 404)

    print("\n【第一批：limit 2】")
    res = client.post("/literature/herbs/336/collect", json={"limit": 2}, headers=A).json()
    check("**統計的 remaining（3）與批次處理順序一致**：處理 BCL2、AHR",
          [x["gene_symbol"] for x in res["results"]] == ["BCL2", "AHR"], res)
    b, a = res["results"]
    check("BCL2：ok、命中總數 57、抓回 8 篇（重複 PMID 只算一次）",
          b["status"] == "ok" and b["total_count"] == 57 and b["n_fetched"] == 8, b)
    check("**AHR 外部錯誤 → 記 error、不中斷整批**", a["status"] == "error" and "429" in a["error"], a)
    check("查詢失敗的仍算待查：remaining 2（AHR、NOISE1）", res["remaining"] == 2, res["remaining"])

    q = CALLS["esearch"][0]
    check("查詢式含藥材名、兩個活性成分、基因三種寫法與癌症條件",
          all(x in q for x in ['"Panax Ginseng"[tiab]', '"Renshen"[tiab]', '"ginsenoside rh2"[tiab]',
                                '"kaempferol"[tiab]', '"BCL2"[tiab]', '"BCL-2"[tiab]',
                                '"Apoptosis regulator Bcl-2"[tiab]', "neoplasms[mh]"]), q)
    check("**非活性成分不進查詢式**", "inactive thing" not in q)

    d = client.get("/literature/herbs/336", headers=U).json()
    check("統計：searched 1、remaining 2", d["counts"] == {"genes": 3, "searched": 1, "remaining": 2}, d["counts"])
    s = d["genes"][0]["summary"]
    check("BCL2 摘要：各層級篇數",
          s["by_level"]["cell"] == 3 and s["by_level"]["animal"] == 1 and s["by_level"]["trial"] == 1
          and s["by_level"]["computational"] == 1 and s["by_level"]["review"] == 1, s["by_level"])
    check("**獨立證據 4 篇**（排除網絡藥理、綜述、撤稿、只靠索引命中）", s["independent"] == 4, s)
    check("最高獨立證據＝臨床試驗", s["best_level"] == "trial" and s["best_level_label"] == "臨床試驗", s)
    check("**藥材層級與只提到成分的分開數**",
          s["herb_level"] == 4 and s["ingredient_only"] == 3, (s["herb_level"], s["ingredient_only"]))
    check("循環論證 1 篇、同句共現與方向統計", s["circular"] == 1 and s["directions"]["down"] >= 4, s)
    check("AHR 列顯示查詢失敗原因", d["genes"][1]["search"]["status"] == "error"
          and "429" in d["genes"][1]["search"]["error"])

    g = client.get("/literature/herbs/336/genes/BCL2", headers=U).json()
    arts = g["articles"]
    check("逐篇依層級排序：臨床試驗在最前、未判定在最後",
          arts[0]["pmid"] == "107" and arts[-1]["pmid"] == "106", [x["pmid"] for x in arts])
    check("附可貼回 PubMed 重跑的查詢式與連結",
          g["query_term"] == q and g["pubmed_search_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/?term="))
    a105 = next(x for x in arts if x["pmid"] == "105")
    check("成分命中記下 mol_id", a105["matched_entities"] == [
        {"kind": "ingredient", "term": "kaempferol", "mol_id": "MOLA02"}], a105["matched_entities"])
    check("文章附 PubMed 連結與共現句", a105["url"] == "https://pubmed.ncbi.nlm.nih.gov/105/"
          and "Kaempferol inhibits BCL2" in a105["evidence_sentence"])

    print("\n【第二批：剩下的全部】")
    before = client.get("/literature/herbs/336", headers=U).json()["counts"]["remaining"]
    res = client.post("/literature/herbs/336/collect", json={"limit": 10}, headers=A).json()
    check("**統計端點的 remaining == 批次端點處理的筆數**（rules.md 4-1）",
          res["processed"] == before == 2, (res["processed"], before))
    check("NOISE1 查無文獻 → empty", res["results"][1] == {"gene_symbol": "NOISE1", "status": "empty",
                                                         "total_count": 0, "n_fetched": 0, "error": None}, res)
    check("AHR 仍失敗 → remaining 1", res["remaining"] == 1, res["remaining"])
    res = client.post("/literature/herbs/336/collect", json={"limit": 10, "genes": ["noise1"]}, headers=A).json()
    check("已查過且沒有 refresh → 不重查", res["processed"] == 0, res)

    print("\n【重查】")
    n_before = db.query(models.LiteratureEvidence).count()
    res = client.post("/literature/herbs/336/collect",
                      json={"limit": 10, "genes": ["BCL2"], "refresh": True}, headers=A).json()
    db.expire_all()
    check("refresh 只查指定的 BCL2", [x["gene_symbol"] for x in res["results"]] == ["BCL2"], res)
    check("**重查覆蓋、不重複累積**", db.query(models.LiteratureEvidence).count() == n_before
          and db.query(models.LiteratureSearch).filter_by(herb_id=336, gene_symbol="BCL2").count() == 1)
    check("清單外的基因不會被查（PSMG1 已被門檻刷掉）",
          client.post("/literature/herbs/336/collect", json={"genes": ["PSMG1"], "refresh": True},
                      headers=A).json()["processed"] == 0)

    logs = db.query(models.AuditLog).filter(models.AuditLog.action == "literature_collect").all()
    check("每次查詢寫入共用稽核紀錄", len(logs) == 5, len(logs))  # 權限矩陣那段另有一次，在此之後

    print("\n【權限矩陣：可執行是否生效】")
    general = db.query(models.Role).filter(models.Role.name == "一般使用者").first()
    perms = client.get(f"/roles/{general.id}/permissions", headers=A).json()
    by_code = {p["feature_code"]: p for p in perms}
    check("**F1-9 標 execute_enforced=true**（後端真的檢查 can_execute）",
          by_code["F1-9"]["execute_enforced"] is True)
    check("**只限管理者的功能（F1-6 成分標準化）標 false**",
          by_code["F1-6"]["execute_enforced"] is False, by_code["F1-6"].get("execute_enforced"))
    check("只有用 require_permission 的功能會被標成生效",
          {c for c, p in by_code.items() if p["execute_enforced"]} == {"F1-9"},
          sorted(c for c, p in by_code.items() if p["execute_enforced"]))
    f19 = db.query(models.Feature).filter(models.Feature.code == "F1-9").first()
    rp = (db.query(models.RolePermission)
          .filter_by(role_id=general.id, feature_id=f19.id).first())
    rp.can_execute = True
    db.commit()
    check("**一般使用者角色勾了可執行 → can_collect 變 true，POST 也放行**（畫面與後端一致）",
          client.get("/literature/herbs/336", headers=U).json()["can_collect"] is True
          and client.post("/literature/herbs/336/collect", json={"limit": 1, "genes": ["NOISE1"]},
                          headers=U).status_code == 200)
    rp.can_execute = False
    db.commit()

    print("\n【功能項目與導覽】")
    feat = db.query(models.Feature).filter(models.Feature.code == "F1-9").first()
    check("F1-9 由 seed 建立", feat is not None and feat.page_url == "literature-evidence.html")
    menu = client.get("/nav/menu", headers=U)
    check("一般使用者的導覽選單看得到這一頁", "literature-evidence.html" in menu.text)
    check("前端頁面存在", client.get("/app/literature-evidence.html").status_code == 200)

    print("\n【唯讀模式：只含 CACHED_TABLES 的本機快取也跑得動】")
    check("兩張新表在快取清單", {"literature_searches", "literature_evidence"} <= set(CACHED_TABLES))
    cache = create_engine("sqlite://")
    tables = [t for t in models.Base.metadata.sorted_tables if t.name in CACHED_TABLES]
    models.Base.metadata.create_all(bind=cache, tables=tables)
    with main_engine.connect() as src, cache.begin() as dst:
        for t in tables:
            rows = [dict(x._mapping) for x in src.execute(select(t))]
            if rows:
                dst.execute(t.insert(), rows)
    local = sessionmaker(bind=cache)()
    try:
        out = lit_router.herb_literature(336, le.dm.DEFAULT_MAX_RATIO, None, local, local)
        check("**herb_literature 在快取上可用**", out["genes"][0]["summary"]["independent"] == 4)
        out = lit_router.gene_articles(336, "BCL2", None, local)
        check("gene_articles 在快取上可用", len(out["articles"]) == 8)
    except Exception as exc:  # noqa: BLE001
        check("唯讀快取可用", False, repr(exc)[:200])
    finally:
        local.close()

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for x in FAIL:
            print("   -", x)
        raise SystemExit(1)
    print("✅ 文獻證據分級驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        main(c)

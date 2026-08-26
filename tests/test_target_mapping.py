"""靶點標準化（UniProt）— 端對端驗證。

不連外網。UniProt 的 HTTP 呼叫以固定 fixture 取代（fixture 內容是實際查詢
rest.uniprot.org 得到的真實回應結構，欄位名稱與巢狀層次都照抄），其餘
（名稱正規化、三層解析、批次端點、人工審核、比對索引、統計重算、權限、稽核）
全部走真實程式碼路徑。

為什麼要有這支測試：標準化的價值全在「AR 這個基因符號到底對不對得到
Androgen receptor 這個靶點」。這件事錯了，覆蓋率數字再漂亮都沒有意義，
所以下面用實際查證過的已知真值當回歸斷言。
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_target_mapping.db")

# 跟新聞模組的測試同一個理由：留著上一輪的資料庫會讓「尚未處理」的計算失準，
# 失敗訊息會變成看不懂的數字對不上，而不是有意義的錯誤。
if (os.environ["DATABASE_URL"] == "sqlite:///./test_target_mapping.db"
        and os.path.exists("test_target_mapping.db")):
    os.remove("test_target_mapping.db")

from fastapi.testclient import TestClient

from app import models, tcmsp_uniprot
from app.database import SessionLocal
from app.main import app
from app.security import hash_password
from app.target_index import symbol_to_targets, target_to_symbols

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        FAIL.append(label)


# ---------------------------------------------------------------------------
# UniProt 回應 fixture（照抄真實回應的欄位結構）
# ---------------------------------------------------------------------------

def _entry(accession, gene, synonyms, protein, organism=9606, kegg=None, reactome=()):
    return {
        "primaryAccession": accession,
        "organism": {"taxonId": organism},
        "genes": [{
            "geneName": {"value": gene},
            "synonyms": [{"value": s} for s in synonyms],
        }],
        "proteinDescription": {
            "recommendedName": {"fullName": {"value": protein}},
        },
        "uniProtKBCrossReferences": (
            ([{"database": "KEGG", "id": kegg}] if kegg else [])
            + [{"database": "Reactome", "id": r} for r in reactome]
        ),
    }


# 已知真值：這七個是實際在 TCMSP 靶點表裡查證過的名稱
FIXTURE = {
    "Androgen receptor": [
        _entry("P10275", "AR", ["DHTR", "NR3C4"], "Androgen receptor",
               kegg="hsa:367", reactome=["R-HSA-383280"])],
    "Cellular tumor antigen p53": [
        _entry("P04637", "TP53", ["P53"], "Cellular tumor antigen p53", kegg="hsa:7157")],
    "RAC-alpha serine/threonine-protein kinase": [
        _entry("P31749", "AKT1", ["PKB", "RAC"],
               "RAC-alpha serine/threonine-protein kinase", kegg="hsa:207")],
    "Adenomatous polyposis coli protein": [
        _entry("P25054", "APC", ["DP2.5"], "Adenomatous polyposis coli protein")],
    "Epidermal growth factor receptor": [
        _entry("P00533", "EGFR", ["ERBB", "ERBB1", "HER1"],
               "Epidermal growth factor receptor", kegg="hsa:1956")],
    # 這兩個是本次設計最在意的案例：名稱只差結尾數字，是兩個不同的基因。
    # 正規化如果把尾數當雜訊剝掉，PTGS1 跟 PTGS2 就會互相污染。
    "Prostaglandin G/H synthase 1": [
        _entry("P23219", "PTGS1", ["COX1"], "Prostaglandin G/H synthase 1")],
    "Prostaglandin G/H synthase 2": [
        _entry("P35354", "PTGS2", ["COX2"], "Prostaglandin G/H synthase 2")],
    # 多候選 → 應該進待確認，不能自動採用
    "Ambiguous kinase": [
        _entry("Q00001", "AAA1", [], "Ambiguous kinase alpha"),
        _entry("Q00002", "BBB1", [], "Ambiguous kinase beta"),
    ],
}

# 第 2 級（拆詞查詢）才找得到的：精確名稱查不到，拆詞後單一命中 → 自動採用
FIXTURE_TIER2 = {
    "Tyrosine protein kinase JAK2": [
        _entry("O60674", "JAK2", ["JTK10"], "Tyrosine-protein kinase JAK2",
               kegg="hsa:3717")],
}

# 第 3 級（全文查詢）才找得到的：就算只回一筆也必須進待確認——
# 全文命中代表「條目內文提到這個字串」，不代表就是同一個蛋白。
FIXTURE_TIER3 = {
    "Vague receptor protein": [
        _entry("Q99999", "VRP1", [], "Some vaguely related receptor")],
}


def fake_search(client, query, size=5):
    """取代 tcmsp_uniprot._search（真正打 HTTP 的那一層）。

    簽名必須跟真的那支一模一樣：resolve_name 把所有例外都吃掉轉成 status=error，
    所以簽名對不上時不會爆錯，只會讓每個斷言都莫名其妙地失敗。
    """
    import re
    m = re.search(r'protein_name:"([^"]+)"', query)      # 第 1 級
    if m:
        return FIXTURE.get(m.group(1), [])
    m = re.search(r"protein_name:\(([^)]+)\)", query)    # 第 2 級
    if m:
        return FIXTURE_TIER2.get(m.group(1), [])
    m = re.match(r'^"([^"]+)"', query)                   # 第 3 級
    if m:
        return FIXTURE_TIER3.get(m.group(1), [])
    return []


def main():
    print("\n" + "=" * 60)
    print("靶點標準化（UniProt）端對端驗證")
    print("=" * 60)

    db = SessionLocal()

    # ---------- 名稱正規化 ----------
    print("\n【名稱正規化與查詢詞】")
    check("normalize 去掉多餘空白並統一大小寫比較基準",
          tcmsp_uniprot.normalize("  Androgen   Receptor ") == "androgen receptor",
          tcmsp_uniprot.normalize("  Androgen   Receptor "))
    t2 = tcmsp_uniprot.query_terms("Prostaglandin G/H synthase 2")
    t1 = tcmsp_uniprot.query_terms("Prostaglandin G/H synthase 1")
    check("query_terms 保留結尾數字（PTGS1/PTGS2 是兩個基因，剝掉就分不出來）",
          t2.split()[-1] == "2" and t1.split()[-1] == "1", (t1, t2))
    check("query_terms 對 synthase 1 / 2 產生不同的查詢詞", t1 != t2, (t1, t2))
    check("query_terms 丟掉單字母雜訊（G、H）但保留有意義的詞",
          "Prostaglandin" in t2 and "synthase" in t2 and " G " not in f" {t2} ", t2)

    # ---------- 三層解析 ----------
    print("\n【三層解析（exact / stripped / fulltext）】")
    orig_search = tcmsp_uniprot._search
    tcmsp_uniprot._search = fake_search
    try:
        r = tcmsp_uniprot.resolve_name(None, "Androgen receptor")
        check("AR：精確命中且自動採用", r["status"] == "auto" and r["gene_symbol"] == "AR", r)
        check("AR：帶回 accession P10275", r["accession"] == "P10275", r.get("accession"))
        check("AR：同義詞有 NR3C4（同義詞是反查對得到的關鍵）",
              "NR3C4" in (r.get("gene_synonyms") or []), r.get("gene_synonyms"))
        check("AR：帶回 KEGG 交叉引用", r.get("kegg_id") == "hsa:367", r.get("kegg_id"))

        r = tcmsp_uniprot.resolve_name(None, "Cellular tumor antigen p53")
        check("TP53：p53 的蛋白全名對得到 TP53", r["gene_symbol"] == "TP53", r.get("gene_symbol"))

        r = tcmsp_uniprot.resolve_name(None, "RAC-alpha serine/threonine-protein kinase")
        check("AKT1：名稱裡完全沒有 AKT 字樣也對得到",
              r["gene_symbol"] == "AKT1", r.get("gene_symbol"))

        r1 = tcmsp_uniprot.resolve_name(None, "Prostaglandin G/H synthase 1")
        r2 = tcmsp_uniprot.resolve_name(None, "Prostaglandin G/H synthase 2")
        check("PTGS1 / PTGS2 沒有互相污染",
              r1["gene_symbol"] == "PTGS1" and r2["gene_symbol"] == "PTGS2",
              (r1.get("gene_symbol"), r2.get("gene_symbol")))

        r = tcmsp_uniprot.resolve_name(None, "Ambiguous kinase")
        check("多個候選 → 待人工確認，不自動採用", r["status"] == "pending", r["status"])
        check("待確認的一樣要把候選存下來給人挑",
              len(r.get("candidates") or []) == 2, len(r.get("candidates") or []))

        r = tcmsp_uniprot.resolve_name(None, "Tyrosine-protein kinase JAK2")
        check("第 2 級（拆詞）單一命中 → 自動採用",
              r["status"] == "auto" and r["method"] == "stripped", (r["status"], r["method"]))
        check("第 2 級也對得到 JAK2", r["gene_symbol"] == "JAK2", r.get("gene_symbol"))

        r = tcmsp_uniprot.resolve_name(None, "Vague receptor protein")
        check("第 3 級（全文）就算只回一筆也必須待確認，不能自動採用",
              r["status"] == "pending" and r["method"] == "fulltext", (r["status"], r["method"]))

        r = tcmsp_uniprot.resolve_name(None, "Nonexistent protein xyz")
        check("查無結果 → unresolved（不是 error，兩者要分得開）",
              r["status"] == "unresolved", r["status"])
    finally:
        tcmsp_uniprot._search = orig_search

    # ---------- 主檔與帳號 ----------
    print("\n【測試資料】")
    TARGETS = [
        ("TARX0001", "Androgen receptor"),
        ("TARX0002", "Cellular tumor antigen p53"),
        ("TARX0003", "RAC-alpha serine/threonine-protein kinase"),
        ("TARX0004", "Prostaglandin G/H synthase 2"),
        ("TARX0005", "Ambiguous kinase"),
        ("TARX0006", "Nonexistent protein xyz"),
        ("TARX0007", "Tyrosine-protein kinase JAK2"),
        ("TARX0008", "Vague receptor protein"),
    ]
    for tar_id, name in TARGETS:
        if not db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == tar_id).first():
            db.add(models.TcmspTarget(tar_id=tar_id, target_name=name))
    db.commit()
    check("靶點主檔就緒", db.query(models.TcmspTarget).count() >= 8)

    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    check("管理者登入 200", r.status_code == 200, r.status_code)
    A = {"Authorization": f"Bearer {r.json()['access_token']}"}

    if not db.query(models.User).filter(models.User.account == "tmuser").first():
        db.add(models.User(account="tmuser", password_hash=hash_password("0000"),
                           status=models.UserStatus.active))
        db.commit()
    r = client.post("/auth/login", json={"account": "tmuser", "password": "0000"})
    U = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ---------- 權限 ----------
    print("\n【權限】")
    check("未帶 token 看覆蓋率 → 401",
          client.get("/tcmsp/target-mapping/stats").status_code == 401)
    check("一般使用者看覆蓋率 → 403",
          client.get("/tcmsp/target-mapping/stats", headers=U).status_code == 403)
    check("未帶 token 反查 → 401",
          client.get("/tcmsp/target-mapping/lookup?symbol=AR").status_code == 401)

    # ---------- 批次解析 ----------
    print("\n【批次解析】")
    before = client.get("/tcmsp/target-mapping/stats", headers=A).json()
    check("解析前覆蓋率為 0", before["resolved"] == 0, before["resolved"])
    check("解析前 remaining 等於靶點總數",
          before["remaining"] == before["total_targets"], before)

    tcmsp_uniprot._search = fake_search
    try:
        r = client.post("/tcmsp/target-mapping/resolve", headers=A, json={"limit": 10})
        check("批次解析 200", r.status_code == 200, r.status_code)
        body = r.json()
        check("八個靶點全部處理到", body["processed"] == 8, body)
        check("五個自動採用（AR/TP53/AKT1/PTGS2/JAK2）", body["auto"] == 5, body)
        check("兩個待確認（多候選、僅全文命中）", body["pending"] == 2, body)
        check("一個查無結果", body["unresolved"] == 1, body)
        check("remaining 歸零", body["remaining"] == 0, body)

        r2 = client.post("/tcmsp/target-mapping/resolve", headers=A, json={"limit": 10})
        check("重複執行不會重跑已處理的（可安全重按）",
              r2.json()["processed"] == 0, r2.json())
    finally:
        tcmsp_uniprot._search = orig_search

    stats = client.get("/tcmsp/target-mapping/stats", headers=A).json()
    check("覆蓋率統計只算 auto/confirmed", stats["resolved"] == 5, stats["resolved"])
    check("待確認不列入已標準化", stats["by_status"]["pending"] == 2, stats["by_status"])

    # ---------- 比對索引（本次改動的重點）----------
    print("\n【比對索引：基因符號 ↔ 靶點】")
    sym_to_tar, mapped = symbol_to_targets(db)
    check("已標準化靶點數 = 5", mapped == 5, mapped)
    check("AR → TARX0001（標準化前完全對不到）",
          "TARX0001" in sym_to_tar.get("AR", set()), sym_to_tar.get("AR"))
    check("TP53 → TARX0002", "TARX0002" in sym_to_tar.get("TP53", set()))
    check("AKT1 → TARX0003", "TARX0003" in sym_to_tar.get("AKT1", set()))
    check("同義詞也能對到：NR3C4 → TARX0001",
          "TARX0001" in sym_to_tar.get("NR3C4", set()), sym_to_tar.get("NR3C4"))
    check("COX2 → TARX0004（同義詞）", "TARX0004" in sym_to_tar.get("COX2", set()))
    check("已標準化的靶點不再走名稱字詞比對（ANDROGEN 這個詞不該再是索引鍵）",
          "ANDROGEN" not in sym_to_tar, sorted(k for k in sym_to_tar if "ANDRO" in k))
    check("未標準化的靶點仍走字詞比對當退路（AMBIGUOUS 仍在索引裡）",
          "AMBIGUOUS" in sym_to_tar)

    tar_to_sym = target_to_symbols(db)
    check("反向索引涵蓋全部靶點",
          set(t for t, _ in TARGETS) <= set(tar_to_sym.keys()),
          len(tar_to_sym))
    check("反向索引：TARX0001 → 含 AR", "AR" in tar_to_sym["TARX0001"], tar_to_sym["TARX0001"])

    # ---------- 統計重算真的因此改變 ----------
    print("\n【統計重算：暗黑基因比對率】")
    for sym in ("AR", "TP53", "AKT1", "PTGS2"):
        if not db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == sym).first():
            db.add(models.DarkGene(hugo_symbol=sym, gene_type="test", status="active"))
    if not db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == "ZZZ9").first():
        db.add(models.DarkGene(hugo_symbol="ZZZ9", gene_type="test", status="active"))
    db.commit()

    from app.recompute_stats import recompute_dark_gene_has_target
    recompute_dark_gene_has_target(db)
    matched = {g.hugo_symbol for g in db.query(models.DarkGene).filter(
        models.DarkGene.has_tcmsp_target.is_(True)).all()}
    check("AR / TP53 / AKT1 / PTGS2 四個都比對到靶點",
          {"AR", "TP53", "AKT1", "PTGS2"} <= matched, sorted(matched))
    check("不存在的基因不會誤中", "ZZZ9" not in matched, sorted(matched))

    # ---------- 反查 ----------
    print("\n【反查端點】")
    r = client.get("/tcmsp/target-mapping/lookup?symbol=AR", headers=U).json()
    check("反查 AR 命中 1 個靶點", r["total"] == 1, r)
    check("反查標示為主要符號", r["items"][0]["matched_as"] == "primary", r["items"][0])
    r = client.get("/tcmsp/target-mapping/lookup?symbol=nr3c4", headers=U).json()
    check("反查同義詞（小寫也可以）命中", r["total"] == 1, r)
    check("反查標示為同義詞", r["items"][0]["matched_as"] == "synonym", r["items"][0])
    r = client.get("/tcmsp/target-mapping/lookup?symbol=NOSUCHGENE", headers=U).json()
    check("查不到就回 0，不是報錯", r["total"] == 0, r)

    # ---------- 人工審核 ----------
    print("\n【人工審核】")
    q = client.get("/tcmsp/target-mapping/review?status=pending", headers=A).json()
    check("待確認清單有 2 筆", q["total"] == 2, q["total"])
    item = next(i for i in q["items"] if i["tar_id"] == "TARX0005")
    check("待確認清單帶出 TCMSP 原始名稱（不然管理者無從判斷）",
          item["target_name"] == "Ambiguous kinase", item.get("target_name"))
    check("待確認清單帶出候選", len(item["candidates"]) == 2, item["candidates"])

    r = client.post("/tcmsp/target-mapping/confirm", headers=A,
                    json={"tar_id": "TARX0005", "accession": "Q00002", "note": "測試確認"})
    check("確認映射 200", r.status_code == 200, r.text[:200])
    check("確認後採用候選裡的基因符號", r.json()["gene_symbol"] == "BBB1", r.json())
    check("確認後狀態變 confirmed", r.json()["status"] == "confirmed")

    sym_to_tar, mapped = symbol_to_targets(db)
    check("確認之後索引立刻多一個（confirmed 要算數）", mapped == 6, mapped)
    check("BBB1 → TARX0005", "TARX0005" in sym_to_tar.get("BBB1", set()))
    check("已確認的靶點不再走字詞比對", "AMBIGUOUS" not in sym_to_tar)

    r = client.post("/tcmsp/target-mapping/reject", headers=A,
                    json={"tar_id": "TARX0006", "note": "TCMSP 這筆不是人類蛋白"})
    check("否決 200", r.status_code == 200, r.status_code)
    _, mapped = symbol_to_targets(db)
    check("否決不會被算成已標準化", mapped == 6, mapped)

    tcmsp_uniprot._search = fake_search
    try:
        r = client.post("/tcmsp/target-mapping/resolve", headers=A, json={"limit": 10})
        check("重跑不會覆蓋人工確認/否決的結果", r.json()["processed"] == 0, r.json())
    finally:
        tcmsp_uniprot._search = orig_search
    row = db.query(models.TcmspTargetUniprot).filter(
        models.TcmspTargetUniprot.tar_id == "TARX0005").first()
    db.refresh(row)
    check("人工確認的 accession 沒被洗掉", row.accession == "Q00002", row.accession)

    check("確認不存在的靶點 → 404",
          client.post("/tcmsp/target-mapping/confirm", headers=A,
                      json={"tar_id": "NOPE", "accession": "P00000"}).status_code == 404)
    check("一般使用者不能確認 → 403",
          client.post("/tcmsp/target-mapping/confirm", headers=U,
                      json={"tar_id": "TARX0005", "accession": "Q00002"}).status_code == 403)

    # ---------- 稽核 ----------
    print("\n【稽核紀錄】")
    actions = [x.action for x in db.query(models.AuditLog).all()]
    for a in ("tcmsp_resolve_targets", "tcmsp_confirm_target_mapping",
              "tcmsp_reject_target_mapping"):
        check(f"{a} 有寫入共用稽核表", a in actions)

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print("   -", f)
        raise SystemExit(1)
    print("✅ 靶點標準化驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        client = c
        main()

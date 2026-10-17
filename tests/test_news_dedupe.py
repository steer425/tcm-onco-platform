"""新聞去重分層（v1.47.1）— 直接驗證 `service._dedupe()`。

執行：`python -m tests.test_news_dedupe`（從專案根目錄）。不連外網、不起 app，只用一個獨立的 SQLite 檔。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

DB_FILE = "test_news_dedupe.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{DB_FILE}")
# ⛔ 絕不能跑在正式資料庫上（同 test_news_e2e）
if not os.environ["DATABASE_URL"].startswith("sqlite"):
    sys.exit("⛔ DATABASE_URL 指向非 SQLite 的資料庫（很可能是正式環境），測試拒絕執行。")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.news import service
from app.news.collectors.base import RawItem, simhash64

if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
engine = create_engine(f"sqlite:///./{DB_FILE}")
Base.metadata.create_all(engine)
db = sessionmaker(bind=engine)()

FAIL = []


def check(label, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra != '' else ''}")
    if not cond:
        FAIL.append(label)


NOW = datetime.now(timezone.utc)
_n = [0]


def mk(slug, title, abstract="", **kw):
    _n[0] += 1
    return RawItem(source_slug=slug, url=kw.pop("url", f"https://example.org/{slug}/{_n[0]}"),
                   title=title, abstract=abstract or f"abstract {_n[0]}",
                   published_at=NOW - timedelta(hours=3), **kw)


def src(slug):
    s = models.NewsSource(slug=slug, name_zh=slug, name_en=slug, homepage="https://example.org",
                          kind=list(models.NewsCollectorKind)[0],
                          evidence_level=list(models.NewsEvidenceLevel)[0])
    db.add(s)
    db.flush()
    return s


def store(source, item, days_ago=1):
    """把一筆 RawItem 當成「已收錄」寫進資料庫。"""
    db.add(models.NewsArticle(
        source_id=source.id, url=item.url, url_hash=item.url_hash, content_hash=item.content_hash,
        title_simhash=f"{simhash64(item.title) & 0xFFFFFFFFFFFFFFFF:016x}",
        external_id=item.external_id, doi=item.doi, title=item.title,
        evidence_level=list(models.NewsEvidenceLevel)[0],
        collected_at=datetime.utcnow() - timedelta(days=days_ago)))
    db.flush()


S = {k: src(k) for k in ("pubmed", "europe_pmc", "clinicaltrials", "who_tcim", "tcm_news")}

# ---- 既有資料 ----
OLD_PM = mk("pubmed", "Ginsenoside Rg3 enhances chemosensitivity in ovarian cancer",
            external_id="41000001", doi="10.1000/rg3")
store(S["pubmed"], OLD_PM)
OLD_NEWS = mk("tcm_news", "Hospital launches integrative oncology clinic for herbal medicine")
store(S["tcm_news"], OLD_NEWS, days_ago=2)
OLD_NEWS_STALE = mk("tcm_news", "Ministry announces new herbal medicine safety guideline for cancer care")
store(S["tcm_news"], OLD_NEWS_STALE, days_ago=10)
OLD_NCT = mk("clinicaltrials", "Phase II herbal formula in lung cancer", external_id="NCT01234567")
store(S["clinicaltrials"], OLD_NCT)
db.commit()

print("\n[1] 各層判定")
c = lambda it, rel=1.0: (it, {}, rel)
batch = [
    c(mk("pubmed", "whatever", url=OLD_PM.url)),                                        # url
    c(mk("pubmed", OLD_PM.title, OLD_PM.abstract)),                                     # content
    c(mk("pubmed", "Rg3 chemosensitivity, revised title", external_id="41000001")),     # id：同來源同 PMID
    c(mk("europe_pmc", "Ginsenoside Rg3 ... ovarian (EPMC copy)", external_id="PMC999", doi="10.1000/RG3 ")),  # id：跨來源 DOI
    c(mk("clinicaltrials", "Phase II herbal formula in lung cancer (updated)", external_id="nct01234567")),  # id：NCT 大小寫
    c(mk("europe_pmc", "Different paper with same number", external_id="41000001")),    # 不同來源同數字 → 不算重複
    # 學術樣板標題只差癌別（實測 simhash 距離 8）、各有 PMID → 都要保留
    c(mk("pubmed", "Traditional Chinese medicine for lung cancer: a systematic review and meta-analysis", external_id="41000010")),
    c(mk("pubmed", "Traditional Chinese medicine for gastric cancer: a systematic review and meta-analysis", external_id="41000011")),
    # 學術標題只差單複數、PMID 不同 → 不同論文，保留
    c(mk("pubmed", "Ginsenoside Rg3 enhances chemosensitivity in ovarian cancers", external_id="41000012")),
    # 新聞：與 2 天前的標題幾乎相同（轉載）→ title 層擋下
    c(mk("who_tcim", "Hospital launches integrative oncology clinic for herbal medicines")),
    # 新聞：與 10 天前的標題相同，但超出 7 天窗口 → 保留
    c(mk("who_tcim", "Ministry announces new herbal medicine safety guideline for cancer care.")),
    # 新聞：同一批內兩則近似，只留分數高的那則
    c(mk("tcm_news", "Herbal formula shows benefit in pancreatic cancer pilot study"), 0.9),
    c(mk("who_tcim", "Herbal formula shows benefit in pancreatic cancer pilot studies"), 0.5),
    # 新聞：只換癌別的樣板標題（距離 8）→ 不同新聞，保留
    c(mk("tcm_news", "Traditional Chinese medicine for colon cancer: a systematic review and meta-analysis")),
    # 同一批內同 PMID 出現兩次 → 第二筆以 id 擋下
    c(mk("pubmed", "Brand-new trial of astragalus", external_id="41000020"), 0.8),
    c(mk("pubmed", "Brand new trial of Astragalus (corrected)", external_id="41000020"), 0.4),
]
kept, dups, info = service._dedupe(db, batch)
titles = {k[0].title for k in kept}
tot = info["total"]
check("url 層 1", tot["url"] == 1, tot)
check("content 層 1", tot["content"] == 1, tot)
check("id 層 4（同 PMID、跨來源 DOI、NCT 大小寫、批內同 PMID）", tot["id"] == 4, tot)
check("title 層 2（新聞轉載、批內新聞近似）", tot["title"] == 2, tot)
check("重複合計 = 各層加總 = 8", dups == 8 == sum(tot.values()), dups)
check("保留 = 候選 − 重複", len(kept) == len(batch) - dups, len(kept))
check("不同來源同數字不算重複", "Different paper with same number" in titles)
check("學術樣板標題只差癌別 → 兩篇都保留",
      {"Traditional Chinese medicine for lung cancer: a systematic review and meta-analysis",
       "Traditional Chinese medicine for gastric cancer: a systematic review and meta-analysis"} <= titles)
check("學術標題只差單複數、PMID 不同 → 保留", "Ginsenoside Rg3 enhances chemosensitivity in ovarian cancers" in titles)
check("超出 7 天窗口的新聞標題 → 保留", "Ministry announces new herbal medicine safety guideline for cancer care." in titles)
check("批內新聞近似留分數高的", "Herbal formula shows benefit in pancreatic cancer pilot study" in titles
      and "Herbal formula shows benefit in pancreatic cancer pilot studies" not in titles)
check("新聞樣板標題只換癌別 → 保留",
      "Traditional Chinese medicine for colon cancer: a systematic review and meta-analysis" in titles)
check("批內同 PMID 留分數高的", "Brand-new trial of astragalus" in titles
      and "Brand new trial of Astragalus (corrected)" not in titles)

print("\n[2] 依來源分層計數")
bs = info["by_source"]
check("pubmed：url 1、content 1、id 2", bs.get("pubmed") == {"url": 1, "content": 1, "id": 2, "title": 0}, bs.get("pubmed"))
check("europe_pmc：id 1（DOI）", bs.get("europe_pmc") == {"url": 0, "content": 0, "id": 1, "title": 0}, bs.get("europe_pmc"))
check("clinicaltrials：id 1", bs.get("clinicaltrials", {}).get("id") == 1, bs.get("clinicaltrials"))
check("who_tcim：title 2", bs.get("who_tcim", {}).get("title") == 2, bs.get("who_tcim"))
check("沒有重複的來源不出現", "tcm_news" not in bs, list(bs))
check("各來源加總 = 全體", all(sum(v[k] for v in bs.values()) == tot[k] for k in service.DEDUPE_LAYERS))

print("\n[3] 邊界")
k0, d0, i0 = service._dedupe(db, [])
check("空輸入", k0 == [] and d0 == 0 and i0["total"] == {k: 0 for k in service.DEDUPE_LAYERS})
check("門檻與窗口", service.SIMHASH_THRESHOLD == 6 and service.SIMHASH_WINDOW_DAYS == 7)
# 有編號的既有文章不進標題比對池：新聞標題和既有 PubMed 標題一樣也不擋
k1, _, i1 = service._dedupe(db, [c(mk("tcm_news", OLD_PM.title + "!"))])
check("有編號的既有論文不參與新聞標題比對", len(k1) == 1, i1["total"])

db.close()
engine.dispose()
os.remove(DB_FILE)
print()
if FAIL:
    print(f"❌ 有 {len(FAIL)} 項未通過：")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("✅ 去重分層驗證全部通過")

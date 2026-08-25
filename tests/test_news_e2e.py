"""每日重點新聞模組 — 端對端驗證（對真實 app、真實 JWT 登入、真實資料表）。

不連外網：collect_all 以假資料替換，其餘（過濾／去重／評分／實體連結／
每日精選／權限／軟刪除／稽核）全部走真實程式碼路徑。
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

# 這支腳本每次都必須從空資料庫跑起。留著上一輪的 test.db，第二次執行時「每日精選」
# 會沿用前一次的紀錄，後面依索引取文章的斷言就會直接 IndexError，而不是給出有意義的
# 失敗訊息——實測過，很容易誤判成「程式壞了」。
# 只在使用預設的本機 test.db 時刪除；外部另外指定 DATABASE_URL（例如指向正式資料庫）
# 時絕對不動它。
if os.environ["DATABASE_URL"] == "sqlite:///./test.db" and os.path.exists("test.db"):
    os.remove("test.db")

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.main import app
from app.news import service as news_service
from app.news.collectors.base import RawItem
from app.news.short_summary import generate as short_summary_generate
from app.security import hash_password

NOW = datetime.now(timezone.utc)
ok = lambda label, cond, extra="": print(f"  {'✅' if cond else '❌'} {label}{('  ' + str(extra)) if extra else ''}")
FAIL = []


def check(label, cond, extra=""):
    ok(label, cond, extra)
    if not cond:
        FAIL.append(label)


def mk(slug, title, abstract="", **kw):
    return RawItem(
        source_slug=slug,
        url=kw.pop("url", f"https://example.org/{slug}/{abs(hash(title)) % 10**8}"),
        title=title, abstract=abstract,
        published_at=kw.pop("published_at", NOW - timedelta(hours=4)), **kw)


FAKE_ITEMS = [
    # 安全訊號（應排 #1）
    mk("msk_about_herbs", "St. John's Wort and chemotherapy",
       "May induce CYP3A4 and reduce efficacy of chemotherapy in cancer patients; interaction risk."),
    # 人體證據 + 藥材/疾病/靶點都可比對到
    mk("pubmed",
       "Scutellariae Radix decoction in gastric cancer: a randomized controlled trial",
       "We randomized 210 patients with gastric cancer. AKT1 signaling was measured.",
       study_design="Randomized Controlled Trial", external_id="40000001"),
    # 近似重複（只差複數 s）→ 應被 simhash 擋下
    mk("pubmed",
       "Scutellariae Radix decoction in gastric cancer: a randomized controlled trials",
       "duplicate-ish", study_design="Randomized Controlled Trial", external_id="40000002"),
    # 臨床前（應排最後）
    mk("pubmed", "Network pharmacology and molecular docking of a herbal formula in liver cancer",
       "In vitro cytotoxic assay on HepG2 cell line with in silico molecular docking.",
       external_id="40000003"),
    # 臨床試驗登錄
    mk("clinicaltrials", "Phase II trial of a chinese herbal formula in lung cancer",
       "[Status: RECRUITING][Phase: PHASE2] herbal medicine for tumor", external_id="NCT09999999"),
    # 不相關 → 應被主題過濾掉
    mk("who_tcim", "WHO Director-General visits Jordan on emergency relief"),
]


async def fake_collect_all(**kwargs):
    stats = {}
    for it in FAKE_ITEMS:
        stats.setdefault(it.source_slug, {"fetched": 0, "error": None, "kind": "api"})
        stats[it.source_slug]["fetched"] += 1
    stats["cn_satcm"] = {"fetched": 0, "error": "ConnectError: DNS failure", "kind": "scrape"}
    return list(FAKE_ITEMS), stats


news_service.collect_all = fake_collect_all



def main():
    global client
    db = SessionLocal()

    # ---------- 準備：TCMSP 主檔 + 一般使用者 ----------
    print("\n【準備測試資料】")
    for hid, cn, py, en in [(1, "黃芩", "huang qin", "Scutellariae Radix"),
                            (2, "薑黃", "jiang huang", "Curcumae Longae Rhizoma")]:
        if not db.query(models.TcmspHerb).filter(models.TcmspHerb.id == hid).first():
            db.add(models.TcmspHerb(id=hid, herb_cn_name=cn, herb_pinyin=py, herb_en_name=en))
    if not db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == "TAR00001").first():
        db.add(models.TcmspTarget(tar_id="TAR00001", target_name="AKT1"))
        db.add(models.TcmspIngredient(mol_id="MOL000098", molecule_name="quercetin"))
        db.add(models.TcmspHerbIngredient(herb_id=1, mol_id="MOL000098"))
        db.add(models.TcmspIngredientTarget(mol_id="MOL000098", tar_id="TAR00001"))
    if not db.query(models.TcmspDisease).filter(models.TcmspDisease.dis_id == "DIS00001").first():
        db.add(models.TcmspDisease(dis_id="DIS00001", disease_name="Gastric cancer",
                                   disease_cn_name="胃癌"))
        db.add(models.TcmspTargetDisease(tar_id="TAR00001", dis_id="DIS00001"))

    if not db.query(models.User).filter(models.User.account == "researcher").first():
        u = models.User(account="researcher", password_hash=hash_password("0000"),
                        status=models.UserStatus.active)
        db.add(u)
    db.commit()
    print("  TCMSP 主檔與測試帳號就緒")

    # ---------- 功能代碼 ----------
    print("\n【功能代碼註冊（F0-13-6 / F0-19）】")
    for code, name in [("F0-13-6", "Dashboard-每日重點新聞小工具"), ("F0-19", "新聞管理（公告管理頁分頁）")]:
        f = db.query(models.Feature).filter(models.Feature.code == code).first()
        check(f"{code} 已由 seed 建立", f is not None, f.name if f else "缺少")

    # ---------- 登入 ----------
    print("\n【登入（真實 JWT）】")
    r = client.post("/auth/login", json={"account": "admin", "password": "0000"})
    check("管理者登入 200", r.status_code == 200, r.status_code)
    admin_tok = r.json().get("access_token")
    A = {"Authorization": f"Bearer {admin_tok}"}

    r = client.post("/auth/login", json={"account": "researcher", "password": "0000"})
    check("一般使用者登入 200", r.status_code == 200, r.status_code)
    user_tok = r.json().get("access_token")
    U = {"Authorization": f"Bearer {user_tok}"}

    check("未帶 token 取新聞 → 401", client.get("/news/daily").status_code == 401)

    # ---------- 收集流程 ----------
    print("\n【執行收集流程】")
    result = news_service.run_daily_collection(db, trigger_type="manual")
    print(f"  抓取 {result['fetched']}、過濾 {result['filtered_out']}、重複 {result['duplicates']}、"
          f"新增 {result['new_articles']}、精選 {result['digest_size']}、實體連結 {result['linked_entities']}")
    check("部分來源失敗 → status=partial", result["status"] == "partial", result["status"])
    check("不相關的 WHO 新聞被過濾", result["filtered_out"] >= 1, result["filtered_out"])
    check("近似重複被擋下", result["duplicates"] >= 1, result["duplicates"])
    check("有建立實體連結", result["linked_entities"] > 0, result["linked_entities"])

    # ---------- 前台每日新聞 ----------
    print("\n【前台 /news/daily】")
    r = client.get("/news/daily", headers=U)
    check("一般使用者可讀 200", r.status_code == 200, r.status_code)
    data = r.json()
    items = data["items"]
    check("有回傳精選新聞", len(items) > 0, len(items))
    check("含免責聲明", "不構成醫療診斷或治療建議" in data["disclaimer"])
    print("  排序：")
    for it in items:
        ents = "、".join(f"{e['type']}:{e['name']}" for e in it["entities"][:4])
        print(f"    #{it['rank']} safety={str(it['is_safety_signal']):<5} {it['evidence_maturity']:<11} "
              f"{(it['title'] or '')[:44]}")
        if ents:
            print(f"         實體 → {ents}")
    check("安全訊號排第一", items[0]["is_safety_signal"] is True)
    check("臨床前研究排最後", items[-1]["evidence_maturity"] == "preclinical",
          items[-1]["evidence_maturity"])
    check("每篇都有解讀注意事項", all(i.get("caveat_zh") for i in items))

    # ---------- 實體連結 ----------
    print("\n【實體連結（可點連到查詢站）】")
    rct = next((i for i in items if "Scutellariae" in i["title"]), None)
    check("找到 RCT 那篇", rct is not None)
    if rct:
        by_type = {e["type"]: e for e in rct["entities"]}
        check("比對到藥材（黃芩）", "herb" in by_type, by_type.get("herb", {}).get("name"))
        check("比對到疾病（胃癌）", "disease" in by_type, by_type.get("disease", {}).get("name"))
        check("比對到靶點（AKT1）", "target" in by_type, by_type.get("target", {}).get("name"))
        if "herb" in by_type:
            check("藥材連結指向 tcmsp_query.html?herb=",
                  by_type["herb"]["link"] == "tcmsp_query.html?herb=1", by_type["herb"]["link"])
        if "disease" in by_type:
            check("疾病連結指向 disease_query.html?dis=",
                  by_type["disease"]["link"] == "disease_query.html?dis=DIS00001",
                  by_type["disease"]["link"])
        if "target" in by_type:
            check("靶點無直接連結（改開彈窗）", by_type["target"]["link"] is None)
            r = client.get(f"/news/targets/{by_type['target']['tar_id']}", headers=U)
            check("靶點彈窗 API 200", r.status_code == 200, r.status_code)
            td = r.json()
            check("靶點帶出關聯藥材", len(td["herbs"]) > 0,
                  [h["name"] for h in td["herbs"]])
            check("靶點帶出關聯疾病", len(td["diseases"]) > 0,
                  [d["name"] for d in td["diseases"]])

    # ---------- 保留 ----------
    print("\n【個人保留】")
    aid = items[1]["id"]
    r = client.post("/news/bookmarks", headers=U, json={"article_id": aid, "note": "重要"})
    check("勾選保留 200", r.status_code == 200, r.status_code)
    r = client.get("/news/bookmarks", headers=U)
    check("我的保留有 1 筆", r.json()["total"] == 1, r.json()["total"])
    r = client.get("/news/daily", headers=A)
    other = next(i for i in r.json()["items"] if i["id"] == aid)
    check("其他使用者的 is_bookmarked 為 False", other["is_bookmarked"] is False)
    check("但看得到保留人數 1", other["bookmark_count"] == 1, other["bookmark_count"])

    # ---------- 後台權限 ----------
    print("\n【後台權限】")
    check("一般使用者查後台 → 403",
          client.post("/news/admin/articles/search", headers=U, json={}).status_code == 403)
    r = client.post("/news/admin/articles/search", headers=A, json={})
    check("管理者查後台 → 200", r.status_code == 200, r.status_code)
    check("後台查得到文章", r.json()["total"] > 0, r.json()["total"])
    check("後台欄位含 delete_note", "delete_note" in r.json()["items"][0])

    print("  中文搜尋『胃癌』：", end="")
    r = client.post("/news/admin/articles/search", headers=A, json={"q": "胃癌"})
    print(r.json()["total"], "筆")
    check("中文關鍵字搜尋有結果", r.json()["total"] >= 1)

    # ---------- 軟刪除 ----------
    print("\n【刪除舊新聞（軟刪除 + 註記）】")
    r = client.post("/news/admin/articles/soft-delete", headers=A, json={"article_ids": [aid]})
    check("缺註記 → 422/400", r.status_code in (400, 422), r.status_code)

    r = client.post("/news/admin/articles/soft-delete", headers=A,
                    json={"older_than_days": 1, "note": "清理一天前", "dry_run": True})
    check("older_than_days=1 不會誤刪今天剛收的新聞", r.json()["affected_count"] == 0,
          r.json()["affected_count"])

    # 全選（含已被保留那篇），驗證保護機制
    all_ids = [i["id"] for i in client.post("/news/admin/articles/search",
                                            headers=A, json={}).json()["items"]]
    r = client.post("/news/admin/articles/soft-delete", headers=A,
                    json={"article_ids": all_ids, "note": "2026Q3 例行清理", "dry_run": True})
    dry = r.json()
    print("  試算：", dry["message"])
    check("試算保護了被保留的文章", dry["blocked_bookmarked"] == 1, dry["blocked_bookmarked"])
    check("試算筆數 = 總數 - 被保留數", dry["affected_count"] == len(all_ids) - 1,
          f"{dry['affected_count']} vs {len(all_ids) - 1}")

    r = client.post("/news/admin/articles/soft-delete", headers=A,
                    json={"article_ids": all_ids, "note": "2026Q3 例行清理"})
    real = r.json()
    print("  執行：", real["message"])
    check("實際刪除筆數 = 試算筆數", real["affected_count"] == dry["affected_count"],
          f"{real['affected_count']} vs {dry['affected_count']}")

    r = client.post("/news/admin/articles/search", headers=A, json={"bookmarked_only": True,
                                                                    "include_deleted": True})
    kept = r.json()["items"][0]
    check("被保留的文章未被刪除", kept["is_deleted"] is False)

    r = client.get("/news/daily", headers=U)
    check("前台看不到已刪除新聞", r.json()["total"] == 1, r.json()["total"])

    r = client.post("/news/admin/articles/search", headers=A, json={"only_deleted": True})
    check("後台仍查得到已刪除", r.json()["total"] == real["affected_count"], r.json()["total"])
    check("刪除註記有留存", r.json()["items"][0]["delete_note"] == "2026Q3 例行清理")

    r = client.get("/news/bookmarks", headers=U)
    check("使用者的保留清單仍在", r.json()["total"] == 1)

    # ---------- 還原 ----------
    print("\n【還原】")
    del_ids = [i["id"] for i in client.post("/news/admin/articles/search", headers=A,
                                            json={"only_deleted": True}).json()["items"][:2]]
    r = client.post("/news/admin/articles/restore", headers=A, json={"article_ids": del_ids})
    check("還原筆數正確", r.json()["affected_count"] == len(del_ids),
          f"{r.json()['affected_count']} vs {len(del_ids)}")

    # ---------- 稽核（用平台現成的 AuditLog）----------
    print("\n【稽核紀錄寫進平台既有 AuditLog】")
    logs = (db.query(models.AuditLog)
            .filter(models.AuditLog.action.like("news_%"))
            .order_by(models.AuditLog.created_at.desc()).all())
    actions = [l.action for l in logs]
    print("  ", actions)
    check("軟刪除有留稽核", "news_soft_delete" in actions)
    check("還原有留稽核", "news_restore" in actions)
    check("試算不留稽核", actions.count("news_soft_delete") == 1, actions.count("news_soft_delete"))
    check("稽核紀錄有記到操作者帳號", logs[0].actor_account == "admin", logs[0].actor_account)

    # ---------- 來源健康度 / 執行紀錄 ----------
    print("\n【來源健康度與執行紀錄】")
    r = client.get("/news/admin/sources", headers=A)
    srcs = r.json()
    check("10 個來源都在", len(srcs) == 10, len(srcs))
    failed = [s for s in srcs if s["last_error"]]
    check("失敗來源有記錄錯誤", len(failed) >= 1, [s["slug"] for s in failed])
    r = client.get("/news/admin/runs", headers=A)
    check("有收集執行紀錄", len(r.json()) >= 1, len(r.json()))
    check("執行紀錄含實體連結數", r.json()[0]["linked_entity_count"] > 0)

    # ---------- 設定 ----------
    print("\n【設定】")
    r = client.put("/news/admin/settings", headers=A, json={"daily_digest_size": 12})
    check("更新每日篇數 200", r.status_code == 200, r.status_code)
    check("設定已生效",
          client.get("/news/admin/settings", headers=A).json()["daily_digest_size"] == 12)
    r = client.put("/news/admin/settings", headers=A, json={"daily_digest_size": 999})
    check("不合法設定被擋 → 422", r.status_code == 422, r.status_code)

    # ---------- 排程端點（不需登入，走共享密鑰標頭）----------
    print("\n【排程端點 /news/admin/collect/scheduled】")
    import os as _os
    _os.environ.pop("NEWS_COLLECT_SECRET", None)
    r = client.post("/news/admin/collect/scheduled", json={})
    check("未設定密鑰時端點停用 → 503", r.status_code == 503, r.status_code)

    _os.environ["NEWS_COLLECT_SECRET"] = "s3cr3t-for-test"
    check("無 Authorization → 401",
          client.post("/news/admin/collect/scheduled", json={}).status_code == 401)
    check("錯誤密鑰 → 401",
          client.post("/news/admin/collect/scheduled", json={},
                      headers={"Authorization": "Bearer wrong"}).status_code == 401)
    check("密鑰放查詢字串無效（已改標頭）",
          client.post("/news/admin/collect/scheduled?secret=s3cr3t-for-test",
                      json={}).status_code == 401)
    r = client.post("/news/admin/collect/scheduled", json={},
                    headers={"Authorization": "Bearer s3cr3t-for-test"})
    check("正確密鑰 → 200", r.status_code == 200, r.status_code)
    check("排程執行紀錄 trigger_type=scheduled",
          any(x["trigger_type"] == "scheduled"
              for x in client.get("/news/admin/runs", headers=A).json()))
    _os.environ.pop("NEWS_COLLECT_SECRET", None)

    # ------------------------------------------------------------------
    print("\n【多語系簡短摘要】")
    # 這一段刻意在「沒有 ANTHROPIC_API_KEY」的狀態下跑，驗證的是降級路徑：
    # 正式環境有 key 時走 AI，沒 key 時要能安全退回截斷，而且不能假裝有韓文摘要。
    _os.environ.pop("ANTHROPIC_API_KEY", None)

    r = client.put("/news/admin/settings", json={"summary_length": 120}, headers=A)
    check("設定摘要字數 120 → 200", r.status_code == 200, r.status_code)
    check("摘要字數上限太小被擋 → 422",
          client.put("/news/admin/settings", json={"summary_length": 10},
                     headers=A).status_code == 422)
    check("摘要字數上限太大被擋 → 422",
          client.put("/news/admin/settings", json={"summary_length": 5000},
                     headers=A).status_code == 422)

    daily = client.get("/news/daily?lang=en", headers=U).json()
    check("/news/daily 回報使用的摘要語系", daily.get("summary_lang") == "en",
          daily.get("summary_lang"))
    check("cn 對應到繁中那一列（OpenCC 在前端轉簡體）",
          client.get("/news/daily?lang=cn", headers=U).json().get("summary_lang") == "zh-TW")
    check("語系參數打錯不會讓每日新聞失敗",
          client.get("/news/daily?lang=xx", headers=U).status_code == 200)

    # 文章 id 從後台查詢取，不從當日精選取——前面的軟刪除與排程重跑會讓當日精選變動，
    # 讓摘要測試相依於那個結果只會製造難查的偶發失敗。
    pool = client.post("/news/admin/articles/search",
                       json={"include_deleted": False, "limit": 3}, headers=A).json()["items"]
    ids = [a["id"] for a in pool][:3]
    check("取得可測試的文章", len(ids) >= 1, len(ids))
    check("尚未產生時 summary 為 None",
          all(i.get("summary") is None for i in daily["items"]),
          [i.get("summary") for i in daily["items"]][:2])
    r = client.post("/news/summaries", json={"article_ids": ids, "lang": "en"}, headers=U)
    check("產生英文摘要 → 200", r.status_code == 200, r.status_code)
    en = r.json()["summaries"]
    check("英文摘要有產出", len(en) >= 1, len(en))
    check("無 API key 時標記為非 AI 產生",
          all(v["is_ai"] is False for v in en.values()))
    check("摘要長度不超過設定上限",
          all(len(v["summary"]) <= 120 for v in en.values() if v["summary"]),
          max((len(v["summary"]) for v in en.values() if v["summary"]), default=0))

    r = client.post("/news/summaries", json={"article_ids": ids, "lang": "ko"}, headers=U)
    check("韓文在無 API key 時不硬塞中文（回空）",
          r.status_code == 200 and not r.json()["summaries"], r.json()["summaries"])

    # 中文降級的關鍵規則：來源是英文時不要拿英文截斷冒充中文摘要。
    # 第一版就是這樣寫的，畫面上「摘要有出來」但根本不是中文，反而更難查出是沒設 API key。
    r = client.post("/news/summaries", json={"article_ids": ids, "lang": "tw"}, headers=U)
    zh = r.json()["summaries"]
    check("英文來源在無 API key 時不產生中文摘要（不冒充）", not zh, zh)

    from app.news.short_summary import fallback as _fb
    check("原文本身是中文時，中文降級仍會截斷沿用",
          bool(_fb({"abstract": "本研究探討黃連素對肝纖維化的作用。" * 20}, "zh-TW", 120)))
    check("原文是英文時，中文降級回 None",
          _fb({"abstract": "OBJECTIVES: To investigate the effects." * 20}, "zh-TW", 120) is None)

    arch = client.get("/news/archive?days=30&lang=en", headers=U).json()
    check("/news/archive 也回報摘要語系", arch.get("summary_lang") == "en",
          arch.get("summary_lang"))
    check("已產生的摘要會出現在列表端點",
          any(i.get("summary") for i in arch["items"] if i["id"] in ids))

    check("不支援的語系 → 400",
          client.post("/news/summaries", json={"article_ids": ids, "lang": "fr"},
                      headers=U).status_code == 400)
    check("一次最多 12 篇",
          client.post("/news/summaries",
                      json={"article_ids": [f"x{i}" for i in range(13)], "lang": "en"},
                      headers=U).status_code == 422)

    r = client.get("/news/admin/summaries/test-key", headers=A)
    check("未設定金鑰時檢測 → not_set",
          r.status_code == 200 and r.json()["reason"] == "not_set", r.json())
    # 用一把假金鑰實際跑一次，確認回應裡不會出現金鑰本身。
    # 不管對方回 401 還是連不到（沙箱可能沒有對外網路），金鑰都不該被回顯。
    _SENTINEL = "sk-ant-sentinel-do-not-echo-0123456789"
    _os.environ["ANTHROPIC_API_KEY"] = _SENTINEL
    r2 = client.get("/news/admin/summaries/test-key", headers=A)
    check("錯誤金鑰不會被判定為有效",
          r2.status_code == 200 and r2.json()["ok"] is False, r2.json().get("reason"))
    check("檢測結果不會外洩金鑰本身", _SENTINEL not in r2.text, r2.json().get("reason"))
    d = r2.json()
    check("回報金鑰長度供判斷是否被截斷", d.get("key_length") == len(_SENTINEL), d.get("key_length"))
    check("回報的前綴只有廠商公開前綴那一段",
          d.get("key_prefix") == _SENTINEL[:14] and len(d.get("key_prefix", "")) == 14)

    # 環境變數夾帶換行是最常見的貼上意外，光看遮蔽過的欄位完全看不出來
    _os.environ["ANTHROPIC_API_KEY"] = "  " + _SENTINEL + "\n"
    d2 = client.get("/news/admin/summaries/test-key", headers=A).json()
    check("偵測到前後夾帶空白/換行", d2.get("had_surrounding_whitespace") is True, d2.get("reason"))
    check("夾帶空白時長度以去除後計算", d2.get("key_length") == len(_SENTINEL), d2.get("key_length"))
    _os.environ.pop("ANTHROPIC_API_KEY", None)

    _os.environ["ANTHROPIC_API_KEY"] = "   \n  "
    check("只有空白等同未設定",
          client.get("/news/admin/summaries/test-key", headers=A).json()["reason"] == "not_set")
    _os.environ.pop("ANTHROPIC_API_KEY", None)

    # 供應商選擇：Gemini 優先（免費層不需信用卡），可用 NEWS_AI_PROVIDER 強制
    from app.news import ai_client
    _os.environ["ANTHROPIC_API_KEY"] = "sk-ant-x"
    check("只有 Anthropic 時選 anthropic", ai_client.active_provider() == "anthropic")
    _os.environ["GEMINI_API_KEY"] = "AIzaTESTKEY"
    check("兩者都有時 Gemini 優先", ai_client.active_provider() == "gemini")
    d3 = client.get("/news/admin/summaries/test-key", headers=A).json()
    check("檢測會回報目前用哪一家", d3.get("provider") == "gemini", d3.get("provider"))
    check("檢測會回報讀的是哪個環境變數", d3.get("key_env") == "GEMINI_API_KEY", d3.get("key_env"))
    check("Gemini 金鑰前綴檢查用 AIza",
          d3.get("looks_like_expected_key") is True, d3.get("key_prefix"))
    _os.environ["NEWS_AI_PROVIDER"] = "anthropic"
    check("可強制指定供應商", ai_client.active_provider() == "anthropic")
    _os.environ["NEWS_AI_PROVIDER"] = "none"
    check("可強制停用 AI", ai_client.active_provider() is None)
    check("停用時摘要走降級",
          all(r["is_ai"] is False for r in
              short_summary_generate([{"abstract": "x" * 400}], "en", 120)))
    for _k in ("NEWS_AI_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        _os.environ.pop(_k, None)
    check("一般使用者不能檢測金鑰 → 403",
          client.get("/news/admin/summaries/test-key", headers=U).status_code == 403)
    check("檢測有留稽核",
          "news_test_api_key" in [x.action for x in db.query(models.AuditLog).all()])

    r = client.get("/news/admin/summaries/stats", headers=A)
    stats = r.json()
    check("覆蓋率統計 → 200", r.status_code == 200, r.status_code)
    check("統計含三個語系", len(stats["by_lang"]) == 3, len(stats["by_lang"]))
    check("統計回報目前沒有 API key", stats["has_api_key"] is False)
    en_stat = next(x for x in stats["by_lang"] if x["lang"] == "en")
    check("英文已有摘要筆數正確", en_stat["have"] == len(en), en_stat["have"])

    check("一般使用者不能回補摘要 → 403",
          client.post("/news/admin/summaries/backfill", json={"lang": "en"},
                      headers=U).status_code == 403)
    r = client.post("/news/admin/summaries/backfill",
                    json={"lang": "en", "days": 30, "limit": 50}, headers=A)
    check("管理者回補摘要 → 200", r.status_code == 200, r.status_code)
    check("全部都有摘要時回補不重複產生（也不重複計費）",
          r.json()["processed"] == 0 and r.json()["remaining"] == 0, r.json())
    check("回補語系打錯 → 400",
          client.post("/news/admin/summaries/backfill", json={"lang": "fr"},
                      headers=A).status_code == 400)
    check("回補有留稽核",
          "news_backfill_summary" in [x.action for x in
                                      db.query(models.AuditLog).all()])

    # 改字數上限不會自動重產（那會讓管理者一改設定就觸發大量 API 呼叫），
    # 但要標成 stale，並且能用 include_stale 明確地重產。
    client.put("/news/admin/settings", json={"summary_length": 200}, headers=A)
    stale_before = next(x for x in
                        client.get("/news/admin/summaries/stats", headers=A).json()["by_lang"]
                        if x["lang"] == "en")["stale"]
    check("改字數上限後舊摘要被標記為 stale", stale_before >= 1, stale_before)
    check("改設定不會自動重產",
          client.post("/news/admin/summaries/backfill",
                      json={"lang": "en", "limit": 50}, headers=A).json()["processed"] == 0)

    r = client.post("/news/admin/summaries/backfill",
                    json={"lang": "en", "limit": 50, "include_stale": True}, headers=A)
    check("include_stale 會重產舊長度的摘要", r.json()["written"] == stale_before, r.json())

    # v1.35.3 的關鍵修正：降級產生的摘要（is_ai=False）也要算「需重產」。
    # 否則先在沒有金鑰時產了一批截斷版，之後補上金鑰，會發現「回補」說沒有缺、
    # 「重產」說沒有 stale，那批降級摘要永遠換不掉。
    en_now = next(x for x in
                  client.get("/news/admin/summaries/stats", headers=A).json()["by_lang"]
                  if x["lang"] == "en")
    check("降級產生的摘要被計入 degraded", en_now["degraded"] == en_now["have"], en_now)
    check("降級產生的摘要被計入需重產", en_now["stale"] == en_now["have"], en_now)
    check("字數過期與降級分開統計", en_now["outdated_length"] == 0, en_now)
    check("有降級摘要時重產按鈕不會是灰的（stale > 0）", en_now["stale"] > 0)
    check("重產後字數已對齊目前設定",
          next(x for x in client.get("/news/admin/summaries/stats", headers=A).json()["by_lang"]
               if x["lang"] == "en")["outdated_length"] == 0)
    check("重產後總筆數不變（是更新不是新增）",
          next(x for x in client.get("/news/admin/summaries/stats", headers=A).json()["by_lang"]
               if x["lang"] == "en")["have"] == en_stat["have"])

    check("關閉摘要功能後不再產生",
          client.put("/news/admin/settings", json={"summary_enabled": False},
                     headers=A).status_code == 200
          and client.post("/news/summaries", json={"article_ids": ids, "lang": "ko"},
                          headers=U).json()["enabled"] is False)
    client.put("/news/admin/settings", json={"summary_enabled": True}, headers=A)

    db.close()
    print("\n" + "=" * 60)
    if FAIL:
        print(f"❌ 有 {len(FAIL)} 項未通過：")
        for f in FAIL:
            print("   -", f)
        raise SystemExit(1)
    print("✅ 端對端驗證全部通過")


if __name__ == "__main__":
    with TestClient(app) as c:
        client = c
        main()
